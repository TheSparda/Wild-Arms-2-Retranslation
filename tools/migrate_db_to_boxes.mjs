#!/usr/bin/env node
/**
 * Migrate the translation corpus from the superseded `10 0c` slot model onto the corrected
 * (chunk, sub) box model the editor uses.  →  github issue #1
 *
 * THE PROBLEM
 *   tools/build_db.py keys every row to "US#n = the nth 10 0c marker". tools/extract_boxes.py
 *   later proved that model wrong: 10 0c is an event OPCODE and is mostly a SUB-SEPARATOR inside
 *   a box, not a box start. The DB therefore has 8,516 slots where the corrected extractor finds
 *   20,652 boxes — and 6,979 finished translations are invisible to the editor.
 *
 * THE MAPPING
 *   An old slot's text begins immediately after its marker, so old US#n at marker offset `off`
 *   is the sub that STARTS at `off + 2`. Walking every chunk and indexing each sub by its
 *   absolute start offset turns that into a direct lookup.
 *
 * WHY THIS IS NODE, NOT PYTHON
 *   The output has to be accepted by the editor, whose import refuses any row whose `enDigest`
 *   does not match what it recomputes from the disc. Re-implementing walkChunks / parseSub /
 *   decodeEnLossy / digest in Python and hoping the two agree would risk refusing all 6,725 rows
 *   over one decoding edge case. So this reuses web/wa2-core.js — the editor's own module — and
 *   the keys and digests are correct by construction rather than by luck.
 *
 * PLACEMENT — a defect found while doing this, not a migration bug
 *   Re-keying is faithful: a row lands on the box whose English matches the DB's English. But
 *   the DB's own `jp`/`lit`/`re` were attached to each slot by the ALIGNER, which drifts, so a
 *   translation can be a correct rendering of the WRONG line. Measured: of the migrated rows
 *   that have a human literal to check, only ~58% are demonstrably on the right box; ~1,100 are
 *   on the wrong one, mostly by +-1 slot.
 *   The literal is ENGLISH, so this is checkable without touching Japanese: if `lit` describes
 *   the box's `en`, the placement is confirmed. Every row therefore carries `placement`:
 *     "verified" the literal matches this box            -> safe to ship
 *     "suspect"  the literal matches a DIFFERENT nearby box (`suggest_us` says which)
 *     "unknown"  no literal, or nothing matched -> unproven, not disproven
 *   --verified-only emits just the safe ones, which is what a first patch should ship.
 *
 * SAFETY
 *   A row is emitted ONLY when the DB's English matches the box's English on the disc. ~250 rows
 *   fail that and are written to the refusals file for a human, never guessed at. A wrong key
 *   writes plausible English into the wrong box, which is the exact failure `enDigest` exists to
 *   catch — so the gate stays strict.
 *
 * USAGE
 *   node tools/migrate_db_to_boxes.mjs [--out data/migrated_corpus.json] [--strict]
 */
import { createRequire } from "module";
import { fileURLToPath } from "url";
import fs from "fs";
import path from "path";
const require = createRequire(import.meta.url);

// fileURLToPath, not URL.pathname — the repo path contains spaces, which pathname %20-encodes
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const C = require(path.join(ROOT, "web/wa2-core.js"));

const DB      = path.join(ROOT, "data/script/wa2_db.json");
const US_BIN  = path.join(ROOT, "Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin");
const argv    = process.argv.slice(2);
const outPath = argv.includes("--out") ? argv[argv.indexOf("--out") + 1]
                                       : path.join(ROOT, "data/migrated_corpus.json");
const refPath = outPath.replace(/\.json$/, "") + ".refused.json";
const NBLK = 120;

