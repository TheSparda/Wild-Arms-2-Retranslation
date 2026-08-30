#!/usr/bin/env node
/**
 * Place translations that no English-side evidence could reach, using the JP alignment. → #10
 *
 * THE GAP THIS FILLS
 *   tools/rekey_placement.mjs verifies placement by comparing a row's human literal against the
 *   box's English. Rows without a literal (or whose retranslation matched nothing) were left
 *   `unknown` — about 2,400 of them, over a third of the corpus.
 *
 * THE IDEA
 *   Those rows still carry their Japanese. Locate that JP exactly in the JP disc, then ask
 *   data/jp_en_alignment.json which EN box that JP box corresponds to. No English gloss needed,
 *   and no cross-language guessing: the alignment came from anchors the corpus itself verified.
 *
 * TRUST
 *   The alignment reports a tier and a radius per box, and hold-out testing gives each tier a
 *   measured accuracy (bracket ~100% within +-1, bounded ~95%, edge ~75%). Only `anchor` and
 *   `bracket` targets are applied by default, because those are the tiers that earn it.
 *   Everything else is recorded as a suggestion. A translation is never moved onto a read-only
 *   box or one already claimed.
 *
 * USAGE
 *   node tools/place_by_alignment.mjs [--tiers anchor,bracket] [--out ...]
 */
import { createRequire } from "module";
import { fileURLToPath } from "url";
import fs from "fs";
import path from "path";
const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const C = require(path.join(ROOT, "web/wa2-core.js"));
const J = require(path.join(ROOT, "web/wa2-jp.js"));

const argv = process.argv.slice(2);
const arg = (k, d) => (argv.includes(k) ? argv[argv.indexOf(k) + 1] : d);
const IN    = arg("--in", path.join(ROOT, "data/migrated_corpus.rekeyed.json"));
const ALIGN = arg("--align", path.join(ROOT, "data/jp_en_alignment.json"));
const OUT   = arg("--out", path.join(ROOT, "data/migrated_corpus.placed.json"));
const DB    = path.join(ROOT, "data/script/wa2_db.json");
const TIERS = new Set(arg("--tiers", "anchor,bracket").split(",").map((s) => s.trim()[0]));
const NBLK = 120;

