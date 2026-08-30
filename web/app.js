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

const S = {
  en: null,          // {file, handle|null, raw:Uint8Array(region), ud:Uint8Array}
  jp: null,          // {jd}
  es: null,          // {ud, from:'ppf'|'bin'}
  jpTables: false,
  blk: 0,
  cache: {},         // blk -> model
  tr: {},            // "blk:off:sub" -> text
};

// ---------- persistence ----------
const LS_KEY = "wa2tr-v1";
function saveTr() {
  try { localStorage.setItem(LS_KEY, JSON.stringify(S.tr)); } catch (e) {}
  $("#editCount").textContent = `${Object.keys(S.tr).length} edits`;
}
try { S.tr = JSON.parse(localStorage.getItem(LS_KEY) || "{}"); } catch (e) { S.tr = {}; }

// ---------- file loading ----------
async function pickFile(accept, cb, wantHandle) {
  if (wantHandle && SUPPORTS_FS) {
    try {
      const [h] = await window.showOpenFilePicker({ types: [{ description: "disc image", accept: { "application/octet-stream": accept } }] });
      cb(await h.getFile(), h); return;
    } catch (e) { if (e && e.name === "AbortError") return; }
  }
  const inp = document.createElement("input");
  inp.type = "file";
  inp.onchange = () => inp.files[0] && cb(inp.files[0], null);
  inp.click();
}

async function loadRegion(file, disc) {
  const span = C.rawSpan(disc);
  if (file.size < span.start + span.len) throw new Error(`file too small for ${disc.name} (is this the right disc/format?)`);
  const raw = new Uint8Array(await file.slice(span.start, span.start + span.len).arrayBuffer());
  return { raw, ud: C.rawToUser(raw, disc.size) };
}

function codecSelfCheck(raw) {
  // recompute EDC/ECC on untouched sectors; must match the disc byte-for-byte
  let okc = 0, n = 64;
  for (let s = 0; s < n; s++) {
    const orig = raw.slice(s * C.RAW, (s + 1) * C.RAW);
    const work = orig.slice();
    work.fill(0, 0x818, 0x930);
    if (C.sectorFix(work, 0) === "form1" && work.every((b, i) => b === orig[i])) okc++;
  }
  return okc === n;
}

async function loadEN(file, handle) {
  $("#stEN").textContent = "reading…";
  try {
    const { raw, ud } = await loadRegion(file, C.DISCS.en);
    const probeChunks = C.walkChunks(ud, 0, C.DISCS.en.blk);
    if (probeChunks.length < 30) throw new Error("STGEVT structure not found — wrong disc, wrong region, or not a raw 2352-byte .bin");
    const codecOk = codecSelfCheck(raw);
    S.en = { file, handle, raw, ud };
    S.cache = {};
    $("#stEN").innerHTML = `<b>${esc(file.name)}</b> ✓ · block 0: ${probeChunks.length} chunks · sector codec ${codecOk ? "verified ✓" : "<b style='color:#e57373'>MISMATCH — exports disabled</b>"}`;
    S.codecOk = codecOk;
    $("#writeInPlace").disabled = !(handle && codecOk);
    $("#saveCopy").disabled = !codecOk || !("showSaveFilePicker" in window);
    $("#navCard").classList.remove("hidden");
    $("#exportCard").classList.remove("hidden");
    renderBlock();
  } catch (e) { $("#stEN").textContent = "✗ " + e.message; }
}
async function loadJP(file) {
  $("#stJP").textContent = "reading…";
  try {
    if (!S.jpTables) {
      J.init(await (await fetch("data/jp_tables.json")).json());
      S.jpTables = true;
    }
    const { ud } = await loadRegion(file, C.DISCS.jp);
    const probe = J.jpBoxes(ud, 0);
    if (probe.length < 20) throw new Error("JP STGEVT structure not found — wrong disc?");
    S.jp = { jd: ud };
    S.cache = {};
    $("#stJP").innerHTML = `<b>${esc(file.name)}</b> ✓ · block 0: ${probe.length} boxes`;
    renderBlock();
  } catch (e) { $("#stJP").textContent = "✗ " + e.message; }
}
async function loadES(file) {
  $("#stES").textContent = "reading…";
  try {
    if (/\.ppf$/i.test(file.name) || file.size < 64 * 1024 * 1024) {
      if (!S.en) throw new Error("load the US disc first — the PPF is applied to it");
      const ppf = C.ppfParse(new Uint8Array(await file.arrayBuffer()));
      const span = C.rawSpan(C.DISCS.en);
      const win = S.en.raw.slice();
      const applied = C.ppfApplyWindow(ppf, win, span.start);
      S.es = { ud: C.rawToUser(win, C.DISCS.en.size), from: "ppf" };
      $("#stES").innerHTML = `<b>${esc(file.name)}</b> ✓ · ${ppf.version} "${esc(ppf.desc)}" · ${applied} records in script region`;
    } else {
      const { ud } = await loadRegion(file, C.DISCS.en);
      S.es = { ud, from: "bin" };
      $("#stES").innerHTML = `<b>${esc(file.name)}</b> ✓ (pre-patched bin)`;
    }
    S.cache = {};
    renderBlock();
  } catch (e) { $("#stES").textContent = "✗ " + e.message; }
}

