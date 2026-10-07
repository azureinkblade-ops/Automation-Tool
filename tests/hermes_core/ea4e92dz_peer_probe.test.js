"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { handleMarker, MARKER } = require("../../tools/hermes_core/container_images/ea4e92dz_peer_probe/marker.js");

function response() {
  return {
    statusCode: 0,
    headers: {},
    body: null,
    setHeader(key, value) { this.headers[key] = value; },
    end(value) { this.body = value; },
  };
}

test("one fixed marker records the socket peer", () => {
  const observed = [];
  const res = response();
  handleMarker({ method: "GET", url: "/marker", socket: { remoteAddress: "172.20.0.2" } }, res,
    (peer) => observed.push(peer));
  assert.deepEqual(observed, ["172.20.0.2"]);
  assert.equal(res.statusCode, 200);
  assert.equal(res.body, MARKER);
});

test("unrecognized route fails without echoing request input", () => {
  const observed = [];
  const res = response();
  handleMarker({ method: "POST", url: "/secret", socket: { remoteAddress: "172.20.0.2" } }, res,
    (peer) => observed.push(peer));
  assert.deepEqual(observed, ["172.20.0.2"]);
  assert.equal(res.statusCode, 404);
  assert.equal(res.body, undefined);
});
