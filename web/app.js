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
    // Corroborate the DP against the curated katakana<->EN glossary. Cheap, high precision, and
    // it both promotes pairs to 'term' and catches real drift ('conflict' + a suggested box).
    J.verifyPairs(pairs, enBoxes.filter((b) => !b.panel).map((b) => b.text),
                  jpb.filter((b) => !b.panel).map((b) => b.text));
    jpPanels = jpb.filter((b) => b.panel).map((b) => b.text);
  }
  // attach jp text to rows
  if (pairs) {
    let story = 0, panel = 0;
    for (const ch of chunks) for (const row of ch.rows) {
      if (!row.good) continue;
      if (row.panel) { row.jp = jpPanels[panel] || ""; row.conf = row.jp ? "approx" : ""; panel++; }
      else {
        const p = pairs[story];
        row.jp = p ? p.jp : ""; row.conf = p ? p.conf : "";
        if (p && p.suggest !== undefined) row.suggest = p.suggest;
        if (p && p.terms) row.terms = p.terms;
        row.storyIdx = story;
        story++;
      }
    }
  }
  const model = { chunks };
  S.cache[blk] = model;
  return model;
}

// ---------- rendering ----------
function keyOf(blk, ch, row) { return `${blk}:${ch.off}:${row.si}`; }

// Preview-only stand-ins for the runtime name codes. The real values are player-set at runtime
// (Brad's given name literally is), so these exist to make the box preview readable and to make
// length checks honest -- a {0} that renders as "Ashley" costs 6 columns, not 3.
// docs/WA2_RE_STYLE_GUIDE.md S3 (which declares itself canonical over the other docs) lists
// {0}Ashley {1}Brad {2}Lilka {3}Marina {4}Kanon {5}Liz {6}Ard. WA2_NAME_DICTIONARY.md disagrees
// on {2}/{3} and omits {4}; the style guide's own precedence rule settles it. Preview only --
// the real values are player-set at runtime, and a {n} must never be typed out as a name.
const NAME_SAMPLES = { "0": "Ashley", "1": "Brad", "2": "Lilka", "3": "Marina",
                       "4": "Kanon", "5": "Liz", "6": "Ard" };
const subNames = (t) => String(t).replace(/\{([0-9])\}/g, (m, d) => NAME_SAMPLES[d] || m);

function chunkBudget(blk, ch) {
  const useMap = $("#charmap").checked;
  const subs = ch.rows.map((row) => {
    const k = keyOf(blk, ch, row);
    if (row.editable && S.tr[k] !== undefined) return { prefix: row.parsed.prefix, text: S.tr[k] };
    return { raw: row.sub };
  });
  return C.rebuildChunk(subs, ch.cap, useMap);
}

// live text for a row: the edit if present, else the box's own current text
const rowText = (blk, ch, row) => {
  const k = keyOf(blk, ch, row);
  return S.tr[k] !== undefined ? S.tr[k] : (row.parsed && !row.parsed.raw ? row.parsed.text : row.disp);
};

function gameWindowHtml(text, speaker) {
  const shown = subNames(text || "");
  const fit = C.fitReport(shown);
  const body = fit.lines.map((ln) => {
    if (ln.length <= fit.maxCols) return esc(ln) || "&nbsp;";
    // mark exactly the columns that fall outside the window
    return esc(ln.slice(0, fit.maxCols)) + `<span class="spill">${esc(ln.slice(fit.maxCols))}</span>`;
  }).map((h, i) => (i >= fit.maxLines ? `<span class="spill">${h}</span>` : h)).join("\n");
  const name = speaker !== null && speaker !== undefined
    ? `<div class="gname">${esc(NAME_SAMPLES[speaker] || "{" + speaker + "}")}</div>` : "";
  return `<div class="game">${name}<div class="gwin${fit.over ? " over" : ""}">` +
    (fit.over ? `<span class="overtag">over ${fit.maxLines}×${fit.maxCols}</span>` : "") +
    `<div class="gtext">${body || '<span class="ph">(empty)</span>'}</div><span class="gcursor"></span></div></div>`;
}

