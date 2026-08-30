#!/usr/bin/env node
/**
 * Lift finished translations out of a (gitignored, derived) worklist into a committed artifact.
 *
 * WHY THIS EXISTS
 *   A worklist is regenerable — it is built from the discs and the alignment, so it is
 *   gitignored. The moment someone fills in `re`, it stops being derived and becomes work that
 *   must not be lost to a `--out` overwrite or a clean checkout. This copies just the filled rows
 *   into translation/new/<area>.json, which IS committed.
 *
 * The output is the editor's strings-JSON, so it imports directly and merges with everything
 * else. Only `re`-bearing rows are carried, together with the key, the source English and its
 * digest (so a drifted box is refused on import rather than silently mis-written), and the JP the
 * line was translated from — the last so a reviewer can check the translation against its source
 * without rebuilding the alignment.
 *
 * USAGE
 *   node tools/harvest_worklist.mjs --worklist data/worklist_TS.json --area TS
 */
import { fileURLToPath } from "url";
import fs from "fs";
import path from "path";
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const argv = process.argv.slice(2);
const arg = (k, d) => (argv.includes(k) ? argv[argv.indexOf(k) + 1] : d);
const WL = arg("--worklist", null);
const AREA = arg("--area", null);
if (!WL) { console.error("need --worklist <file> [--area CODE]"); process.exit(1); }

const wl = JSON.parse(fs.readFileSync(WL, "utf8"));
const filled = wl.rows.filter((r) => typeof r.re === "string" && r.re.trim());
if (!filled.length) { console.log("no filled rows to harvest"); process.exit(0); }

const area = AREA || filled[0].area || "misc";
const OUT = arg("--out", path.join(ROOT, "translation", "new", `${area}.json`));

// merge with anything already harvested for this area, newest wins
let existing = [];
if (fs.existsSync(OUT)) {
  try { existing = JSON.parse(fs.readFileSync(OUT, "utf8")).rows || []; } catch (e) {}
}
const merged = new Map(existing.map((r) => [r.key, r]));
for (const r of filled) {
  merged.set(r.key, {
    key: r.key, blk: r.blk, off: r.off, sub: r.sub, area: r.area,
    en: r.en, enDigest: r.enDigest,
    jp: r.jp, jp_tier: r.jp_tier,
    re: r.re,
    editable: true, panel: !!r.panel,
    chunk: r.chunk, chunkBytes: r.chunkBytes,
  });
}
const rows = [...merged.values()].sort((a, b) => (a.blk - b.blk) || (a.off - b.off) || (a.sub - b.sub));

fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, JSON.stringify({
  app: "wa2-translation-editor", version: 2, kind: "strings",
  scope: "retranslation", area,
  disc: { lang: "en", label: "US (STGEVT.BIN)" },
  fit: wl.fit, charmap: wl.charmap,
  notes: [
    `Retranslated boxes for area ${area}. Committed work product, not derived — do not regenerate.`,
    "Each row was translated from the 'jp' field, which came from the anchored alignment, and was",
    "checked by tools/apply_translations.mjs against the chunk byte budget, the 3x35 on-screen",
    "ceiling and the WA2_RE_STYLE_GUIDE lint before being accepted.",
    "'en' is the shipped localization being replaced; 'enDigest' guards the mapping on import.",
    "Import through the editor's 'Import strings JSON'.",
  ],
  rows,
}, null, 1));

console.log(`harvested ${filled.length} filled row(s); ${rows.length} total in ${path.relative(ROOT, OUT)}`);
const byTier = {};
for (const r of rows) byTier[r.jp_tier] = (byTier[r.jp_tier] || 0) + 1;
console.log(`  JP source tiers: ${JSON.stringify(byTier)}`);
