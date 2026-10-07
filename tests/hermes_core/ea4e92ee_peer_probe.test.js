"use strict";

const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const test = require("node:test");
const { MARKER, createPendingMarker } = require(
  "../../tools/hermes_core/container_images/ea4e92ee_peer_probe/marker.js");

function response() {
  const res = new EventEmitter();
  res.statusCode = 200;
  res.destroyed = false;
  res.ended = false;
  res.end = (body = "") => { res.ended = true; res.body = body; };
  return res;
}

function request(method = "GET", url = "/marker", peer = "172.20.0.2") {
  return { method, url, socket: { remoteAddress: peer } };
}

test("accepted peer waits for explicit release while the client remains pending", () => {
  const events = [];
  let closed = 0;
  const session = createPendingMarker((event) => events.push(event), () => closed++);
  const res = response();
  assert.equal(session.release(), false);
  session.accept(request(), res);
  assert.deepEqual(events, [{ event: "PEER_ACCEPTED", peer: "172.20.0.2" }]);
  assert.equal(session.state(), "pending");
  assert.equal(res.ended, false);
  assert.equal(session.release(), true);
  assert.equal(res.statusCode, 200);
  assert.equal(res.body, MARKER);
  assert.equal(closed, 1);
  assert.equal(session.release(), false);
});

test("timeout denies the marker and release cannot revive it", () => {
  const events = [];
  const terminal = [];
  const session = createPendingMarker((event) => events.push(event),
    (status) => terminal.push(status));
  const res = response();
  session.accept(request(), res);
  assert.equal(session.expire(), true);
  assert.equal(res.statusCode, 504);
  assert.equal(res.body, "");
  assert.equal(session.release(), false);
  assert.equal(events.length, 1);
  assert.deepEqual(terminal, [504]);
});

test("wrong path consumes the one request without logging or releasing a marker", () => {
  const events = [];
  const session = createPendingMarker((event) => events.push(event), () => {});
  const rejected = response();
  session.accept(request("POST", "/secret"), rejected);
  assert.equal(rejected.statusCode, 404);
  assert.equal(session.release(), false);
  assert.deepEqual(events, []);
  const second = response();
  session.accept(request(), second);
  assert.equal(second.statusCode, 503);
});

test("closed client cannot receive a later marker", () => {
  let closed = 0;
  const session = createPendingMarker(() => {}, () => closed++);
  const res = response();
  session.accept(request(), res);
  res.destroyed = true;
  res.emit("close");
  assert.equal(session.release(), false);
  assert.equal(res.ended, false);
  assert.equal(closed, 1);
});