function fitLineHtml(blk, ch, row) {
  const txt = rowText(blk, ch, row);
  const fit = C.fitReport(subNames(txt));
  const rb = chunkBudget(blk, ch);
  const used = rb.err ? (rb.total || ch.cap) : (rb.total ?? ch.cap);
  const cls = (bad) => (bad ? "bad" : "good");
  // docs/WA2_INSERTION_MODEL.md ("EARLIER-DOC CORRECTION"): a box has no stored size cap. The
  // chunk length is the ceiling for a POINTER-SAFE, same-size overwrite only. Longer text is
  // possible with a pointer-recalculating pass (what gadesx/CUE did) — so an over-budget box is
  // "needs the repointer", not "impossible". We can't repoint yet, hence the export still
  // refuses; but the editor should not teach a limit the format doesn't actually have.
  // rb.err is either an over-budget chunk or an unencodable character — very different problems,
  // so don't collapse them into one label.
  const overBytes = rb.err && rb.err.startsWith("over budget");
  const byteLabel = overBytes
    ? `<span class="bad" title="No repointer exists yet, so patch export refuses this box. Tighten the English, or flag it for a future repointer pass.">bytes ${used}/${ch.cap} — needs repointer</span>`
    : rb.err
      ? `<span class="bad" title="${esc(rb.err)}">${esc(rb.err)}</span>`
      : `<span class="good" title="Same-size or shorter: overwrites in place with no pointer changes.">bytes ${used}/${ch.cap} pointer-safe</span>`;
  const lintMsgs = C.lintText(txt, { en: row.parsed && !row.parsed.raw ? row.parsed.text : row.disp });
  const errs = lintMsgs.filter((m) => m.sev === "error").length;
  const lintHtml = lintMsgs.length
    ? `<div class="lint">${lintMsgs.map((m) =>
        `<span class="lint-${m.sev}" title="${esc(m.msg)}">${esc(m.rule)}</span>`).join("")}</div>` : "";
  return byteLabel +
    `<span class="${cls(fit.overLines)}">lines ${fit.nLines}/${fit.maxLines}</span>` +
    `<span class="${cls(fit.overCols)}">longest ${fit.longest}/${fit.maxCols}</span>` +
    (errs ? `<span class="bad">${errs} style error${errs === 1 ? "" : "s"}</span>` : "") +
    lintHtml;
}

const PAGE = 60;   // boxes per page — a block can hold 600+, and 600 live previews is not usable
let page = 0;

function visibleRows(model) {
  const q = ($("#findBox").value || "").toLowerCase();
  const onlyEd = $("#onlyEdited").checked;
  const onlyProb = $("#onlyProblems").checked;
  const out = [];
  for (const ch of model.chunks) for (const row of ch.rows) {
    if (!row.good) continue;
    const k = keyOf(S.blk, ch, row);
    if (onlyEd && S.tr[k] === undefined) continue;
    if (q && ![row.disp, row.es, row.jp, S.tr[k]].some((t) => t && t.toLowerCase().includes(q))) continue;
    if (onlyProb) {
      const txt = S.tr[k] !== undefined ? S.tr[k] : "";
      const bad = row.conf === "conflict" ||
        (txt && (C.fitReport(subNames(txt)).over ||
                 C.lintText(txt, { en: row.disp }).some((m) => m.sev === "error")));
      if (!bad) continue;
    }
    out.push({ ch, row });
  }
  return out;
}

