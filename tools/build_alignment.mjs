#!/usr/bin/env node
/**
 * Build a JP-box -> EN-box alignment from the harvested anchors.  →  github issue #4
 *
 * THE METHOD (docs/WA2_INSERTION_MODEL.md prescribes it; the anchors make it possible)
 *   Take two consecutive anchors in a block, A=(en1,jp1) and B=(en2,jp2):
 *     * if (en2-en1) == (jp2-jp1) the stretch between them has no insertion or deletion, so
 *       every box in it maps 1:1. This is SAFE, not a guess.
 *     * if they differ, an edit lies inside and we cannot say where. But the disagreement is
 *       usually tiny (median 1), so the true target is still within a known radius of the linear
 *       estimate. That is reported as a BOUNDED range rather than thrown away — narrowing a
 *       candidate window from +-16 to +-1 is most of the value.
 *   Extrapolating past the outermost anchors of a block is marked separately and trusted least.
 *
 * WHY PER BLOCK
 *   Blocks are separate event files. An alignment must never run across a block boundary, so
 *   anchors, interpolation and extrapolation are all confined within a block.
 *
 * HONEST ACCURACY
 *   --holdout hides a share of the anchors, rebuilds from the rest, and reports how often the map
 *   predicts the hidden ones. That is a real out-of-sample number, not a restatement of the input.
 *   The figure to beat is the existing aligner's ~38% within +-1.
 *
 * USAGE
 *   node tools/build_alignment.mjs
 *   node tools/build_alignment.mjs --holdout 0.2
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
const ANCHORS = arg("--anchors", path.join(ROOT, "data/jp_en_anchors.json"));
const CONFIRMED = arg("--confirmed", path.join(ROOT, "data/confirmed_anchors.json"));
const OUT = arg("--out", path.join(ROOT, "data/jp_en_alignment.json"));
const NBLK = 120;

const readRegion = (p, disc) => {
  const s = C.rawSpan(disc), fd = fs.openSync(p, "r"), b = Buffer.alloc(s.len);
  fs.readSync(fd, b, 0, s.len, s.start); fs.closeSync(fd);
  return C.rawToUser(new Uint8Array(b), disc.size);
};

/** ordered box lists, and where each block's boxes start/end in them */
function boxIndex() {
  J.init(JSON.parse(fs.readFileSync(path.join(ROOT, "web/data/jp_tables.json"), "utf8")));
  const jd = readRegion(path.join(ROOT, "Game Files/JP/Wild Arms - 2nd Ignition (Japan) (Disc 1)/Wild Arms - 2nd Ignition (Japan) (Disc 1).bin"), C.DISCS.jp);
  const ud = readRegion(path.join(ROOT, "Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin"), C.DISCS.en);
  const jp = [], en = [], jpRange = {}, enRange = {};
  for (let blk = 0; blk < NBLK; blk++) {
    jpRange[blk] = [jp.length, 0];
    for (const b of J.jpBoxes(jd, blk)) jp.push({ blk, text: b.text });
    jpRange[blk][1] = jp.length;
    enRange[blk] = [en.length, 0];
    const lo = blk * C.DISCS.en.blk, hi = lo + C.DISCS.en.blk;
    for (const ch of C.walkChunks(ud, lo, hi)) ch.subs.forEach((sub, si) => {
      if (!ch.good[si]) return;
      const p = C.parseSub(sub, false), l = C.decodeEnLossy(sub, false);
      en.push({ blk, key: `${blk}:${ch.off}:${si}`, text: p.raw ? l.text : p.text });
    });
    enRange[blk][1] = en.length;
  }
  return { jp, en, jpRange, enRange };
}

/**
 * @returns Map en_index -> { jp, radius, tier }
 *   tier: "anchor" exact | "bracket" 1:1 between agreeing anchors | "bounded" inside a
 *         disagreeing bracket, jp is the linear estimate and radius its uncertainty |
 *         "edge" extrapolated past the block's outermost anchor
 */
