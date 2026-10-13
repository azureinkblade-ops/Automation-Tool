"use strict";

const crypto = require("node:crypto");
const http = require("node:http");

const MAX_BYTES = 65536;
const TIMEOUT_MS = 20000;

function validateResponse(responseBytes, expectedSha256, taskHash, receiptHash) {
  if (!Buffer.isBuffer(responseBytes) || responseBytes.length === 0 ||
      responseBytes.length > MAX_BYTES ||
      typeof expectedSha256 !== "string" ||
      !/^[0-9a-f]{64}$/.test(expectedSha256) ||
      !/^[0-9a-f]{64}$/.test(taskHash) ||
      !/^[0-9a-f]{64}$/.test(receiptHash)) {
    throw new Error("attempt-bound response denied");
  }
  const actual = crypto.createHash("sha256").update(responseBytes).digest("hex");
  if (actual !== expectedSha256) throw new Error("response hash mismatch");
  const wire = responseBytes.toString("utf8");
  if (!Buffer.from(wire, "utf8").equals(responseBytes) ||
      !wire.startsWith("data: ") || !wire.endsWith("\n\ndata: [DONE]\n\n")) {
    throw new Error("response framing denied");
  }
  const firstFrame = wire.slice(6, -"\n\ndata: [DONE]\n\n".length);
  let event;
  let candidate;
  try {
    event = JSON.parse(firstFrame);
    candidate = JSON.parse(event.choices[0].delta.content);
  } catch (_) {
    throw new Error("response JSON denied");
  }
  if (candidate.schema_version !== "1" || candidate.outcome !== "SUCCEEDED" ||
      candidate.result_payload?.task_input_hash !== taskHash ||
      candidate.result_payload?.receiver_receipt_hash !== receiptHash ||
      candidate.result_payload?.statement !== "kilo-cli-agent:PING_OK") {
    throw new Error("response lineage denied");
  }
  return Buffer.from(responseBytes);
}

function createPendingPing({ responseBytes, expectedSha256, taskHash, receiptHash,
                             attemptId, report, done }) {
  const responseBody = validateResponse(responseBytes, expectedSha256,
                                        taskHash, receiptHash);
  if (typeof attemptId !== "string" || !/^[A-Za-z0-9._:-]{1,128}$/.test(attemptId) ||
      typeof report !== "function" || typeof done !== "function") {
    throw new Error("gateway callbacks required");
  }
  let state = "idle";
  let response = null;
  let timer = null;

  function finish(status, body = Buffer.alloc(0)) {
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
      timer.unref();
      res.on("close", () => finish(504));
      req.on("aborted", () => finish(504));
      req.on("data", (part) => {
        if (state !== "reading") return;
        if (!Buffer.isBuffer(part) || bodyBytes + part.length > MAX_BYTES) {
          finish(413);
          return;
        }
        bodyBytes += part.length;
        hash.update(part);
      });
      req.on("end", () => {
        if (state !== "reading") return;
        if (bodyBytes === 0) return finish(400);
        state = "pending";
        try {
          report({ event: "FAKE_PING_REQUEST_PENDING",
            attempt_id: attemptId, response_sha256: expectedSha256,
            peer: req.socket.remoteAddress, body_bytes: bodyBytes,
            body_sha256: hash.digest("hex") });
        } catch (_) {
          finish(500);
        }
      });
    },
    release() { return state === "pending" && finish(200, responseBody); },
    expire() { return finish(504); },
    state() { return state; },
  };
}

function loadFakeConfig(env) {
  if (env.EA4E_QUALIFICATION_ONLY !== "1" ||
      typeof env.EA4E_PING_SSE_BASE64 !== "string" ||
      !/^[A-Za-z0-9+/]+={0,2}$/.test(env.EA4E_PING_SSE_BASE64)) {
    throw new Error("fake-only gateway configuration denied");
  }
  const responseBytes = Buffer.from(env.EA4E_PING_SSE_BASE64, "base64");
  if (responseBytes.toString("base64") !== env.EA4E_PING_SSE_BASE64) {
    throw new Error("noncanonical fake response encoding denied");
  }
  const config = {
    attemptId: env.EA4E_ATTEMPT_ID,
    responseBytes, expectedSha256: env.EA4E_PING_SSE_SHA256,
    taskHash: env.EA4E_TASK_INPUT_HASH,
    receiptHash: env.EA4E_RECEIVER_RECEIPT_HASH,
  };
  validateResponse(config.responseBytes, config.expectedSha256,
                   config.taskHash, config.receiptHash);
  if (typeof config.attemptId !== "string" ||
      !/^[A-Za-z0-9._:-]{1,128}$/.test(config.attemptId)) {
    throw new Error("attempt identity denied");
  }
  return config;
}

function runFakeGateway(env = process.env) {
  const config = loadFakeConfig(env);
  let server;
  const session = createPendingPing({ ...config,
    report: (event) => process.stdout.write(JSON.stringify(event) + "\n"),
    done: (status) => {
      if (status !== 200) process.exitCode = 2;
      server.close();
    },
  });
  server = http.createServer((req, res) => session.accept(req, res));
  process.on("SIGUSR2", () => session.release());
  server.requestTimeout = TIMEOUT_MS;
  server.listen(8181, "0.0.0.0");
  setTimeout(() => {
    if (session.state() === "idle") {
      process.exitCode = 2;
      server.close();
    }
  }, TIMEOUT_MS).unref();
  return server;
}

if (require.main === module) runFakeGateway();

module.exports = { MAX_BYTES, validateResponse, createPendingPing,
  loadFakeConfig, runFakeGateway };
