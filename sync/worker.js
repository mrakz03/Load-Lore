// Load Lore sync: keeps a copy of a user's handloads, favorite loads and prices under a sync code,
// so the web site on different devices can share them. No accounts: the code
// (12 random letters / digits, about 59 bits) is the only key, so it works like a password.
// Only a SHA-256 hash of the code is stored, never the code itself.
//
//   POST   /v1/sync   {data}       -> 201 {code, rev}   a new code holding data
//   GET    /v1/sync                -> {rev, data}       Authorization: Bearer <code>
//   PUT    /v1/sync   {rev, data}  -> {rev}             only if rev is still the stored one, else
//                                     409 {rev, data}  (the client merges and tries again)
//   DELETE /v1/sync                -> 204               removes the stored copy
//
// Limits: 1 MB of data per code, 60 requests a minute per address (LIMITER), 5 new codes a minute
// per address (NEW_LIMITER). Copies nobody has opened for IDLE_DAYS are removed by the daily cron.

const MAX_BYTES = 1_000_000;
const IDLE_DAYS = 730;
const ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ";   // no 0/O, 1/I/L, U: easy to read and type
const CODE_LEN = 12;

const CORS = {
  "Access-Control-Allow-Origin": "*",   // no cookies: the code in the header is the only key
  "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
  "Access-Control-Allow-Headers": "Authorization, Content-Type",
  "Access-Control-Max-Age": "86400",
};
const json = (body, status = 200) => new Response(body == null ? null : JSON.stringify(body), {
  status, headers: Object.assign({ "Content-Type": "application/json", "Cache-Control": "no-store" }, CORS),
});
const fail = (status, error) => json({ error }, status);

function newCode() {
  const out = [];
  while (out.length < CODE_LEN) {
    for (const b of crypto.getRandomValues(new Uint8Array(32))) {
      if (b < 240 && out.length < CODE_LEN) out.push(ALPHABET[b % 30]);   // 240 = 8 x 30: no bias
    }
  }
  return out.join("");
}
// "k7q4-mz8p-x2rt" -> "K7Q4MZ8PX2RT"; anything that can't be a code -> null
function cleanCode(s) {
  const c = String(s || "").toUpperCase().replace(/[\s-]/g, "");
  return c.length === CODE_LEN && [...c].every(ch => ALPHABET.includes(ch)) ? c : null;
}
async function hashOf(code) {
  const d = await crypto.subtle.digest("SHA-256", new TextEncoder().encode("load-lore-sync:" + code));
  return [...new Uint8Array(d)].map(b => b.toString(16).padStart(2, "0")).join("");
}
async function limited(limiter, key) {
  if (!limiter) return false;   // no binding (local tests): no limit
  try { return !(await limiter.limit({ key })).success; } catch (e) { return false; }
}
// the request's {data} (and rev), checked for size and shape; a string -> an error message
async function readBody(req) {
  const text = await req.text();
  if (text.length > MAX_BYTES + 200) return "Too much data (the limit is 1 MB).";
  let body;
  try { body = JSON.parse(text); } catch (e) { return "Not JSON."; }
  if (!body || typeof body !== "object" || !body.data || typeof body.data !== "object" || Array.isArray(body.data))
    return "Missing data.";
  const data = JSON.stringify(body.data);
  if (data.length > MAX_BYTES) return "Too much data (the limit is 1 MB).";
  return { data, rev: Number.isInteger(body.rev) ? body.rev : null };
}

export default {
  async fetch(req, env) {
    if (req.method === "OPTIONS") return new Response(null, { status: 204, headers: CORS });
    const url = new URL(req.url);
    if (url.pathname === "/" && req.method === "GET") return new Response("Load Lore sync\n", { headers: CORS });
    if (url.pathname !== "/v1/sync") return fail(404, "Not found.");
    const ip = req.headers.get("CF-Connecting-IP") || "local";
    if (await limited(env.LIMITER, ip)) return fail(429, "Too many requests. Try again in a minute.");
    const now = Date.now();

    if (req.method === "POST") {
      if (await limited(env.NEW_LIMITER, ip)) return fail(429, "Too many new codes. Try again in a minute.");
      const b = await readBody(req);
      if (typeof b === "string") return fail(400, b);
      for (let i = 0; i < 5; i++) {   // a clash is next to impossible; try again if it happens
        const code = newCode();
        const r = await env.DB.prepare(
          "INSERT OR IGNORE INTO sync (id, rev, data, created, updated, seen) VALUES (?, 1, ?, ?, ?, ?)"
        ).bind(await hashOf(code), b.data, now, now, now).run();
        if (r.meta.changes) return json({ code, rev: 1 }, 201);
      }
      return fail(500, "Couldn't make a code. Try again.");
    }

    const auth = req.headers.get("Authorization") || "";
    const code = cleanCode(auth.replace(/^Bearer\s+/i, ""));
    if (!code) return fail(401, "That isn't a sync code.");
    const id = await hashOf(code);

    if (req.method === "GET") {
      const row = await env.DB.prepare("SELECT rev, data, seen FROM sync WHERE id = ?").bind(id).first();
      if (!row) return fail(404, "No data is saved under that code.");
      if (now - row.seen > 86400000)   // note the visit at most once a day (keeps writes low)
        await env.DB.prepare("UPDATE sync SET seen = ? WHERE id = ?").bind(now, id).run();
      return json({ rev: row.rev, data: JSON.parse(row.data) });
    }
    if (req.method === "PUT") {
      const b = await readBody(req);
      if (typeof b === "string") return fail(400, b);
      if (b.rev == null) return fail(400, "Missing rev.");
      const r = await env.DB.prepare(
        "UPDATE sync SET data = ?, rev = rev + 1, updated = ?, seen = ? WHERE id = ? AND rev = ?"
      ).bind(b.data, now, now, id, b.rev).run();
      if (r.meta.changes) return json({ rev: b.rev + 1 });
      const row = await env.DB.prepare("SELECT rev, data FROM sync WHERE id = ?").bind(id).first();
      if (!row) return fail(404, "No data is saved under that code.");
      return json({ rev: row.rev, data: JSON.parse(row.data) }, 409);   // changed elsewhere: merge, retry
    }
    if (req.method === "DELETE") {
      await env.DB.prepare("DELETE FROM sync WHERE id = ?").bind(id).run();
      return json(null, 204);
    }
    return fail(405, "Method not allowed.");
  },
  // daily: remove copies nobody has opened in IDLE_DAYS
  async scheduled(event, env) {
    await env.DB.prepare("DELETE FROM sync WHERE seen < ?").bind(Date.now() - IDLE_DAYS * 86400000).run();
  },
};
