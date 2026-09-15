const fs = require("node:fs");
const path = require("node:path");
const { spawnSync, spawn } = require("node:child_process");

const root = path.resolve(__dirname, "..");
const web = path.join(root, "web");
const client = path.join(root, "client");
const required = [
  "web/node_modules/vue-tsc/bin/vue-tsc.js",
  "web/node_modules/typescript/bin/tsc",
  "web/node_modules/vite/bin/vite.js",
  "client/node_modules/electron/dist/electron.exe",
];
for (const entry of required) {
  if (!fs.existsSync(path.join(root, entry))) {
    console.error(`[ERROR] Missing ${entry}\nRun pnpm --dir web install --frozen-lockfile and pnpm --dir client install --frozen-lockfile from ${root}`);
    process.exit(1);
  }
}

console.log("Checking and building the desktop UI...");
for (const [script, ...args] of [
  ["node_modules/vue-tsc/bin/vue-tsc.js", "--noEmit", "-p", "tsconfig.app.json"],
  ["node_modules/typescript/bin/tsc", "--noEmit", "-p", "tsconfig.node.json"],
  ["node_modules/vite/bin/vite.js", "build"],
]) {
  const result = spawnSync(process.execPath, [path.join(web, script), ...args], { cwd: web, stdio: "inherit" });
  if (result.error) console.error(result.error.message);
  if (result.status !== 0) process.exit(result.status || 1);
}

// Launch the real desktop runtime with file:// storage, not a browser API proxy.
const env = { ...process.env };
delete env.ELECTRON_RUN_AS_NODE;
delete env.YOUXUEBAN_CLIENT_URL;
const app = spawn(path.join(client, "node_modules/electron/dist/electron.exe"), [client], {
  cwd: client, env, detached: true, stdio: "ignore",
});
app.on("error", (error) => {
  console.error(`[ERROR] ${error.message}`);
  process.exitCode = 1;
});
app.once("spawn", () => {
  app.unref();
  console.log("Desktop opened. Close it and run this script again after code changes. No release package was created.");
});
