// WA2 Translation Editor — UI glue. All byte-level logic lives in wa2-core.js (tested against
// the real discs) and wa2-jp.js (parity-tested against the python tools). This file only:
// loads files, renders blocks, tracks edits, and drives the exporters.
"use strict";
const C = WA2Core, J = WA2JP, V = Vcdiff;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const SUPPORTS_FS = "showOpenFilePicker" in window;
const NBLK = 120;

const SLOTS = {
  en1: { lang: "en", label: "US Disc 1", role: "target" },
  en2: { lang: "en", label: "US Disc 2", role: "target" },
  jp1: { lang: "jp", label: "JP Disc 1", role: "source" },
  jp2: { lang: "jp", label: "JP Disc 2", role: "source" },
  es:  { lang: "es", label: "Spanish patch", role: "reference" },
};

const S = {
  d: {},             // slot -> {file, handle, raw, ud, name, codecOk}
  jpTables: false,
  blk: 0,
  cache: {},
  tr: {},
};
// STGEVT.BIN is byte-identical across disc 1 and disc 2 (verified at the raw sector level for
// both EN and JP), so any loaded disc of a language serves as that language's script, and an
// edit at a given offset is valid for every disc of that language.
const enPrimary = () => S.d.en1 || S.d.en2 || null;
const jpSource  = () => S.d.jp1 || S.d.jp2 || null;
const enTargets = () => ["en1", "en2"].filter((k) => S.d[k]).map((k) => ({ key: k, ...S.d[k] }));

// ---------- persistence ----------
const LS_KEY = "wa2tr-v1";
function saveTr() {
  try { localStorage.setItem(LS_KEY, JSON.stringify(S.tr)); } catch (e) {}
  const n = Object.keys(S.tr).length;
  const ec = $("#editCount"); if (ec) ec.textContent = `${n} edit${n === 1 ? "" : "s"}`;
}
try { S.tr = JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch (e) { S.tr = {}; }

// IndexedDB: FileSystemFileHandles are structured-cloneable, so on Chromium we can remember the
// actual discs and re-open them next visit (after a permission click) instead of re-picking four
// files. Elsewhere handles don't exist, so we remember names only and show them as a reminder.
const IDB = (() => {
  let dbp = null;
  const open = () => dbp || (dbp = new Promise((res, rej) => {
    const r = indexedDB.open("wa2-editor", 1);
    r.onupgradeneeded = () => r.result.createObjectStore("kv");
    r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error);
  }));
  const tx = async (mode, fn) => {
    const db = await open();
    return new Promise((res, rej) => {
      const t = db.transaction("kv", mode), st = t.objectStore("kv");
      const out = fn(st);
      t.oncomplete = () => res(out && out.result !== undefined ? out.result : undefined);
      t.onerror = () => rej(t.error);
    });
  };
  return {
    get: (k) => tx("readonly", (st) => st.get(k)).catch(() => undefined),
    set: (k, v) => tx("readwrite", (st) => st.put(v, k)).catch(() => {}),
    del: (k) => tx("readwrite", (st) => st.delete(k)).catch(() => {}),
  };
})();

async function rememberSlot(slot, file, handle) {
  const meta = (await IDB.get("meta")) || {};
  meta[slot] = { name: file.name, size: file.size, at: Date.now() };
  await IDB.set("meta", meta);
  if (handle) {
    const hs = (await IDB.get("handles")) || {};
    hs[slot] = handle;
    await IDB.set("handles", hs);
  }
}
async function forgetAll() {
  await IDB.del("meta"); await IDB.del("handles");
  $("#restoreBar").classList.add("hidden");
}

// ---------- file loading ----------
async function pickFile(slot) {
  const wantHandle = SUPPORTS_FS;
  if (wantHandle) {
    try {
      const [h] = await window.showOpenFilePicker({
        types: [{ description: slot === "es" ? "PPF patch or disc image" : "disc image",
                  accept: { "application/octet-stream": slot === "es" ? [".ppf", ".bin"] : [".bin", ".img", ".iso"] } }],
      });
      return loadSlot(slot, await h.getFile(), h);
    } catch (e) { if (e && e.name === "AbortError") return; }
  }
  const inp = document.createElement("input");
  inp.type = "file";
  inp.onchange = () => inp.files[0] && loadSlot(slot, inp.files[0], null);
  inp.click();
}

