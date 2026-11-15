const test = require("node:test");
const assert = require("node:assert");
const { streak } = require("./streak.js");

test("counts back from the last day", () => {
  assert.strictEqual(streak([true, false, true, true]), 2);
});

test("an empty log has no streak", () => {
  assert.strictEqual(streak([]), 0);
});
