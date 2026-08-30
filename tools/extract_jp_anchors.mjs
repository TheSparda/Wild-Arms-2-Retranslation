#!/usr/bin/env node
/**
 * Recover verified JP-box <-> EN-box anchors from the project's own translation corpus.
 *   feeds #4 (aligner) and #10 (placement)
 *
 * WHY THIS EXISTS
 *   The aligner corroborates only ~3.5% of its JP<->EN pairings (550 curated glossary terms plus
 *   9 shared digit runs). Meanwhile the FINAL files hold years of human work in which a person
 *   sat with a JP line and an EN slot together. That pairing was never harvested.
 *
 * HOW A ROW BECOMES AN ANCHOR
 *   1. The row's JP text is located EXACTLY in the JP disc -> a JP box index. Not fuzzy: the JP
 *      in the DB was decoded from that disc, so it matches on whitespace-stripped equality.
 *   2. The row's EN key resolves to an EN box index (established by tools/migrate_db_to_boxes.mjs,
 *      which only emits rows whose English matches the disc).
 *   3. The row's placement is `verified` — its human literal describes that EN box, so the JP
 *      really is the source of that English. Without this the pair would just re-assert whatever
 *      the old aligner guessed, which is the thing being replaced.
 *   Steps 1 and 2 are exact; step 3 is what makes the pair trustworthy rather than circular.
 *
 * MONOTONICITY
 *   A correct alignment is order-preserving, so anchors are filtered to their longest strictly
 *   increasing subsequence. Anchors dropped by that filter are contradictions and are reported —
 *   they are leads, not noise to hide.
 *
 * USAGE
 *   node tools/extract_jp_anchors.mjs [--in data/migrated_corpus.rekeyed.json] [--out data/jp_en_anchors.json]
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
const IN  = arg("--in",  path.join(ROOT, "data/migrated_corpus.rekeyed.json"));
const OUT = arg("--out", path.join(ROOT, "data/jp_en_anchors.json"));
const DB  = path.join(ROOT, "data/script/wa2_db.json");
const EN_BIN = path.join(ROOT, "Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin");
const JP_BIN = path.join(ROOT, "Game Files/JP/Wild Arms - 2nd Ignition (Japan) (Disc 1)/Wild Arms - 2nd Ignition (Japan) (Disc 1).bin");
const NBLK = 120;

const readRegion = (p, disc) => {
  if (!fs.existsSync(p)) { console.error(`missing ${p}`); process.exit(1); }
  const s = C.rawSpan(disc), fd = fs.openSync(p, "r"), b = Buffer.alloc(s.len);
  fs.readSync(fd, b, 0, s.len, s.start); fs.closeSync(fd);
  return C.rawToUser(new Uint8Array(b), disc.size);
};
/**
 * Canonicalise decoded JP so a match survives DECODER CHANGES.
 *
 * The DB's `jp` was decoded when each FINAL file was written; the disc side is decoded now, and
 * the decoder is actively improving. Resolving the f0xx ellipsis run to "…" and gating Shift-JIS
 * trail bytes moved the JP box count 19,904 -> 19,919 and cost 107 anchors — purely because
 * stored and fresh text stopped being byte-equal. Nothing about the script itself changed.
 *
 * So the old spelling is TRANSLATED into the new one rather than either being deleted. Two
 * alternatives were tried and measured, both worse:
 *   - deleting ellipsis entirely: collapses lines that differ only in ellipsis LENGTH into
 *     collisions, and ambiguity rose from 1,260 to 1,435;
 *   - also stripping 。、！？: erases what distinguishes short lines, no better.
 * Mapping each ellipsis cell to one "…" preserves its length, so the texts stay distinguishable
 * and both sides agree. Still-unresolved codes and layout are dropped from both.
 */
const norm = (s) => String(s || "")
  .replace(/<f04[012]>/gi, "…")                                     // ellipsis run, old -> new
  .replace(/<f045>/gi, "ー")                                        // long vowel, old -> new
  .replace(/<b:[0-9a-f]{4}>|<[0-9a-f]{4}>|\[[0-9a-f]{2}\]/gi, "")   // still-unresolved codes
  .replace(/[\s／\/]/g, "");                                        // layout