const stEl = (slot) => document.querySelector(`[data-st="${slot}"]`);
function setStatus(slot, html, filled) {
  const el = stEl(slot); if (el) el.innerHTML = html;
  const box = document.querySelector(`.drop[data-slot="${slot}"]`);
  if (box) box.classList.toggle("filled", !!filled);
}

async function loadRegion(file, disc) {
  const span = C.rawSpan(disc);
  if (file.size < span.start + span.len)
    throw new Error(`file too small for ${disc.name} — wrong disc, or not a raw 2352-byte/sector .bin`);
  const raw = new Uint8Array(await file.slice(span.start, span.start + span.len).arrayBuffer());
  return { raw, ud: C.rawToUser(raw, disc.size) };
}

function codecSelfCheck(raw) {
  let okc = 0; const n = 64;
  for (let s = 0; s < n; s++) {
    const orig = raw.slice(s * C.RAW, (s + 1) * C.RAW);
    const work = orig.slice();
    work.fill(0, 0x818, 0x930);
    if (C.sectorFix(work, 0) === "form1" && work.every((b, i) => b === orig[i])) okc++;
  }
  return okc === n;
}

// Cross-check a newly loaded disc against an already-loaded disc of the same language.
// They must match: same script container on both discs. A mismatch means an unexpected
// revision/variant, and silently editing one would desync the pair.
function crossCheck(slot) {
  const lang = SLOTS[slot].lang;
  const peers = Object.keys(S.d).filter((k) => k !== slot && SLOTS[k] && SLOTS[k].lang === lang && S.d[k].raw);
  for (const p of peers) {
    const a = S.d[slot].raw, b = S.d[p].raw;
    if (a.length !== b.length) return `differs from ${SLOTS[p].label} (region size)`;
    for (let i = 0; i < a.length; i++) if (a[i] !== b[i])
      return `script region differs from ${SLOTS[p].label} at 0x${i.toString(16)} — unexpected variant; patches may desync`;
  }
  return null;
}

async function loadDisc(slot, file, handle) {
  const lang = SLOTS[slot].lang;
  const disc = C.DISCS[lang];
  setStatus(slot, "reading…");
  const { raw, ud } = await loadRegion(file, disc);
  if (lang === "en") {
    const probe = C.walkChunks(ud, 0, disc.blk);
    if (probe.length < 30) throw new Error("STGEVT script structure not found — is this a US disc?");
    const codecOk = codecSelfCheck(raw);
    S.d[slot] = { file, handle, raw, ud, name: file.name, codecOk };
    const warn = crossCheck(slot);
    setStatus(slot, `<b>${esc(file.name)}</b> ✓ · ${probe.length} chunks in block 0 · sector codec ${
      codecOk ? "verified" : "<b style='color:#e57373'>MISMATCH — exports disabled</b>"}` +
      (warn ? `<div class="warnline">⚠ ${esc(warn)}</div>` : ""), true);
  } else {
    if (!S.jpTables) { J.init(await (await fetch("data/jp_tables.json")).json()); S.jpTables = true; }
    const probe = J.jpBoxes(ud, 0);
    if (probe.length < 20) throw new Error("JP STGEVT structure not found — is this a JP disc?");
    S.d[slot] = { file, handle, raw, ud, name: file.name };
    const warn = crossCheck(slot);
    setStatus(slot, `<b>${esc(file.name)}</b> ✓ · ${probe.length} JP boxes in block 0` +
      (warn ? `<div class="warnline">⚠ ${esc(warn)}</div>` : ""), true);
  }
}

