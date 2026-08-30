// Node tests for web/wa2-core.js against the REAL local discs (skipped if absent).
// Run from repo root: node web/tests/core.test.mjs
import { createRequire } from "module";
import fs from "fs";
const require = createRequire(import.meta.url);
const C = require("../wa2-core.js");

const EN_BIN = "Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin";
const ES_BIN = "WA2_CD1_spanish.bin";
const PPF = "spanish_patch/Wild Arms 2 Traducción español - gadesx v1.01 (multi)/Wild Arms 2 CD1 T+esp beta 1.01 gadesx (normal).ppf";

let pass = 0, fail = 0;
const ok = (cond, name) => { if (cond) { pass++; console.log("  ok:", name); } else { fail++; console.log("  FAIL:", name); } };

function readSpan(path, start, len) {
  const fd = fs.openSync(path, "r");
  const buf = Buffer.alloc(len);
  fs.readSync(fd, buf, 0, len, start); fs.closeSync(fd);
  return new Uint8Array(buf);
}

if (!fs.existsSync(EN_BIN)) { console.log("EN disc not present — skipping all disc tests"); process.exit(0); }
const span = C.rawSpan(C.DISCS.en);
const enRaw = readSpan(EN_BIN, span.start, span.len);

// 1 ---- EDC/ECC port vs the disc's own sector codes -------------------------
{
  let matched = 0, total = 0, form2 = 0;
  for (let s = 0; s < 256; s++) {
    const off = s * C.RAW;
    const orig = enRaw.slice(off, off + C.RAW);
    const work = enRaw.slice(off, off + C.RAW);
    // wipe the codes, recompute, compare
    work.fill(0, 0x818, 0x81c); work.fill(0, 0x81c, 0x930);
    const form = C.sectorFix(work, 0);
    if (form === "form2") { form2++; continue; }
    total++;
    if (Buffer.compare(Buffer.from(work), Buffer.from(orig)) === 0) matched++;
  }
  console.log(`EDC/ECC: ${matched}/${total} sectors byte-identical after recompute (${form2} form2)`);
  ok(total > 200 && matched === total, "EDC+ECC recompute matches the US disc exactly");
}

// 2 ---- PPF parse+apply vs gadesx's own patched disc -------------------------
if (fs.existsSync(PPF) && fs.existsSync(ES_BIN)) {
  const ppf = C.ppfParse(new Uint8Array(fs.readFileSync(PPF)));
  console.log(`PPF: ${ppf.version} "${ppf.desc}" — ${ppf.records.length} records`);
  const win = enRaw.slice();
  const applied = C.ppfApplyWindow(ppf, win, span.start);
  const esRaw = readSpan(ES_BIN, span.start, span.len);
  const identical = Buffer.compare(Buffer.from(win), Buffer.from(esRaw)) === 0;
  console.log(`PPF: ${applied} records landed in the STGEVT window`);
  ok(identical, "EN + gadesx PPF == gadesx's patched disc, byte-for-byte across the whole STGEVT region");

  // 3 ---- PPF build -> parse roundtrip ---------------------------------------
  const edits = [{ off: span.start + 1000, bytes: new Uint8Array(600).fill(0xab), old: new Uint8Array(600).fill(1) }];
  const rt = C.ppfParse(C.ppfBuild("roundtrip test", edits));
  const flat = Buffer.concat(rt.records.map((r) => Buffer.from(r.data)));
  ok(rt.records.length === 3 && rt.records[0].off === span.start + 1000 &&
     flat.length === 600 && flat.every((b) => b === 0xab), "ppfBuild -> ppfParse roundtrip (255-byte record split)");
} else console.log("gadesx PPF / ES bin not present — skipping PPF ground-truth test");

// 4 ---- chunk codec identity over a whole block ------------------------------
{
  const ud = C.rawToUser(enRaw, C.DISCS.en.size);
  const BLK = C.DISCS.en.blk, blk = 3, lo = blk * BLK, hi = lo + BLK;
  let chunks = 0, identity = 0, editable = 0, subsN = 0;
  let i = lo;
  while (i < hi - 1) {
    let frame = 0;
    if (ud[i] === 0x10 && ud[i + 1] === 0x0c) frame = 2;
    else if (ud[i] === 0x06 || ud[i] === 0x0d) frame = 1;
    if (!frame) { i++; continue; }
    const s = i + frame;
    let k = s; while (k < hi && ud[k] !== 0x00) k++;
    if (k <= s) { i++; continue; }
    const content = ud.slice(s, k);
    // split into subs exactly like extract_boxes: on \x10\x0c
    const subs = [];
    let last = 0;
    for (let p = 0; p + 1 < content.length; p++)
      if (content[p] === 0x10 && content[p + 1] === 0x0c) { subs.push(content.slice(last, p)); last = p + 2; p++; }
    subs.push(content.slice(last));
    const parsed = subs.map((b) => C.parseSub(b, false));
    chunks++; subsN += subs.length;
    if (parsed.some((p) => !p.raw)) editable++;
    const rb = C.rebuildChunk(parsed, content.length, false);
    if (!rb.err && Buffer.compare(Buffer.from(rb.bytes), Buffer.from(content)) === 0) identity++;
    i = k;
  }
  console.log(`chunk codec: ${chunks} chunks, ${subsN} subs, ${editable} with editable text, identity ${identity}/${chunks}`);
  ok(identity === chunks, "parse->rebuild is byte-identity for every untouched chunk in block 3");
}

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
