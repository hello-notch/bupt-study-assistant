const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const { version } = require("./package.json");

const env = { ...process.env };
delete env.npm_config_user_agent;
delete env.npm_execpath;
delete env.npm_node_execpath;

const builderCli = path.join(__dirname, "node_modules", "electron-builder", "out", "cli", "cli.js");
const distDir = path.join(__dirname, "dist");
const unpackedDir = path.join(distDir, "win-unpacked");
const archivePath = path.join(distDir, `YouXueBan-${version}-Windows-x64-full.zip`);

// Always archive a fresh unpacked build so stale files from an earlier run
// cannot leak into the published package.
fs.rmSync(unpackedDir, { recursive: true, force: true });
fs.rmSync(archivePath, { force: true });

const result = spawnSync(process.execPath, [builderCli, "--win", "--x64", "--dir"], {
  cwd: __dirname,
  env,
  stdio: "inherit",
});

if (result.error) throw result.error;
if ((result.status ?? 1) !== 0) process.exit(result.status ?? 1);

const archiveCommand = [
  "$ErrorActionPreference = 'Stop'",
  `Compress-Archive -Path '${unpackedDir.replace(/'/g, "''")}\\*' -DestinationPath '${archivePath.replace(/'/g, "''")}' -Force`,
].join("; ");
const archiveResult = spawnSync("powershell.exe", ["-NoLogo", "-NoProfile", "-NonInteractive", "-Command", archiveCommand], {
  cwd: __dirname,
  env,
  stdio: "inherit",
});
if (archiveResult.error) throw archiveResult.error;
if ((archiveResult.status ?? 1) !== 0) process.exit(archiveResult.status ?? 1);
console.log(`Created ${archivePath}`);
