"use strict";

const http = require("node:http");

const MARKER = "EA4E_PEER_OK\n";
const PORT = 8181;
const REQUEST_TIMEOUT_MS = 20000;

function createPendingMarker(report, done) {
  let state = "idle";
  let response = null;
  let timer = null;

  function finish(status, body) {
    if (state !== "pending") return false;
    clearTimeout(timer);
    state = "finished";
    if (!response.destroyed) {
      response.statusCode = status;
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
      if (req.method !== "GET" || req.url !== "/marker" ||
          !req.socket || typeof req.socket.remoteAddress !== "string") {
        state = "finished";
        res.statusCode = 404;
        res.end();
        done(404);
        return;
      }
      state = "pending";
      response = res;
      res.on("close", () => {
        if (state === "pending") finish(504, "");
      });
      timer = setTimeout(() => finish(504, ""), REQUEST_TIMEOUT_MS);
      report({ event: "PEER_ACCEPTED", peer: req.socket.remoteAddress });
    },
    release() { return finish(200, MARKER); },
    expire() { return finish(504, ""); },
    state() { return state; },
  };
}

function runGateway() {
  let server;
  const session = createPendingMarker(
    (event) => process.stdout.write(JSON.stringify(event) + "\n"),
    (status) => {
      if (status !== 200) process.exitCode = 2;
      server.close();
    },
  );
  server = http.createServer((req, res) => session.accept(req, res));
  process.on("SIGUSR2", () => session.release());
  server.requestTimeout = REQUEST_TIMEOUT_MS;
  server.listen(PORT, "0.0.0.0");
  setTimeout(() => {
    if (session.state() === "idle") {
      process.exitCode = 2;
      server.close();
    }
  }, REQUEST_TIMEOUT_MS).unref();
}

function runClient() {
  const request = http.get({
    hostname: "ea4e-peer-gateway", port: PORT, path: "/marker",
    timeout: REQUEST_TIMEOUT_MS + 5000,
  }, (response) => {
    let body = "";
    response.setEncoding("utf8");
    response.on("data", (part) => {
      body += part;
      if (body.length > MARKER.length) response.destroy();
    });
    response.on("end", () => {
      if (response.statusCode !== 200 || body !== MARKER) {
        process.exitCode = 3;
        return;
      }
      process.stdout.write("MARKER_MATCH\n");
    });
  });
  request.on("timeout", () => request.destroy(new Error("timeout")));
  request.on("error", () => { process.exitCode = 4; });
}

if (require.main === module) {
  if (process.argv[2] === "gateway") runGateway();
  else if (process.argv[2] === "client") runClient();
  else process.exitCode = 1;
}

module.exports = { MARKER, createPendingMarker };
