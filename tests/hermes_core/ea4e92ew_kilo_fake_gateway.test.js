"use strict";

const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const { EventEmitter } = require("node:events");
const test = require("node:test");
const { createPendingFake, FAKE_SSE, MAX_BODY_BYTES } = require(
  "../../tools/hermes_core/container_images/ea4e92ew_kilo_fake_gateway/gateway.js");

function response() {
  const res = new EventEmitter();
  res.statusCode = 200;
  res.destroyed = false;
  res.headers = {};
  res.setHeader = (key, value) => { res.headers[key] = value; };
  res.end = (body = "") => { res.body = body; res.ended = true; };
  return res;
}

function request(overrides = {}) {
  const req = new EventEmitter();
  Object.assign(req, { method: "POST", url: "/v1/chat/completions",
    headers: { "content-type": "application/json" },
    socket: { remoteAddress: "172.20.0.2" } }, overrides);
  return req;
}

test("bounded body reports only digest and holds until one release", () => {
  const events = [];
  const terminal = [];
  const session = createPendingFake((event) => events.push(event),
    (status) => terminal.push(status));
  const req = request();
  const res = response();
  const raw = Buffer.from('{"model":"ea4e-inert"}');
  assert.equal(session.release(), false);
  session.accept(req, res);
  req.emit("data", raw);
  req.emit("end");
  assert.equal(res.ended, undefined);
  assert.deepEqual(events, [{ event: "FAKE_REQUEST_PENDING", peer: "172.20.0.2",
    body_bytes: raw.length,
    body_sha256: crypto.createHash("sha256").update(raw).digest("hex") }]);
  assert.equal(session.release(), true);
  assert.equal(res.statusCode, 200);
  assert.equal(res.headers["Content-Type"], "text/event-stream");
  assert.equal(res.body, FAKE_SSE);
  assert.deepEqual(terminal, [200]);
  assert.equal(session.release(), false);
});

test("oversized body denies without reporting or release", () => {
  const events = [];
  const session = createPendingFake((event) => events.push(event), () => {});
  const req = request();
  const res = response();
  session.accept(req, res);
  req.emit("data", Buffer.alloc(MAX_BODY_BYTES + 1));
  req.emit("end");
  assert.equal(res.statusCode, 413);
  assert.deepEqual(events, []);
  assert.equal(session.release(), false);
});

test("empty body denies without a pending event", () => {
  const events = [];
  const session = createPendingFake((event) => events.push(event), () => {});
  const req = request();
  const res = response();
  session.accept(req, res);
  req.emit("end");
  assert.equal(res.statusCode, 400);
  assert.deepEqual(events, []);
  assert.equal(session.release(), false);
});

test("reporting failure cannot release a fake response", () => {
  const session = createPendingFake(() => { throw new Error("report failure"); },
    () => {});
  const req = request();
  const res = response();
  session.accept(req, res);
  req.emit("data", Buffer.from("{}"));
  req.emit("end");
  assert.equal(res.statusCode, 500);
  assert.equal(session.release(), false);
});

test("wrong route consumes the one request and reports nothing", () => {
  const events = [];
  const session = createPendingFake((event) => events.push(event), () => {});
  const rejected = response();
  session.accept(request({ url: "/secret" }), rejected);
  assert.equal(rejected.statusCode, 404);
  assert.deepEqual(events, []);
  assert.equal(session.release(), false);
  const retry = response();
  session.accept(request(), retry);
  assert.equal(retry.statusCode, 503);
});

test("aborted client cannot receive fake response", () => {
  const events = [];
  const session = createPendingFake((event) => events.push(event), () => {});
  const req = request();
  const res = response();
  session.accept(req, res);
  req.emit("data", Buffer.from("{}"));
  req.emit("end");
  req.emit("aborted");
  assert.equal(session.release(), false);
  assert.equal(res.statusCode, 504);
  assert.equal(events.length, 1);
});
