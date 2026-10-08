"use strict";

const crypto = require("node:crypto");
const http = require("node:http");

const PORT = 8181;
const MAX_BODY_BYTES = 65536;
const TIMEOUT_MS = 20000;
const FAKE_SSE = 'data: {"choices":[{"delta":{"content":"EA4E_INERT_OK"}}]}\n\ndata: [DONE]\n\n';

function createPendingFake(report, done) {
  let state = "idle";
  let response = null;
  let timer = null;

  function finish(status, body = "") {
    if (state !== "reading" && state !== "pending") return false;
    state = "finished";
    clearTimeout(timer);
    if (!response.destroyed) {
      response.statusCode = status;
      if (status === 200) response.setHeader("Content-Type", "text/event-stream");
      response.end(body);
    }
    done(status);
    return true;
  }

  return {
    accept(req, res) {
      if (state !== "idle") {
        res.statusCode = 503;
        res.end();
        return;
      }
      if (req.method !== "POST" || req.url !== "/v1/chat/completions" ||
          req.headers["content-type"] !== "application/json" ||
          !req.socket || typeof req.socket.remoteAddress !== "string") {
        state = "finished";
        res.statusCode = 404;
        res.end();
        done(404);
        return;
      }
      state = "reading";
      response = res;
      const hash = crypto.createHash("sha256");
      let bodyBytes = 0;
      timer = setTimeout(() => finish(504), TIMEOUT_MS);
      res.on("close", () => finish(504));
      req.on("aborted", () => finish(504));
      req.on("data", (part) => {
        if (state !== "reading") return;
        if (!Buffer.isBuffer(part) || bodyBytes + part.length > MAX_BODY_BYTES) {
          finish(413);
          return;
        }
        bodyBytes += part.length;
        hash.update(part);
      });
      req.on("end", () => {
        if (state !== "reading") return;
        if (bodyBytes === 0) {
          finish(400);
          return;
        }
        state = "pending";
        try {
          report({ event: "FAKE_REQUEST_PENDING", peer: req.socket.remoteAddress,
            body_bytes: bodyBytes, body_sha256: hash.digest("hex") });
        } catch (_) {
          finish(500);
        }
      });
    },
    release() { return state === "pending" && finish(200, FAKE_SSE); },
    expire() { return finish(504); },
    state() { return state; },
  };
}

function runGateway() {
  let server;
  const session = createPendingFake(
    (event) => process.stdout.write(JSON.stringify(event) + "\n"),
    (status) => {
      if (status !== 200) process.exitCode = 2;
      server.close();
    },
  );
  server = http.createServer((req, res) => session.accept(req, res));
  process.on("SIGUSR2", () => session.release());
  server.requestTimeout = TIMEOUT_MS;
  server.listen(PORT, "0.0.0.0");
  setTimeout(() => {
    if (session.state() === "idle") {
      process.exitCode = 2;
      server.close();
    }
  }, TIMEOUT_MS).unref();
}

if (require.main === module) runGateway();

module.exports = { MAX_BODY_BYTES, FAKE_SSE, createPendingFake };