async function loadES(slot, file) {
  setStatus(slot, "reading…");
  const en = enPrimary();
  if (/\.ppf$/i.test(file.name)) {
    if (!en) throw new Error("load a US disc first — the PPF is applied on top of it");
    const ppf = C.ppfParse(new Uint8Array(await file.arrayBuffer()));
    const span = C.rawSpan(C.DISCS.en);
    const win = en.raw.slice();
    const applied = C.ppfApplyWindow(ppf, win, span.start);
    S.d.es = { ud: C.rawToUser(win, C.DISCS.en.size), from: "ppf", name: file.name };
    setStatus(slot, `<b>${esc(file.name)}</b> ✓ · ${ppf.version} "${esc(ppf.desc)}" · ${applied} records in script region`, true);
  } else {
    const { ud } = await loadRegion(file, C.DISCS.en);
    S.d.es = { ud, from: "bin", name: file.name };
    setStatus(slot, `<b>${esc(file.name)}</b> ✓ (pre-patched disc)`, true);
  }
}

async function loadSlot(slot, file, handle) {
  try {
    if (slot === "es") await loadES(slot, file);
    else await loadDisc(slot, file, handle);
    await rememberSlot(slot, file, handle);
    S.cache = {};
    refreshAvailability();
    renderBlock();
  } catch (e) {
    setStatus(slot, "✗ " + esc(e.message));
  }
}

function refreshAvailability() {
  const en = enPrimary();
  const on = !!en;
  $("#navCard").classList.toggle("hidden", !on);
  $("#exportCard").classList.toggle("hidden", !on);
  const codecOk = enTargets().every((t) => t.codecOk);
  const writable = enTargets().filter((t) => t.handle).length;
  $("#writeInPlace").disabled = !(writable && codecOk);
  $("#writeInPlace").textContent = writable > 1 ? `Write ${writable} discs in place` : "Write disc in place";
  $("#saveCopy").disabled = !on || !codecOk || !("showSaveFilePicker" in window);
  const tgt = enTargets();
  $("#targetNote").innerHTML = tgt.length
    ? `patch targets: <b>${tgt.map((t) => SLOTS[t.key].label).join(" + ")}</b>` +
      (tgt.length === 1 ? ` — <span class="warnline">disc 2 not loaded; it will keep the original text</span>` : "")
    : "";
}

// ---------- session restore ----------
async function initRestore() {
  const meta = (await IDB.get("meta")) || {};
  const keys = Object.keys(meta);
  if (!keys.length) return;
  $("#restoreList").textContent = keys.map((k) => `${SLOTS[k] ? SLOTS[k].label : k}: ${meta[k].name}`).join(" · ");
  $("#restoreBar").classList.remove("hidden");
  const hs = (await IDB.get("handles")) || {};
  if (!Object.keys(hs).length) {
    $("#restoreBtn").textContent = "Re-pick files";
    $("#restoreBtn").title = "this browser can't reopen files automatically — pick them again";
    return;
  }
  // If the origin still holds permission, reload with no click at all.
  let auto = true;
  for (const k of Object.keys(hs)) {
    try { if ((await hs[k].queryPermission({ mode: "read" })) !== "granted") auto = false; }
    catch (e) { auto = false; }
  }
  if (auto) { $("#restoreBtn").textContent = "Reloading…"; await restoreAll(hs); }
}

async function restoreAll(hs) {
  hs = hs || (await IDB.get("handles")) || {};
  const order = ["en1", "en2", "jp1", "jp2", "es"];        // EN first: ES needs a disc loaded
  let okN = 0, failN = 0;
  for (const k of order) {
    const h = hs[k]; if (!h) continue;
    try {
      if ((await h.queryPermission({ mode: "read" })) !== "granted" &&
          (await h.requestPermission({ mode: "read" })) !== "granted") { failN++; continue; }
      await loadSlot(k, await h.getFile(), h);
      okN++;
    } catch (e) { failN++; setStatus(k, "✗ could not reopen — pick it again"); }
  }
  $("#restoreBtn").textContent = "Reload these";
  if (okN && !failN) $("#restoreBar").classList.add("hidden");
}

