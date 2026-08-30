#!/usr/bin/env node
/**
 * Merge finished translations into a worklist, and refuse the ones that would not ship.
 *
 * A translation has to clear three independent gates, and passing one says nothing about the
 * others — this is exactly where hand-written lines go wrong:
 *   1. BYTE BUDGET. Chunk length is fixed on disc, and the budget is shared by every box in the
 *      chunk, so a line can be short and still overflow because of its neighbours.
 *   2. ON-SCREEN FIT. 3 lines x 35 columns. The game does not auto-wrap; breaks are manual.
 *      Independent of the byte budget: text can fit the chunk and still run off the window.
 *   3. HOUSE STYLE. docs/WA2_RE_STYLE_GUIDE.md SS1-SS3, enforced by wa2-core's lintText: no em
 *      dashes, no box ending on a comma, balanced |emphasis|, {n} name codes kept, and so on.
 *
 * Anything failing gate 1 or 2, or raising a style ERROR, is REJECTED and reported rather than
 * written — a rejected line is a line to rewrite, not a line to ship and discover later.
 *
 * USAGE
 *   node tools/apply_translations.mjs --worklist data/worklist_TS.json --in translations.json
 *   node tools/apply_translations.mjs ... --write     # persist into the worklist
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
const WL = arg("--worklist", null);
const IN = arg("--in", null);
const WRITE = argv.includes("--write");
if (!WL || !IN) { console.error("need --worklist <file> --in <translations.json>"); process.exit(1); }

// preview-only stand-ins, so a {n} is measured at the width it really renders
const NAMES = { "0": "Ashley", "1": "Brad", "2": "Lilka", "3": "Marina", "4": "Kanon", "5": "Liz", "6": "Ard" };
const subNames = (t) => String(t).replace(/\{([0-9])\}/g, (m, d) => NAMES[d] || m);

// The byte budget can only be judged against the real chunk, so the disc is required.
function readDisc() {
  const p = path.join(ROOT, "Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin");
  if (!fs.existsSync(p)) {
    console.error(`missing ${p}\n  the US disc is needed to measure chunk budgets honestly`);
    process.exit(1);
  }
  const s = C.rawSpan(C.DISCS.en), fd = fs.openSync(p, "r"), b = Buffer.alloc(s.len);
  fs.readSync(fd, b, 0, s.len, s.start); fs.closeSync(fd);
  return C.rawToUser(new Uint8Array(b), C.DISCS.en.size);
}

function main() {
  const wl = JSON.parse(fs.readFileSync(WL, "utf8"));
  const tr = JSON.parse(fs.readFileSync(IN, "utf8"));
  const byKey = new Map(wl.rows.map((r) => [r.key, r]));

  // group by chunk: the byte budget is shared, so it can only be judged per chunk
  const chunkRows = new Map();
  for (const r of wl.rows) {
    if (!chunkRows.has(r.chunk)) chunkRows.set(r.chunk, []);
    chunkRows.get(r.chunk).push(r);
  }

  const accepted = [], rejected = [], unknown = [];
  for (const [key, text] of Object.entries(tr)) {
    const row = byKey.get(key);
    if (!row) { unknown.push(key); continue; }
    const problems = [];

    // gate 2: on-screen fit, measured on the name-expanded text
    const fit = C.fitReport(subNames(text));
    if (fit.overLines) problems.push(`${fit.nLines} lines > ${fit.maxLines}`);
    if (fit.overCols) problems.push(`longest line ${fit.longest} > ${fit.maxCols}`);

    // gate 3: house style — errors block, warnings are reported
    const lint = C.lintText(text, { en: row.en });
    for (const m of lint.filter((x) => x.sev === "error")) problems.push(`style: ${m.rule}`);

    // gate 1: encodable at all?
    const enc = C.encodeText(text, false);
    if (enc.err) problems.push(enc.err);

    (problems.length ? rejected : accepted).push({ key, text, problems, warns: lint.filter((x) => x.sev === "warn").map((w) => w.rule) });
  }

  // gate 1 proper: rebuild each affected chunk FROM THE DISC.
  //
  // Summing only the worklist's rows for a chunk is wrong and was: a worklist holds only the
  // UNTRANSLATED boxes, while the chunk on disc also carries already-translated and read-only
  // boxes that still occupy bytes. That undercount passed 20 chunks the editor then rejected.
  // The only correct measure is the editor's own: rebuild every sub of the chunk, substituting
  // the new text where we have it and keeping the original bytes everywhere else.
  const applied = new Map(accepted.map((a) => [a.key, a.text]));
  const overBudget = [];
  const ud = readDisc();
  const NBLK = 120;
  const touched = new Set([...applied.keys()].map((k) => k.split(":").slice(0, 2).join(":")));
  for (let blk = 0; blk < NBLK; blk++) {
    const lo = blk * C.DISCS.en.blk, hi = lo + C.DISCS.en.blk;
    for (const ch of C.walkChunks(ud, lo, hi)) {
      const chunkId = `${blk}:${ch.off}`;
      if (!touched.has(chunkId)) continue;
      const subs = ch.subs.map((sub, si) => {
        const key = `${blk}:${ch.off}:${si}`;
        const parsed = C.parseSub(sub, false);
        if (applied.has(key) && !parsed.raw) return { prefix: parsed.prefix, text: applied.get(key) };
        return { raw: sub };                       // untouched subs keep their exact bytes
      });
      const rb = C.rebuildChunk(subs, ch.cap, false);
      if (rb.err) {
        const keys = ch.subs.map((_s, si) => `${blk}:${ch.off}:${si}`).filter((k) => applied.has(k));
        overBudget.push({ chunk: chunkId, used: rb.total ?? ch.cap, cap: ch.cap,
                          over: (rb.total ?? ch.cap) - ch.cap, err: rb.err, keys });
      }
    }
  }
  const overKeys = new Set(overBudget.flatMap((o) => o.keys));
  const finalOk = accepted.filter((a) => !overKeys.has(a.key));

  console.log(`translations offered : ${Object.keys(tr).length}`);
  console.log(`  ACCEPTED           : ${finalOk.length}`);
  console.log(`  rejected (fit/style/encoding): ${rejected.length}`);
  console.log(`  rejected (chunk over budget) : ${overKeys.size}`);
  if (unknown.length) console.log(`  key not in this worklist     : ${unknown.length}`);

  for (const r of rejected) console.log(`\n  REJECT ${r.key}\n     ${r.problems.join("; ")}\n     ${r.text.replace(/\n/g, " / ").slice(0, 76)}`);
  for (const o of overBudget) console.log(`\n  OVER BUDGET ${o.chunk}: ${o.used}/${o.cap} bytes (+${o.over}) — ${o.keys.join(", ")}`);

  const warned = finalOk.filter((a) => a.warns.length);
  if (warned.length) {
    console.log(`\n  accepted with style warnings (${warned.length}):`);
    for (const w of warned.slice(0, 10)) console.log(`     ${w.key}: ${w.warns.join(", ")}`);
  }

  if (WRITE) {
    for (const a of finalOk) byKey.get(a.key).re = a.text;
    const done = wl.rows.filter((r) => r.re).length;
    fs.writeFileSync(WL, JSON.stringify(wl, null, 1));
    console.log(`\nwrote ${finalOk.length} into ${path.relative(ROOT, WL)} (${done}/${wl.rows.length} filled)`);
  } else {
    console.log(`\n(dry run — pass --write to persist)`);
  }
}
main();
