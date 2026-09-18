const fs = require("node:fs");
const path = require("node:path");
const { createRequire } = require("node:module");
const root = path.resolve(__dirname, "..");
const requireVite = createRequire(require.resolve("vite", { paths: [path.join(root, "web")] }));
const { build } = requireVite("esbuild");
const runtime = path.join(root, "android/runtime");
const assets = path.join(root, "android/app/src/main/assets");

async function main() {
  fs.mkdirSync(assets, { recursive: true });
  // Only generated assets are replaced, never application data or signing keys.
  for (const directory of ["web", "runtime"]) {
    fs.rmSync(path.join(assets, directory), { recursive: true, force: true });
    fs.mkdirSync(path.join(assets, directory), { recursive: true });
  }
  fs.cpSync(path.join(root, "web/dist"), path.join(assets, "web"), { recursive: true });
  fs.copyFileSync(path.join(runtime, "ui-bridge.js"), path.join(assets, "web/android-bridge.js"));
  const entry = path.join(assets, "web/index.html");
  const html = fs.readFileSync(entry, "utf8").replace("<head>", '<head><script src="./android-bridge.js"></script>');
  fs.writeFileSync(entry, html);
  await build({
    entryPoints: [path.join(runtime, "entry.cjs")],
    outfile: path.join(assets, "runtime/runtime.js"),
    bundle: true, format: "iife", platform: "browser", target: "chrome100",
    plugins: [{
      name: "android-platform",
      setup(build) {
        build.onResolve({ filter: /^node:(fs|path|crypto)$/ }, () => ({ path: path.join(runtime, "node-shims.cjs") }));
        build.onResolve({ filter: /^linkedom$/ }, () => ({ path: path.join(runtime, "dom.cjs") }));
        build.onResolve({ filter: /playwright-auth\.cjs$/ }, () => ({ path: path.join(runtime, "campus-auth.cjs") }));
      },
    }],
  });
  fs.writeFileSync(path.join(assets, "runtime/index.html"), '<!doctype html><meta charset="utf-8"><script src="./runtime.js"></script>');
  const drawable = path.join(root, "android/app/src/main/res/drawable");
  fs.mkdirSync(drawable, { recursive: true });
  fs.copyFileSync(path.join(root, "client/resources/app-icon.png"), path.join(drawable, "app_icon.png"));
  console.log("Android assets built from the shared Windows UI and local runtime.");
}
main().catch((error) => { console.error(error.message); process.exitCode = 1; });
