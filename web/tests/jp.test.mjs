// Parity test: the JS JP decoder/aligner must match the Python originals exactly.
// Golden fixture from `python3 web/gen_tables.py`. Run from repo root.
import { createRequire } from "module";
import fs from "fs";
const require = createRequire(import.meta.url);
const JP = require("../wa2-jp.js");
const C = require("../wa2-core.js");

const JP_BIN = "Game Files/JP/Wild Arms - 2nd Ignition (Japan) (Disc 1)/Wild Arms - 2nd Ignition (Japan) (Disc 1).bin";
if (!fs.existsSync(JP_BIN)) { console.log("JP disc not present — skipped"); process.exit(0); }

JP.init(JSON.parse(fs.readFileSync("web/data/jp_tables.json", "utf8")));
const gold = JSON.parse(fs.readFileSync("web/tests/fixtures/jp_golden.json", "utf8"));

const span = C.rawSpan(C.DISCS.jp);
const fd = fs.openSync(JP_BIN, "r");
const raw = Buffer.alloc(span.len);
fs.readSync(fd, raw, 0, span.len, span.start); fs.closeSync(fd);
const jd = C.rawToUser(new Uint8Array(raw), C.DISCS.jp.size);

// EN side for align()
const EN_BIN = "Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin";
const enSpan = C.rawSpan(C.DISCS.en);
const efd = fs.openSync(EN_BIN, "r");
const eraw = Buffer.alloc(enSpan.len);
fs.readSync(efd, eraw, 0, enSpan.len, enSpan.start); fs.closeSync(efd);
const ud = C.rawToUser(new Uint8Array(eraw), C.DISCS.en.size);
// EN boxes via the same walk the app uses (panel flag needed by align)
function enBoxes(blk) {
  const BLK = C.DISCS.en.blk, lo = blk * BLK, hi = lo + BLK;
  const out = []; let i = lo;
  while (i < hi - 1) {
    let frame = 0;
    if (ud[i] === 0x10 && ud[i + 1] === 0x0c) frame = 2;
    else if (ud[i] === 0x06 || ud[i] === 0x0d) frame = 1;
    if (!frame) { i++; continue; }
    const s = i + frame; let k = s;
    while (k < hi && ud[k] !== 0x00) k++;
    if (k <= s) { i++; continue; }
    const content = ud.slice(s, k);
    const subs = []; let last = 0;
    for (let p = 0; p + 1 < content.length; p++)
      if (content[p] === 0x10 && content[p + 1] === 0x0c) { subs.push(content.slice(last, p)); last = p + 2; p++; }
    subs.push(content.slice(last));
    let emitted = false;
    for (const sub of subs) {
      if (!sub.length) continue;
      const d = C.decodeEnLossy(sub, false);
      if (C.goodEn(d)) {
        out.push({ text: d.text, panel: d.text.replace(/^[({ ]+/, "").startsWith("*") });
        emitted = true;
      }
    }
    if (emitted && k > s) { i = k; continue; }
    i++;
  }
  return out;
}

let pass = 0, fail = 0;
const ok = (c, n) => { if (c) { pass++; console.log("  ok:", n); } else { fail++; console.log("  FAIL:", n); } };

for (const blk of [3, 24]) {
  const g = gold[String(blk)];
  const jpb = JP.jpBoxes(jd, blk);
  ok(jpb.length === g.jp.length, `blk${blk}: JP box count ${jpb.length} == python ${g.jp.length}`);
  let tmatch = 0;
  for (let i = 0; i < Math.min(jpb.length, g.jp.length); i++)
    if (jpb[i].text === g.jp[i].text && jpb[i].panel === g.jp[i].panel) tmatch++;
  ok(tmatch === g.jp.length, `blk${blk}: all ${g.jp.length} JP texts identical to python decode`);

  const enb = enBoxes(blk);
  const { pairs, n, m } = JP.align(enb, jpb);
  ok(n === g.n && m === g.m, `blk${blk}: align dims (${n},${m}) == python (${g.n},${g.m})`);
  let pmatch = 0;
  for (let i = 0; i < Math.min(pairs.length, g.pairs.length); i++)
    if (pairs[i].jp === g.pairs[i].jp && pairs[i].conf === g.pairs[i].conf) pmatch++;
  ok(pmatch === g.pairs.length, `blk${blk}: all ${g.pairs.length} DP pairs identical (jp text + conf)`);
}
console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