function renderBlock() {
  if (!enPrimary()) return;
  const blk = S.blk, model = blockModel(blk);
  const rows = visibleRows(model);
  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  if (page >= pages) page = 0;
  const slice = rows.slice(page * PAGE, page * PAGE + PAGE);

  const cols = ["jp", "en", "es"].filter((c) => $(`.coltog[data-col="${c}"]`).checked);
  const html = [];
  let curChunk = null;
  for (const { ch, row } of slice) {
    if (ch !== curChunk) {
      if (curChunk) html.push("</div>");
      const rb = chunkBudget(blk, ch);
      const used = rb.err ? (rb.total || ch.cap) : (rb.total ?? ch.cap);
      html.push(`<div class="chunk" data-off="${ch.off}"><div class="chunk-h">
        <span class="bid">0x${ch.off.toString(16)}</span><span class="muted">${ch.frame}</span>
        <div class="bar"><div class="bar-fill" style="width:${Math.min(100, Math.round(used / ch.cap * 100))}%${rb.err ? ";background:#c0392b" : ""}"></div></div>
        <span class="cap">${used}/${ch.cap} B</span></div>`);
      curChunk = ch;
    }
    const k = keyOf(blk, ch, row);
    const edited = S.tr[k] !== undefined;
    const spk = row.parsed && !row.parsed.raw ? C.speakerCode(row.sub) : null;
    const colHtml = cols.map((c) => {
      const val = c === "en" ? row.disp : c === "es" ? row.es : row.jp;
      const has = val !== undefined && val !== null && val !== "";
      let chip = "";
      if (c === "jp" && row.conf) {
        const title = row.conf === "term" ? `corroborated by glossary term: ${(row.terms || []).join(", ")}`
          : row.conf === "conflict" ? `this JP names "${(row.terms || [])[0]}", which appears in box #${row.suggest} instead — the pairing is probably wrong`
          : row.conf === "anchor" ? "matched on a shared digit run" : "DP guess — verify before trusting";
        chip = ` <span class="conf-${row.conf}" title="${esc(title)}">${row.conf}</span>`;
        if (row.conf === "conflict" && row.suggest !== undefined)
          chip += ` <span class="suggest">→ likely box #${row.suggest}</span>`;
      }
      return `<div class="col col-${c}"><span class="lab">${c.toUpperCase()}${chip}</span>` +
        `<span class="txt${has ? "" : " none"}">${has ? esc(val) : (val === undefined ? "not loaded" : "—")}</span></div>`;
    }).join("");
    html.push(`<div class="bx" data-k="${k}">
      <div class="bx-h"><span class="bid">#${row.si}</span>
        ${row.panel ? '<span class="badge badge-panel">panel</span>' : ""}
        ${edited ? '<span class="badge badge-edit">edited</span>' : ""}
        ${row.editable ? "" : '<span class="badge badge-ro">read-only</span>'}</div>
      <div class="bx-body">
        <div class="cols side" style="--ncol:${cols.length || 1}">${colHtml}</div>
        ${gameWindowHtml(rowText(blk, ch, row), spk)}
        <div class="re-wrap">
          ${row.editable
            ? `<textarea data-k="${k}" rows="2" placeholder="${esc(row.parsed.text)}">${esc(S.tr[k] ?? "")}</textarea>
               <div class="fitline">${fitLineHtml(blk, ch, row)}</div>`
            : `<div class="muted" style="font-size:12px">read-only — this box carries control codes the encoder can't rebuild yet</div>`}
        </div>
      </div></div>`);
  }
  if (curChunk) html.push("</div>");
  $("#chunkList").innerHTML = html.join("");

  const nEd = rows.filter(({ ch, row }) => S.tr[keyOf(blk, ch, row)] !== undefined).length;
  $("#blkStats").textContent =
    `block ${blk}: ${rows.length} box${rows.length === 1 ? "" : "es"} match · ${nEd} edited` +
    (pages > 1 ? ` · page ${page + 1}/${pages}` : "");
  const pager = pages > 1
    ? `<button class="pill" data-pg="-1" ${page === 0 ? "disabled" : ""}>◀ prev</button>
       <span class="muted">page ${page + 1} of ${pages}</span>
       <button class="pill" data-pg="1" ${page >= pages - 1 ? "disabled" : ""}>next ▶</button>` : "";
  $("#pagerTop").innerHTML = pager; $("#pagerBot").innerHTML = pager;
  $$("[data-pg]").forEach((b) => b.onclick = () => { page += +b.dataset.pg; renderBlock(); });
  saveTr();
  wireEditors(blk, model);
}

function wireEditors(blk, model) {
  $$("#chunkList textarea").forEach((ta) => {
    const bx = ta.closest(".bx");
    const chOff = +ta.closest(".chunk").dataset.off;
    const ch = model.chunks.find((c) => c.off === chOff);
    const row = ch.rows.find((r) => keyOf(blk, ch, r) === ta.dataset.k);
    const repaint = () => {
      // live: game preview, fit line, chunk bar
      const spk = row.parsed && !row.parsed.raw ? C.speakerCode(row.sub) : null;
      const g = bx.querySelector(".game");
      g.outerHTML = gameWindowHtml(rowText(blk, ch, row), spk);
      bx.querySelector(".fitline").innerHTML = fitLineHtml(blk, ch, row);
      const rb = chunkBudget(blk, ch);
      const used = rb.err ? (rb.total || ch.cap) : (rb.total ?? ch.cap);
      const h = bx.closest(".chunk").querySelector(".chunk-h");
      const bar = h.querySelector(".bar-fill");
      bar.style.width = Math.min(100, Math.round(used / ch.cap * 100)) + "%";
      bar.style.background = rb.err ? "#c0392b" : "";
      h.querySelector(".cap").textContent = `${used}/${ch.cap} B`;
      ta.classList.toggle("over", !!rb.err || C.fitReport(subNames(rowText(blk, ch, row))).over);
      const badge = bx.querySelector(".badge-edit");
      const isEd = S.tr[ta.dataset.k] !== undefined;
      if (isEd && !badge) bx.querySelector(".bx-h").insertAdjacentHTML("beforeend", '<span class="badge badge-edit">edited</span>');
      if (!isEd && badge) badge.remove();
    };
    ta.addEventListener("input", () => {
      if (ta.value === "") delete S.tr[ta.dataset.k]; else S.tr[ta.dataset.k] = ta.value;
      repaint(); saveTr();
    });
    // Enter inserts the real line break the game uses (\x0d); the 3-line ceiling is shown live.
    ta.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); ta.blur(); }
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

// ---------- strings JSON: full-corpus export / import ----------
// The point of this format is OFFLINE work: someone exports, translates in a spreadsheet or a
// script or with an LLM, and reimports. So every row must stand alone -- source text, context,
// and both budgets -- not just the sparse key->text map the old "project" export produced,
// which was unreadable away from the app.
const CORPUS_VERSION = 2;

// Cheap stable digest of a row's EN source. Import compares it and refuses rows whose source
// has moved: a JSON built against a different disc/extraction would otherwise write good-looking
// text into the wrong boxes, which is silent and very hard to notice later.
function digest(str) {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  return h.toString(16).padStart(8, "0");
}

function corpusRow(blk, ch, row) {
  const k = keyOf(blk, ch, row);
  const src = row.parsed && !row.parsed.raw ? row.parsed.text : row.disp;
  const r = {
    key: k, blk, off: ch.off, sub: row.si,
    en: src,
    enDigest: digest(src),
    re: S.tr[k] !== undefined ? S.tr[k] : "",
    editable: !!row.editable,
    panel: !!row.panel,
    chunk: `${blk}:${ch.off}`,
    chunkBytes: ch.cap,
  };
  if (row.jp !== undefined) { r.jp = row.jp; r.jpConf = row.conf || ""; }
  if (row.es !== undefined) r.es = row.es || "";
  const spk = row.parsed && !row.parsed.raw ? C.speakerCode(row.sub) : null;
  if (spk !== null) r.speaker = spk;
  return r;
}

// Async so a 120-block sweep (each block runs the JP aligner) can report progress instead of
// freezing the tab.
async function buildCorpus(scope, todoOnly, onProgress) {
  const blocks = scope === "block" ? [S.blk] : [...Array(NBLK).keys()];
  const rows = [];
  for (let i = 0; i < blocks.length; i++) {
    const blk = blocks[i];
    const model = blockModel(blk);
    for (const ch of model.chunks) for (const row of ch.rows) {
      if (!row.good) continue;
      const k = keyOf(blk, ch, row);
      if (scope === "edited" && S.tr[k] === undefined) continue;
      if (todoOnly && S.tr[k] !== undefined && S.tr[k] !== "") continue;
      rows.push(corpusRow(blk, ch, row));
    }
    if (onProgress && (i % 8 === 0 || i === blocks.length - 1)) {
      onProgress(i + 1, blocks.length, rows.length);
      await new Promise((r) => setTimeout(r, 0));
    }
  }
  return {
    app: "wa2-translation-editor",
    version: CORPUS_VERSION,
    kind: "strings",
    scope, todoOnly: !!todoOnly,
    disc: { lang: "en", label: "US (STGEVT.BIN)", blocks: blocks.length },
    sources: Object.keys(S.d).filter((x) => SLOTS[x]).map((x) => `${SLOTS[x].label}: ${S.d[x].name || "?"}`),
    fit: { lines: C.FIT.lines, cols: C.FIT.cols },
    charmap: C.ES_MAP,
    notes: [
      "Edit the 're' field only. Everything else is context and is used to place your text back.",
      "'en' is the current English; 'jp' the Japanese source; 'es' the gadesx Spanish reference.",
      "Two independent budgets: 'chunkBytes' is the byte capacity SHARED by every row with the",
      "same 'chunk' value, and fit.lines x fit.cols (3 x 35) is the on-screen ceiling — the game",
      "does not auto-wrap, so use \\n in 're' for real line breaks.",
      "Rows with editable:false cannot be written back (they carry control codes).",
      "'enDigest' guards the mapping; do not edit key/blk/off/sub/enDigest.",
    ],
    rows,
  };
}

function applyCorpus(obj, mode) {
  if (!obj || obj.kind !== "strings" || !Array.isArray(obj.rows))
    throw new Error("not a WA2 strings JSON (expected kind:\"strings\" and a rows array)");
  if (obj.version > CORPUS_VERSION)
    throw new Error(`file is version ${obj.version}, this editor understands up to ${CORPUS_VERSION}`);

  // index the CURRENT disc so we can validate every incoming row against it
  const cur = new Map();
  const blocks = new Set(obj.rows.map((r) => r.blk).filter((b) => Number.isInteger(b)));
  for (const blk of blocks) {
    const model = blockModel(blk);
    for (const ch of model.chunks) for (const row of ch.rows) {
      if (!row.good) continue;
      const src = row.parsed && !row.parsed.raw ? row.parsed.text : row.disp;
      cur.set(keyOf(blk, ch, row), { editable: !!row.editable, src });
    }
  }

  const rep = { total: obj.rows.length, applied: 0, cleared: 0, unchanged: 0, blank: 0,
                unknown: [], drifted: [], readonly: [], overBytes: [], overFit: [] };
  const next = mode === "replace" ? {} : { ...S.tr };

  for (const r of obj.rows) {
    if (!r || typeof r.key !== "string") { rep.unknown.push("(row without a key)"); continue; }
    const c = cur.get(r.key);
    if (!c) { rep.unknown.push(r.key); continue; }
    if (r.enDigest && c.src !== undefined && digest(c.src) !== r.enDigest) { rep.drifted.push(r.key); continue; }
    const re = typeof r.re === "string" ? r.re : "";
    if (!re.trim()) {
      rep.blank++;
      if (mode === "replace") delete next[r.key];
      else if (next[r.key] !== undefined && re === "") { /* keep existing on merge */ }
      continue;
    }
    if (!c.editable) { rep.readonly.push(r.key); continue; }
    if (next[r.key] === re) { rep.unchanged++; continue; }
    next[r.key] = re;
    rep.applied++;
    const fit = C.fitReport(subNames(re));
    if (fit.over) rep.overFit.push(`${r.key} (${fit.nLines}L/${fit.longest}c)`);
  }

  S.tr = next;
  // chunk budgets can only be judged after everything is in place (a chunk is shared)
  const seen = new Set();
  for (const r of obj.rows) {
    const [blk, off] = String(r.chunk || "").split(":").map(Number);
    if (!Number.isInteger(blk) || seen.has(r.chunk)) continue;
    seen.add(r.chunk);
    const model = blockModel(blk);
    const ch = model.chunks.find((c2) => c2.off === off);
    if (!ch) continue;
    const rb = chunkBudget(blk, ch);
    if (rb.err) rep.overBytes.push(`${r.chunk} — ${rb.err}`);
  }
  return rep;
}

function reportHtml(rep) {
  const li = (label, n, cls) => n ? `<tr><td class="n ${cls || ""}">${n}</td><td>${label}</td></tr>` : "";
  const det = (label, arr, cls) => arr.length
    ? `<details><summary class="${cls}">${arr.length} ${label}</summary><pre>${esc(arr.slice(0, 200).join("\n"))}${
        arr.length > 200 ? `\n… and ${arr.length - 200} more` : ""}</pre></details>` : "";
  return `<div class="iorep"><h4>Import result</h4><table>
    ${li("rows in file", rep.total)}
    ${li("translations applied", rep.applied, "ok")}
    ${li("already matched (no change)", rep.unchanged)}
    ${li("blank 're' (skipped)", rep.blank)}
    </table>
    ${det("keys not on this disc — skipped", rep.unknown, "warn")}
    ${det("source text drifted — skipped, rebuilt against a different disc?", rep.drifted, "bad")}
    ${det("read-only boxes — skipped", rep.readonly, "warn")}
    ${det("now over the 3×35 on-screen ceiling", rep.overFit, "warn")}
    ${det("chunks now over their byte budget — export will refuse these", rep.overBytes, "bad")}
  </div>`;
}

const ioStatus = (h) => { $("#ioStatus").innerHTML = h; };

$("#exportStrings").onclick = async () => {
  if (!enPrimary()) return;
  const scope = $("#expScope").value, todoOnly = $("#expTodo").checked;
  $("#exportStrings").disabled = true;
  try {
    ioStatus("building…");
    const corpus = await buildCorpus(scope, todoOnly,
      (i, n, rows) => ioStatus(`building… block ${i}/${n} · ${rows.toLocaleString()} rows`));
    const json = JSON.stringify(corpus, null, 1);
    const name = `wa2_strings_${scope}${todoOnly ? "_todo" : ""}.json`;
    download(name, new TextEncoder().encode(json));
    ioStatus(`exported <b>${corpus.rows.length.toLocaleString()}</b> rows to ${esc(name)} ` +
      `(${(json.length / 1048576).toFixed(1)} MB) · edit the <code>re</code> field, then import it back`);
  } catch (e) { ioStatus(`<span style="color:#e57373">export failed: ${esc(e.message)}</span>`); }
  finally { $("#exportStrings").disabled = false; }
};

$("#importStrings").onclick = () => $("#importFile").click();
$("#importFile").onchange = async (ev) => {
  const f = ev.target.files[0]; ev.target.value = "";
  if (!f || !enPrimary()) return;
  try {
    ioStatus("reading…");
    const obj = JSON.parse(await f.text());
    const nEx = Object.keys(S.tr).length;
    const mode = nEx && confirm(
      `You have ${nEx} translation${nEx === 1 ? "" : "s"} in the editor.\n\n` +
      `OK = merge (imported rows win; your other work is kept)\n` +
      `Cancel = replace (discard everything not in this file)`) ? "merge" : (nEx ? "replace" : "merge");
    const rep = applyCorpus(obj, mode);
    saveTr(); S.cache = {}; renderBlock();
    ioStatus(`<b>${mode}</b> from ${esc(f.name)}` + reportHtml(rep));
  } catch (e) { ioStatus(`<span style="color:#e57373">import failed: ${esc(e.message)}</span>`); }
};

// ---------- nav ----------
const blkSel = $("#blkSel");
for (let b = 0; b < NBLK; b++) { const o = document.createElement("option"); o.value = b; o.textContent = "block " + b; blkSel.append(o); }
blkSel.onchange = () => { S.blk = +blkSel.value; page = 0; renderBlock(); };
$("#prevBlk").onclick = () => { S.blk = (S.blk + NBLK - 1) % NBLK; blkSel.value = S.blk; page = 0; renderBlock(); };
$("#nextBlk").onclick = () => { S.blk = (S.blk + 1) % NBLK; blkSel.value = S.blk; page = 0; renderBlock(); };
$("#findBox").oninput = () => { page = 0; renderBlock(); };
$("#onlyEdited").onchange = () => { page = 0; renderBlock(); };
$("#onlyProblems").onchange = () => { page = 0; renderBlock(); };
$$("[data-view]").forEach((b) => b.onclick = () => {
  $$("[data-view]").forEach((x) => x.classList.toggle("on", x === b));
  document.body.classList.remove("view-cols", "view-game", "view-both");
  document.body.classList.add("view-" + b.dataset.view);
  try { localStorage.setItem("wa2view", b.dataset.view); } catch (e) {}
});
$$(".coltog").forEach((c) => c.onchange = () => renderBlock());
(() => {                                   // restore the saved view mode
  let v = "both"; try { v = localStorage.getItem("wa2view") || "both"; } catch (e) {}
  const btn = document.querySelector(`[data-view="${v}"]`);
  if (btn) btn.click();
})();
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
                  enTargets, refreshAvailability, restoreAll, initRestore, forgetAll, IDB,
                  buildCorpus, applyCorpus, digest, keyOf, chunkBudget };
