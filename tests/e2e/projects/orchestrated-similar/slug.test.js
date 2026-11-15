const test = require("node:test");
const assert = require("node:assert");
const { slug } = require("./slug.js");

test("spaces and marks become dashes", () => {
  assert.strictEqual(slug("  Hello, World! "), "hello-world");
});
