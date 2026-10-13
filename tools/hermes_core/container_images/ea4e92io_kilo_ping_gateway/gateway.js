"use strict";

const crypto = require("node:crypto");

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
                             report, done }) {
  const responseBody = validateResponse(responseBytes, expectedSha256,
                                        taskHash, receiptHash);
  if (typeof report !== "function" || typeof done !== "function") {
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

module.exports = { MAX_BYTES, validateResponse, createPendingPing };
