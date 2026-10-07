"use strict";

const http = require("node:http");

const MARKER = "EA4E_PEER_OK\n";
const PORT = 8181;
const TIMEOUT_MS = 15000;

function handleMarker(req, res, recordPeer) {
  const peer = req.socket && req.socket.remoteAddress;
  recordPeer(typeof peer === "string" ? peer : "missing");
  if (req.method !== "GET" || req.url !== "/marker") {
    res.statusCode = 404;
    res.end();
    return;
  }
  res.statusCode = 200;
  res.setHeader("Content-Type", "text/plain");
  res.end(MARKER);
}

function runGateway() {
  let seen = false;
  const server = http.createServer((req, res) => {
    if (seen) {
      res.statusCode = 503;
      res.end();
      return;
    }
    seen = true;
    handleMarker(req, res, (peer) => {
      process.stdout.write(JSON.stringify({ peer }) + "\n");
    });
    server.close();
  });
  server.requestTimeout = 5000;
  server.listen(PORT, "0.0.0.0");
  setTimeout(() => {
    if (!seen) process.exitCode = 2;
    server.close();
  }, TIMEOUT_MS).unref();
}

function runClient() {
  const request = http.get({
    hostname: "ea4e-peer-gateway",
    port: PORT,
    path: "/marker",
    timeout: 5000,
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

module.exports = { MARKER, handleMarker };