function buildMap(anchors, enRange, jpRange) {
  const byBlk = new Map();
  for (const a of anchors) {
    if (!byBlk.has(a.blk)) byBlk.set(a.blk, []);
    byBlk.get(a.blk).push(a);
  }
  const map = new Map();
  for (const [blk, list] of byBlk) {
    list.sort((x, y) => x.en - y.en);
    for (const a of list) map.set(a.en, { jp: a.jp, radius: 0, tier: "anchor" });
    for (let i = 0; i + 1 < list.length; i++) {
      const A = list[i], B = list[i + 1];
      const de = B.en - A.en, dj = B.jp - A.jp;
      const slack = Math.abs(de - dj);
      for (let e = A.en + 1; e < B.en; e++) {
        const frac = (e - A.en) / de;
        const est = slack === 0 ? A.jp + (e - A.en) : Math.round(A.jp + frac * dj);
        if (!map.has(e)) map.set(e, { jp: est, radius: slack, tier: slack === 0 ? "bracket" : "bounded" });
      }
    }
    // extrapolate to the block edges using the nearest anchor's offset
    const [eLo, eHi] = enRange[blk], [jLo, jHi] = jpRange[blk];
    const first = list[0], last = list[list.length - 1];
    for (let e = eLo; e < first.en; e++) {
      const est = first.jp - (first.en - e);
      if (est >= jLo && !map.has(e)) map.set(e, { jp: est, radius: 2, tier: "edge" });
    }
    for (let e = last.en + 1; e < eHi; e++) {
      const est = last.jp + (e - last.en);
      if (est < jHi && !map.has(e)) map.set(e, { jp: est, radius: 2, tier: "edge" });
    }
  }
  return map;
}

