#!/usr/bin/env node
/**
 * Build a translation worklist: untranslated boxes with a TRUSTWORTHY Japanese source attached.
 *
 * WHY THIS AND NOT THE EDITOR'S STRINGS EXPORT
 *   The editor's export carries the DP aligner's `jp`, which is ~87% unverified guesswork. Asking
 *   anyone to translate against that produces confident, wrong lines. This attaches the JP from
 *   data/jp_en_alignment.json instead, which is anchored to the corpus and hold-out tested at
 *   78.5% exact / 94.3% within +-1 — and, crucially, it reports per row how far it can be
 *   trusted rather than presenting every row as equally solid.
 *
 * TIERS (--tier picks the floor, default `exact`)
 *   exact   radius 0: the JP is pinned 1:1. 1,426 untranslated boxes qualify today. Translate
 *           these straight down the list.
 *   near    radius <=2: the true JP is within a box or two; the alternatives ride along in
 *           `jp_candidates` so a translator can pick while reading the scene.
 *   any     everything the alignment covers, including `edge` extrapolation (measured 35% exact)
 *           — for bulk reading, not for committing translations from.
 *
 * OUTPUT is the editor's own strings-JSON, so a filled-in file imports straight back: edit `re`,
 * then Import strings JSON. Rows carry the byte budget and the 3x35 on-screen ceiling, the two
 * independent limits a line has to satisfy.
 *
 * USAGE
 *   node tools/build_worklist.mjs                        # exact tier, all areas
 *   node tools/build_worklist.mjs --tier near --area VC  # one area, looser tier
 *   node tools/build_worklist.mjs --list-areas
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
const TIER = arg("--tier", "exact");
const AREA = arg("--area", null);
const OUT = arg("--out", path.join(ROOT, `data/worklist_${AREA || "all"}_${TIER}.json`));
const PLACED = path.join(ROOT, "data/migrated_corpus.placed.json");
const ALIGN = path.join(ROOT, "data/jp_en_alignment.json");
const DB = path.join(ROOT, "data/script/wa2_db.json");
const NBLK = 120;
const MAXR = { exact: 0, near: 2, any: 99 }[TIER];
if (MAXR === undefined) { console.error(`--tier must be exact | near | any`); process.exit(1); }

const readRegion = (p, disc) => {
  if (!fs.existsSync(p)) { console.error(`missing ${p}`); process.exit(1); }
  const s = C.rawSpan(disc), fd = fs.openSync(p, "r"), b = Buffer.alloc(s.len);
  fs.readSync(fd, b, 0, s.len, s.start); fs.closeSync(fd);
  return C.rawToUser(new Uint8Array(b), disc.size);
};

function main() {
  J.init(JSON.parse(fs.readFileSync(path.join(ROOT, "web/data/jp_tables.json"), "utf8")));
  const ud = readRegion(path.join(ROOT, "Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin"), C.DISCS.en);
  const jd = readRegion(path.join(ROOT, "Game Files/JP/Wild Arms - 2nd Ignition (Japan) (Disc 1)/Wild Arms - 2nd Ignition (Japan) (Disc 1).bin"), C.DISCS.jp);
  // the gadesx Spanish disc is optional; it is a reference column, not a dependency
  const esPath = path.join(ROOT, "WA2_CD1_spanish.bin");
  const esd = fs.existsSync(esPath) ? readRegion(esPath, C.DISCS.en) : null;

  // block -> area, from the hand-annotated rows
  const db = JSON.parse(fs.readFileSync(DB, "utf8")).rows;
  const tally = {};
  for (const r of db) if (typeof r.area === "string" && r.area)
    (tally[r.block] = tally[r.block] || {})[r.area] = (tally[r.block][r.area] || 0) + 1;
  const blockArea = {};
  for (const b of Object.keys(tally))
    blockArea[b] = Object.entries(tally[b]).sort((x, y) => y[1] - x[1])[0][0];

  if (argv.includes("--list-areas")) {
    const c = {};
    for (const [b, a] of Object.entries(blockArea)) (c[a] = c[a] || []).push(+b);
    Object.entries(c).sort().forEach(([a, bs]) => console.log(`  ${a.padEnd(5)} block(s) ${bs.sort((x, y) => x - y).join(", ")}`));
    return;
  }

  const align = JSON.parse(fs.readFileSync(ALIGN, "utf8")).map;
  const done = new Set(JSON.parse(fs.readFileSync(PLACED, "utf8")).rows.map((r) => r.key));
  const jpCache = {};
  const jpFor = (b) => (jpCache[b] || (jpCache[b] = J.jpBoxes(jd, b)));

  const rows = [];
  const skipped = { translated: 0, readonly: 0, noAlign: 0, tooLoose: 0, otherArea: 0 };
  for (let blk = 0; blk < NBLK; blk++) {
    const area = blockArea[blk] || "??";
    const lo = blk * C.DISCS.en.blk, hi = lo + C.DISCS.en.blk;
    for (const ch of C.walkChunks(ud, lo, hi)) {
      // the Spanish disc is byte-identical in layout, so the same chunk window holds its text
      let esSubs = null;
      if (esd) {
        const seg = esd.slice(ch.start, ch.start + ch.cap);
        esSubs = []; let last = 0;
        for (let p = 0; p + 1 < seg.length; p++)
          if (seg[p] === 0x10 && seg[p + 1] === 0x0c) { esSubs.push(seg.slice(last, p)); last = p + 2; p++; }
        esSubs.push(seg.slice(last));
      }
      let goodOrd = 0;
      ch.subs.forEach((sub, si) => {
        if (!ch.good[si]) return;
        const ord = goodOrd++;
        const key = `${blk}:${ch.off}:${si}`;
        if (AREA && area !== AREA) { skipped.otherArea++; return; }
        if (done.has(key)) { skipped.translated++; return; }
        const parsed = C.parseSub(sub, false);
        if (parsed.raw) { skipped.readonly++; return; }
        const a = align[key];
        if (!a) { skipped.noAlign++; return; }
        const [jblk, jord, radius, tier] = a;
        if (jblk < 0 || radius > MAXR) { skipped.tooLoose++; return; }

        const list = jpFor(jblk);
        const cands = [];
        for (let d = -radius; d <= radius; d++) if (list[jord + d]) cands.push(list[jord + d].text);
        const lossy = C.decodeEnLossy(sub, false);

        // ES reference: same ordinal among the chunk's good subs
        let es;
        if (esSubs) {
          const good = esSubs.filter((s) => s.length && C.goodEn(C.decodeEnLossy(s, true)));
          if (good[ord]) es = C.decodeEnLossy(good[ord], true).text;
        }

        rows.push({
          key, blk, off: ch.off, sub: si, area,
          en: parsed.text,
          enDigest: C.digest(parsed.text),
          jp: list[jord] ? list[jord].text : "",
          jp_tier: { a: "anchor", b: "exact", o: "±" + radius, e: "edge" }[tier] || tier,
          ...(cands.length > 1 ? { jp_candidates: cands } : {}),
          ...(es ? { es } : {}),
          re: "",
          editable: true,
          panel: lossy.text.replace(/^[({ ]+/, "").startsWith("*"),
          chunk: `${blk}:${ch.off}`, chunkBytes: ch.cap,
        });
      });
    }
  }

  const out = {
    app: "wa2-translation-editor", version: 2, kind: "strings",
    scope: "worklist", todoOnly: true,
    disc: { lang: "en", label: "US (STGEVT.BIN)", blocks: NBLK },
    sources: [`worklist: untranslated boxes, JP from the anchored alignment, tier '${TIER}'`
              + (AREA ? `, area ${AREA}` : "")],
    fit: { lines: C.FIT.lines, cols: C.FIT.cols },
    charmap: C.ES_MAP,
    notes: [
      "Fill in the 're' field only; everything else places your text back.",
      "'jp' is the Japanese source, attached via data/jp_en_alignment.json — NOT the DP aligner.",
      "'jp_tier' says how firmly: anchor/exact are pinned 1:1; '±n' means the true box is within n",
      "and the alternatives are listed in 'jp_candidates'; 'edge' is extrapolated, ~35% exact.",
      "'en' is the shipped localization (what we are replacing) and 'es' the gadesx Spanish, both",
      "reference only. Translate from the Japanese.",
      "Two independent limits: 'chunkBytes' is the byte capacity SHARED by every row with the same",
      "'chunk', and 3 x 35 is the on-screen ceiling — the game does not auto-wrap, so use \\n.",
      "Import back through the editor's 'Import strings JSON'.",
    ],
    rows,
  };
  fs.mkdirSync(path.dirname(OUT), { recursive: true });
  fs.writeFileSync(OUT, JSON.stringify(out, null, 1));

  const byArea = {};
  for (const r of rows) byArea[r.area] = (byArea[r.area] || 0) + 1;
  console.log(`tier '${TIER}'${AREA ? `, area ${AREA}` : ""} -> ${rows.length.toLocaleString()} boxes to translate`);
  console.log(`  with a Spanish reference: ${rows.filter((r) => r.es).length.toLocaleString()}`);
  console.log(`  skipped — already translated ${skipped.translated.toLocaleString()}, read-only ${skipped.readonly.toLocaleString()}, `
            + `no JP mapped ${skipped.noAlign.toLocaleString()}, looser than tier ${skipped.tooLoose.toLocaleString()}`);
  console.log(`\nby area:`);
  Object.entries(byArea).sort((a, b) => b[1] - a[1]).slice(0, 14)
    .forEach(([a, n]) => console.log(`   ${a.padEnd(5)} ${String(n).padStart(5)}`));
  console.log(`\nwrote ${path.relative(ROOT, OUT)}`);
}
main();
