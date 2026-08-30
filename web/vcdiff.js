// Minimal VCDIFF (RFC 3284) encoder — shared by the ISO editor (iso.js) and the Node tests.
// It turns a set of known byte edits against a source file into a standard .xdelta patch that
// `xdelta3 -d -s <pristine> <patch> <out>` (or any VCDIFF decoder) applies to reproduce the
// edited file. We don't diff the 4 GB disc: the web editor already tracks every changed byte
// range, so we synthesize the patch directly as COPY-from-source + ADD-literal windows.
//
// Format choices (kept deliberately simple, all standard / decoder-required-to-support):
//   • header: magic D6 C3 C4 00, Hdr_Indicator 0x00 (no secondary compressor, no app header)
//   • per window: VCD_SOURCE, source segment = the same byte range this window outputs
//   • instructions use only the RFC default code table opcodes 1 (ADD, explicit size) and
//     19 (COPY, explicit size, mode 0 = VCD_SELF); no caches, no secondary compression.
// The whole target is tiled into windows so the decoder reproduces the entire file; unchanged
// windows are a single COPY, so the patch stays tiny even for a multi-GB disc.
(function (root) {
  // VCDIFF integer: base-128, big-endian, 0x80 continuation bit on all but the last byte.
  function pushInt(arr, n) {
    if (n < 0) throw new Error("vcdiff int < 0");
    const bytes = [n & 0x7f]; n = Math.floor(n / 128);
    while (n > 0) { bytes.push((n & 0x7f) | 0x80); n = Math.floor(n / 128); }
    for (let i = bytes.length - 1; i >= 0; i--) arr.push(bytes[i]);   // most-significant first
  }

  // edits: [{off, data:Uint8Array}] (data = the NEW bytes). sourceSize: total file length.
  // opts.window: target window size (default 8 MiB). Returns a Uint8Array patch.
  function buildXdelta(sourceSize, edits, opts) {
    const WIN = (opts && opts.window) || (8 * 1024 * 1024);
    edits = (edits || []).filter((e) => e.data && e.data.length)
      .map((e) => ({ off: e.off, data: e.data })).sort((a, b) => a.off - b.off);
    for (let i = 1; i < edits.length; i++)
      if (edits[i].off < edits[i - 1].off + edits[i - 1].data.length)
        throw new Error("vcdiff: overlapping edits");
    // Split any edit that straddles a window boundary so each piece lives in one window.
    const split = [];
    for (const e of edits) {
      let o = e.off, d = e.data;
      while (o + d.length > (Math.floor(o / WIN) + 1) * WIN) {
        const cut = (Math.floor(o / WIN) + 1) * WIN;
        split.push({ off: o, data: d.subarray(0, cut - o) });
        d = d.subarray(cut - o); o = cut;
      }
      split.push({ off: o, data: d });
    }
    edits = split;

    const out = [0xd6, 0xc3, 0xc4, 0x00, 0x00];   // magic + Hdr_Indicator (no app header)
    let ei = 0;                                    // index into edits, advanced across windows

    for (let ws = 0; ws < sourceSize; ws += WIN) {
      const we = Math.min(ws + WIN, sourceSize);
      const tlen = we - ws;
      const data = [], inst = [], addr = [];       // three window sections

      const emitCopy = (srcRel, len) => {          // COPY len bytes from source-segment offset srcRel
        if (len <= 0) return;
        inst.push(19); pushInt(inst, len);         // opcode 19 = COPY size0 mode0; size follows
        pushInt(addr, srcRel);                     // mode 0 (SELF): absolute addr = segment offset
      };
      const emitAdd = (bytes) => {
        if (!bytes.length) return;
        inst.push(1); pushInt(inst, bytes.length); // opcode 1 = ADD size0; size follows
        for (let i = 0; i < bytes.length; i++) data.push(bytes[i]);
      };

      let p = ws;
      while (ei < edits.length && edits[ei].off < we) {
        const e = edits[ei];
        if (e.off + e.data.length > we) throw new Error("vcdiff: edit spans a window boundary");
        emitCopy(p - ws, e.off - p);               // unchanged run before the edit
        emitAdd(e.data);                           // the edited bytes
        p = e.off + e.data.length;
        ei++;
      }
      emitCopy(p - ws, we - p);                     // trailing unchanged run

      // Delta encoding block: [target size][Delta_Indicator][|data|][|inst|][|addr|] data inst addr
      const block = [];
      pushInt(block, tlen);
      block.push(0x00);                             // Delta_Indicator: no section compression
      pushInt(block, data.length);
      pushInt(block, inst.length);
      pushInt(block, addr.length);
      for (const b of data) block.push(b);
      for (const b of inst) block.push(b);
      for (const b of addr) block.push(b);

      out.push(0x01);                              // Win_Indicator = VCD_SOURCE
      pushInt(out, tlen);                          // source segment size (= this window's span)
      pushInt(out, ws);                            // source segment position
      pushInt(out, block.length);                  // length of the delta encoding
      for (const b of block) out.push(b);
    }
    return Uint8Array.from(out);
  }

  // =========================================================================================
  // DECODER — enough of RFC 3284 to apply real patches, so the editor can consume a mod and
  // not just publish one. Unlike the encoder (which only has to emit one shape), this must
  // read whatever xdelta3 produced: the full default code table, all nine address modes with
  // both caches, RUN, VCD_TARGET windows, app headers and xdelta3's VCD_ADLER32 extension.
  //
  // The ONE thing it deliberately does not do is secondary compression. `xdelta3 -e` defaults
  // to LZMA-compressing the delta sections (VCD_SECONDARY + VCD_DATACOMP/VCD_INSTCOMP), and
  // shipping an LZMA decoder here would dwarf the rest of the editor. Such a patch is detected
  // and reported with the fix (`-S none`) rather than mis-decoded.
  // =========================================================================================
  const VCD_DECOMPRESS = 0x01, VCD_CODETABLE = 0x02;          // Hdr_Indicator
  const VCD_SOURCE = 0x01, VCD_TARGET = 0x02, VCD_ADLER32 = 0x04;   // Win_Indicator
  const NOOP = 0, ADD = 1, RUN = 2, COPY = 3;

  // RFC 3284 §5.4 — the default code table, built by the spec's own algorithm rather than
  // pasted as 256 magic rows (a transcription slip here would silently mis-decode patches).
  // Each entry is [inst1, size1, mode1, inst2, size2, mode2]; size 0 means "size follows in
  // the instruction stream".
  function defaultCodeTable() {
    const t = [];
    t.push([RUN, 0, 0, NOOP, 0, 0]);                                     // 1
    for (let s = 0; s <= 17; s++) t.push([ADD, s, 0, NOOP, 0, 0]);        // 18
    for (let m = 0; m <= 8; m++) {                                       // 9 * 16
      t.push([COPY, 0, m, NOOP, 0, 0]);
      for (let s = 4; s <= 18; s++) t.push([COPY, s, m, NOOP, 0, 0]);
    }
    for (let m = 0; m <= 5; m++)                                         // 6 * 4 * 3
      for (let a = 1; a <= 4; a++)
        for (let c = 4; c <= 6; c++) t.push([ADD, a, 0, COPY, c, m]);
    for (let m = 6; m <= 8; m++)                                         // 3 * 4
      for (let a = 1; a <= 4; a++) t.push([ADD, a, 0, COPY, 4, m]);
    for (let m = 0; m <= 8; m++) t.push([COPY, 4, m, ADD, 1, 0]);        // 9
    if (t.length !== 256) throw new Error("vcdiff: code table is " + t.length + ", expected 256");
    return t;
  }
  let CODE_TABLE = null;

  // RFC 3284 §5.3 — address cache. Modes 0/1 are self/here-relative; 2..5 read the "near"
  // ring; 6..8 read the "same" hash. Every decoded address feeds both caches.
  function AddrCache(nearSize, sameSize) {
    const near = new Int32Array(nearSize), same = new Int32Array(sameSize * 256);
    let nextSlot = 0;
    return {
      reset() { near.fill(0); same.fill(0); nextSlot = 0; },
      update(addr) {
        if (nearSize) { near[nextSlot] = addr; nextSlot = (nextSlot + 1) % nearSize; }
        if (sameSize) same[addr % (sameSize * 256)] = addr;
      },
      decode(mode, here, addrBuf, ap) {
        let addr;
        if (mode === 0) addr = readInt(addrBuf, ap);
        else if (mode === 1) addr = here - readInt(addrBuf, ap);
        else if (mode - 2 < nearSize) addr = near[mode - 2] + readInt(addrBuf, ap);
        else addr = same[(mode - (2 + nearSize)) * 256 + addrBuf[ap.i++]];
        this.update(addr);
        return addr;
      },
    };
  }

  // adler32 (RFC 1950) — used to verify a decoded window against the checksum xdelta3 stored.
  function adler32(bytes) {
    let a = 1, b = 0;
    for (let i = 0; i < bytes.length;) {
      // chunk so the sums can't exceed 2^31 before the modulo
      const end = Math.min(i + 5552, bytes.length);
      for (; i < end; i++) { a += bytes[i]; b += a; }
      a %= 65521; b %= 65521;
    }
    return ((b << 16) | a) >>> 0;
  }

  function readInt(buf, pos) {
    let n = 0, b, guard = 0;
    do {
      if (pos.i >= buf.length) throw new Error("vcdiff: truncated integer");
      if (++guard > 8) throw new Error("vcdiff: integer too large");
      b = buf[pos.i++]; n = n * 128 + (b & 0x7f);
    } while (b & 0x80);
    return n;
  }

  // Walk a patch window by window. `onWindow(win)` receives
  //   { targetStart, targetLen, sourceStart, sourceLen, fromTarget, decode(sourceBytes) }
  // and returns nothing; `decode` materialises that window's target bytes given its source
  // segment (or the already-decoded target, for a VCD_TARGET window). Splitting it this way
  // lets a caller pull only the source ranges it actually needs — decisive for a 4 GB file
  // that can't be held in memory.
  function eachWindow(patch, onWindow) {
    if (patch.length < 5 || patch[0] !== 0xd6 || patch[1] !== 0xc3 || patch[2] !== 0xc4)
      throw new Error("Not a VCDIFF/.xdelta patch (bad magic).");
    if (patch[3] !== 0x00) throw new Error("Unsupported VCDIFF version " + patch[3] + ".");
    const p = { i: 4 };
    const hdr = patch[p.i++];
    if (hdr & VCD_DECOMPRESS)
      throw new Error("This patch uses secondary compression, which this editor can't read. " +
        "Re-create it with:  xdelta3 -e -S none -s <source> <target> <patch>");
    if (hdr & VCD_CODETABLE)
      throw new Error("This patch ships a custom code table, which this editor can't read.");
    if (hdr & 0x04) { const n = readInt(patch, p); p.i += n; }        // app header — skip
    if (!CODE_TABLE) CODE_TABLE = defaultCodeTable();
    const cache = AddrCache(4, 3);

    let targetStart = 0;
    while (p.i < patch.length) {
      const win = patch[p.i++];
      if (win & ~(VCD_SOURCE | VCD_TARGET | VCD_ADLER32))
        throw new Error("Unsupported window indicator 0x" + win.toString(16) + ".");
      let sourceLen = 0, sourceStart = 0;
      if (win & (VCD_SOURCE | VCD_TARGET)) { sourceLen = readInt(patch, p); sourceStart = readInt(patch, p); }
      readInt(patch, p);                                              // delta encoding length
      const targetLen = readInt(patch, p);
      const deltaInd = patch[p.i++];
      if (deltaInd) throw new Error("This patch compresses its delta sections, which this editor " +
        "can't read. Re-create it with:  xdelta3 -e -S none -s <source> <target> <patch>");
      const dlen = readInt(patch, p), ilen = readInt(patch, p), alen = readInt(patch, p);
      // xdelta3's VCD_ADLER32 extension: an adler32 of this window's TARGET bytes. Keeping it
      // is what lets an applied patch be verified — a wrong or already-modified source disc
      // produces different target bytes, so the checksum won't match. (The patches this editor
      // *exports* carry no checksum; the ones it applies usually do.)
      let adler = null;
      if (win & VCD_ADLER32) {
        adler = ((patch[p.i] << 24) | (patch[p.i + 1] << 16) | (patch[p.i + 2] << 8) | patch[p.i + 3]) >>> 0;
        p.i += 4;
      }
      const data = patch.subarray(p.i, p.i + dlen); p.i += dlen;
      const inst = patch.subarray(p.i, p.i + ilen); p.i += ilen;
      const addr = patch.subarray(p.i, p.i + alen); p.i += alen;
      if (p.i > patch.length) throw new Error("vcdiff: truncated window");

      const fromTarget = !!(win & VCD_TARGET);
      const w = {
        targetStart, targetLen, sourceStart, sourceLen, adler32: adler, fromTarget,
        // Walk the instructions WITHOUT any source bytes, returning the spans of this window's
        // target that don't provably come from the same position of the same file. Applying a
        // patch to a multi-GB disc hinges on this: it narrows "what might have changed" to a
        // few kilobytes so the caller reads only those ranges instead of the whole disc.
        //
        // It tracks PROVENANCE, not just the literal COPY address. xdelta3 bounds its source
        // window, so the tail of a large target is encoded as copies from earlier *target*
        // bytes rather than from the source; those are still unchanged data, and following the
        // provenance through them is the difference between flagging a few KB and flagging
        // hundreds of MB. A COPY that happens to fetch equal bytes from a different offset is
        // still reported — this over-reports but never under-reports, so callers must confirm
        // candidates against real bytes before trusting them.
        plan() {
          const prov = new Int32Array(targetLen).fill(-1);   // absolute source position, or -1
          const ip = { i: 0 }, ap = { i: 0 };
          let tp = 0;
          cache.reset();
          while (ip.i < inst.length) {
            const row = CODE_TABLE[inst[ip.i++]];
            for (let half = 0; half < 2; half++) {
              const op = row[half * 3], sz0 = row[half * 3 + 1], mode = row[half * 3 + 2];
              if (op === NOOP) continue;
              const size = sz0 === 0 ? readInt(inst, ip) : sz0;
              if (tp + size > targetLen) throw new Error("vcdiff: instruction overruns the window");
              if (op === ADD || op === RUN) { tp += size; continue; }   // stays -1 = new bytes
              let a = cache.decode(mode, sourceLen + tp, addr, ap);
              for (let k = 0; k < size; k++, a++, tp++) {
                if (fromTarget) continue;                      // VCD_TARGET: provenance unknown
                prov[tp] = a < sourceLen ? sourceStart + a
                  : (a - sourceLen < tp ? prov[a - sourceLen] : -1);   // follow self-references
              }
            }
          }
          const spans = [];
          for (let i = 0; i < targetLen; i++) {
            if (prov[i] === targetStart + i) continue;
            const from = i;
            while (i < targetLen && prov[i] !== targetStart + i) i++;
            spans.push([from, i]);
          }
          return spans;
        },
        // src must be the `sourceLen` bytes at `sourceStart` (of the source file, or of the
        // already-decoded target when fromTarget).
        decode(src) {
          if (sourceLen && (!src || src.length < sourceLen)) throw new Error("vcdiff: short source segment");
          const out = new Uint8Array(targetLen);
          const ip = { i: 0 }, ap = { i: 0 };
          let dp = 0, tp = 0;
          cache.reset();
          while (ip.i < inst.length) {
            const row = CODE_TABLE[inst[ip.i++]];
            for (let half = 0; half < 2; half++) {
              const op = row[half * 3], sz0 = row[half * 3 + 1], mode = row[half * 3 + 2];
              if (op === NOOP) continue;
              const size = sz0 === 0 ? readInt(inst, ip) : sz0;
              if (tp + size > targetLen) throw new Error("vcdiff: instruction overruns the window");
              if (op === ADD) { for (let k = 0; k < size; k++) out[tp++] = data[dp++]; }
              else if (op === RUN) { const b = data[dp++]; for (let k = 0; k < size; k++) out[tp++] = b; }
              else {
                // Addresses live in one space: [0, sourceLen) is the source segment,
                // [sourceLen, ...) is the part of this window already emitted (so a COPY
                // can reference its own output — that's how RLE-ish runs are encoded).
                let a = cache.decode(mode, sourceLen + tp, addr, ap);
                for (let k = 0; k < size; k++, a++) out[tp++] = a < sourceLen ? src[a] : out[a - sourceLen];
              }
            }
          }
          if (tp !== targetLen) throw new Error("vcdiff: window produced " + tp + " of " + targetLen + " bytes");
          if (adler !== null && adler32(out) !== adler)
            throw new Error("Checksum mismatch — this patch was built against a different " +
              "source file (or the disc has already been modified).");
          return out;
        },
      };
      onWindow(w);
      targetStart += targetLen;
    }
    return targetStart;   // total target size
  }

  // Convenience whole-file decode — used by the tests and fine for small inputs. The ISO
  // editor does NOT use this (it would mean materialising 4 GB); see applyToRange.
  function decode(source, patch) {
    const chunks = [];
    let produced = 0;
    const total = eachWindow(patch, (w) => {
      const src = w.fromTarget
        ? concat(chunks, produced).subarray(w.sourceStart, w.sourceStart + w.sourceLen)
        : source.subarray(w.sourceStart, w.sourceStart + w.sourceLen);
      const out = w.decode(src);
      chunks.push(out); produced += out.length;
    });
    const all = concat(chunks, produced);
    if (all.length !== total) throw new Error("vcdiff: size mismatch");
    return all;
  }
  function concat(chunks, total) {
    const all = new Uint8Array(total);
    let o = 0; for (const c of chunks) { all.set(c, o); o += c.length; }
    return all;
  }

  const api = { buildXdelta, pushInt, eachWindow, decode, defaultCodeTable, adler32 };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.Vcdiff = api;
})(typeof self !== "undefined" ? self : globalThis);