function main() {
  const data = JSON.parse(fs.readFileSync(ANCHORS, "utf8"));
  const { jp, en, jpRange, enRange } = boxIndex();
  const enKeyIdx = new Map(en.map((b, i) => [b.key, i]));

  // Human confirmations outrank everything: a translator saying "this JP box is the source of
  // this EN box" is the strongest evidence available. An anchor also splits its bracket in two,
  // which spills over into neighbours — but only modestly. MEASURED by removing 200 anchors and
  // feeding them back: +244 exact boxes, i.e. 1.22 per confirmation. Plan for roughly one
  // confirmation per box you need mapped; do not expect a stretch to fall to a single pick.
  let confirmed = [];
  if (fs.existsSync(CONFIRMED)) {
    // Tolerate an empty or malformed file rather than dying: this path is optional, and a broken
    // confirmations file must not take the whole alignment down.
    let raw = null;
    try { raw = JSON.parse(fs.readFileSync(CONFIRMED, "utf8") || "{}"); }
    catch (e) { console.error(`warning: ignoring ${path.basename(CONFIRMED)} — ${e.message}`); raw = {}; }
    for (const c of (raw && raw.confirmations) || []) {
      const ei = enKeyIdx.get(c.en_key);
      const ji = jpRange[c.jp_blk] ? jpRange[c.jp_blk][0] + c.jp_ord : undefined;
      if (ei === undefined || ji === undefined || !jp[ji]) continue;
      confirmed.push({ en: ei, jp: ji, blk: en[ei].blk, key: c.en_key, human: true });
    }
  }
  // A human confirmation replaces any harvested anchor on the same EN box.
  const humanEn = new Set(confirmed.map((c) => c.en));
  const all = [...data.anchors.filter((a) => !humanEn.has(a.en)), ...confirmed];
  all.sort((a, b) => a.en - b.en);
  if (confirmed.length) console.log(`merged ${confirmed.length} human confirmation(s) from ${path.basename(CONFIRMED)}`);

  if (argv.includes("--holdout")) {
    const frac = +arg("--holdout", 0.2);
    // deterministic split — every 1/frac-th anchor is hidden
    const step = Math.max(2, Math.round(1 / frac));
    const train = all.filter((_, i) => i % step !== 0);
    const test = all.filter((_, i) => i % step === 0);
    const map = buildMap(train, enRange, jpRange);
    let n = 0, exact = 0, within1 = 0, within3 = 0, inRadius = 0, uncovered = 0;
    const byTier = {};
    for (const t of test) {
      const m = map.get(t.en);
      if (!m) { uncovered++; continue; }
      n++;
      const d = Math.abs(m.jp - t.jp);
      byTier[m.tier] = byTier[m.tier] || { n: 0, exact: 0, w1: 0 };
      byTier[m.tier].n++;
      if (d === 0) { exact++; byTier[m.tier].exact++; }
      if (d <= 1) { within1++; byTier[m.tier].w1++; }
      if (d <= 3) within3++;
      if (d <= Math.max(m.radius, 0)) inRadius++;
    }
    console.log(`HOLD-OUT: trained on ${train.length} anchors, testing ${test.length} hidden ones`);
    console.log(`  predicted (covered by the map): ${n}   uncovered: ${uncovered}`);
    console.log(`  exact          : ${exact} (${(exact / n * 100).toFixed(1)}%)`);
    console.log(`  within +-1     : ${within1} (${(within1 / n * 100).toFixed(1)}%)`);
    console.log(`  within +-3     : ${within3} (${(within3 / n * 100).toFixed(1)}%)`);
    console.log(`  inside the stated radius: ${inRadius} (${(inRadius / n * 100).toFixed(1)}%)  <- is the uncertainty honest?`);
    console.log(`\n  by tier:`);
    for (const [k, v] of Object.entries(byTier))
      console.log(`    ${k.padEnd(8)} n=${String(v.n).padStart(4)}  exact ${(v.exact / v.n * 100).toFixed(1)}%  within+-1 ${(v.w1 / v.n * 100).toFixed(1)}%`);
    console.log(`\n  the aligner this replaces scores ~38% within +-1`);
    return;
  }

  const map = buildMap(all, enRange, jpRange);
  const tiers = {};
  for (const v of map.values()) tiers[v.tier] = (tiers[v.tier] || 0) + 1;
  // Emit stable identities, not array positions: an EN box by its `blk:off:sub` key, and a JP box
  // by (block, ordinal within block). The editor recomputes those from the discs; it cannot
  // safely reconstruct a global index, and a confirmation must survive an extractor change.
  const out = { version: 1,
    what: "JP-box -> EN-box alignment interpolated from verified anchors (issue #4)",
    tiers: { anchor: "exact, harvested from the translation corpus",
             bracket: "between two anchors that agree on offset: 1:1, safe",
             bounded: "inside a disagreeing bracket: jp is a linear estimate, radius is the uncertainty",
             edge: "extrapolated past a block's outermost anchor; trust least" },
    counts: { ...tiers, en_boxes: en.length, jp_boxes: jp.length, covered: map.size },
    map: Object.fromEntries([...map].map(([e, v]) => {
      const jb = jp[v.jp];
      return [en[e].key, [jb ? jb.blk : -1, jb ? v.jp - jpRange[jb.blk][0] : -1, v.radius, v.tier[0]]];
    })) };
  fs.writeFileSync(OUT, JSON.stringify(out));
  console.log(`EN boxes ${en.length.toLocaleString()}   JP boxes ${jp.length.toLocaleString()}`);
  console.log(`\naligned EN boxes: ${map.size.toLocaleString()} (${(map.size / en.length * 100).toFixed(1)}% of the disc)`);
  for (const [k, v] of Object.entries(tiers)) console.log(`   ${k.padEnd(8)} ${v.toLocaleString()}`);
  console.log(`\nwrote ${path.relative(ROOT, OUT)}`);
}
main();
