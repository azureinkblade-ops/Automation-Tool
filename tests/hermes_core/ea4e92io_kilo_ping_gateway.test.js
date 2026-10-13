"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const { EventEmitter } = require("node:events");
const test = require("node:test");
const { createPendingPing, loadFakeConfig, MAX_BYTES } = require(
  "../../tools/hermes_core/container_images/ea4e92io_kilo_ping_gateway/gateway.js");

const TASK = "a".repeat(64);
const RECEIPT = "b".repeat(64);

function body(taskHash = TASK, receiptHash = RECEIPT) {
  const candidate = JSON.stringify({
    schema_version: "1", outcome: "SUCCEEDED",
    result_payload: { task_input_hash: taskHash,
      receiver_receipt_hash: receiptHash,
      statement: "kilo-cli-agent:PING_OK" },
    output_manifest: [], evidence_manifest: [],
    error_code: null, error_summary: null,
  });
  return Buffer.from(`data: ${JSON.stringify({
    choices: [{ delta: { content: candidate } }],
  })}\n\ndata: [DONE]\n\n`);
}

function fixture(overrides = {}) {
  const responseBytes = body();
  const events = [];
  const statuses = [];
  const session = createPendingPing({
    responseBytes,
    expectedSha256: crypto.createHash("sha256").update(responseBytes).digest("hex"),
    taskHash: TASK, receiptHash: RECEIPT,
    report: (event) => events.push(event), done: (status) => statuses.push(status),
    ...overrides,
  });
  return { responseBytes, events, statuses, session };
}

function request(overrides = {}) {
  const req = new EventEmitter();
  Object.assign(req, { method: "POST", url: "/v1/chat/completions",
    headers: { "content-type": "application/json" },
    socket: { remoteAddress: "172.20.0.2" } }, overrides);
  return req;
}

function response() {
  const res = new EventEmitter();
  res.statusCode = 200;
  res.destroyed = false;
  res.headers = {};
  res.setHeader = (key, value) => { res.headers[key] = value; };
  res.end = (value) => { res.body = value; res.ended = true; };
  return res;
}

test("one bounded request releases only the pinned attempt response", () => {
  const { session, responseBytes, events, statuses } = fixture();
  const req = request();
  const res = response();
  const sent = Buffer.from('{"model":"ea4e-inert"}');
  assert.equal(session.release(), false);
  session.accept(req, res);
  req.emit("data", sent);
  req.emit("end");
  assert.equal(res.ended, undefined);
  assert.deepEqual(events, [{ event: "FAKE_PING_REQUEST_PENDING",
    peer: "172.20.0.2", body_bytes: sent.length,
    body_sha256: crypto.createHash("sha256").update(sent).digest("hex") }]);
  assert.equal(session.release(), true);
  assert.equal(res.statusCode, 200);
  assert.equal(res.headers["Content-Type"], "text/event-stream");
  assert.deepEqual(res.body, responseBytes);
  assert.deepEqual(statuses, [200]);
  assert.equal(session.release(), false);
  const retry = response();
  session.accept(request(), retry);
  assert.equal(retry.statusCode, 503);
});

test("response lineage and digest must match before accepting requests", () => {
  const responseBytes = body("c".repeat(64));
  assert.throws(() => fixture({ responseBytes,
    expectedSha256: crypto.createHash("sha256").update(responseBytes).digest("hex") }),
  /response lineage denied/);
  assert.throws(() => fixture({ expectedSha256: "0".repeat(64) }),
    /response hash mismatch/);
  assert.throws(() => fixture({ responseBytes: Buffer.from("EA4E_INERT_OK"),
    expectedSha256: crypto.createHash("sha256").update("EA4E_INERT_OK").digest("hex") }),
  /response framing denied/);
});

test("oversized or empty request cannot reach pending", () => {
  for (const bytes of [Buffer.alloc(0), Buffer.alloc(MAX_BYTES + 1)]) {
    const { session, events } = fixture();
    const req = request();
    const res = response();
    session.accept(req, res);
    if (bytes.length) req.emit("data", bytes);
    req.emit("end");
    assert.equal(res.statusCode, bytes.length ? 413 : 400);
    assert.equal(session.release(), false);
    assert.deepEqual(events, []);
  }
});

test("report failure and client abort deny release", () => {
  const failed = fixture({ report: () => { throw new Error("report failed"); } });
  const req = request();
  const res = response();
  failed.session.accept(req, res);
  req.emit("data", Buffer.from("{}"));
  req.emit("end");
  assert.equal(res.statusCode, 500);
  assert.equal(failed.session.release(), false);

  const aborted = fixture();
  const req2 = request();
  const res2 = response();
  aborted.session.accept(req2, res2);
  req2.emit("data", Buffer.from("{}"));
  req2.emit("end");
  req2.emit("aborted");
  assert.equal(res2.statusCode, 504);
  assert.equal(aborted.session.release(), false);
});

test("fake-only bootstrap requires canonical response and exact lineage", () => {
  const responseBytes = body();
  const env = {
    EA4E_QUALIFICATION_ONLY: "1",
    EA4E_PING_SSE_BASE64: responseBytes.toString("base64"),
    EA4E_PING_SSE_SHA256:
      crypto.createHash("sha256").update(responseBytes).digest("hex"),
    EA4E_TASK_INPUT_HASH: TASK,
    EA4E_RECEIVER_RECEIPT_HASH: RECEIPT,
  };
  assert.deepEqual(loadFakeConfig(env).responseBytes, responseBytes);
  assert.throws(() => loadFakeConfig({ ...env, EA4E_QUALIFICATION_ONLY: "0" }),
    /fake-only gateway configuration denied/);
  assert.throws(() => loadFakeConfig({ ...env, EA4E_PING_SSE_BASE64: "!!!!" }),
    /fake-only gateway configuration denied/);
  assert.throws(() => loadFakeConfig({ ...env, EA4E_PING_SSE_BASE64:
    env.EA4E_PING_SSE_BASE64 + "=" }),
  /noncanonical fake response encoding denied/);
  assert.throws(() => loadFakeConfig({ ...env, EA4E_TASK_INPUT_HASH:
    "c".repeat(64) }), /response lineage denied/);
  assert.throws(() => loadFakeConfig({ ...env, EA4E_PING_SSE_SHA256:
    "0".repeat(64) }), /response hash mismatch/);
});