// ---------- block model ----------
function blockModel(blk) {
  if (S.cache[blk]) return S.cache[blk];
  const BLK = C.DISCS.en.blk, lo = blk * BLK, hi = lo + BLK;
  const chunks = C.walkChunks(enPrimary().ud, lo, hi);
  // EN boxes in python order (good subs) + panel flag; story/panel ordinals for JP pairing
  const enBoxes = [];
  for (const ch of chunks) {
    ch.rows = [];
    let goodOrd = 0;
    ch.subs.forEach((sub, si) => {
      const good = ch.good[si];
      const d = C.decodeEnLossy(sub, false);
      const parsed = C.parseSub(sub, false);
      const row = { si, sub, good, disp: d.text, editable: good && !parsed.raw, parsed };
      if (good) {
        row.panel = d.text.replace(/^[({ ]+/, "").startsWith("*");
        row.boxIdx = enBoxes.length;
        enBoxes.push({ text: d.text, panel: row.panel });
        goodOrd++;
      }
      ch.rows.push(row);
    });
    // ES reference: same chunk window in the ES user data, good-sub ordinal pairing
    if (S.d.es) {
      const eseg = S.d.es.ud.slice(ch.start, ch.start + ch.cap);
      const esubs = []; let last = 0;
      for (let p = 0; p + 1 < eseg.length; p++)
        if (eseg[p] === 0x10 && eseg[p + 1] === 0x0c) { esubs.push(eseg.slice(last, p)); last = p + 2; p++; }
      esubs.push(eseg.slice(last));
      const esGood = [];
      for (const es of esubs) {
        if (!es.length) continue;
        const d = C.decodeEnLossy(es, true);
        if (C.goodEn(d)) esGood.push(d.text);
      }
      let k = 0;
      for (const row of ch.rows) if (row.good) { row.es = esGood[k]; k++; }
    }
  }
  // JP pairing
  let pairs = null, jpPanels = [];
  const jps = jpSource();
  if (jps) {
    const jpb = J.jpBoxes(jps.ud, blk);
    const res = J.align(enBoxes, jpb);
    pairs = res.pairs;
    jpPanels = jpb.filter((b) => b.panel).map((b) => b.text);
  }
  // attach jp text to rows
  if (pairs) {
    let story = 0, panel = 0;
    for (const ch of chunks) for (const row of ch.rows) {
      if (!row.good) continue;
      if (row.panel) { row.jp = jpPanels[panel] || ""; row.conf = row.jp ? "approx" : ""; panel++; }
      else { const p = pairs[story]; row.jp = p ? p.jp : ""; row.conf = p ? p.conf : ""; story++; }
    }
  }
  const model = { chunks };
  S.cache[blk] = model;
  return model;
}

// ---------- rendering ----------
function keyOf(blk, ch, row) { return `${blk}:${ch.off}:${row.si}`; }

function chunkBudget(blk, ch) {
  const useMap = $("#charmap").checked;
  const subs = ch.rows.map((row) => {
    const k = keyOf(blk, ch, row);
    if (row.editable && S.tr[k] !== undefined)
      return { prefix: row.parsed.prefix, text: S.tr[k] };
    return { raw: row.sub };
  });
  return C.rebuildChunk(subs, ch.cap, useMap);
}

function renderBlock() {
  if (!enPrimary()) return;
  const blk = S.blk, model = blockModel(blk);
  const q = ($("#findBox").value || "").toLowerCase();
  const list = $("#chunkList");
  let nEd = 0, nBox = 0, html = [];
  for (const ch of model.chunks) {
    const rows = ch.rows.filter((r) => r.good);
    if (!rows.length) continue;
    if (q && !rows.some((r) => (r.disp + " " + (r.es || "") + " " + (r.jp || "")).toLowerCase().includes(q))) continue;
    nBox += rows.length;
    const rb = chunkBudget(blk, ch);
    const used = rb.err ? (rb.total || ch.cap) : rb.total ?? ch.cap;
    const pct = Math.min(100, Math.round(used / ch.cap * 100));
    html.push(`<div class="chunk" data-off="${ch.off}">
      <div class="chunk-h"><span class="tag">0x${ch.off.toString(16)}</span><span>${ch.frame}</span>
        <div class="bar"><div class="bar-fill" style="width:${pct}%${rb.err ? ";background:#c0392b" : ""}"></div></div>
        <span class="cap">${used}/${ch.cap} B</span>
        ${rb.err ? `<span class="over-note">${esc(rb.err)}</span>` : ""}</div>`);
    for (const row of ch.rows) {
      if (!row.good) continue;
      const k = keyOf(blk, ch, row);
      const val = S.tr[k] !== undefined ? S.tr[k] : "";
      if (S.tr[k] !== undefined) nEd++;
      html.push(`<div class="boxrow">
        <div class="refs">
          <div class="ref-en">${row.panel ? '<span class="badge-panel">panel</span> ' : ""}${esc(row.disp)}</div>
          ${row.es !== undefined ? `<div class="ref-es">ES ${esc(row.es || "—")}</div>` : ""}
          ${row.jp !== undefined ? `<div class="ref-jp">${row.conf ? `<span class="conf-${row.conf}">${row.conf}</span> ` : ""}${esc(row.jp || "—")}</div>` : ""}
        </div>
        <div>
          ${row.editable
            ? `<textarea data-k="${k}" placeholder="${esc(row.parsed.text)}">${esc(val)}</textarea>`
            : `<span class="badge-ro">read-only</span> <span class="muted">box contains control codes the editor can't re-encode yet</span>`}
        </div></div>`);
    }
    html.push("</div>");
  }
  list.innerHTML = html.join("");
  $("#blkStats").textContent = `block ${blk}: ${nBox} boxes shown · ${nEd} edited in this block`;
  saveTr();
  $$("#chunkList textarea").forEach((ta) => {
    ta.addEventListener("input", () => {
      const k = ta.dataset.k;
      if (ta.value === "") delete S.tr[k]; else S.tr[k] = ta.value;
      const ch = model.chunks.find((c2) => c2.off === +ta.closest(".chunk").dataset.off);
      const rb = chunkBudget(blk, ch);
      const h = ta.closest(".chunk").querySelector(".chunk-h");
      const used = rb.err ? (rb.total || ch.cap) : rb.total ?? ch.cap;
      h.querySelector(".bar-fill").style.width = Math.min(100, Math.round(used / ch.cap * 100)) + "%";
      h.querySelector(".bar-fill").style.background = rb.err ? "#c0392b" : "";
      h.querySelector(".cap").textContent = `${used}/${ch.cap} B`;
      let note = h.querySelector(".over-note");
      if (rb.err) { if (!note) { note = document.createElement("span"); note.className = "over-note"; h.appendChild(note); } note.textContent = rb.err; }
      else if (note) note.remove();
      ta.classList.toggle("over", !!rb.err);
      saveTr();
    });
  });
}

// ---------- patch building ----------
function buildEdits() {
  // Compute the patched script region once. Every loaded US disc gets the SAME bytes at the
  // SAME offsets — STGEVT.BIN is byte-identical across disc 1 and 2 — so one computation
  // serves all targets; we just re-emit it per disc.
  const en = enPrimary();
  const span = C.rawSpan(C.DISCS.en);
  const newUd = en.ud.slice();
  const errors = [];
  for (let blk = 0; blk < NBLK; blk++) {
    if (!Object.keys(S.tr).some((k) => k.startsWith(blk + ":"))) continue;
    const model = blockModel(blk);
    for (const ch of model.chunks) {
      if (!ch.rows.some((r) => S.tr[keyOf(blk, ch, r)] !== undefined)) continue;
      const rb = chunkBudget(blk, ch);
      if (rb.err) { errors.push(`block ${blk} 0x${ch.off.toString(16)}: ${rb.err}`); continue; }
      newUd.set(rb.bytes, ch.start);
    }
  }
  const dirty = new Set();
  for (let u = 0; u < newUd.length; u++)
    if (newUd[u] !== en.ud[u]) { dirty.add(Math.floor(u / C.USER)); u = (Math.floor(u / C.USER) + 1) * C.USER - 1; }
  const sectors = [...dirty].sort((a, b) => a - b);
  const edits = sectors.map((sn) => {
    const secOff = sn * C.RAW;
    const sec = en.raw.slice(secOff, secOff + C.RAW);
    sec.set(newUd.subarray(sn * C.USER, (sn + 1) * C.USER), C.HDR);
    C.sectorFix(sec, 0);
    return { off: span.start + secOff, bytes: sec, old: en.raw.slice(secOff, secOff + C.RAW) };
  });
  return { edits, errors };
}

function download(name, bytes) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([bytes]));
  a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 5000);
}
function exportStatus(msg) { $("#exportStatus").innerHTML = msg; }

function withEdits(fn) {
  if (!enPrimary()) return;
  if (!enTargets().every((t) => t.codecOk))
    return exportStatus("sector codec self-check failed on a loaded disc — refusing to export");
  const { edits, errors } = buildEdits();
  if (errors.length) return exportStatus(`<b style="color:#e57373">${errors.length} over-budget chunk(s):</b> ` + esc(errors.slice(0, 4).join(" · ")));
  if (!edits.length) return exportStatus("no changes to export");
  fn(edits);
}

$("#dlPPF").onclick = () => withEdits((edits) => {
  const tgt = enTargets();
  for (const t of tgt)
    download(`WA2_retranslation_${t.key.toUpperCase()}.ppf`,
             C.ppfBuild(`WA2 retranslation (${SLOTS[t.key].label})`, edits));
  exportStatus(`${tgt.length} PPF3 patch${tgt.length > 1 ? "es" : ""} written · ${edits.length} sector${edits.length === 1 ? "" : "s"} each · ` +
    `${tgt.map((t) => SLOTS[t.key].label).join(" + ")}` +
    (tgt.length === 1 ? ` · <span class="warnline">only one disc loaded</span>` : ""));
});
$("#dlXdelta").onclick = () => withEdits((edits) => {
  const tgt = enTargets();
  for (const t of tgt) {
    const patch = V.buildXdelta(t.file.size, edits.map((e) => ({ off: e.off, data: e.bytes })));
    download(`WA2_retranslation_${t.key.toUpperCase()}.xdelta`, patch);
  }
  exportStatus(`${tgt.length} xdelta patch${tgt.length > 1 ? "es" : ""} written · ` +
    `apply: xdelta3 -d -s &lt;disc&gt;.bin patch out.bin`);
});
$("#writeInPlace").onclick = () => withEdits(async (edits) => {
  const tgt = enTargets().filter((t) => t.handle);
  let done = 0;
  for (const t of tgt) {
    try {
      if ((await t.handle.queryPermission({ mode: "readwrite" })) !== "granted" &&
          (await t.handle.requestPermission({ mode: "readwrite" })) !== "granted") {
        exportStatus(`write permission denied for ${SLOTS[t.key].label}`); continue;
      }
      const w = await t.handle.createWritable({ keepExistingData: true });
      for (const e of edits) { await w.seek(e.off); await w.write(e.bytes); }
      await w.close();
      const file = await t.handle.getFile();
      const { raw, ud } = await loadRegion(file, C.DISCS.en);
      S.d[t.key].file = file; S.d[t.key].raw = raw; S.d[t.key].ud = ud;
      done++;
      exportStatus(`wrote ${SLOTS[t.key].label} (${done}/${tgt.length})…`);
    } catch (e) { exportStatus(`write failed on ${SLOTS[t.key].label}: ` + esc(e.message)); return; }
  }
  S.cache = {};
  exportStatus(`wrote ${edits.length} sectors in place to ${done} disc${done === 1 ? "" : "s"} ✓ — keep a PPF/xdelta as the shareable patch`);
  renderBlock();
});
$("#saveCopy").onclick = () => withEdits(async (edits) => {
  try {
    const t = enTargets()[0];
    const src = t.file;
    const h = await window.showSaveFilePicker({ suggestedName: src.name.replace(/\.bin$/i, "") + ".patched.bin" });
    const w = await h.createWritable();
    const CH = 8 * 1024 * 1024;
    const em = new Map(edits.map((e) => [e.off, e]));
    for (let p = 0; p < src.size; p += CH) {
      const end = Math.min(p + CH, src.size);
      const buf = new Uint8Array(await src.slice(p, end).arrayBuffer());
      for (const e of edits) {
        if (e.off + e.bytes.length <= p || e.off >= end) continue;
        const from = Math.max(e.off, p), to = Math.min(e.off + e.bytes.length, end);
        buf.set(e.bytes.subarray(from - e.off, to - e.off), from - p);
      }
      await w.write(buf);
      exportStatus(`writing patched copy of ${SLOTS[t.key].label}… ${Math.round(end / src.size * 100)}%`);
    }
    await w.close();
    exportStatus(`patched copy of ${SLOTS[t.key].label} saved ✓ (${edits.length} sectors changed)` +
      (enTargets().length > 1 ? " — repeat for the other disc, or use the PPF/xdelta which covers both" : ""));
  } catch (e) { if (e.name !== "AbortError") exportStatus("save failed: " + esc(e.message)); }
});

// ---------- project io ----------
$("#exportProj").onclick = () => {
  const proj = { app: "wa2-translation-editor", version: 1, disc: "US CD1",
    key: "blk:chunkOffset:subIndex", translations: S.tr };
  download("wa2_project.json", new TextEncoder().encode(JSON.stringify(proj, null, 1)));
};
$("#importProj").onclick = () => $("#importFile").click();
$("#importFile").onchange = async (ev) => {
  const f = ev.target.files[0]; if (!f) return;
  try {
    const proj = JSON.parse(await f.text());
    if (!proj.translations) throw new Error("no translations field");
    S.tr = { ...S.tr, ...proj.translations };
    saveTr(); renderBlock();
  } catch (e) { alert("import failed: " + e.message); }
};

// ---------- nav ----------
const blkSel = $("#blkSel");
for (let b = 0; b < NBLK; b++) { const o = document.createElement("option"); o.value = b; o.textContent = "block " + b; blkSel.append(o); }
blkSel.onchange = () => { S.blk = +blkSel.value; renderBlock(); };
$("#prevBlk").onclick = () => { S.blk = (S.blk + NBLK - 1) % NBLK; blkSel.value = S.blk; renderBlock(); };
$("#nextBlk").onclick = () => { S.blk = (S.blk + 1) % NBLK; blkSel.value = S.blk; renderBlock(); };
$("#findBox").oninput = () => renderBlock();
$("#charmap").onchange = () => renderBlock();

$$("[data-pick]").forEach((b) => b.onclick = () => pickFile(b.dataset.pick));
$$(".drop[data-slot]").forEach((el) => {
  el.addEventListener("dragover", (e) => e.preventDefault());
  el.addEventListener("drop", (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files[0];
    if (f) loadSlot(el.dataset.slot, f, null);
  });
});
$("#restoreBtn").onclick = () => restoreAll();
$("#forgetBtn").onclick = () => forgetAll();

// mode tabs
$$(".mtab").forEach((t) => t.onclick = () => {
  $$(".mtab").forEach((x) => x.classList.toggle("on", x === t));
  $$(".mode").forEach((m) => m.classList.toggle("hidden", m.id !== "mode-" + t.dataset.mode));
});
saveTr();
initRestore();

// test hook: lets automated tests drive the app without native file pickers
window.WA2App = { S, SLOTS, loadSlot, renderBlock, buildEdits, blockModel, enPrimary, jpSource,
                  enTargets, refreshAvailability, restoreAll, initRestore, forgetAll, IDB };