// ---------- block model ----------
function blockModel(blk) {
  if (S.cache[blk]) return S.cache[blk];
  const BLK = C.DISCS.en.blk, lo = blk * BLK, hi = lo + BLK;
  const chunks = C.walkChunks(S.en.ud, lo, hi);
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
    if (S.es) {
      const eseg = S.es.ud.slice(ch.start, ch.start + ch.cap);
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
  if (S.jp) {
    const jpb = J.jpBoxes(S.jp.jd, blk);
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
  if (!S.en) return;
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
  // returns [{off(abs raw file), bytes, old}] whole modified sectors, EDC/ECC fixed
  const span = C.rawSpan(C.DISCS.en);
  const newUd = S.en.ud.slice();
  const errors = [];
  for (let blk = 0; blk < NBLK; blk++) {
    const hasEdit = Object.keys(S.tr).some((k) => k.startsWith(blk + ":"));
    if (!hasEdit) continue;
    const model = blockModel(blk);
    for (const ch of model.chunks) {
      if (!ch.rows.some((r) => S.tr[keyOf(blk, ch, r)] !== undefined)) continue;
      const rb = chunkBudget(blk, ch);
      if (rb.err) { errors.push(`0x${ch.off.toString(16)} (block ${blk}): ${rb.err}`); continue; }
      newUd.set(rb.bytes, ch.start);
    }
  }
  // dirty sectors
  const dirty = new Set();
  for (let u = 0; u < newUd.length; u++) {
    if (newUd[u] !== S.en.ud[u]) { dirty.add(Math.floor(u / C.USER)); u = (Math.floor(u / C.USER) + 1) * C.USER - 1; }
  }
  const edits = [];
  for (const s of [...dirty].sort((a, b) => a - b)) {
    const secOff = s * C.RAW;
    const sec = S.en.raw.slice(secOff, secOff + C.RAW);
    sec.set(newUd.subarray(s * C.USER, (s + 1) * C.USER), C.HDR);
    C.sectorFix(sec, 0);
    edits.push({ off: span.start + secOff, bytes: sec, old: S.en.raw.slice(secOff, secOff + C.RAW) });
  }
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
  if (!S.en) return;
  if (!S.codecOk) return exportStatus("sector codec self-check failed on this disc — refusing to export");
  const { edits, errors } = buildEdits();
  if (errors.length) return exportStatus(`<b style="color:#e57373">${errors.length} over-budget chunk(s):</b> ` + esc(errors.slice(0, 4).join(" · ")));
  if (!edits.length) return exportStatus("no changes to export");
  fn(edits);
}

$("#dlPPF").onclick = () => withEdits((edits) => {
  download("WA2_retranslation_CD1.ppf", C.ppfBuild("WA2 retranslation (web editor)", edits));
  exportStatus(`PPF3 written · ${edits.length} sectors patched (undo data included)`);
});
$("#dlXdelta").onclick = () => withEdits((edits) => {
  const patch = V.buildXdelta(S.en.file.size, edits.map((e) => ({ off: e.off, data: e.bytes })));
  download("WA2_retranslation_CD1.xdelta", patch);
  exportStatus(`xdelta written · ${edits.length} sectors patched · apply: xdelta3 -d -s original.bin patch out.bin`);
});
$("#writeInPlace").onclick = () => withEdits(async (edits) => {
  try {
    const w = await S.en.handle.createWritable({ keepExistingData: true });
    for (const e of edits) { await w.seek(e.off); await w.write(e.bytes); }
    await w.close();
    // refresh in-memory copies so budgets/old-bytes stay truthful
    S.en.file = await S.en.handle.getFile();
    const { raw, ud } = await loadRegion(S.en.file, C.DISCS.en);
    S.en.raw = raw; S.en.ud = ud; S.cache = {};
    exportStatus(`wrote ${edits.length} sectors in place ✓ (keep your PPF/xdelta as the shareable patch)`);
    renderBlock();
  } catch (e) { exportStatus("in-place write failed: " + esc(e.message)); }
});
$("#saveCopy").onclick = () => withEdits(async (edits) => {
  try {
    const h = await window.showSaveFilePicker({ suggestedName: S.en.file.name.replace(/\.bin$/i, "") + ".patched.bin" });
    const w = await h.createWritable();
    const CH = 8 * 1024 * 1024;
    const em = new Map(edits.map((e) => [e.off, e]));
    for (let p = 0; p < S.en.file.size; p += CH) {
      const end = Math.min(p + CH, S.en.file.size);
      const buf = new Uint8Array(await S.en.file.slice(p, end).arrayBuffer());
      for (const e of edits) {
        if (e.off + e.bytes.length <= p || e.off >= end) continue;
        const from = Math.max(e.off, p), to = Math.min(e.off + e.bytes.length, end);
        buf.set(e.bytes.subarray(from - e.off, to - e.off), from - p);
      }
      await w.write(buf);
      exportStatus(`writing patched copy… ${Math.round(end / S.en.file.size * 100)}%`);
    }
    await w.close();
    exportStatus(`patched copy saved ✓ (${edits.length} sectors changed)`);
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

$("#pickEN").onclick = () => pickFile({ ".bin": [".bin"] }, loadEN, true);
$("#pickJP").onclick = () => pickFile({ ".bin": [".bin"] }, loadJP, false);
$("#pickES").onclick = () => pickFile({ ".ppf/.bin": [".ppf", ".bin"] }, loadES, false);
for (const [id, fn] of [["dropEN", loadEN], ["dropJP", loadJP], ["dropES", loadES]]) {
  const el = $("#" + id);
  el.addEventListener("dragover", (e) => e.preventDefault());
  el.addEventListener("drop", (e) => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (f) fn(f, null); });
}

// mode tabs
$$(".mtab").forEach((t) => t.onclick = () => {
  $$(".mtab").forEach((x) => x.classList.toggle("on", x === t));
  $$(".mode").forEach((m) => m.classList.toggle("hidden", m.id !== "mode-" + t.dataset.mode));
});
saveTr();

// test hook: lets automated tests drive the app without native file pickers
window.WA2App = { S, loadEN, loadJP, loadES, renderBlock, buildEdits, blockModel };
