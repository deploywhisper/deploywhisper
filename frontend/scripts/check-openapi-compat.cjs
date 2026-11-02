"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { createRequire } = require("node:module");
const adapter = require("./redocly-minimatch-compat.cjs");
const redocly = createRequire(require.resolve("@redocly/openapi-core"));
const { readFileFromUrl } = redocly("./utils.js");

test("Redocly configured schema headers retain matching semantics", async () => {
  const requests = [];
  const config = {
    headers: [
      { matches: "schemas.example.invalid/**", name: "X-Scoped", value: "synthetic" },
      { matches: "https://other.example.invalid/**", name: "X-Other", value: "excluded" },
    ],
    customFetch: async (url, options) => {
      requests.push({ url, headers: options.headers });
      return { ok: true, text: async () => "{}", headers: new Map([["content-type", "application/json"]]) };
    },
  };
  const result = await readFileFromUrl("https://schemas.example.invalid/schema.json", config);
  assert.equal(result.body, "{}");
  assert.deepEqual(requests[0].headers, { "X-Scoped": "synthetic" });
  await readFileFromUrl("https://unrelated.example.invalid/schema.json", config);
  assert.deepEqual(requests[1].headers, {});
});

test("the scoped adapter preserves callable and named minimatch exports", () => {
  const scoped = redocly("minimatch");
  assert.equal(typeof scoped, "function");
  assert.equal(scoped, adapter);
  assert.equal(scoped("schemas/x.json", "schemas/*.json"), true);
  assert.equal(scoped.minimatch("schemas/x.json", "schemas/*.json"), true);
  assert.equal(new scoped.Minimatch("schemas/*.json").match("schemas/x.json"), true);
});
