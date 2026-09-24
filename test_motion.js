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
  context.anime.stagger = (ms) => ms;
  vm.createContext(context);
  vm.runInContext(fs.readFileSync("static/motion.js", "utf8"), context);
  return calls;
}

const calls = run(false);
assert.strictEqual(calls.length, 2);
assert.strictEqual(calls[0].targets, ".signin, .heading, .notice, .error, .booking, .empty");
assert.strictEqual(calls[0].translateY[0], 16);
assert.strictEqual(calls[0].translateY[1], 0);
assert.strictEqual(calls[1].targets, "aside");
assert.strictEqual(calls[1].translateX[0], 24);
assert.strictEqual(run(true).length, 0);

const html = fs.readFileSync("templates/index.html", "utf8");
const motion = fs.readFileSync("static/motion.js", "utf8");
assert.ok(html.includes("vendor/anime.min.js"));
assert.ok(html.includes("motion.js"));
assert.ok(!html.includes("heart"));
assert.ok(!motion.includes(".heart"));
assert.ok(!motion.includes("App-logo"));
assert.ok(!/gsap|react-spring|framer-motion/i.test(html + motion));
assert.ok(fs.readFileSync("static/vendor/anime.min.js", "utf8").includes("anime.js v3.2.2"));

console.log("ok");
