// Map a model id requested by a workflow (often a Claude id, or a bare
// opus/sonnet/haiku alias from a Claude-authored script or an agentType
// definition) onto a model the local Codex app-server actually exposes.

export function modelId(m) {
  if (typeof m === "string") return m;
  if (m && typeof m === "object") return m.id ?? m.slug ?? m.model ?? m.name ?? null;
  return null;
}

// Legacy provider aliases are intentionally not translated to a concrete model.
// Let Codex select the active configured model instead.
function isLegacyAlias(id) {
  return /(?:claude-|^)(?:opus|sonnet|haiku)(?:-|$)/i.test(String(id));
}

/** Resolve an explicit available Codex model, otherwise inherit Codex config. */
export function resolveModel(requested, available = [], log = () => {}) {
  if (!requested || /^(inherit|default)$/i.test(requested)) return undefined;
  if (isLegacyAlias(requested)) {
    log(`model: '${requested}' is a legacy alias → using Codex config default`);
    return undefined;
  }
  if (!available.length) return requested;
  if (available.includes(requested)) return requested;
  log(`model: '${requested}' not exposed by Codex → using config default (have: ${available.join(", ")})`);
  return undefined;
}

// Pick the latest frontier model from a `model/list` result: the newest,
// strongest general model. Excludes -mini/-spark variants and hidden models;
// ranks by version number parsed from the id (5.5 > 5.4 > 5.3-codex > 5.2),
// breaking ties toward the flagged default and the shorter (base) id.
export function pickFrontier(models = []) {
  const id = (m) => (typeof m === "string" ? m : m?.id ?? m?.model ?? m?.slug ?? m?.name);
  const ver = (s) => {
    const mt = String(s).match(/(\d+(?:\.\d+)?)/);
    return mt ? parseFloat(mt[1]) : -1;
  };
  const eligible = models
    .map((m) => ({
      id: id(m),
      isDefault: typeof m === "object" && !!m?.isDefault,
      hidden: typeof m === "object" && !!m?.hidden,
    }))
    .filter((m) => m.id && !m.hidden && !/(mini|spark)/i.test(m.id));
  if (!eligible.length) return undefined;
  eligible.sort(
    (a, b) =>
      ver(b.id) - ver(a.id) ||
      Number(b.isDefault) - Number(a.isDefault) ||
      a.id.length - b.id.length,
  );
  return eligible[0].id;
}
