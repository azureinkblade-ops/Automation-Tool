// SPDX-License-Identifier: LicenseRef-AzureInkblade-Internal
"use strict";

const childProcess = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const net = require("node:net");

const PROBE_IDS = Object.freeze([
  "NQ-01", "NQ-02", "NQ-03", "NQ-04", "NQ-05", "NQ-06",
  "NQ-07", "NQ-08", "NQ-09", "NQ-10", "NQ-11", "NQ-12",
]);
const REQUEST_KEYS = Object.freeze([
  "budgets", "probeConfig", "probeId", "requestId", "schemaVersion",
]);
const BUDGET_KEYS = Object.freeze([
  "activeProcesses", "descendants", "inputBytes", "processMemoryBytes",
  "stderrBytes", "stdoutBytes", "wallClockMs",
]);
const FIXED_BUDGETS = Object.freeze({
  activeProcesses: 1,
  descendants: 0,
  inputBytes: 64 * 1024,
  processMemoryBytes: 256 * 1024 * 1024,
  stderrBytes: 64 * 1024,
  stdoutBytes: 4 * 1024 * 1024,
  wallClockMs: 10_000,
});
const REQUEST_ID = /^[a-z0-9][a-z0-9-]{7,63}$/;
const SHA256 = /^[0-9a-f]{64}$/;

function fail(message) {
  throw new Error(message);
}

function exactKeys(value, expected, label) {
  if (value === null || Array.isArray(value) || typeof value !== "object") {
    fail(`${label} must be an object`);
  }
  const actual = Object.keys(value).sort();
  if (JSON.stringify(actual) !== JSON.stringify([...expected].sort())) {
    fail(`${label} keys differ from contract`);
  }
}

function canonical(value) {
  if (Array.isArray(value)) {
    return value.map(canonical);
  }
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.keys(value).sort().map((key) => [key, canonical(value[key])]),
    );
  }
  return value;
}

function parseArgs(argv) {
  if (argv.length !== 6 || argv[0] !== "--probe-id" ||
      argv[2] !== "--request-id" || argv[4] !== "--request") {
    fail("exact ordered probe arguments required");
  }
  const result = Object.freeze({
    probeId: argv[1],
    requestId: argv[3],
    requestPath: argv[5],
  });
  if (!PROBE_IDS.includes(result.probeId) || !REQUEST_ID.test(result.requestId) ||
      !result.requestPath || result.requestPath.includes("\0")) {
    fail("probe arguments malformed");
  }
  return result;
}

function expectedConfigKeys(probeId) {
  if (probeId === "NQ-04" || probeId === "NQ-05") {
    return ["host", "port"];
  }
  if (probeId === "NQ-06" || probeId === "NQ-07") {
    return ["path", "sha256"];
  }
  return [];
}

function validateConfig(probeId, config) {
  exactKeys(config, expectedConfigKeys(probeId), "probe config");
  if (probeId === "NQ-04" || probeId === "NQ-05") {
    if (typeof config.host !== "string" || !config.host ||
        !Number.isInteger(config.port) || config.port < 1 || config.port > 65535) {
      fail("network probe config malformed");
    }
  }
  if (probeId === "NQ-06" || probeId === "NQ-07") {
    if (typeof config.path !== "string" || !config.path ||
        config.path.includes("\0") || typeof config.sha256 !== "string" ||
        !SHA256.test(config.sha256)) {
      fail("filesystem probe config malformed");
    }
  }
}

function readRequest(path, args) {
  const bytes = fs.readFileSync(path);
  if (bytes.length < 1 || bytes.length > FIXED_BUDGETS.inputBytes) {
    fail("request byte budget exceeded");
  }
  const text = bytes.toString("utf8");
  const request = JSON.parse(text);
  exactKeys(request, REQUEST_KEYS, "request");
  exactKeys(request.budgets, BUDGET_KEYS, "budgets");
  if (request.schemaVersion !== 1 || request.requestId !== args.requestId ||
      request.probeId !== args.probeId ||
      JSON.stringify(request.budgets) !== JSON.stringify(FIXED_BUDGETS)) {
    fail("request identity or budgets differ from arguments");
  }
  validateConfig(request.probeId, request.probeConfig);
  if (text !== JSON.stringify(canonical(request))) {
    fail("request is not canonical JSON");
  }
  return Object.freeze(request);
}

function writeFrame(value) {
  const payload = Buffer.from(JSON.stringify(canonical(value)), "utf8");
  if (payload.length > 64 * 1024) {
    fail("result frame exceeds contract");
  }
  const header = Buffer.alloc(4);
  header.writeUInt32BE(payload.length, 0);
  process.stdout.write(header);
  process.stdout.write(payload);
}

function networkAttempt(config) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: config.host, port: config.port });
    let settled = false;
    const finish = (connected, code) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve({ connected, code: code || null });
    };
    socket.setTimeout(1000, () => finish(false, "TIMEOUT"));
    socket.once("connect", () => finish(true, null));
    socket.once("error", (error) => finish(false, error.code || "ERROR"));
  });
}

function readFixture(config) {
  const bytes = fs.readFileSync(config.path);
  const sha256 = crypto.createHash("sha256").update(bytes).digest("hex");
  if (sha256 !== config.sha256) {
    fail("filesystem probe target identity mismatch");
  }
  return { read: true, sha256 };
}

function waitForever() {
  return new Promise(() => setInterval(() => {}, 1000));
}

const ACTIONS = Object.freeze({
  "NQ-01": async () => fail("NQ-01 must terminate before resume"),
  "NQ-02": async () => ({ transport: "ok" }),
  "NQ-03": async () => {
    const child = childProcess.spawnSync(process.execPath, ["-e", "process.exit(0)"], {
      env: process.env,
      stdio: "ignore",
      windowsHide: true,
    });
    return { childStarted: child.error === undefined, code: child.error?.code || null };
  },
  "NQ-04": async (request) => networkAttempt(request.probeConfig),
  "NQ-05": async (request) => networkAttempt(request.probeConfig),
  "NQ-06": async (request) => readFixture(request.probeConfig),
  "NQ-07": async (request) => readFixture(request.probeConfig),
  "NQ-08": async () => waitForever(),
  "NQ-09": async () => {
    const allocations = [];
    for (;;) allocations.push(Buffer.alloc(8 * 1024 * 1024, 0xa5));
  },
  "NQ-10": async () => {
    for (;;) process.stdout.write(Buffer.alloc(64 * 1024, 0x58));
  },
  "NQ-11": async () => {
    for (;;) process.stderr.write(Buffer.alloc(4096, 0x59));
  },
  "NQ-12": async () => waitForever(),
});

async function main(argv) {
  const args = parseArgs(argv);
  const request = readRequest(args.requestPath, args);
  const observed = await ACTIONS[args.probeId](request);
  writeFrame({
    observed,
    probeId: args.probeId,
    requestId: args.requestId,
    schemaVersion: 1,
  });
}

if (require.main === module) {
  main(process.argv.slice(2)).catch((error) => {
    process.stderr.write(`EA4E92S_PROBE_ERROR:${error.message}\n`);
    process.exitCode = 1;
  });
}

module.exports = Object.freeze({
  ACTIONS,
  FIXED_BUDGETS,
  PROBE_IDS,
  canonical,
  main,
  parseArgs,
  readRequest,
  readFixture,
  waitForever,
  writeFrame,
});
