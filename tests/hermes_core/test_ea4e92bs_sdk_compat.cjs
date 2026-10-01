"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");

const expected = {
  "@ai-sdk/openai-compatible": ["2.0.41", "sha512-kNAGINk71AlOXx10Dq/PXw4t/9XjdK8uxfpVElRwtSFMdeSiLVt58p9TPx4/FJD+hxZuVhvxYj9r42osxWq79g=="],
  "ai": ["6.0.168", "sha512-2HqCJuO+1V2aV7vfYs5LFEUfxbkGX+5oa54q/gCCTL7KLTdbxcCu5D7TdLA5kwsrs3Szgjah9q6D9tpjHM3hUQ=="],
  "@ai-sdk/provider": ["3.0.8", "sha512-oGMAgGoQdBXbZqNG0Ze56CHjDZ1IDYOwGYxYjO5KLSlz5HiNQ9udIXsPZ61VWaHGZ5XW/jyjmr6t2xz2jGVwbQ=="],
  "@ai-sdk/provider-utils": ["4.0.23", "sha512-z8GlDaCmRSDlqkMF2f4/RFgWxdarvIbyuk+m6WXT1LYgsnGiXRJGTD2Z1+SDl3LqtFuRtGX1aghYvQLoHL/9pg=="],
  "zod": ["4.1.8", "sha512-5R1P+WwQqmmMIEACyzSvo4JXHY5WiAFHRMg+zBZKgKS+Q1viRa0C1hmUKtHltoIFKtIdki3pRxkmpP74jnNYHQ=="],
  "eventsource-parser": ["3.1.0", "sha512-kJezFj9YFAMLeORyi7aCLxLbD5/qWMQnoMVlVPyHIll7lgRJCc3JVln9Vgl9nwQi0YkMnhdGTMNn7CkRRAptMg=="],
  "@standard-schema/spec": ["1.1.0", "sha512-l2aFy5jALhniG5HgqrD6jXLi/rUWrKvqN/qJx6yoJsgKhblVd+iqqU4RCXavm/jPityDo5TCvKMnpjKnOriy0w=="],
};

function denyCapability(name) {
  return () => { throw new Error(`unexpected capability: ${name}`); };
}

for (const name of ["node:http", "node:https", "node:net", "node:tls"]) {
  const module = require(name);
  for (const method of ["request", "get", "connect", "createConnection"]) {
    if (typeof module[method] === "function") module[method] = denyCapability(`${name}.${method}`);
  }
}
const child = require("node:child_process");
for (const method of ["spawn", "exec", "execFile", "fork"]) {
  child[method] = denyCapability(`child_process.${method}`);
}
globalThis.fetch = denyCapability("global.fetch");

async function main() {
  const root = process.env.EA92BS_SDK_ROOT;
  assert.ok(root && path.isAbsolute(root), "isolated SDK root is required");
  const lock = JSON.parse(fs.readFileSync(path.join(root, "package-lock.json"), "utf8"));
  const fromRoot = createRequire(path.join(root, "package.json"));
  for (const [name, [version, integrity]] of Object.entries(expected)) {
    const installed = JSON.parse(fs.readFileSync(
      path.join(root, "node_modules", name, "package.json"), "utf8",
    ));
    const locked = lock.packages[`node_modules/${name}`];
    assert.equal(installed.version, version, `${name} installed version`);
    assert.equal(locked.version, version, `${name} lock version`);
    assert.equal(locked.integrity, integrity, `${name} lock integrity`);
  }

  const { createOpenAICompatible } = fromRoot("@ai-sdk/openai-compatible");
  const { streamText, generateText } = fromRoot("ai");
  const requests = [];
  let responseMode = "stream";
  const transport = async (url, options) => {
    const body = JSON.parse(options.body);
    requests.push({ url: String(url), method: options.method, body });
    assert.equal(String(url), "http://127.0.0.1:1/v1/chat/completions");
    assert.equal(options.method, "POST");
    if (responseMode === "failure") {
      return new Response("synthetic failure", { status: 503 });
    }
    if (responseMode === "generate") {
      return new Response(JSON.stringify({
        id: "fake-1", object: "chat.completion", created: 1, model: "fake-model",
        choices: [{ index: 0, message: { role: "assistant", content: "ok" }, finish_reason: "stop" }],
        usage: { prompt_tokens: 1, completion_tokens: 1, total_tokens: 2 },
      }), { status: 200, headers: { "content-type": "application/json" } });
    }
    const chunk = (delta, finish_reason) => `data: ${JSON.stringify({
      id: "fake-1", object: "chat.completion.chunk", created: 1, model: "fake-model",
      choices: [{ index: 0, delta, finish_reason }],
    })}\n\n`;
    const sse = chunk({ role: "assistant", content: "ok" }, null)
      + chunk({}, "stop") + "data: [DONE]\n\n";
    return new Response(sse, { status: 200, headers: { "content-type": "text/event-stream" } });
  };
  const provider = createOpenAICompatible({
    name: "ea92bs-inert", baseURL: "http://127.0.0.1:1/v1", fetch: transport,
  });
  const model = provider("fake-model");
  const input = {
    model, prompt: "inert SDK compatibility probe", maxRetries: 0,
    onError() {},
  };

  const streamed = streamText(input);
  assert.equal(await streamed.text, "ok");
  assert.equal(requests.length, 1, "one simple stream must make one request");
  assert.equal(requests[0].body.stream, true, "streamText must request streaming");

  responseMode = "failure";
  requests.length = 0;
  let failed = false;
  try { await streamText(input).text; } catch { failed = true; }
  assert.equal(failed, true, "synthetic 503 must fail");
  assert.equal(requests.length, 1, "maxRetries=0 must not retry synthetic 503");

  requests.length = 0;
  failed = false;
  try { await streamText({ ...input, maxRetries: 2 }).text; } catch { failed = true; }
  assert.equal(failed, true, "synthetic 503 with retries must eventually fail");
  assert.equal(requests.length, 3, "maxRetries=2 must make three attempts");

  responseMode = "generate";
  requests.length = 0;
  const generated = await generateText(input);
  assert.equal(generated.text, "ok");
  assert.equal(requests.length, 1, "one generate must make one request");
  assert.notEqual(requests[0].body.stream, true, "generateText must not request streaming");

  process.stdout.write(JSON.stringify({
    sdkOnly: true, realReceiverStarted: false, realNetworkCalls: 0,
    streamText: { requests: 1, stream: true },
    streamFailure503: { requests: 1, retried: false },
    streamFailure503WithTwoRetries: { requests: 3, retried: true },
    generateText: { requests: 1, stream: false },
  }) + "\n");
}

main().catch((error) => { process.stderr.write(`${error.stack}\n`); process.exitCode = 1; });
