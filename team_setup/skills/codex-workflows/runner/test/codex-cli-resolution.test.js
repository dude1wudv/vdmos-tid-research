import assert from "node:assert/strict";
import { needsShell, resolveCodexCommand, resolveLatestCodexCommand, shellCommand } from "../src/codexCli.js";

const env = {
  Path: "C:\\Users\\teammate\\AppData\\Roaming\\npm;C:\\Tools\\old;C:\\Tools\\new;C:\\Windows\\System32",
  PATHEXT: ".COM;.EXE;.BAT;.CMD",
};
const cmd = resolveCodexCommand({ env, platform: "win32", existsSync: (p) => p.endsWith("\\codex.cmd") });

assert.equal(cmd, "C:\\Users\\teammate\\AppData\\Roaming\\npm\\codex.cmd");
assert.equal(needsShell(cmd, "win32"), true, "Windows npm .cmd shim must be run through the shell");
assert.equal(shellCommand("C:\\Program Files\\Codex\\codex.cmd", ["--version"]), '"C:\\Program Files\\Codex\\codex.cmd" --version');

assert.equal(
  resolveCodexCommand({ env: { PATH: "/usr/bin:/bin" }, platform: "linux", existsSync: (p) => p === "/usr/bin/codex" }),
  "/usr/bin/codex",
);

assert.equal(
  await resolveLatestCodexCommand({
    env,
    platform: "win32",
    existsSync: (p) => p.endsWith("\\codex.cmd"),
    runVersion: async (p) => p.includes("new") ? "0.143.0" : p.includes("old") ? "0.135.0" : null,
  }),
  "C:\\Tools\\new\\codex.cmd",
  "latest installed Codex on PATH wins",
);
