"use strict";

// Redocly 1.x expects the callable minimatch export. Keep its supported API
// generator while using the security-patched matcher, scoped to this process.
// Do not patch package files or weaken URL-pattern/header matching.
const { createRequire } = require("node:module");
const redocly = createRequire(require.resolve("@redocly/openapi-core"));
const id = redocly.resolve("minimatch");
const modern = redocly("minimatch");

if (typeof modern === "function") {
  module.exports = modern;
} else {
  if (typeof modern.minimatch !== "function" || !require.cache[id]) {
    throw new TypeError("Unsupported minimatch export for OpenAPI generation");
  }
  const callable = (...args) => modern.minimatch(...args);
  Object.assign(callable, modern);
  require.cache[id].exports = callable;
  module.exports = callable;
}
