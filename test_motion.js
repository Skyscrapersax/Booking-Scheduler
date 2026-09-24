const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

function run(reduce) {
  const calls = [];
  const context = {
    matchMedia(query) {
      assert.strictEqual(query, "(prefers-reduced-motion: reduce)");
      return { matches: reduce };
    },
    anime(opts) {
      calls.push(opts);
    },
  };
  vm.createContext(context);
  vm.runInContext(fs.readFileSync("static/motion.js", "utf8"), context);
  return calls;
}

const calls = run(false);
assert.strictEqual(calls.length, 2);
assert.strictEqual(calls[0].targets, ".App-logo");
assert.strictEqual(calls[0].rotate, "1turn");
assert.strictEqual(calls[0].loop, true);
assert.strictEqual(calls[0].easing, "linear");
assert.strictEqual(calls[1].targets, ".heart");
assert.strictEqual(calls[1].scale[0], 1);
assert.strictEqual(calls[1].scale[1], 1.25);
assert.strictEqual(calls[1].loop, true);
assert.strictEqual(run(true).length, 0);

const html = fs.readFileSync("templates/index.html", "utf8");
assert.ok(html.includes("vendor/anime.min.js"));
assert.ok(html.includes("motion.js"));
assert.ok(!/gsap|react-spring|framer-motion/i.test(html + fs.readFileSync("static/motion.js", "utf8")));
assert.ok(fs.readFileSync("static/vendor/anime.min.js", "utf8").includes("anime.js v3.2.2"));

console.log("ok");