function main() {
  J.init(JSON.parse(fs.readFileSync(path.join(ROOT, "web/data/jp_tables.json"), "utf8")));
  const jd = readRegion(JP_BIN, C.DISCS.jp), ud = readRegion(EN_BIN, C.DISCS.en);

  const jpBoxes = [];
  for (let blk = 0; blk < NBLK; blk++) for (const b of J.jpBoxes(jd, blk)) jpBoxes.push({ blk, text: b.text });
  const enBoxes = [], enKey = new Map();
  for (let blk = 0; blk < NBLK; blk++) {
    const lo = blk * C.DISCS.en.blk, hi = lo + C.DISCS.en.blk;
    for (const ch of C.walkChunks(ud, lo, hi)) ch.subs.forEach((sub, si) => {
      if (!ch.good[si]) return;
      const p = C.parseSub(sub, false), l = C.decodeEnLossy(sub, false);
      enKey.set(`${blk}:${ch.off}:${si}`, enBoxes.length);
      enBoxes.push({ blk, key: `${blk}:${ch.off}:${si}`, en: p.raw ? l.text : p.text });
    });
  }
  // A JP text that occurs more than once cannot identify a box, so ambiguous keys are dropped.
  const seen = new Map();
  jpBoxes.forEach((b, i) => { const k = norm(b.text); if (k.length >= 6) seen.set(k, seen.has(k) ? -1 : i); });

  const db = new Map(JSON.parse(fs.readFileSync(DB, "utf8")).rows.map((r) => [r.us, r]));
  const rows = JSON.parse(fs.readFileSync(IN, "utf8")).rows;
  const S = (r, k) => (typeof r?.[k] === "string" ? r[k] : "");

  const cand = [];
  let noJp = 0, notLocated = 0, ambiguous = 0, notVerified = 0;
  for (const row of rows) {
    const jp = S(db.get(row.us), "jp");
    if (!jp) { noJp++; continue; }
    const ji = seen.get(norm(jp));
    if (ji === undefined) { notLocated++; continue; }
    if (ji === -1) { ambiguous++; continue; }
    if (row.placement !== "verified") { notVerified++; continue; }
    const ei = enKey.get(row.key);
    if (ei === undefined) continue;
    cand.push({ jp: ji, en: ei, blk: row.blk, key: row.key, us: row.us });
  }

  // longest strictly increasing subsequence on jp, ordered by en
  cand.sort((a, b) => a.en - b.en || a.jp - b.jp);
  const tails = [], tailIdx = [], prev = new Array(cand.length).fill(-1);
  for (let i = 0; i < cand.length; i++) {
    const v = cand[i].jp;
    let lo = 0, hi = tails.length;
    while (lo < hi) { const m = (lo + hi) >> 1; if (tails[m] < v) lo = m + 1; else hi = m; }
    tails[lo] = v; tailIdx[lo] = i;
    prev[i] = lo > 0 ? tailIdx[lo - 1] : -1;
  }
  const keep = new Set();
  for (let i = tailIdx.length ? tailIdx[tailIdx.length - 1] : -1; i >= 0; i = prev[i]) keep.add(i);
  const anchors = cand.filter((_, i) => keep.has(i));
  const contradictions = cand.filter((_, i) => !keep.has(i));

  const perBlk = {};
  for (const a of anchors) perBlk[a.blk] = (perBlk[a.blk] || 0) + 1;
  const covered = Object.keys(perBlk).length;

  fs.writeFileSync(OUT, JSON.stringify({
    version: 1,
    what: "verified JP-box <-> EN-box anchors recovered from the project's translation corpus",
    how: "row JP located exactly in the JP disc + row placement verified + monotonic (LIS) filter",
    caveat: "Indices are positions in the ordered good-box lists produced by wa2-jp.jpBoxes and "
          + "wa2-core.walkChunks over disc 1. Regenerate if either extractor changes.",
    counts: { anchors: anchors.length, contradictions: contradictions.length,
              blocks_covered: covered, blocks_total: NBLK,
              jp_boxes: jpBoxes.length, en_boxes: enBoxes.length },
    anchors, contradictions,
  }, null, 1));

  console.log(`JP boxes ${jpBoxes.length.toLocaleString()}   EN boxes ${enBoxes.length.toLocaleString()}`);
  console.log(`\ncorpus rows examined: ${rows.length.toLocaleString()}`);
  console.log(`  no JP text            : ${noJp}`);
  console.log(`  JP not found on disc  : ${notLocated}`);
  console.log(`  JP text ambiguous     : ${ambiguous}`);
  console.log(`  placement not verified: ${notVerified}`);
  console.log(`\ncandidate pairs: ${cand.length.toLocaleString()}`);
  console.log(`ANCHORS (monotonic)  : ${anchors.length.toLocaleString()}`);
  console.log(`contradictions dropped: ${contradictions.length.toLocaleString()}  (reported, not hidden)`);
  console.log(`\nblocks covered: ${covered}/${NBLK}`);
  console.log(`for comparison, the aligner corroborates 550 pairs by glossary + 9 by digit run`);
  console.log(`\nwrote ${path.relative(ROOT, OUT)}`);
}
main();
