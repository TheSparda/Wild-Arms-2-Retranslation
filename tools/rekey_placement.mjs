#!/usr/bin/env node
/**
 * Re-key migrated translations onto the box they actually belong to.  →  github issue #10
 *
 * THE DEFECT
 *   tools/migrate_db_to_boxes.mjs re-keys faithfully: a translation lands on the box whose
 *   English matches the DB's English. But the DB's jp/lit/re were attached to each slot by the
 *   ALIGNER, which drifts — so a translation can be a correct rendering of the WRONG line.
 *   Only ~1,516 of 6,155 migrated rows were demonstrably on the right box.
 *
 * WHY IT IS FIXABLE
 *   `lit` is a human-written ENGLISH gloss of the Japanese, so "which box does this translation
 *   describe" is an English-to-English match, not the cross-language problem that makes the
 *   aligner hard. Where there is no literal, the retranslation itself is used as a weaker probe.
 *
 * WHY VITERBI AND NOT PER-ROW BEST MATCH
 *   The drift is not per-row noise, it is piecewise constant: measured, 222 runs of >=5
 *   consecutive rows share one offset and cover 3,062 rows, the longest being 55 rows at -6.
 *   Picking each row's best offset independently would scatter isolated rows onto spurious
 *   matches and would leave every evidence-free row unplaced. A Viterbi pass over offset states
 *   with a switch penalty prefers long runs, so a row with no evidence of its own INHERITS the
 *   offset of the run it sits in — which is the whole point.
 *
 * OFFSETS ARE IN BOXES ON DISC, not positions in the migrated array: untranslated and read-only
 * boxes sit between migrated rows, so "one slot over" is not "one array element over".
 *
 * USAGE
 *   node tools/rekey_placement.mjs [--in data/migrated_corpus.json] [--out ...] [--window 8]
 */
import { createRequire } from "module";
import { fileURLToPath } from "url";
import fs from "fs";
import path from "path";
const require = createRequire(import.meta.url);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const C = require(path.join(ROOT, "web/wa2-core.js"));

const argv = process.argv.slice(2);
const arg = (k, d) => (argv.includes(k) ? argv[argv.indexOf(k) + 1] : d);
const IN   = arg("--in",  path.join(ROOT, "data/migrated_corpus.json"));
const OUT  = arg("--out", path.join(ROOT, "data/migrated_corpus.rekeyed.json"));
const DB   = path.join(ROOT, "data/script/wa2_db.json");
const BIN  = path.join(ROOT, "Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin");
const WIN  = +arg("--window", 8);          // search +-WIN boxes
const SWITCH_PENALTY = +arg("--penalty", 0.55);
const NBLK = 120;