// normalise for the identity check
const norm = (s) => (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");

// English-to-English overlap, used to check whether a row's literal really describes its box.
const WORD = /[a-z']{4,}/g;
const toks = (s) => new Set(((s || "").toLowerCase().match(WORD) || []));
function sim(a, b) {
  const A = toks(a), B = toks(b);
  if (!A.size || !B.size) return 0;
  let n = 0; for (const x of A) if (B.has(x)) n++;
  return n / Math.min(A.size, B.size);
}
const PLACE_MIN = 0.34;      // same threshold the placement survey used

/**
 * Re-render a sub the way build_insert.py's us_disp() did, which is what produced the DB's `en`.
 * It kept every printable ASCII byte except '@' and dropped all control bytes — so the DIGIT
 * following a \x05 (speaker) or \x0a (name) code survived as bare text: "*0's party can board".
 * parseSub instead lifts \x05 N out to the nameplate and renders \x0a N as "{N}", giving
 * "*'s party can board". Both are correct; they are just different renderings of one box.
 * Comparing against the dumper's own rendering is the like-for-like check, and it is what makes
 * the identity gate strict without being wrong.
 */
function dumperText(sub) {
  let o = "";
  for (const b of sub) if (b >= 0x20 && b < 0x7f && b !== 0x40) o += String.fromCharCode(b);
  return o;
}

function readRegion() {
  if (!fs.existsSync(US_BIN)) {
    console.error(`missing ${US_BIN}\n  the US disc is gitignored — point --bin at your copy`);
    process.exit(1);
  }
  const span = C.rawSpan(C.DISCS.en);
  const fd = fs.openSync(US_BIN, "r");
  const buf = Buffer.alloc(span.len);
  fs.readSync(fd, buf, 0, span.len, span.start);
  fs.closeSync(fd);
  return C.rawToUser(new Uint8Array(buf), C.DISCS.en.size);
}

/** every good sub on the disc, indexed by the absolute offset its bytes start at */
function indexSubs(ud) {
  const bySubStart = new Map();
  for (let blk = 0; blk < NBLK; blk++) {
    const lo = blk * C.DISCS.en.blk, hi = lo + C.DISCS.en.blk;
    for (const ch of C.walkChunks(ud, lo, hi)) {
      let pos = ch.start;
      ch.subs.forEach((sub, si) => {
        if (ch.good[si]) {
          const parsed = C.parseSub(sub, false);
          const lossy = C.decodeEnLossy(sub, false);
          bySubStart.set(pos, {
            blk, chunk: ch, si, sub,
            editable: !parsed.raw,
            src: parsed.raw ? lossy.text : parsed.text,
            disp: lossy.text,
            panel: lossy.text.replace(/^[({ ]+/, "").startsWith("*"),
          });
        }
        pos += sub.length + 2;                    // +2 for the \x10\x0c separator that split them
      });
    }
  }
  return bySubStart;
}

function oldMarkers(ud) {
  const out = [];
  for (let i = 0; i < ud.length - 1; i++) if (ud[i] === 0x10 && ud[i + 1] === 0x0c) out.push(i);
  return out;
}

function main() {
  const ud = readRegion();
  const subs = indexSubs(ud);
  const marks = oldMarkers(ud);
  const db = JSON.parse(fs.readFileSync(DB, "utf8")).rows;
  const byUs = new Map(db.map((r) => [r.us, r]));
  const str = (r, k) => (typeof r[k] === "string" ? r[k] : "");

  const rows = [], refused = [];
  let noTranslation = 0, noSub = 0, textMismatch = 0, notEditable = 0;

  marks.forEach((off, us) => {
    const r = byUs.get(us);
    if (!r) return;
    const re = str(r, "re").trim();
    const en = str(r, "en").trim();

    const hit = subs.get(off + 2);
    if (!hit) {
      if (re) { noSub++; refused.push({ us, reason: "no box starts at this marker", en: en.slice(0, 80) }); }
      return;
    }
    // THE GATE: the DB's English must be the box's English. No fuzzy fallback.
    const a = norm(en);
    const cands = [norm(hit.src), norm(hit.disp), norm(dumperText(hit.sub))];
    if (!a || !cands.includes(a)) {
      if (re) {
        textMismatch++;
        refused.push({ us, key: `${hit.blk}:${hit.chunk.off}:${hit.si}`,
                       reason: "EN text does not match the box on disc",
                       db_en: en.slice(0, 90), disc_en: hit.src.slice(0, 90) });
      }
      return;
    }
    if (!re) { noTranslation++; return; }
    if (!hit.editable) {
      notEditable++;
      refused.push({ us, key: `${hit.blk}:${hit.chunk.off}:${hit.si}`,
                     reason: "box is read-only (control codes) — see issue #6", en: en.slice(0, 80) });
      return;
    }
    rows.push({
      key: `${hit.blk}:${hit.chunk.off}:${hit.si}`,
      blk: hit.blk, off: hit.chunk.off, sub: hit.si,
      en: hit.src,
      enDigest: C.digest(hit.src),
      re: re.split(" / ").join("\n"),            // build_db joins display lines with " / "
      editable: true, panel: hit.panel,
      chunk: `${hit.blk}:${hit.chunk.off}`, chunkBytes: hit.chunk.cap,
      us,                                         // provenance back to the old slot id
    });
  });

  // ---- placement pass: does each row's literal actually describe the box it landed on? ----
  const order = rows.map((r) => r.us);
  const idx = new Map(order.map((u, i) => [u, i]));
  let verified = 0, suspect = 0, unknown = 0;
  for (const row of rows) {
    const r = byUs.get(row.us);
    const lit = str(r, "lit").trim();
    if (!lit) { row.placement = "unknown"; unknown++; continue; }
    const i = idx.get(row.us);
    let best = 0, bestD = null;
    for (let d = -6; d <= 6; d++) {
      const j = i + d;
      if (j < 0 || j >= rows.length) continue;
      const sc = sim(lit, rows[j].en);
      if (sc > best) { best = sc; bestD = d; }
    }
    if (best < PLACE_MIN) { row.placement = "unknown"; unknown++; }
    else if (bestD === 0) { row.placement = "verified"; verified++; }
    else {
      row.placement = "suspect";
      row.suggest_us = rows[i + bestD].us;
      row.suggest_key = rows[i + bestD].key;
      suspect++;
    }
  }

  const out = {
    app: "wa2-translation-editor", version: 2, kind: "strings",
    scope: "all", todoOnly: false,
    disc: { lang: "en", label: "US (STGEVT.BIN)", blocks: NBLK },
    sources: ["migrated from data/script/wa2_db.json (10 0c slot model)"],
    fit: { lines: C.FIT.lines, cols: C.FIT.cols },
    charmap: C.ES_MAP,
    notes: [
      "Migrated corpus: the project's existing translations re-keyed from the superseded 10 0c",
      "slot model onto the corrected (chunk, sub) box model. See issue #1.",
      "Every row's English was verified against the disc before it was emitted; rows that could",
      "not be verified are in the .refused.json file next to this one, not silently remapped.",
      "READ `placement` BEFORE SHIPPING A ROW. The re-keying is faithful, but the DB's own JP was",
      "attached by an aligner that drifts, so a translation can be a correct rendering of the",
      "WRONG line. verified = its literal describes this box. suspect = its literal describes the",
      "box at suggest_key instead. unknown = no literal to check; unproven, not disproven.",
    ],
    rows,
  };
  if (argv.includes("--verified-only")) {
    out.rows = rows.filter((r) => r.placement === "verified");
    out.notes.push(`--verified-only: emitting ${out.rows.length} of ${rows.length} rows.`);
  }
  fs.writeFileSync(outPath, JSON.stringify(out, null, 1));
  fs.writeFileSync(refPath, JSON.stringify({ count: refused.length, refused }, null, 1));

  const withRe = db.filter((r) => str(r, "re").trim()).length;
  console.log(`old slots (10 0c markers): ${marks.length.toLocaleString()}`);
  console.log(`DB rows carrying a translation: ${withRe.toLocaleString()}`);
  console.log(`\nMIGRATED: ${rows.length.toLocaleString()} translations -> ${path.relative(ROOT, outPath)}`);
  console.log(`  refused (written to ${path.basename(refPath)}): ${refused.length}`);
  console.log(`     EN text mismatch : ${textMismatch}`);
  console.log(`     no box at marker : ${noSub}`);
  console.log(`     box is read-only : ${notEditable}`);
  console.log(`  skipped, no translation on the row: ${noTranslation.toLocaleString()}`);
  const pct = (rows.length / withRe * 100).toFixed(1);
  console.log(`\ncarried ${pct}% of the existing translation`);
  console.log(`\nPLACEMENT (is each translation on the right box?)`);
  console.log(`  verified (literal describes this box) : ${verified.toLocaleString()}`);
  console.log(`  suspect  (literal describes another)  : ${suspect.toLocaleString()}  <- see suggest_key`);
  console.log(`  unknown  (no literal to check)        : ${unknown.toLocaleString()}`);
  if (!argv.includes("--verified-only"))
    console.log(`\n  re-run with --verified-only to emit just the ${verified.toLocaleString()} safe rows`);
  if (argv.includes("--strict") && refused.length > textMismatch + noSub + notEditable) process.exit(1);
}
main();
