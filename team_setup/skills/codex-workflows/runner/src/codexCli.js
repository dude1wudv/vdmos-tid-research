import { spawn } from "node:child_process";
import { existsSync as nodeExistsSync } from "node:fs";

export function resolveCodexCommand({ env = process.env, platform = process.platform, existsSync = nodeExistsSync } = {}) {
  return listCodexCandidates({ env, platform, existsSync })[0] ?? (platform === "win32" ? "codex.cmd" : "codex");
}

export async function resolveLatestCodexCommand({
  env = process.env,
  platform = process.platform,
  existsSync = nodeExistsSync,
  runVersion = readCodexVersion,
} = {}) {
  const override = env.CODEX_WORKFLOWS_CODEX ?? env.CODEX_CLI;
  if (override) return override;

  const candidates = listCodexCandidates({ env, platform, existsSync });
  const probed = await Promise.all(candidates.map(async (command, i) => ({ command, i, version: await runVersion(command) })));
  probed.sort((a, b) => compareSemver(b.version, a.version) || a.i - b.i);
  return probed.find((p) => p.version)?.command ?? resolveCodexCommand({ env, platform, existsSync });
}

export function listCodexCandidates({ env = process.env, platform = process.platform, existsSync = nodeExistsSync } = {}) {
  const override = env.CODEX_WORKFLOWS_CODEX ?? env.CODEX_CLI;
  if (override) return [override];

  const separator = platform === "win32" ? ";" : ":";
  const dirs = String(env.Path ?? env.PATH ?? env.path ?? "").split(separator).filter(Boolean);
  const names = platform === "win32" ? ["codex.cmd", "codex.exe", "codex.bat", "codex.com", "codex"] : ["codex"];
  const seen = new Set();
  const out = [];
  for (const dir of dirs) {
    for (const name of names) {
      const candidate = joinForPlatform(dir, name, platform);
      const key = platform === "win32" ? candidate.toLowerCase() : candidate;
      if (!seen.has(key) && existsSync(candidate)) {
        seen.add(key);
        out.push(candidate);
      }
    }
  }
  return out;
}

export function needsShell(command, platform = process.platform) {
  return platform === "win32" && /\.(cmd|bat)$/i.test(command);
}

export function shellCommand(command, args = []) {
  return [quote(command), ...args.map(quote)].join(" ");
}

export function readCodexVersion(command, timeoutMs = 3_000) {
  const args = ["--version"];
  return new Promise((resolve) => {
    let child;
    try {
      child = needsShell(command) ? spawn(shellCommand(command, args), { shell: true }) : spawn(command, args);
    } catch {
      resolve(null);
      return;
    }
    let stdout = "";
    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      resolve(null);
    }, timeoutMs);
    child.stdout?.on("data", (d) => (stdout += d.toString("utf8")));
    child.on("error", () => {
      clearTimeout(timer);
      resolve(null);
    });
    child.on("exit", () => {
      clearTimeout(timer);
      resolve(parseVersion(stdout));
    });
  });
}

export function parseVersion(text) {
  return String(text ?? "").match(/(\d+\.\d+\.\d+)/)?.[1] ?? null;
}

export function compareSemver(a, b) {
  if (!a && !b) return 0;
  if (!a) return -1;
  if (!b) return 1;
  const av = a.split(".").map(Number);
  const bv = b.split(".").map(Number);
  for (let i = 0; i < Math.max(av.length, bv.length); i++) {
    const d = (av[i] ?? 0) - (bv[i] ?? 0);
    if (d) return d;
  }
  return 0;
}

function quote(s) {
  const text = String(s);
  return /[\s"]/u.test(text) ? `"${text.replace(/"/g, '\\"')}"` : text;
}

function joinForPlatform(dir, file, platform) {
  const sep = platform === "win32" ? "\\" : "/";
  return `${String(dir).replace(/[\\/]+$/, "")}${sep}${file}`;
}