const WORD = /[a-z']{4,}/g;
const toks = (s) => new Set((String(s || "").toLowerCase().match(WORD) || []));
function sim(a, b) {
  const A = toks(a), B = toks(b);
  if (!A.size || !B.size) return 0;
  let n = 0; for (const x of A) if (B.has(x)) n++;
  return n / Math.min(A.size, B.size);
}

/** every good box on disc, in play order */
function allBoxes() {
  const span = C.rawSpan(C.DISCS.en);
  const fd = fs.openSync(BIN, "r");
  const buf = Buffer.alloc(span.len);
  fs.readSync(fd, buf, 0, span.len, span.start);
  fs.closeSync(fd);
  const ud = C.rawToUser(new Uint8Array(buf), C.DISCS.en.size);
  const out = [];
  for (let blk = 0; blk < NBLK; blk++) {
    const lo = blk * C.DISCS.en.blk, hi = lo + C.DISCS.en.blk;
    for (const ch of C.walkChunks(ud, lo, hi))
      ch.subs.forEach((sub, si) => {
        if (!ch.good[si]) return;
        const p = C.parseSub(sub, false), l = C.decodeEnLossy(sub, false);
        out.push({ key: `${blk}:${ch.off}:${si}`, blk, off: ch.off, sub: si,
                   en: p.raw ? l.text : p.text, editable: !p.raw,
                   cap: ch.cap, chunk: `${blk}:${ch.off}`,
                   panel: l.text.replace(/^[({ ]+/, "").startsWith("*") });
      });
  }
  return out;
}

function main() {
  const corpus = JSON.parse(fs.readFileSync(IN, "utf8"));
  const db = new Map(JSON.parse(fs.readFileSync(DB, "utf8")).rows.map((r) => [r.us, r]));
  const boxes = allBoxes();
  const boxIdx = new Map(boxes.map((b, i) => [b.key, i]));
  const str = (r, k) => (typeof r?.[k] === "string" ? r[k] : "");

  // migrated rows, in disc order, with their probe text
  const items = corpus.rows
    .map((row) => {
      const i = boxIdx.get(row.key);
      if (i === undefined) return null;
      const lit = str(db.get(row.us), "lit").trim();
      return { row, i, probe: lit || row.re, kind: lit ? "lit" : "re" };
    })
    .filter(Boolean)
    .sort((a, b) => a.i - b.i);

  // ---- Viterbi over offset states ----
  const offsets = [];
  for (let d = -WIN; d <= WIN; d++) offsets.push(d);
  const S = offsets.length;
  const emit = items.map((it) =>
    offsets.map((d) => {
      const j = it.i + d;
      if (j < 0 || j >= boxes.length) return -1;             // off the end: strongly discouraged
      const s = sim(it.probe, boxes[j].en);
      // a `re` probe is legitimately allowed to differ from the old localization, so trust it less
      return (it.kind === "lit" ? s : s * 0.75);
    }));
  const dp = Array.from({ length: items.length }, () => new Float64Array(S).fill(-Infinity));
  const bt = Array.from({ length: items.length }, () => new Int16Array(S));
  for (let s = 0; s < S; s++) dp[0][s] = emit[0][s] + (offsets[s] === 0 ? 0.08 : 0);  // mild prior on "already right"
  for (let t = 1; t < items.length; t++) {
    for (let s = 0; s < S; s++) {
      let best = -Infinity, bs = 0;
      for (let p = 0; p < S; p++) {
        const v = dp[t - 1][p] - (p === s ? 0 : SWITCH_PENALTY);
        if (v > best) { best = v; bs = p; }
      }
      dp[t][s] = best + emit[t][s] + (offsets[s] === 0 ? 0.08 : 0);
      bt[t][s] = bs;
    }
  }
  let s = 0;
  for (let k = 1; k < S; k++) if (dp[items.length - 1][k] > dp[items.length - 1][s]) s = k;
  const pathOff = new Array(items.length);
  for (let t = items.length - 1; t >= 0; t--) { pathOff[t] = offsets[s]; s = bt[t][s]; }

  // ---- decide which moves to apply: evidence at the RUN level ----
  // Three policies were tried. Moving every row Viterbi wants (hand-reading found many wrong).
  // Moving only rows with their own probe match (structurally incoherent — it strands the rest of
  // a genuinely shifted run and produced 453 collisions). What actually fits the data: the drift
  // is piecewise constant, so evidence AGGREGATES over a run. A 51-row run at +2 with 20 members
  // independently confirming +2 is not chance, and the unconfirmed members of that run are
  // shifted too. Measured: 133 non-zero runs (562 rows) have >=50% independent support and only
  // 12 runs (167 rows) fall under 25%.
  const MATCH_MIN = 0.34;
  const RUN_MIN_CONFIRM = +arg("--min-confirm", 2);      // absolute confirmations needed
  const RUN_MIN_FRAC    = +arg("--min-frac", 0.25);      // and this share of the run
  const APPLY_ALL = argv.includes("--apply-all");

  // segment the Viterbi path into constant-offset runs
  const runs = [];
  for (let a = 0, t = 1; t <= items.length; t++)
    if (t === items.length || pathOff[t] !== pathOff[a]) { runs.push({ off: pathOff[a], a, b: t }); a = t; }

  const runOf = new Array(items.length);
  const accepted = new Set();
  let acceptedRuns = 0, rejectedRuns = 0, rejectedRows = 0;
  for (const r of runs) {
    for (let t = r.a; t < r.b; t++) runOf[t] = r;
    if (r.off === 0) { r.ok = true; continue; }
    let confirm = 0;
    for (let t = r.a; t < r.b; t++) {
      const tgt = boxes[items[t].i + r.off];
      if (tgt && sim(items[t].probe, tgt.en) >= MATCH_MIN) confirm++;
    }
    r.confirm = confirm; r.n = r.b - r.a; r.frac = confirm / r.n;
    r.ok = APPLY_ALL || (confirm >= RUN_MIN_CONFIRM && r.frac >= RUN_MIN_FRAC);
    if (r.ok) { acceptedRuns++; for (let t = r.a; t < r.b; t++) accepted.add(t); }
    else { rejectedRuns++; rejectedRows += r.n; }
  }

  // ---- apply, refusing collisions ----
  const claim = new Map();                    // target box index -> item
  const moved = [], stayed = [], collided = [], blocked = [];
  const suggestions = new Map();
  items.forEach((it, t) => {
    let d = pathOff[t];
    if (d !== 0 && !accepted.has(t)) {
      const cand = boxes[it.i + d];
      const r = runOf[t];
      suggestions.set(it.row.key, { to: cand ? cand.key : null, by: d,
        why: `run of ${r.n} row(s) at offset ${d > 0 ? "+" : ""}${d} had only ${r.confirm} independent confirmation(s)` });
      d = 0;                                   // leave it where it is, record the hypothesis
    }
    const j = it.i + d;
    const tgt = boxes[j];
    if (!tgt) { blocked.push({ key: it.row.key, why: "target out of range" }); return; }
    if (!tgt.editable) { blocked.push({ key: it.row.key, to: tgt.key, why: "target box is read-only (#6)" }); return; }
    if (claim.has(j)) { collided.push({ key: it.row.key, to: tgt.key, with: claim.get(j).row.key }); return; }
    claim.set(j, it);
    (d === 0 ? stayed : moved).push({ from: it.row.key, to: tgt.key, by: d });
  });

  const outRows = [];
  // A refused row (collision, read-only target, out of range) must STAY WHERE IT WAS and be
  // flagged — dropping it would silently delete finished translation work.
  const claimed = new Set([...claim.values()].map((it) => it.row.key));
  for (const it of items) {
    if (claimed.has(it.row.key)) continue;
    outRows.push({ ...it.row, placement: "unresolved",
                   unresolved_why: (collided.find((c) => c.key === it.row.key) ? "target box already claimed by another translation"
                                  : (blocked.find((b) => b.key === it.row.key) || {}).why || "could not place") });
  }
  for (const [j, it] of claim) {
    const tgt = boxes[j];
    const score = sim(it.probe, tgt.en);
    outRows.push({
      ...it.row,
      key: tgt.key, blk: tgt.blk, off: tgt.off, sub: tgt.sub,
      en: tgt.en, enDigest: C.digest(tgt.en),
      chunk: tgt.chunk, chunkBytes: tgt.cap, panel: tgt.panel,
      placement: score >= MATCH_MIN ? "verified" : "unknown",
      moved_by: boxes[it.i].key === tgt.key ? 0 : pathOff[items.indexOf(it)],
      probe_kind: it.kind,
      ...(suggestions.has(it.row.key)
          ? { suggest_key: suggestions.get(it.row.key).to,
              suggest_by: suggestions.get(it.row.key).by,
              suggest_basis: suggestions.get(it.row.key).why }
          : {}),
    });
  }
  outRows.sort((a, b) => (a.blk - b.blk) || (a.off - b.off) || (a.sub - b.sub));

  // --verified-only: the subset whose placement is backed by its own probe matching its box.
  // Hand-reading says this tier is reliable and the inherited tier is roughly a coin flip, so
  // this is what should be translated against, reviewed, or shipped.
  let emitRows = outRows;
  if (argv.includes("--verified-only")) emitRows = outRows.filter((r) => r.placement === "verified");
  const out = { ...corpus, rows: emitRows };
  out.sources = [...(corpus.sources || []), "re-keyed by tools/rekey_placement.mjs (issue #10)"];
  out.notes = [...(corpus.notes || []),
    `Re-keyed: ${moved.length} translations moved onto the box their literal/retranslation`,
    `describes, via a Viterbi pass over offset states (window +-${WIN}, switch penalty ${SWITCH_PENALTY}).`,
    "Offsets are in boxes on disc. Collisions and read-only targets were refused, not forced."];
  fs.writeFileSync(OUT, JSON.stringify(out, null, 1));
  if (emitRows !== outRows) console.log(`--verified-only: emitting ${emitRows.length} of ${outRows.length} rows`);

  if (outRows.length !== items.length)
    console.error(`INTERNAL: ${items.length - outRows.length} rows lost — refusing to write`), process.exit(1);

  const before = corpus.rows.reduce((a, r) => (a[r.placement] = (a[r.placement] || 0) + 1, a), {});
  const after  = outRows.reduce((a, r) => (a[r.placement] = (a[r.placement] || 0) + 1, a), {});
  const hist = {};
  for (const m of moved) hist[m.by] = (hist[m.by] || 0) + 1;
  console.log(`boxes on disc: ${boxes.length.toLocaleString()}   migrated rows: ${items.length.toLocaleString()}`);
  console.log(`\nplacement BEFORE: ${JSON.stringify(before)}`);
  console.log(`placement AFTER : ${JSON.stringify(after)}`);
  console.log(`\nmoved (evidence-backed): ${moved.length.toLocaleString()}   stayed: ${stayed.length.toLocaleString()}`);
  console.log(`runs: ${acceptedRuns} accepted, ${rejectedRuns} rejected for weak support (${rejectedRows} rows left in place)`);
  console.log(`suggested but NOT applied: ${suggestions.size.toLocaleString()} (see suggest_key / suggest_basis)`);
  console.log(`refused — collisions: ${collided.length}   read-only/out-of-range targets: ${blocked.length}`);
  console.log(`\noffset histogram of moves:`);
  Object.entries(hist).sort((a, b) => +a[0] - +b[0]).forEach(([d, n]) => console.log(`   ${(+d > 0 ? "+" : "") + d}  ${n}`));
  console.log(`\nwrote ${path.relative(ROOT, OUT)}`);
}
main();
