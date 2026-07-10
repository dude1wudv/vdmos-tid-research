// Detect the installed `codex` CLI version. The runner intentionally uses the
// newest working Codex found on PATH, so local upgrades do not require editing
// this package.

import { readCodexVersion, resolveLatestCodexCommand } from "./codexCli.js";

export const VERIFIED_CODEX_VERSION = "auto";

export async function detectCodexVersion() {
  try {
    return await readCodexVersion(await resolveLatestCodexCommand(), 10_000);
  } catch {
    return null;
  }
}

// Returns a warning string if an explicit pinned version differs from `found`.
// Default auto mode accepts the newest local Codex CLI without a stale warning.
export function versionDriftNote(found, pinned = VERIFIED_CODEX_VERSION) {
  if (!found || !pinned || pinned === "auto" || found === pinned) return null;
  return (
    `⚠ codex ${found} detected; this runner's app-server bindings were verified against ${pinned}. ` +
    `Calls should still work, but if they fail, regenerate bindings:\n` +
    `    codex app-server generate-json-schema --out ./schema`
  );
}