const readRegion = (p, disc) => {
  const s = C.rawSpan(disc), fd = fs.openSync(p, "r"), b = Buffer.alloc(s.len);
  fs.readSync(fd, b, 0, s.len, s.start); fs.closeSync(fd);
  return C.rawToUser(new Uint8Array(b), disc.size);
};
const norm = (s) => String(s || "").replace(/\s+/g, "").replace(/[／\/]/g, "");
// English-to-English overlap, used to CROSS-CHECK an alignment placement against the row's
// human literal. Two independent signals agreeing is the bar; the alignment alone is not enough.
const WORD = /[a-z']{4,}/g;
const toks = (s) => new Set((String(s || "").toLowerCase().match(WORD) || []));
function sim(a, b) {
  const A = toks(a), B = toks(b);
  if (!A.size || !B.size) return 0;
  let n = 0; for (const x of A) if (B.has(x)) n++;
  return n / Math.min(A.size, B.size);
}
const LIT_MIN = 0.34;

function main() {
  J.init(JSON.parse(fs.readFileSync(path.join(ROOT, "web/data/jp_tables.json"), "utf8")));
  const jd = readRegion(path.join(ROOT, "Game Files/JP/Wild Arms - 2nd Ignition (Japan) (Disc 1)/Wild Arms - 2nd Ignition (Japan) (Disc 1).bin"), C.DISCS.jp);
  const ud = readRegion(path.join(ROOT, "Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin"), C.DISCS.en);

  const jpBoxes = [];
  for (let blk = 0; blk < NBLK; blk++) for (const b of J.jpBoxes(jd, blk)) jpBoxes.push({ blk, text: b.text });
  const enBoxes = [], enIdx = new Map();
  for (let blk = 0; blk < NBLK; blk++) {
    const lo = blk * C.DISCS.en.blk, hi = lo + C.DISCS.en.blk;
    for (const ch of C.walkChunks(ud, lo, hi)) ch.subs.forEach((sub, si) => {
      if (!ch.good[si]) return;
      const p = C.parseSub(sub, false), l = C.decodeEnLossy(sub, false);
      enIdx.set(`${blk}:${ch.off}:${si}`, enBoxes.length);
      enBoxes.push({ blk, key: `${blk}:${ch.off}:${si}`, en: p.raw ? l.text : p.text,
                     editable: !p.raw, cap: ch.cap, chunk: `${blk}:${ch.off}`,
                     panel: l.text.replace(/^[({ ]+/, "").startsWith("*") });
    });
  }
  // unique JP text -> its box index (duplicated text cannot identify a box)
  const jpLoc = new Map();
  jpBoxes.forEach((b, i) => { const k = norm(b.text); if (k.length >= 6) jpLoc.set(k, jpLoc.has(k) ? -1 : i); });
  // Fallback: build_db truncates its decoded JP (400 chars) and re-joins lines, so ~1,100 rows
  // fail exact equality despite being real lines. A unique 12-character prefix identifies the box
  // for 534 of them; prefixes matching several boxes stay unresolved rather than being guessed.
  const jpPfx = new Map();
  jpBoxes.forEach((b, i) => {
    const k = norm(b.text).slice(0, 12);
    if (k.length >= 8) { if (!jpPfx.has(k)) jpPfx.set(k, []); jpPfx.get(k).push(i); }
  });
  const locate = (jp) => {
    const n = norm(jp);
    const e = jpLoc.get(n);
    if (e !== undefined && e !== -1) return { i: e, how: "exact" };
    if (e === -1) return { i: -1, how: "ambiguous" };
    const c = jpPfx.get(n.slice(0, 12));
    if (c && c.length === 1) return { i: c[0], how: "prefix" };
    if (c && c.length > 1) return { i: -1, how: "ambiguous" };
    return { i: undefined, how: "absent" };
  };

  const align = JSON.parse(fs.readFileSync(ALIGN, "utf8")).map;
  // The alignment is keyed by EN box key, with the JP box given as (block, ordinal) — stable
  // identities rather than array positions. Rebuild the global JP index to match.
  const jpBase = {};
  { let n = 0; for (let blk = 0; blk < NBLK; blk++) { jpBase[blk] = n; n += J.jpBoxes(jd, blk).length; } }
  // invert: jp box -> the EN boxes claiming it, keeping the best tier
  const RANK = { a: 3, b: 2, o: 1, e: 0 };            // anchor, bracket, bounded, edge
  const jpToEn = new Map();
  for (const [enKey, [jblk, jord, r, t]] of Object.entries(align)) {
    if (jblk < 0) continue;
    const j = jpBase[jblk] + jord;
    const e = enIdx.get(enKey);
    if (e === undefined) continue;
    const cur = jpToEn.get(j);
    if (!cur || RANK[t] > RANK[cur.t]) jpToEn.set(j, { en: e, r, t });
    else if (cur && RANK[t] === RANK[cur.t] && cur.en !== e) cur.ambiguous = true;
  }

  const db = new Map(JSON.parse(fs.readFileSync(DB, "utf8")).rows.map((r) => [r.us, r]));
  const rows = JSON.parse(fs.readFileSync(IN, "utf8")).rows;
  const S = (r, k) => (typeof r?.[k] === "string" ? r[k] : "");

  const taken = new Set(rows.filter((r) => r.placement === "verified").map((r) => enIdx.get(r.key)));
  let placed = 0, confirmed = 0, suggested = 0, noJp = 0, notLocated = 0, ambiguous = 0,
      noAlign = 0, occupied = 0, readonly = 0, litRejected = 0, litSilent = 0;
  const out = [];
  for (const row of rows) {
    if (row.placement === "verified") { out.push(row); continue; }
    const jp = S(db.get(row.us), "jp");
    if (!jp) { noJp++; out.push(row); continue; }
    const loc = locate(jp);
    const ji = loc.i;
    if (ji === undefined) { notLocated++; out.push(row); continue; }
    if (ji === -1) { ambiguous++; out.push(row); continue; }
    const hit = jpToEn.get(ji);
    if (!hit || hit.ambiguous) { noAlign++; out.push(row); continue; }
    const tgt = enBoxes[hit.en];
    if (!tgt) { noAlign++; out.push(row); continue; }

    // CROSS-CHECK: the human literal vetoes the alignment — but ONLY where the literal has an
    // opinion. Measured: of 1,037 placements the literal rejected outright, 719 (69%) had a
    // literal that matches NO box within +-20. Those are lines the localization rewrote past
    // recognition; the literal knows nothing there and must not veto. The remaining 31% are
    // genuine disagreements, and a human's reading of the Japanese outranks an interpolation.
    const lit = S(db.get(row.us), "lit").trim();
    const tgtBox = enBoxes[hit.en];
    let litQuiet = false;
    if (lit && tgtBox && sim(lit, tgtBox.en) < LIT_MIN) {
      const here = enIdx.get(row.key);
      let bestElsewhere = 0;
      if (here !== undefined)
        for (let d = -20; d <= 20; d++) {
          const j = here + d;
          if (j >= 0 && j < enBoxes.length) bestElsewhere = Math.max(bestElsewhere, sim(lit, enBoxes[j].en));
        }
      if (bestElsewhere >= LIT_MIN) {          // the literal points somewhere else — it wins
        litRejected++;
        out.push({ ...row, suggest_key: tgtBox.key,
                   suggest_basis: "alignment points here but this row's literal describes a different box" });
        continue;
      }
      litSilent++;  litQuiet = true;             // literal has no opinion anywhere; alignment stands
    }
    const already = enIdx.get(row.key) === hit.en;
    const applyTier = TIERS.has(hit.t);
    if (already) {                                     // the alignment agrees with where it sits
      confirmed++;
      out.push({ ...row, placement: "verified", placed_by: `alignment:${hit.t}/${loc.how}`,
                 evidence: litQuiet ? "alignment-only (literal silent)" : (lit ? "alignment+literal" : "alignment-only (no literal)") });
      taken.add(hit.en);
      continue;
    }
    if (!applyTier) { suggested++; out.push({ ...row, suggest_key: tgt.key, suggest_basis: `alignment tier '${hit.t}' is below the apply threshold` }); continue; }
    if (!tgt.editable) { readonly++; out.push({ ...row, suggest_key: tgt.key, suggest_basis: "alignment target is a read-only box (#6)" }); continue; }
    if (taken.has(hit.en)) { occupied++; out.push({ ...row, suggest_key: tgt.key, suggest_basis: "alignment target already holds a verified translation" }); continue; }
    taken.add(hit.en);
    placed++;
    out.push({ ...row, key: tgt.key, blk: tgt.blk, off: +tgt.key.split(":")[1], sub: +tgt.key.split(":")[2],
               en: tgt.en, enDigest: C.digest(tgt.en), chunk: tgt.chunk, chunkBytes: tgt.cap,
               panel: tgt.panel, placement: "verified", placed_by: `alignment:${hit.t}/${loc.how}`,
               evidence: litQuiet ? "alignment-only (literal silent)" : (lit ? "alignment+literal" : "alignment-only (no literal)") });
  }

  const src = JSON.parse(fs.readFileSync(IN, "utf8"));
  fs.writeFileSync(OUT, JSON.stringify({ ...src, rows: out,
    notes: [...(src.notes || []), "Rows also placed via data/jp_en_alignment.json (issue #10/#4)."] }, null, 1));

  const before = rows.reduce((a, r) => (a[r.placement] = (a[r.placement] || 0) + 1, a), {});
  const after = out.reduce((a, r) => (a[r.placement] = (a[r.placement] || 0) + 1, a), {});
  console.log(`placement BEFORE: ${JSON.stringify(before)}`);
  console.log(`placement AFTER : ${JSON.stringify(after)}`);
  console.log(`\nvia alignment — moved ${placed}, confirmed in place ${confirmed}, suggested only ${suggested}`);
  console.log(`not reachable — no JP ${noJp}, JP not on disc ${notLocated}, JP text ambiguous ${ambiguous}, no alignment ${noAlign}`);
  console.log(`refused — literal names a different box ${litRejected}, target occupied ${occupied}, target read-only ${readonly}`);
  console.log(`literal had no opinion anywhere (alignment allowed to stand): ${litSilent}`);
  const ev = out.reduce((a, r) => (r.evidence ? (a[r.evidence] = (a[r.evidence] || 0) + 1) : 0, a), {});
  console.log(`\nevidence behind alignment placements:`);
  for (const [k, v] of Object.entries(ev)) console.log(`   ${k.padEnd(34)} ${v}`);
  console.log(`   (rows verified earlier by literal alone are unchanged and unlabelled)`);
  console.log(`\nwrote ${path.relative(ROOT, OUT)}`);
}
main();
