const { spawnSync } = require("node:child_process");
const path = require("node:path");

const env = { ...process.env };
delete env.npm_config_user_agent;
delete env.npm_execpath;
delete env.npm_node_execpath;

const builderCli = path.join(__dirname, "node_modules", "electron-builder", "out", "cli", "cli.js");
const result = spawnSync(process.execPath, [builderCli, "--win", "--x64", "--dir"], {
  cwd: __dirname,
  env,
  stdio: "inherit",
});

if (result.error) throw result.error;
process.exit(result.status ?? 1);
