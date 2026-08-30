// WA2 Translation Editor — pure core logic (no DOM). Loaded by app.js in the browser and by
// the Node tests (web/tests/core.test.mjs) against the real discs, so every routine here is
// verified against ground truth: the EDC/ECC port against the US disc's own sector codes, the
// PPF pipeline against gadesx's shipped Spanish patch, the chunk codec by identity roundtrip.
(function (root) {
  "use strict";

  // ---- disc geometry --------------------------------------------------------
  const RAW = 2352, USER = 2048, HDR = 24;              // Mode 2 Form 1 (PS1/XA)
  // STGEVT.BIN regions (LBA + user-data size), from tools/extract_boxes.py + wa2_jp_decode.py
  const DISCS = {
    en: { lba: 12586, size: 10813440, blk: 90112,  name: "Wild Arms 2 (USA) Disc 1" },
    jp: { lba: 12601, size: 13271040, blk: 110592, name: "Wild Arms 2nd Ignition (JP) Disc 1" },
  };
  const nsec = (size) => Math.ceil(size / USER);
  const rawSpan = (d) => ({ start: d.lba * RAW, len: nsec(d.size) * RAW });

  // raw 2352-byte sectors -> contiguous user data (the Python readfile())
  function rawToUser(raw, size) {
    const out = new Uint8Array(size);
    const full = Math.floor(size / USER), rem = size % USER;
    for (let s = 0; s < full; s++) out.set(raw.subarray(s * RAW + HDR, s * RAW + HDR + USER), s * USER);
    if (rem) out.set(raw.subarray(full * RAW + HDR, full * RAW + HDR + rem), full * USER);
    return out;
  }
  // user-data offset -> offset inside the raw region slice
  const userToRawOff = (u) => Math.floor(u / USER) * RAW + HDR + (u % USER);

  // ---- EDC / ECC (Mode 2 Form 1) --------------------------------------------
  // Port of the public-domain ECM codec (Neill Corlett). Verified in tests/core.test.mjs by
  // recomputing EDC+ECC of untouched US-disc sectors and comparing with the disc's own bytes.
  const eccF = new Uint8Array(256), eccB = new Uint8Array(256), edcT = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let j = ((i << 1) ^ ((i & 0x80) ? 0x11d : 0)) & 0xff;
    eccF[i] = j; eccB[i ^ j] = i;
    let edc = i;
    for (let k = 0; k < 8; k++) edc = (edc >>> 1) ^ ((edc & 1) ? 0xd8018001 : 0);
    edcT[i] = edc >>> 0;
  }
  function edcCompute(buf, off, len) {
    let edc = 0;
    for (let i = 0; i < len; i++) edc = ((edc >>> 8) ^ edcT[(edc ^ buf[off + i]) & 0xff]) >>> 0;
    return edc >>> 0;
  }
  // sec = Uint8Array window on one 2352-byte sector. Address bytes (12..15) count as ZERO for
  // mode 2. index space = 4 address bytes ++ sector[0x10..].
  function eccBlock(sec, majorCount, minorCount, majorMult, minorInc, eccOff) {
    const size = majorCount * minorCount;
    for (let major = 0; major < majorCount; major++) {
      let index = (major >> 1) * majorMult + (major & 1);
      let a = 0, b = 0;
      for (let minor = 0; minor < minorCount; minor++) {
        const t = index < 4 ? 0 : sec[0x10 + index - 4];
        index += minorInc; if (index >= size) index -= size;
        a ^= t; b ^= t; a = eccF[a];
      }
      a = eccB[eccF[a] ^ b];
      sec[eccOff + major] = a;
      sec[eccOff + major + majorCount] = a ^ b;
    }
  }
  // Recompute EDC+ECC of the Mode2Form1 sector starting at rawOff. Form 2 gets its EDC only.
  function sectorFix(raw, rawOff) {
    const sec = raw.subarray(rawOff, rawOff + RAW);
    if (sec[0x12] & 0x20) {                        // submode form-2 bit
      const edc = edcCompute(sec, 0x10, 0x91c);
      sec[0x92c] = edc & 0xff; sec[0x92d] = (edc >>> 8) & 0xff;
      sec[0x92e] = (edc >>> 16) & 0xff; sec[0x92f] = (edc >>> 24) & 0xff;
      return "form2";
    }
    const edc = edcCompute(sec, 0x10, 0x808);
    sec[0x818] = edc & 0xff; sec[0x819] = (edc >>> 8) & 0xff;
    sec[0x81a] = (edc >>> 16) & 0xff; sec[0x81b] = (edc >>> 24) & 0xff;
    eccBlock(sec, 86, 24, 2, 86, 0x81c);           // P parity
    eccBlock(sec, 52, 43, 86, 88, 0x8c8);          // Q parity
    return "form1";
  }

  // ---- PPF (PlayStation Patch File) -----------------------------------------
  // Parses v3 ("PPF30") and v2 ("PPF20"); records = absolute offsets into the raw .bin.
  function ppfParse(buf) {
    const dv = new DataView(buf.buffer, buf.byteOffset, buf.byteLength);
    const magic = String.fromCharCode(...buf.subarray(0, 5));
    const recs = [];
    let desc = "", undo = false;
    if (magic === "PPF30") {
      desc = String.fromCharCode(...buf.subarray(6, 56)).replace(/\0+$/, "").trim();
      const blockcheck = buf[57] === 1; undo = buf[58] === 1;
      let p = 60 + (blockcheck ? 1024 : 0);
      while (p + 9 <= buf.length) {
        if (buf[p] === 0x40 && String.fromCharCode(...buf.subarray(p, p + 18)) === "@BEGIN_FILE_ID.DIZ") break;
        const off = dv.getUint32(p, true) + dv.getUint32(p + 4, true) * 0x100000000;
        const len = buf[p + 8]; p += 9;
        recs.push({ off, data: buf.slice(p, p + len) }); p += len;
        if (undo) p += len;
      }
    } else if (magic === "PPF20") {
      desc = String.fromCharCode(...buf.subarray(6, 56)).replace(/\0+$/, "").trim();
      let p = 56 + 4 + 1024;                       // binlen + blockcheck
      while (p + 5 <= buf.length) {
        if (buf[p] === 0x40 && String.fromCharCode(...buf.subarray(p, p + 18)) === "@BEGIN_FILE_ID.DIZ") break;
        const off = dv.getUint32(p, true); const len = buf[p + 4]; p += 5;
        recs.push({ off, data: buf.slice(p, p + len) }); p += len;
      }
    } else throw new Error("not a PPF v2/v3 file");
    return { version: magic, desc, records: recs };
  }
  // apply the records that land inside [winStart, winStart+win.length) of the raw file
  function ppfApplyWindow(ppf, win, winStart) {
    let applied = 0;
    for (const r of ppf.records) {
      const end = r.off + r.data.length;
      if (end <= winStart || r.off >= winStart + win.length) continue;
      const from = Math.max(r.off, winStart), to = Math.min(end, winStart + win.length);
      win.set(r.data.subarray(from - r.off, to - r.off), from - winStart);
      applied++;
    }
    return applied;
  }
  // edits: [{off(absolute raw), bytes, old}] -> PPF3.0 with undo data
  function ppfBuild(desc, edits) {
    const out = [];
    const push = (...b) => out.push(...b);
    push(...[..."PPF30"].map((c) => c.charCodeAt(0)), 2);
    const d = (desc || "WA2 retranslation").slice(0, 50).padEnd(50, " ");
    push(...[...d].map((c) => c.charCodeAt(0) & 0xff));
    push(0, 0, 1, 0);                              // imagetype BIN, no blockcheck, undo=1, dummy
    for (const e of edits) {
      for (let i = 0; i < e.bytes.length; i += 255) {
        const chunk = e.bytes.subarray(i, i + 255), old = e.old.subarray(i, i + 255);
        const off = e.off + i;
        const lo = off >>> 0, hi = Math.floor(off / 0x100000000);
        push(lo & 0xff, (lo >>> 8) & 0xff, (lo >>> 16) & 0xff, (lo >>> 24) & 0xff,
             hi & 0xff, (hi >>> 8) & 0xff, (hi >>> 16) & 0xff, (hi >>> 24) & 0xff, chunk.length);
        push(...chunk, ...old);
      }
    }
    return new Uint8Array(out);
  }

  // ---- text codec ------------------------------------------------------------
  // gadesx's Spanish glyph slots (solved in tools/extract_es.py). Encoding with these bytes
  // only renders correctly on a disc whose font was repointed the same way.
  const ES_MAP = { 0x5c: "¡", 0x5e: "¿", 0x5f: "ñ", 0x7b: "ú",
                   0x7c: "ó", 0x7d: "í", 0x7e: "é", 0x7f: "á" };
  const ES_REV = Object.fromEntries(Object.entries(ES_MAP).map(([k, v]) => [v, +k]));

  // Exact mirror of tools/extract_boxes._decode_en: decode an EN sub for DISPLAY, dropping
  // unknown controls but counting them; the good-gate below reproduces the python box emission
  // (so the app's box list matches data/script/boxes.json). parseSub (stricter) governs editing.
  function decodeEnLossy(raw, useMap) {
    const out = []; let j = 0, ctrl = 0; const n = raw.length;
    while (j < n) {
      const b = raw[j];
      if (b === 0x0a && j + 1 < n && raw[j + 1] >= 0x30 && raw[j + 1] <= 0x39) { out.push("{" + String.fromCharCode(raw[j + 1]) + "}"); j += 2; continue; }
      if (b === 0x05 && j + 1 < n) { j += 2; continue; }
      if (b === 0x40) { j += 1; continue; }
      if (useMap && ES_MAP[b]) { out.push(ES_MAP[b]); j += 1; continue; }
      if (b >= 0x20 && b < 0x7f) { out.push(String.fromCharCode(b)); j += 1; continue; }
      if (b === 0x0d) { out.push(" "); j += 1; continue; }
      ctrl++; j += 1;
    }
    const text = out.join("").split(/\s+/).filter(Boolean).join(" ");
    return { text, ctrl };
  }
  function goodEn(d) {
    const letters = (d.text.match(/[a-zA-Z]/g) || []).length;
    return letters >= 3 && d.ctrl <= Math.max(2, Math.floor(d.text.length / 8));
  }

  // A sub-box parses to {prefix, text} when it is (\x05 X)* '@'? then pure text tokens
  // (printable / \x0d newline / \x0a-digit {n} name code / charmap glyph). Anything else
  // (item-ref codes 07 30 11 …, unknown controls) => {raw} and the box is read-only.
  function parseSub(bytes, useMap) {
    let j = 0; const pre = [];
    while (j + 1 < bytes.length && bytes[j] === 0x05) { pre.push(bytes[j], bytes[j + 1]); j += 2; }
    if (bytes[j] === 0x40) { pre.push(0x40); j++; }
    let text = "";
    for (; j < bytes.length; j++) {
      const b = bytes[j];
      if (b === 0x0d) { text += "\n"; continue; }
      if (b === 0x0a && j + 1 < bytes.length && bytes[j + 1] >= 0x30 && bytes[j + 1] <= 0x39) {
        text += "{" + String.fromCharCode(bytes[++j]) + "}"; continue;
      }
      if (useMap && ES_MAP[b]) { text += ES_MAP[b]; continue; }
      if (b >= 0x20 && b < 0x7f) { text += String.fromCharCode(b); continue; }
      return { raw: bytes };                       // unknown control -> read-only
    }
    return { prefix: new Uint8Array(pre), text };
  }
  // text -> bytes, or {err} on a character the disc can't show
  function encodeText(text, useMap) {
    const out = [];
    for (let i = 0; i < text.length; i++) {
      const c = text[i];
      if (c === "\n") { out.push(0x0d); continue; }
      if (c === "{" && /^\{\d\}/.test(text.slice(i))) { out.push(0x0a, text.charCodeAt(i + 1)); i += 2; continue; }
      const cc = c.charCodeAt(0);
      if (cc >= 0x20 && cc < 0x7f) { out.push(cc); continue; }
      if (useMap && ES_REV[c] !== undefined) { out.push(ES_REV[c]); continue; }
      return { err: `character ${JSON.stringify(c)} not encodable` + (ES_REV[c] !== undefined ? " (enable the gadesx charmap)" : "") };
    }
    return { bytes: new Uint8Array(out) };
  }
  // subs: [{prefix,text}|{raw}]; capacity = chunk content bytes (frame..NUL exclusive).
  // Shorter output is padded with 0x20 before the NUL — the gadesx model, proven on hardware.
  function rebuildChunk(subs, capacity, useMap) {
    const parts = [];
    for (const s of subs) {
      if (s.raw) { parts.push(s.raw); continue; }
      const enc = encodeText(s.text, useMap);
      if (enc.err) return { err: enc.err };
      const merged = new Uint8Array(s.prefix.length + enc.bytes.length);
      merged.set(s.prefix); merged.set(enc.bytes, s.prefix.length);
      parts.push(merged);
    }
    const total = parts.reduce((a, p) => a + p.length, 0) + (parts.length - 1) * 2;
    if (total > capacity) return { err: `over budget: ${total} > ${capacity} bytes`, total };
    const out = new Uint8Array(capacity).fill(0x20);
    let p = 0;
    parts.forEach((part, k) => {
      if (k) { out[p] = 0x10; out[p + 1] = 0x0c; p += 2; }
      out.set(part, p); p += part.length;
    });
    return { bytes: out, total };
  }

  // Stable digest of a box's English source, used as the migration/import guard: a strings-JSON
  // row whose `en` no longer matches the disc is refused rather than written to the wrong box.
  // Lives here rather than in app.js so the editor and tools/migrate_db_to_boxes.mjs cannot
  // drift apart — a mismatch would silently refuse every migrated row.
  function digest(str) {
    let h = 0x811c9dc5;
    for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
    return h.toString(16).padStart(8, "0");
  }

  // On-screen fit. Distinct from the BYTE budget: the script carries explicit \x0d line
  // breaks (the game does not auto-wrap), so a box can sit inside its chunk capacity and still
  // overflow the visible window. Measured over all 21,644 EN boxes: 99.5% are <=3 lines and
  // the longest-line mass sits at <=39 chars, matching the 3 x ~35 standard box.
  const FIT = { lines: 3, cols: 35 };
  function fitReport(text) {
    const lines = String(text == null ? "" : text).split("\n");
    const longest = lines.reduce((m, l) => Math.max(m, l.length), 0);
    return {
      lines, nLines: lines.length, longest,
      overLines: lines.length > FIT.lines,
      overCols: longest > FIT.cols,
      over: lines.length > FIT.lines || longest > FIT.cols,
      maxLines: FIT.lines, maxCols: FIT.cols,
    };
  }

  // House-style lint. These are not my opinions -- they are the hard rules in
  // docs/WA2_RE_STYLE_GUIDE.md (§1-§3), which is the project's declared source of truth for how
  // a retranslated line is written. Encoding them here means the editor enforces the same
  // standard the offline FINAL-file workflow does, at the moment of typing.
  const GLOSSARY_FIXES = [                       // official EN -> the project's decided RE term
    [/\bmercs?\b/i, "|Wandering Crows| (the project's decided term for 渡り烏, not \"Mercs\")"],
    [/\bsebok\b/i, "T'Bok (canonical spelling)"],
    [/\bthe ruins\b/i, "\"ruins district\" where 遺跡街 is meant (JP 街 = district)"],
  ];
  const NAME_WORDS = [["ashley", "0"], ["brad", "1"], ["lilka", "2"], ["marina", "3"],
                      ["kanon", "4"], ["liz", "5"], ["ard", "6"]];

  function lintText(text, opts) {
    const t = String(text == null ? "" : text);
    const out = [];
    if (!t.trim()) return out;
    const add = (sev, rule, msg) => out.push({ sev, rule, msg });

    // §2 punctuation
    if (/—|(?:^|[^-])--(?:[^-]|$)/.test(t))
      add("error", "em-dash", "no em dashes or `--` — they read as machine output; use a comma, a period, or two sentences");
    // §2 forbids a BOX ending on a comma or a dangling conjunction, because the box closes there
    // and reads as truncated. An interior line break may absolutely end on a comma — the sentence
    // simply continues on the next line, which is normal in a 3-line box. Checking every line
    // instead of the last was rejecting correct translations.
    const lastLine = t.split("\n").map((x) => x.trim()).filter(Boolean).pop() || "";
    if (/,$/.test(lastLine))
      add("error", "trailing-comma", "a box must not END on a comma — use `...` for a lead-in, or make it a complete sentence");
    if (/\b(and|but|so|then)$/i.test(lastLine))
      add("warn", "dangling-conj", `box ends on "${lastLine.split(/\s+/).pop()}" — finish the thought or end with \`...\``);
    const commas = (t.match(/,/g) || []).length;
    if (commas >= 3 && !/[.!?]/.test(t.replace(/\.\.\./g, "")))
      add("warn", "run-on", `${commas} commas and no sentence end — break the clause chain into sentences`);

    // §3 name codes: a renameable character spelled out where a {n} belongs
    for (const [word, code] of NAME_WORDS) {
      const re = new RegExp("\\b" + word + "\\b", "i");
      if (re.test(t) && !t.includes("{" + code + "}"))
        add("warn", "name-code", `"${word}" is player-renameable — use {${code}} instead of spelling it out`);
    }
    // emphasis markers must be balanced
    const bars = (t.match(/\|/g) || []).length;
    if (bars % 2) add("error", "emphasis", "unbalanced |emphasis| marker — the game's bars must come in pairs");

    // glossary decisions
    for (const [re, msg] of GLOSSARY_FIXES) if (re.test(t)) add("warn", "glossary", "prefer " + msg);

    // §5 / insert README: an annotation inside the body gets reflowed into the box
    if (/(^|\s)#\s/.test(t)) add("warn", "inline-note", "a `#` note belongs on its own line, never inside the box text");

    // sanity against the source
    if (opts && opts.en) {
      const codes = (x) => (x.match(/\{[0-9]\}/g) || []).sort().join("");
      if (codes(opts.en) !== codes(t))
        add("warn", "codes-changed", `name codes differ from the original box (${codes(opts.en) || "none"} → ${codes(t) || "none"})`);
      const star = (x) => x.trimStart().startsWith("*");
      if (star(opts.en) !== star(t))
        add("warn", "panel-marker", star(opts.en) ? "the original is an examine panel — keep the leading `*`" : "leading `*` marks an examine panel; the original isn't one");
    }
    return out;
  }

  // Nameplate: a sub beginning \x05 N selects the speaker (N is an ASCII digit indexing the
  // same runtime name table as the inline {n} codes). This is the only reliable speaker signal
  // in the disc bytes -- a "short first \x0d segment" heuristic was tried and rejected, it
  // mis-flagged examine panels like "*Handle with Care!" as speakers.
  function speakerCode(raw) {
    return (raw && raw.length > 1 && raw[0] === 0x05 && raw[1] >= 0x30 && raw[1] <= 0x39)
      ? String.fromCharCode(raw[1]) : null;
  }

  // Walk one block of user data into the chunk model the editor operates on.
  // chunk = frame byte(s) .. NUL; subs = \x10\x0c-splits of the content. Structure only —
  // display/gating live in decodeEnLossy/goodEn, editing in parseSub/rebuildChunk.
  function walkChunks(data, lo, hi) {
    const chunks = []; let i = lo;
    while (i < hi - 1) {
      let frame = null, flen = 0;
      if (data[i] === 0x10 && data[i + 1] === 0x0c) { frame = "idx"; flen = 2; }
      else if (data[i] === 0x06) { frame = "inline"; flen = 1; }
      else if (data[i] === 0x0d) { frame = "cont"; flen = 1; }
      if (!frame) { i++; continue; }
      const s = i + flen;
      if (s >= hi) break;
      let k = s; while (k < hi && data[k] !== 0x00) k++;
      if (k <= s) { i++; continue; }
      const content = data.slice(s, k);
      const subs = []; let last = 0;
      for (let p = 0; p + 1 < content.length; p++)
        if (content[p] === 0x10 && content[p + 1] === 0x0c) { subs.push(content.slice(last, p)); last = p + 2; p++; }
      subs.push(content.slice(last));
      // only keep chunks that contain at least one python-good EN box (mirrors extract_boxes:
      // a frame with no good sub is not treated as a box boundary there either)
      const good = subs.map((b) => b.length ? goodEn(decodeEnLossy(b, false)) : false);
      if (good.some(Boolean)) {
        chunks.push({ off: i, frame, start: s, cap: k - s, subs, good });
        i = k; continue;
      }
      i++;
    }
    return chunks;
  }

  const api = { RAW, USER, HDR, DISCS, nsec, rawSpan, rawToUser, userToRawOff,
                edcCompute, sectorFix, ppfParse, ppfApplyWindow, ppfBuild,
                ES_MAP, ES_REV, parseSub, encodeText, rebuildChunk, decodeEnLossy, goodEn, walkChunks, fitReport, speakerCode, FIT, lintText, digest };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.WA2Core = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
