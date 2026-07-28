#!/usr/bin/env python3
"""
WA2 translation wiki builder.
Parses insert/*_FINAL.txt (4-column JP/LIT/EN/RE boxes) + the chapter map, and emits a single
self-contained interactive HTML file (wiki/index.html). Re-run after each mission to auto-update.

Usage:  python3 tools_wa2/build_wiki.py
"""
import re, os, sys, glob, html, json, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_db as DB   # SINGLE SOURCE OF TRUTH for all config maps + the DB accessor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSERT = os.path.join(ROOT, 'insert')
GS_DIR = os.path.join(ROOT, 'game_script')
OUT = os.path.join(ROOT, 'wiki', 'index.html')

# ---- raw decoded JP per US# from the master DB (shown as fallback when a FINAL file omits the
# JP line — which we do for coded/unsolved JP). Coded JP with <b:...> placeholders is still worth
# showing so every slot's Japanese source is visible in the wiki. ----
US_JP = {}
try:
    for _r in json.load(open(os.path.join(GS_DIR, 'wa2_db.json')))['rows']:
        if _r.get('jp'): US_JP[_r['us']] = _r['jp']
except Exception:
    pass

# ---- all shared config now imported from build_db (edit mappings THERE, not here) ----
_SECTION_AREAS = DB.SECTION_AREAS
# area code -> game_script section id that contains it (for placeholder transcript fallback)
AREA_SECTION = {}
for _sid, _codes in _SECTION_AREAS.items():
    for _c in _codes:
        AREA_SECTION.setdefault(_c, _sid)
for _c, _sid in DB.AREA_SECTION_EXTRA.items():
    AREA_SECTION.setdefault(_c, _sid)

def gamescript_html(area_code):
    """Render the parsed English transcript for this AREA as placeholder content.
    Prefers the per-location file (game_script/loc/<AREA>.txt) — split on the transcript's own
    ~~Location~~ markers, so content lands under the right area — and falls back to the coarser
    chapter file only if this area has no location split. Returns (html, source_label, box_count)."""
    loc_path = os.path.join(GS_DIR, 'loc', area_code + '.txt')
    if os.path.exists(loc_path):
        path = loc_path; label = 'loc/' + area_code
    else:
        sid = AREA_SECTION.get(area_code)
        if not sid: return '', None, 0
        path = os.path.join(GS_DIR, sid + '.txt')
        if not os.path.exists(path): return '', None, 0
        label = sid
    rows = []; n = 0
    for ln in open(path, encoding='utf-8').read().split('\n'):
        if ln.startswith('#') or not ln.strip():
            continue
        s = ln.strip()
        if s.startswith('~~') and s.endswith('~~'):
            rows.append(f'<div class="gs-sub">{html.escape(s.strip("~ "))}</div>'); continue
        if s.startswith('[') and s.endswith(']'):
            rows.append(f'<div class="gs-dir">{html.escape(s[1:-1])}</div>'); continue
        if s.startswith('->'):
            rows.append(f'<div class="gs-choice">{html.escape(s[2:].strip())}</div>'); continue
        m = re.match(r'^([^:]{1,30}):\s*(.*)$', s)
        if m:
            n += 1
            rows.append(f'<div class="gs-line"><span class="gs-spk">{html.escape(m.group(1))}</span>'
                        f'<span class="gs-txt">{html.escape(m.group(2))}</span></div>')
        else:
            rows.append(f'<div class="gs-line"><span class="gs-txt">{html.escape(s)}</span></div>')
    return '\n'.join(rows), label, n

# area code -> game_script section id(s) that contain it (a section can list several areas)
_AREA_SIDS = {}
for _sid, _codes in _SECTION_AREAS.items():
    for _c in _codes:
        _AREA_SIDS.setdefault(_c, []).append(_sid)

def _norm(t):
    t = re.sub(r'\{[0-9]\}', '', t)
    t = re.sub(r'[|<>*@>_\-]', ' ', t)
    t = re.sub(r'[^a-z0-9 ]', ' ', t.lower())
    return ' '.join(t.split())

def _script_dialogue(sid):
    p = os.path.join(GS_DIR, sid + '.txt'); out = []
    if not os.path.exists(p): return out
    for ln in open(p, encoding='utf-8').read().split('\n'):
        if ln.startswith('#') or not ln.strip(): continue
        s = ln.strip()
        if s.startswith(('~~','[','->')) and not re.match(r'^[^:]{1,30}:', s): continue
        m = re.match(r'^([^:]{1,30}):\s*(.*)$', s)
        if m: out.append((m.group(1), m.group(2)))
    return out

def section_gap_html(sid, box_word_set, thresh=0.6):
    """Uncovered script lines for a section: script dialogue whose content words are mostly absent
    from the translated boxes' EN text. Returns (html, n_uncovered, n_total)."""
    lines = _script_dialogue(sid)
    rows = []; nun = 0
    for spk, txt in lines:
        nt = _norm(txt)
        if len(nt) < 6: continue
        ws = [w for w in nt.split() if len(w) > 2]
        if not ws: continue
        cov = sum(1 for w in ws if w in box_word_set) / len(ws)
        if cov < thresh:
            nun += 1
            rows.append(f'<div class="gs-line"><span class="gs-spk">{html.escape(spk)}</span>'
                        f'<span class="gs-txt">{html.escape(txt)}</span></div>')
    return '\n'.join(rows), nun, len(lines)

# ---- guide spine + scene/first-pass registries: imported from build_db (single source) ----
GUIDE_AREAS = DB.GUIDE_AREAS
DISC_LABEL  = DB.DISC_LABEL
SCENES      = DB.SCENES
FIRSTPASS   = DB.FIRSTPASS

def parse_final(path):
    """Return (header_desc, [boxes]) where box = dict(id, speaker, jp, lit, en, re, noslot)."""
    lines = open(path, encoding='utf-8').read().splitlines()
    header = []
    boxes = []
    i = 0
    # collect leading comment header
    while i < len(lines) and (lines[i].startswith('#') or not lines[i].strip()):
        s = lines[i].lstrip('#').strip()
        if s and not set(s) <= set('=') and 'Columns:' not in s:
            header.append(s)
        i += 1
    cur = None
    def flush():
        nonlocal cur
        if cur:
            # fall back to the master-DB raw JP when the FINAL file has no JP line
            # (we omit the JP line for coded/unsolved JP, but it should still display)
            if not cur['jp']:
                mus = re.match(r'US#(\d+)$', cur['id'])
                if mus: cur['jp'] = US_JP.get(int(mus.group(1)), '')
            boxes.append(cur); cur = None
    while i < len(lines):
        ln = lines[i]
        m = re.match(r'\[(US#\d+|NO-SLOT[^\]]*|[^\]]+)\]\s*(.*)', ln)
        if m and not ln.startswith('#'):
            flush()
            bid = m.group(1).strip()
            spk = m.group(2).strip()
            # speaker often in (parens) after id; strip trailing inline # comment
            spk = re.sub(r'\s*#.*$', '', spk).strip()
            # a box has a real insert slot only if its id is a US#number. Everything else
            # (NO-SLOT..., US~amp-*, [soldier], [mook]) is translated content without an assigned slot.
            has_slot = bool(re.match(r'US#\d+$', bid))
            cur = {'id': bid, 'speaker': spk, 'jp': '', 'lit': '', 'en': '', 're': [],
                   'noslot': not has_slot}
            i += 1; continue
        if cur is not None:
            fm = re.match(r'\s{2}(JP|LIT|EN|RE)\s*:\s?(.*)', ln)
            if fm:
                tag, val = fm.group(1), fm.group(2)
                if tag == 'RE':
                    cur['re'].append(val.rstrip())
                else:
                    cur[tag.lower()] = val.strip()
                i += 1; continue
            # RE continuation: 7-space indent, not a comment
            if cur['re'] is not None and re.match(r'\s{7}\S', ln) and not ln.strip().startswith('#'):
                cur['re'].append(ln.strip())
                i += 1; continue
        i += 1
    flush()
    return ' '.join(header), boxes

def esc(s): return html.escape(s or '')

def box_html(b, srcfile=''):
    cls = 'box' + (' noslot' if b['noslot'] else '')
    idlabel = esc(b['id'])
    spk = esc(b['speaker'])
    re_raw = [x for x in b['re'] if x.strip()]
    re_lines = '<br>'.join(esc(x) for x in re_raw)
    rows = []
    if b['jp']:  rows.append(f'<div class="row jp"><span class="lab">JP</span><span class="txt">{esc(b["jp"])}</span></div>')
    if b['lit']: rows.append(f'<div class="row lit"><span class="lab">LIT</span><span class="txt">{esc(b["lit"])}</span></div>')
    if b['en']:  rows.append(f'<div class="row en"><span class="lab">EN</span><span class="txt">{esc(b["en"])}</span></div>')
    if re_lines: rows.append(f'<div class="row re"><span class="lab">RE</span><span class="txt">{re_lines}</span></div>')
    noslot = '<span class="badge nos">no assigned slot</span>' if b['noslot'] else ''
    # in-game window mockup: RE lines rendered as they'd appear in WA2's dialogue box.
    # Player-name codes {0}=Ashley {1}=Brad {2}=Lilka {3}=Marina shown as sample names.
    NAMES = {'{0}': 'Ashley', '{1}': 'Brad', '{2}': 'Lilka', '{3}': 'Marina',
             '{5}': 'Liz', '{6}': 'Ard'}
    def sub_names(s):
        for k, v in NAMES.items(): s = s.replace(k, v)
        return s
    game_lines = '<br>'.join(esc(sub_names(x)) for x in re_raw) or '<span class="ph">(no RE text)</span>'
    # WA2 real ceiling: 3 lines x 35 chars. Flag overflow against the name-substituted text
    # (what actually renders in-game).
    disp = [sub_names(x) for x in re_raw]
    over = len(disp) > 3 or any(len(x) > 35 for x in disp)
    overcls = ' over' if over else ''
    overtag = '<span class="overtag">over 3x35</span>' if over else ''
    # speaker name-plate above the box: clean the parsed speaker field.
    #   "(King of Meria Boule)"      -> "King of Meria Boule"
    #   "({0} Ashley, at console)"   -> "Ashley"   (leading name-code = party member)
    #   "({2} the kid, proud)"       -> "the kid"
    #   "(soldier, hunting)"         -> "soldier"
    sp = b['speaker'].strip()
    sp = re.sub(r'^\(', '', sp).strip()              # drop leading paren
    sp = re.split(r'[),\[#]|\s—\s|\s//', sp)[0].strip()  # cut at ) , [ # em-dash // — keep name only
    m2 = re.match(r'\{([0-9])\}\s*(.*)$', sp)         # leading name-code?
    if m2:
        # party member: prefer the mapped canonical name; ignore any redundant spelled name
        sp = NAMES.get('{' + m2.group(1) + '}', m2.group(2)) or m2.group(2)
    sp = sub_names(sp).strip()
    # Suppress the name-plate for examine-text / readable panels: these have NO speaker (their
    # JP begins with the ＊/* examine marker), so their "(speaker)" field is really a description
    # (e.g. "power formula 1", "resonance transmission"). Detect by the JP marker — robust.
    is_examine = b['jp'].lstrip().startswith(('＊', '*'))
    DESC = {'region lore', 'directions to Sword Cathedral', 'party'}
    is_desc = is_examine or (':' in b['speaker']) or (sp in DESC)
    valid_name = bool(re.match(r'[A-Za-z]', sp))     # must start with a letter (drops "— house arrest")
    nameplate = f'<div class="gname">{esc(sp)}</div>' if (sp and valid_name and not is_desc) else ''
    # stable comment key: "file#boxid" — carries the EXACT slot id so feedback maps to source.
    key = f"{srcfile}#{b['id']}"
    re_plain = ' / '.join(x for x in re_raw)  # single-line RE snapshot stored with the comment
    game = f'''<div class="game" data-key="{esc(key)}">
      {nameplate}
      <div class="gwin{overcls}">{overtag}<div class="gtext" data-orig="{esc(re_plain)}">{game_lines}</div><span class="gcursor">▼</span></div>
    </div>'''
    cbtn = (f'<button class="cbtn" data-key="{esc(key)}" data-re="{esc(re_plain)}" '
            f'data-spk="{esc(sp)}">💬 <span class="cbtn-lbl">comment</span></button>')
    ebtn = (f'<button class="ebtn" data-key="{esc(key)}" data-re="{esc(re_plain)}" '
            f'data-spk="{esc(sp)}">✎ <span class="cbtn-lbl">edit text</span></button>')
    return f'''<div class="{cls}" data-key="{esc(key)}">
  <div class="boxhead"><span class="bid">{idlabel}</span> <span class="spk">{spk}</span>{noslot}{cbtn}{ebtn}</div>
  <div class="boxbody">
    <div class="cols">{''.join(rows)}</div>
    {game}
  </div>
  <div class="cwrap" data-key="{esc(key)}"></div>
</div>'''

def font_face_css():
    """Inline the MedievalSharp Latin subset (self-contained, offline). Falls back gracefully
    if the woff2 isn't present."""
    import base64
    fp = os.path.join(ROOT, 'wiki', 'fonts', 'medievalsharp_latin.woff2')
    if not os.path.exists(fp):
        return ''  # graceful: game window falls back to serif stack
    b64 = base64.b64encode(open(fp, 'rb').read()).decode('ascii')
    return ("@font-face {{ font-family:'WA2Font'; font-style:normal; font-weight:400; "
            "font-display:swap; src:url(data:font/woff2;base64,{}) format('woff2'); }}").format(b64)

def build():
    # index SCENES by guide-area code (an area may hold several translated scenes)
    by_area = {}
    present = {s[0] for s in SCENES}
    for fname, area, subtitle, blk in SCENES:
        path = os.path.join(INSERT, fname)
        if not os.path.exists(path):
            continue
        desc, boxes = parse_final(path)
        real = [b for b in boxes if not b['noslot']]
        by_area.setdefault(area, []).append(dict(file=fname, area=area, subtitle=subtitle, block=blk,
                                desc=desc, boxes=boxes, nboxes=len(real), ntotal=len(boxes)))
    all_final = {os.path.basename(p) for p in glob.glob(os.path.join(INSERT, '*_FINAL.txt'))}
    # multi-block sweep files span many areas; they are routed per-box via block->area in
    # build_db.py (not a single SCENES entry), so they are registered by design — not a gap.
    DB_ROUTED = {'disc1_cleanup_FINAL.txt', 'boilerplate_sweep_FINAL.txt', 'story_disc1_gapfill_FINAL.txt'}
    unregistered = sorted(all_final - present - DB_ROUTED)

    # index FIRSTPASS files by area code (auto-generated, US#-verified, not deep RE)
    fp_area = {}
    FPDIR = os.path.join(INSERT, 'firstpass')
    for fname, codes, blk, label in FIRSTPASS:
        path = os.path.join(FPDIR, fname)
        if not os.path.exists(path):
            continue
        desc, boxes = parse_final(path)
        real = [b for b in boxes if not b['noslot']]
        rec = dict(file='firstpass/'+fname, block=blk, label=label,
                   boxes=boxes, nboxes=len(real), ntotal=len(boxes))
        for code in codes:
            fp_area.setdefault(code, []).append(rec)

    # ---- per-AREA word set (box EN for that specific area) for gap placeholders ----
    area_words = {}
    for _c in set(list(by_area) + list(fp_area)):
        ws = set()
        for sc in by_area.get(_c, []) + fp_area.get(_c, []):
            for b in sc['boxes']:
                if b.get('en'): ws.update(_norm(b['en']).split())
        area_words[_c] = ws
    def section_gap_block(code):
        """Uncovered lines for THIS area, from its per-location transcript file (loc/<code>.txt).
        Split on the transcript's own ~~Location~~ markers, so gaps land under the right area."""
        loc_path = os.path.join(GS_DIR, 'loc', code + '.txt')
        if not os.path.exists(loc_path): return ''
        lines = []
        for ln in open(loc_path, encoding='utf-8').read().split('\n'):
            if ln.startswith('#') or not ln.strip(): continue
            s = ln.strip()
            if s.startswith(('~~', '[', '->')) and not re.match(r'^[^:]{1,30}:', s): continue
            m = re.match(r'^([^:]{1,30}):\s*(.*)$', s)
            if m: lines.append((m.group(1), m.group(2)))
        bw = area_words.get(code, set())
        rows = []; nun = 0
        for spk, txt in lines:
            nt = _norm(txt)
            if len(nt) < 6: continue
            wl = [w for w in nt.split() if len(w) > 2]
            if not wl: continue
            if sum(1 for w in wl if w in bw)/len(wl) < 0.6:
                nun += 1
                rows.append(f'<div class="gs-line"><span class="gs-spk">{html.escape(spk)}</span>'
                            f'<span class="gs-txt">{html.escape(txt)}</span></div>')
        if not nun: return ''
        return (f'<div class="subscene gap"><h3>Not yet translated in this area '
                f'<span class="subm">{nun} of {len(lines)} script lines · <code>loc/{esc(code)}</code></span></h3>'
                f'<p class="scenedesc">These English game-script lines (for this location) have no matching translated box yet. Placeholder reference.</p>'
                f'<div class="gamescript">{"".join(rows)}</div></div>')

    total_boxes = sum(sc['nboxes'] for scs in by_area.values() for sc in scs)
    fp_boxes = sum(sc['nboxes'] for scs in fp_area.values() for sc in scs)
    total_scenes = sum(len(scs) for scs in by_area.values())
    total_areas = sum(len(v) for v in GUIDE_AREAS.values())
    done_areas = sum(1 for d in GUIDE_AREAS for code,_ in GUIDE_AREAS[d] if code in by_area)
    fp_areas = sum(1 for d in GUIDE_AREAS for code,_ in GUIDE_AREAS[d] if code in fp_area and code not in by_area)

    now = datetime.date.today().isoformat()
    fontface = font_face_css()

    # DB-driven per-area untranslated-slot counts (NPC/ambient gap), from area_todo.py json
    try:
        AREA_TODO = json.load(open(os.path.join(GS_DIR, 'area_todo.json')))
    except Exception:
        AREA_TODO = {}

    # ---- slot-level progress from the master DB (the honest project-wide numbers) ----
    try:
        _dbrows = json.load(open(os.path.join(GS_DIR, 'wa2_db.json')))['rows']
    except Exception:
        _dbrows = []
    # honest box-level coverage over the CORRECT box set (game_script/box_coverage.json),
    # generated by tools_wa2/box_coverage.py. The DB 'slot' counts below measure only the
    # \x10\x0c-indexed subset; box_* measures every real dialogue box (see memory:
    # wa2-extraction-two-framings).
    try:
        _cov = json.load(open(os.path.join(GS_DIR, 'box_coverage.json')))
        box_total = _cov['total']; box_match = _cov['match']
    except Exception:
        box_total = box_match = 0
    box_pct = round(100 * box_match / box_total) if box_total else 0
    box_left = box_total - box_match

    slot_total = len(_dbrows)
    slot_deep = sum(1 for r in _dbrows if r.get('status') == 'deep')
    slot_fp   = sum(1 for r in _dbrows if r.get('status') == 'firstpass')
    slot_remaining = sum(1 for r in _dbrows if r.get('status') == 'placeholder'
                         and r.get('en') and 'Demo Version' not in r['en'])
    def _pct(x): return round(100 * x / slot_total) if slot_total else 0
    # an area counts as "done" when it has translated boxes and NO clean-JP slots left to translate
    # (remaining todo is only dirty-JP/unsolved-code or SFX slots we can't cleanly translate yet)
    areas_complete = sum(1 for a, v in AREA_TODO.items()
                         if v.get('done', 0) > 0 and v.get('todo_clean', 0) == 0)

    def area_anchor(disc, code): return f'a-{disc}-{code}'

    # ---- NAV: legend, then walk the guide spine (overall progress lives in the status card) ----
    nav_html = [
        f'<div class="nav-legend"><span class="todotag star">*N</span> N untranslated slots (NPC/ambient) still in this area</div>'
    ]
    for disc in sorted(GUIDE_AREAS):
        areas = GUIDE_AREAS[disc]
        d_done = sum(1 for code, _ in areas if code in by_area)
        d_fp = sum(1 for code, _ in areas if code in fp_area and code not in by_area)
        d_cov = d_done + d_fp
        d_pct = round(100 * d_done / len(areas)) if areas else 0
        d_covpct = round(100 * d_cov / len(areas)) if areas else 0
        nav_html.append(
            f'<div class="nav-disc">{DISC_LABEL.get(disc, "DISC "+str(disc))}'
            f'<span class="dprog"><span class="dprog-fp" style="width:{d_covpct}%"></span>'
            f'<span class="dprog-fill" style="width:{d_pct}%"></span></span>'
            f'<span class="dcnt">{d_done}+{d_fp}/{len(areas)}</span></div>')
        for code, aname in areas:
            anc = area_anchor(disc, code)
            scs = by_area.get(code, [])
            fps = fp_area.get(code, [])
            # untranslated NPC/ambient slots still in this area's block(s) (DB-driven, the real gap)
            nleft = AREA_TODO.get(code, {}).get('todo', 0)
            gap_star = (f' <span class="todotag star" title="{nleft} untranslated slots (NPC/ambient) still in this area\'s block">*{nleft}</span>'
                        if nleft else '')
            if scs:
                nb = sum(x['nboxes'] for x in scs)
                nav_html.append(f'<a class="nav-scene done" href="#{anc}">{esc(aname)} <span class="cnt">{nb}</span>{gap_star}</a>')
            elif fps:
                nb = sum(x['nboxes'] for x in fps)
                nav_html.append(f'<a class="nav-scene fp" href="#{anc}">{esc(aname)} <span class="cnt">{nb}◐</span>{gap_star}</a>')
            else:
                # untranslated: * if we have English game-script placeholder text for this location
                has_script = os.path.exists(os.path.join(GS_DIR, 'loc', code + '.txt'))
                tag = '<span class="todotag star" title="English game-script placeholder available (not yet retranslated)">*</span>' if has_script else '<span class="todotag">·</span>'
                nav_html.append(f'<a class="nav-scene todo" href="#{anc}">{esc(aname)} {tag}</a>')
    nav_html = '\n'.join(nav_html)

    # ---- per-area context line (disc · code · box counts · untranslated slots · status) ----
    def area_meta(disc, code, deep_boxes=0, fp_boxes_n=0):
        t = AREA_TODO.get(code, {})
        todo, todoc = t.get('todo', 0), t.get('todo_clean', 0)
        parts = [f'{DISC_LABEL.get(disc,"Disc "+str(disc))} · guide area <code>{esc(code)}</code>']
        def _n(x, s):
            if x == 1: return f'{x} {s}'
            return f'{x} {s}es' if s.endswith(('x', 's')) else f'{x} {s}s'
        if deep_boxes:    parts.append(_n(deep_boxes, 'deep box'))
        if fp_boxes_n:    parts.append(_n(fp_boxes_n, 'first-pass box'))
        if todoc:         parts.append(f'<span class="meta-gap">{_n(todoc, "line")} still to translate</span>')
        elif todo and (deep_boxes or fp_boxes_n):
                          parts.append('<span class="meta-ok">no clean-JP lines left</span>')
        if todo and not todoc: parts.append(_n(todo, 'untranslatable/SFX slot'))
        return '<div class="scenemeta">' + ' · '.join(parts) + '</div>'

    # ---- BODY: one section per guide area; placeholder if untranslated ----
    body = []
    for disc in sorted(GUIDE_AREAS):
        body.append(f'<div class="disc-head" id="disc-{disc}">{DISC_LABEL.get(disc, "DISC "+str(disc))}</div>')
        for code, aname in GUIDE_AREAS[disc]:
            anc = area_anchor(disc, code)
            scs = by_area.get(code, [])
            fps = fp_area.get(code, [])
            if not scs and fps:
                # FIRST-PASS area: localization reflowed + US#-verified, not deep RE
                hdr_boxes = sum(x['nboxes'] for x in fps)
                body.append(f'<section class="scene firstpass" id="{anc}"><h2>{esc(aname)} '
                            f'<span class="pill fp">first pass — {hdr_boxes} boxes</span></h2>'
                            f'{area_meta(disc, code, fp_boxes_n=hdr_boxes)}'
                            f'<p class="scenedesc">First pass: US localization reflowed to the display window and verified against '
                            f'the real message slots. Not a deep retranslation yet — flagged for a literary RE pass.</p>')
                for s in fps:
                    boxes_html = '\n'.join(box_html(b, s['file']) for b in s['boxes'])
                    body.append(f'''  <div class="subscene">
    <h3>{esc(s['label'])} <span class="subm">block {esc(s['block'])} · {s['nboxes']} slots · <code>insert/{esc(s['file'])}</code></span></h3>
    {boxes_html}
  </div>''')
                body.append(section_gap_block(code))
                body.append('</section>')
                continue
            if not scs:
                gs, gs_sid, gs_n = gamescript_html(code)
                gs_block = ''
                if gs:
                    gs_block = (f'<p class="scenedesc">Placeholder — no retranslation yet. Showing the '
                                f'English game-script transcript (section <code>{esc(gs_sid)}</code>, '
                                f'{gs_n} lines) as reference.</p>'
                                f'<div class="gamescript">{gs}</div>')
                else:
                    gs_block = '<p class="scenedesc">Placeholder — this area is in the walkthrough spine but has no retranslation yet.</p>'
                body.append(f'''<section class="scene placeholder" id="{anc}">
  <h2>{esc(aname)} <span class="pill todo">not yet translated</span></h2>
  {area_meta(disc, code)}
  {gs_block}
</section>''')
                continue
            # translated area: header + each scene's boxes
            hdr_boxes = sum(x['nboxes'] for x in scs)
            body.append(f'<section class="scene" id="{anc}"><h2>{esc(aname)} <span class="pill done">{hdr_boxes} boxes</span></h2>'
                        f'{area_meta(disc, code, deep_boxes=hdr_boxes)}')
            for s in scs:
                boxes_html = '\n'.join(box_html(b, s['file']) for b in s['boxes'])
                nnos = s['ntotal'] - s['nboxes']
                noslot_note = (f'<p class="notewarn">{nnos} box(es) below have no assigned US# slot (embedded/over-expanded) — shown for reference.</p>' if nnos else '')
                body.append(f'''  <div class="subscene">
    <h3>{esc(s['subtitle'])} <span class="subm">block {esc(s['block'])} · {s['nboxes']} slots · <code>insert/{esc(s['file'])}</code></span></h3>
    <p class="scenedesc">{esc(s['desc'])}</p>
    {noslot_note}
    {boxes_html}
  </div>''')
            body.append(section_gap_block(code))
            body.append('</section>')
    body = '\n'.join(body)

    unreg_html = ''
    if unregistered:
        unreg_html = '<p class="notewarn">Unregistered FINAL files (add to SCENES in build_wiki.py): ' + ', '.join(esc(u) for u in unregistered) + '</p>'


    doc = f'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wild Arms 2 — Retranslation Wiki</title>
<style>
{fontface}
/* palette tuned to the WA2 in-game menu: deep blue-slate panels, parchment text,
   pale-cyan headers, burgundy accent frame */
:root {{ --bg:#0e1622; --panel:#1c2740; --panel2:#243350; --ink:#ece3c8; --dim:#9fa8bd; --acc:#8fd0e8;
        --jp:#f0c674; --lit:#a7d29a; --en:#c9a0ff; --re:#8fd0e8; --warn:#e88f6b; --line:#3a4a6e;
        --bevel-hi:#3d5488; --bevel-lo:#0a1120; --frame:#7a2f3a; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--ink); font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif; }}
#wrap {{ display:flex; min-height:100vh; }}
#side {{ width:310px; flex:0 0 310px;
         background:linear-gradient(180deg,#1c2740,#141d30);
         border-right:2px solid var(--frame); box-shadow:inset -1px 0 0 var(--bevel-hi);
         position:sticky; top:0; height:100vh; overflow:auto; padding:16px 12px; }}
#side h1 {{ font-size:17px; margin:0 0 8px; color:#fff; letter-spacing:.5px;
            text-shadow:0 1px 2px #000, 0 0 6px rgba(143,208,232,.35); }}
#side .sub {{ color:var(--dim); font-size:12px; margin-bottom:14px; }}
.statuscard {{ background:linear-gradient(180deg,#243350,#1a2338);
               border:1px solid var(--bevel-hi); border-radius:6px;
               box-shadow:inset 0 1px 0 rgba(143,208,232,.15), 0 2px 4px var(--bevel-lo);
               padding:10px 11px; margin:0 0 14px; font-size:11.5px; }}
.statuscard .sc-row {{ display:flex; align-items:center; gap:6px; padding:1.5px 0; }}
.statuscard .sc-k {{ color:var(--dim); flex:1; }}
.statuscard .sc-v {{ color:var(--ink); font-variant-numeric:tabular-nums; font-weight:600; }}
.statuscard .sc-bar {{ position:relative; height:7px; border-radius:4px; background:var(--bg);
                       overflow:hidden; margin:5px 0 7px; border:1px solid var(--line); }}
.statuscard .sc-fp {{ position:absolute; left:0; top:0; height:100%; background:var(--jp); opacity:.5; }}
.statuscard .sc-deep {{ position:absolute; left:0; top:0; height:100%; background:var(--acc); z-index:1; }}
.statuscard .sc-dot {{ width:8px; height:8px; border-radius:2px; flex:0 0 auto; }}
.statuscard .sc-dot.deep {{ background:var(--acc); }}
.statuscard .sc-dot.fp {{ background:var(--jp); opacity:.6; }}
.statuscard .sc-dot.rem {{ background:var(--line); }}
.statuscard .sc-sep {{ height:1px; background:var(--line); margin:7px 0; }}
.statuscard .sc-note {{ color:var(--dim); font-size:10px; margin-top:6px; line-height:1.4; }}
/* progress bar (overall) */
.prog {{ margin:6px 0 14px; }}
.prog-lbl {{ display:flex; justify-content:space-between; font-size:11px; color:var(--dim); margin-bottom:4px; }}
.prog-track {{ position:relative; height:8px; background:var(--panel2); border-radius:5px; overflow:hidden; border:1px solid var(--line); }}
.prog-fp {{ position:absolute; left:0; top:0; height:100%; background:var(--jp); opacity:.4; border-radius:5px; }}
.prog-fill {{ position:absolute; left:0; top:0; height:100%; background:linear-gradient(90deg,var(--acc),var(--re)); border-radius:5px; transition:width .3s; }}
/* per-disc mini progress */
.nav-disc {{ margin:14px 0 6px; font-size:12px; letter-spacing:.12em; color:var(--acc); font-weight:700;
             display:flex; align-items:center; gap:6px; }}
.dprog {{ position:relative; flex:1; height:4px; background:var(--panel2); border-radius:3px; overflow:hidden; }}
.dprog-fp {{ position:absolute; left:0; top:0; height:100%; background:var(--jp); opacity:.4; border-radius:3px; }}
.dprog-fill {{ position:absolute; left:0; top:0; height:100%; background:var(--acc); border-radius:3px; }}
/* first-pass area states */
.nav-scene.fp {{ color:var(--jp); opacity:.85; }}
.nav-scene.fp:hover {{ opacity:1; }}
.scene.firstpass h2 {{ border-bottom:1px dashed var(--jp); }}
.pill.fp {{ background:rgba(255,212,121,.15); color:var(--jp); }}
.dcnt {{ font-size:10px; color:var(--dim); font-weight:400; letter-spacing:0; }}
.nav-mission {{ margin:8px 0 2px; font-size:12.5px; color:var(--dim); font-weight:600; }}
.nav-scene {{ display:block; padding:3px 8px; margin:1px 0 1px 8px; color:var(--ink); text-decoration:none;
              border-radius:6px; font-size:13px; }}
.nav-scene:hover {{ background:var(--panel2); }}
.nav-scene.active {{ background:var(--panel2); box-shadow:inset 3px 0 0 var(--acc); color:var(--acc); font-weight:600; }}
.cnt {{ color:var(--dim); font-size:11px; }}
#main {{ flex:1; padding:26px 34px 80px; max-width:1000px; }}
.topbar {{ display:flex; gap:18px; align-items:baseline; flex-wrap:wrap; margin-bottom:6px; }}
.topbar h1 {{ font-size:22px; margin:0; color:#fff; letter-spacing:.5px;
              text-shadow:0 1px 2px #000, 0 0 8px rgba(143,208,232,.3); }}
.stats {{ color:var(--dim); font-size:13px; }}
.controls {{ margin:14px 0 22px; display:flex; gap:14px; flex-wrap:wrap; font-size:13px; color:var(--dim); }}
.controls label {{ cursor:pointer; user-select:none; }}
.scene {{ margin:0 0 40px; scroll-margin-top:14px; }}
.scene h2 {{ font-size:19px; margin:0 0 4px; color:#fff; padding:4px 10px;
             background:linear-gradient(180deg,#2a3a5e,#1a2338);
             border:1px solid var(--bevel-hi); border-left:4px solid var(--frame); border-radius:5px;
             box-shadow:inset 0 1px 0 rgba(143,208,232,.15); text-shadow:0 1px 2px #000; }}
.scenemeta {{ color:var(--dim); font-size:12px; margin-bottom:8px; }}
.scenemeta .meta-gap {{ color:var(--warn); font-weight:600; }}
.scenemeta .meta-ok {{ color:var(--re); }}
.scenemeta code {{ color:var(--dim); }}
.scenedesc {{ color:var(--dim); font-size:13px; margin:6px 0 16px; font-style:italic; }}
.notewarn {{ color:var(--warn); font-size:12.5px; background:rgba(255,157,118,.08); padding:6px 10px; border-radius:6px; }}
/* guide-spine nav states */
.nav-scene.done {{ color:var(--ink); }}
.nav-scene.todo {{ color:var(--dim); opacity:.65; }}
.nav-scene.todo:hover {{ opacity:1; }}
.todotag {{ color:var(--line); }}
.todotag.star {{ color:var(--warn); font-weight:700; }}
.nav-legend {{ font-size:10px; color:var(--dim); margin-top:5px; }}
/* disc headers + placeholders + area sub-scenes */
.disc-head {{ font-size:13px; letter-spacing:.14em; color:var(--acc); font-weight:800; margin:28px 0 10px;
              border-bottom:2px solid var(--line); padding-bottom:6px; scroll-margin-top:14px; }}
.scene.placeholder {{ margin:0 0 14px; }}
.scene.placeholder h2 {{ font-size:16px; border-bottom:1px dashed var(--line); opacity:.7; }}
.gamescript {{ margin:10px 0 4px; padding:12px 14px; background:rgba(255,255,255,.02);
  border-left:3px solid var(--warn); border-radius:4px; }}
.gs-line {{ display:flex; gap:10px; padding:3px 0; line-height:1.5; }}
.gs-spk {{ flex:0 0 130px; text-align:right; color:var(--warn); font-weight:600; font-size:12.5px; }}
.gs-txt {{ flex:1; color:var(--ink); font-size:13.5px; }}
.gs-dir {{ color:var(--dim); font-style:italic; font-size:12.5px; padding:6px 0 6px 140px; }}
.gs-sub {{ color:var(--re); font-weight:700; font-size:13px; margin:12px 0 4px; padding-left:140px; }}
.gs-choice {{ color:var(--lit); font-size:12.5px; padding:2px 0 2px 140px; }}
body.hide-gs .gamescript {{ display:none; }}
.subscene.gap {{ border-left:3px solid var(--warn); padding-left:12px; margin-top:18px; opacity:.92; }}
.subscene.gap h3 {{ color:var(--warn); }}
body.hide-gs .subscene.gap {{ display:none; }}
.pill {{ font-size:11px; font-weight:700; padding:1px 8px; border-radius:10px; vertical-align:middle; }}
.pill.done {{ background:rgba(111,178,255,.15); color:var(--acc); }}
.pill.todo {{ background:rgba(154,160,180,.15); color:var(--dim); }}
.subscene {{ margin:10px 0 20px; }}
.subscene h3 {{ font-size:15px; margin:14px 0 2px; color:var(--re); }}
.subscene .subm {{ font-size:11.5px; color:var(--dim); font-weight:400; }}
.box {{ background:linear-gradient(180deg,#1e2942,#18213600); background-color:#1b2438;
        border:1px solid var(--bevel-hi); border-radius:6px; padding:10px 12px; margin:10px 0;
        box-shadow:inset 0 1px 0 rgba(143,208,232,.10), 0 1px 3px var(--bevel-lo); }}
.box.noslot {{ opacity:.55; border-style:dashed; }}
.boxhead {{ margin-bottom:6px; }}
.bid {{ font-weight:700; color:var(--acc); font-size:12.5px; }}
.spk {{ color:var(--dim); font-size:12.5px; }}
.badge.nos {{ float:right; color:var(--warn); border:1px solid var(--warn); border-radius:5px; font-size:10px; padding:0 5px; }}
.row {{ display:flex; gap:8px; padding:2px 0; align-items:baseline; }}
.lab {{ flex:0 0 30px; font-size:10.5px; font-weight:700; color:var(--dim); text-align:right; padding-top:2px; letter-spacing:.06em; }}
.txt {{ flex:1; }}
.row.jp .txt {{ color:var(--jp); }}
.row.lit .txt {{ color:var(--lit); font-size:13.5px; }}
.row.en .txt {{ color:var(--en); font-size:13.5px; }}
.row.re .txt {{ color:var(--re); font-weight:600; }}
body.hide-jp .row.jp, body.hide-lit .row.lit, body.hide-en .row.en {{ display:none; }}
/* in-game dialogue window mockup */
.boxbody {{ display:flex; gap:16px; align-items:flex-start; }}
.cols {{ flex:1; min-width:0; }}
.game {{ flex:0 0 340px; }}
/* WA2 in-game textbox: slate blue-gray fill w/ dither texture, warm tan double frame.
   Sized to the REAL game standard box: 3 lines x ~35 chars (verified: 99.9% of 7744 boxes are
   <=3 lines; only 6 boxes in the whole game go to 4-5, all endgame lore). --gfs = font size. */
.gwin {{ position:relative;
         background-color:#464f5a;
         background-image:
           repeating-linear-gradient(0deg, rgba(255,255,255,.035) 0 1px, transparent 1px 3px),
           repeating-linear-gradient(90deg, rgba(0,0,0,.06) 0 1px, transparent 1px 3px),
           linear-gradient(180deg,#525c68 0%,#3d454f 100%);
         border:3px solid #8a6a3a;
         border-radius:12px;
         padding:14px 18px 20px;
         box-shadow:0 3px 12px rgba(0,0,0,.55),
                    inset 0 0 0 3px #d8bd82,
                    inset 0 0 0 4px #b8955a;
         width:max-content; }}
.gtext {{ --gfs:18px; --lines:3;
          color:#f2ead6; font-size:var(--gfs); line-height:1.5; letter-spacing:.01em;
          font-family:'WA2Font',"MedievalSharp",Georgia,serif;
          text-shadow:1px 1px 1px rgba(0,0,0,.75); white-space:pre-wrap;
          /* WA2 standard box = ~35 chars/line, 3 lines. Cap width so long RE lines wrap at the
             same visual point, and reserve 3 lines of height (the game's normal max). */
          width:calc(35 * 0.52 * var(--gfs));   /* ~35 avg-char widths of MedievalSharp */
          min-height:calc(var(--lines) * 1.5 * var(--gfs));
          box-sizing:content-box; }}
.gname {{ display:inline-block; margin:0 0 -3px 6px; padding:3px 12px;
          background:linear-gradient(180deg,#525c68,#3d454f);
          border:3px solid #8a6a3a; border-bottom:none;
          border-radius:8px 8px 0 0;
          box-shadow:inset 0 0 0 2px #d8bd82;
          color:#ffe9b0; font-family:'WA2Font',"MedievalSharp",Georgia,serif; font-size:14px;
          text-shadow:1px 1px 1px rgba(0,0,0,.7); position:relative; z-index:1; }}
.gcursor {{ position:absolute; right:14px; bottom:9px; width:3px; height:16px;
            background:#8fe07a; box-shadow:0 0 3px #8fe07a; color:transparent;
            animation:blink 1.1s steps(1) infinite; }}
/* overflow warning: RE that exceeds the 5-line ceiling gets a red edge */
.gwin.over {{ box-shadow:0 3px 12px rgba(0,0,0,.55), inset 0 0 0 3px #ff6b6b, inset 0 0 0 4px #b8955a; }}
.overtag {{ position:absolute; top:-9px; right:8px; background:#ff6b6b; color:#111; font-size:10px;
            font-weight:700; padding:0 6px; border-radius:5px; font-family:-apple-system,sans-serif; }}
.ph {{ color:var(--dim); font-style:italic; }}
@keyframes blink {{ 50% {{ opacity:0; }} }}
/* view modes */
body.mode-game .cols {{ display:none; }}
body.mode-game .game {{ flex:1 1 auto; max-width:420px; }}
body.mode-game .boxhead {{ margin-bottom:8px; }}
body.mode-cols .game {{ display:none; }}
footer {{ color:var(--dim); font-size:12px; border-top:1px solid var(--line); padding-top:14px; margin-top:30px; }}
a {{ color:var(--acc); }}
/* comments */
.cbtn {{ float:right; background:transparent; border:1px solid var(--line); color:var(--dim);
         border-radius:6px; font-size:11px; padding:1px 8px; cursor:pointer; }}
.cbtn:hover {{ border-color:var(--acc); color:var(--acc); }}
.box.has-comment {{ border-left:3px solid var(--warn); }}
.box.has-comment .cbtn {{ border-color:var(--warn); color:var(--warn); }}
.cbtn.on {{ border-color:var(--acc); color:var(--acc); }}
.ebtn {{ float:right; background:transparent; border:1px solid var(--line); color:var(--dim);
         border-radius:6px; font-size:11px; padding:1px 8px; cursor:pointer; margin-right:6px; }}
.ebtn:hover {{ border-color:var(--re); color:var(--re); }}
.ebtn.on {{ border-color:var(--re); color:var(--re); }}
.box.has-edit {{ border-left:3px solid var(--re); }}
.box.has-edit .ebtn {{ border-color:var(--re); color:var(--re); }}
/* live-editable in-game textbox */
.gtext[contenteditable="true"] {{ outline:2px dashed var(--re); outline-offset:4px; cursor:text; }}
.gwin.edited .gtext {{ }}
.ehint {{ font-size:11px; color:var(--dim); margin:6px 0 0; }}
.erow {{ display:flex; gap:8px; margin-top:8px; align-items:center; }}
.erow button {{ font-size:12px; padding:3px 12px; border-radius:6px; border:1px solid var(--line);
                background:var(--panel2); color:var(--ink); cursor:pointer; }}
.erow button.save {{ border-color:var(--re); color:var(--re); }}
.dre.edited {{ color:var(--re); }}
.cwrap {{ }}
.ceditor {{ margin:8px 0 2px; background:var(--panel2); border:1px solid var(--line); border-radius:8px; padding:10px; }}
.ceditor textarea {{ width:100%; min-height:64px; background:#12141a; color:var(--ink); border:1px solid var(--line);
                     border-radius:6px; padding:8px; font:13px/1.5 inherit; resize:vertical; box-sizing:border-box; }}
.ceditor .crow {{ display:flex; gap:8px; margin-top:6px; align-items:center; }}
.ceditor button {{ font-size:12px; padding:3px 12px; border-radius:6px; border:1px solid var(--line);
                   background:var(--panel); color:var(--ink); cursor:pointer; }}
.ceditor button.save {{ border-color:var(--acc); color:var(--acc); }}
.ceditor button.del {{ border-color:var(--warn); color:var(--warn); }}
.csaved {{ margin:6px 0; padding:8px 10px; background:rgba(255,157,118,.08); border-left:3px solid var(--warn);
           border-radius:0 6px 6px 0; font-size:13px; color:var(--ink); white-space:pre-wrap; }}
.csaved .meta {{ color:var(--dim); font-size:11px; }}
/* export bar (sticky bottom-right) */
#cbar {{ position:fixed; right:18px; bottom:18px; z-index:50; display:flex; gap:8px; align-items:center;
         background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:8px 12px;
         box-shadow:0 4px 16px rgba(0,0,0,.5); font-size:13px; }}
#cbar .cnum {{ color:var(--warn); font-weight:700; }}
#cbar button {{ font-size:12px; padding:4px 12px; border-radius:6px; border:1px solid var(--acc);
                background:var(--panel); color:var(--acc); cursor:pointer; }}
#cbar button.clear {{ border-color:var(--warn); color:var(--warn); }}
#cbar.empty {{ opacity:.5; }}
#exportmodal {{ position:fixed; inset:0; z-index:60; background:rgba(0,0,0,.6); display:none; align-items:center; justify-content:center; }}
#exportmodal.show {{ display:flex; }}
#exportmodal .card {{ background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:18px;
                      width:min(760px,92vw); max-height:82vh; display:flex; flex-direction:column; }}
#exportmodal textarea {{ width:100%; flex:1; min-height:340px; background:#12141a; color:var(--ink);
                         border:1px solid var(--line); border-radius:8px; padding:12px; font:12.5px/1.5 "Courier New",monospace; }}
#exportmodal .er {{ display:flex; gap:10px; margin-top:10px; }}
/* comments dashboard */
.nav-special {{ display:block; padding:6px 8px; margin:2px 0; color:var(--ink); text-decoration:none;
                border-radius:6px; font-size:13px; font-weight:600; border:1px solid var(--line); }}
.nav-special:hover {{ background:var(--panel2); border-color:var(--acc); }}
#nav-scenes {{ display:none; }}                       /* shown only in comments view */
body.view-comments #nav-scenes {{ display:block; }}
body.view-comments #nav-comments {{ border-color:var(--warn); color:var(--warn); }}
#comments-dash {{ display:none; margin-bottom:30px; }}
body.view-comments #comments-dash {{ display:block; }}
/* roadmap view */
#roadmap-dash {{ display:none; margin-bottom:30px; }}
body.view-roadmap #roadmap-dash {{ display:block; }}
body.view-roadmap .scene, body.view-roadmap .disc-head, body.view-roadmap .controls,
body.view-roadmap #comments-dash {{ display:none; }}
body.view-roadmap #nav-scenes {{ display:block; }}
body.view-roadmap #nav-roadmap {{ border-color:var(--acc); color:var(--acc); }}
#roadmap-dash h2 {{ font-size:19px; color:var(--acc); border-bottom:1px solid var(--line); padding-bottom:6px; }}
.rm-item {{ background:var(--panel); border:1px solid var(--line); border-left:4px solid var(--line);
            border-radius:0 8px 8px 0; padding:11px 14px; margin:10px 0; }}
.rm-item.st-done {{ border-left-color:var(--acc); }}
.rm-item.st-prog {{ border-left-color:var(--jp); }}
.rm-item.st-todo {{ border-left-color:var(--warn); }}
.rm-head {{ display:flex; justify-content:space-between; align-items:baseline; gap:12px; margin-bottom:4px; }}
.rm-title {{ font-weight:700; font-size:15px; }}
.rm-status {{ font-size:11px; font-weight:700; padding:2px 9px; border-radius:10px; white-space:nowrap; }}
.st-done .rm-status {{ background:rgba(111,178,255,.15); color:var(--acc); }}
.st-prog .rm-status {{ background:rgba(255,212,121,.15); color:var(--jp); }}
.st-todo .rm-status {{ background:rgba(255,157,118,.15); color:var(--warn); }}
.rm-body {{ color:var(--dim); font-size:13px; line-height:1.55; }}
body.view-comments .scene {{ display:none; }}          /* hide the scene list in comments view */
body.view-comments .controls {{ display:none; }}
#comments-dash h2 {{ font-size:19px; color:var(--acc); border-bottom:1px solid var(--line); padding-bottom:6px; }}
.dashbar {{ display:flex; gap:12px; align-items:center; margin:12px 0 16px; font-size:13px; color:var(--dim); flex-wrap:wrap; }}
.dashbar button {{ font-size:12px; padding:4px 12px; border-radius:6px; border:1px solid var(--line); background:var(--panel); cursor:pointer; }}
.dashbar button.save {{ border-color:var(--acc); color:var(--acc); }}
.dashbar button.del {{ border-color:var(--warn); color:var(--warn); }}
.dash-empty {{ color:var(--dim); font-style:italic; }}
.ditem {{ background:var(--panel); border:1px solid var(--line); border-left:3px solid var(--warn);
          border-radius:0 8px 8px 0; padding:10px 12px; margin:8px 0; }}
.ditem .dhead {{ display:flex; justify-content:space-between; align-items:baseline; gap:10px; margin-bottom:5px; }}
.ditem .dkey {{ font-size:12px; color:var(--acc); font-weight:700; }}
.ditem .dspk {{ color:var(--dim); font-size:12px; }}
.ditem .dts {{ color:var(--dim); font-size:11px; }}
.ditem .dre {{ color:var(--re); font-size:12.5px; margin:2px 0 5px; }}
.ditem .dre.edited {{ font-weight:600; }}
.ditem .dkind {{ font-size:10px; color:var(--warn); font-weight:600; }}
.ditem .dtext {{ color:var(--ink); font-size:13.5px; white-space:pre-wrap; }}
.ditem .dacts {{ margin-top:7px; display:flex; gap:8px; }}
.ditem .dacts button, .ditem .dacts a {{ font-size:11.5px; padding:2px 10px; border-radius:5px; border:1px solid var(--line);
          background:var(--panel2); color:var(--ink); cursor:pointer; text-decoration:none; }}
.ditem .dacts .djump {{ border-color:var(--acc); color:var(--acc); }}
.ditem .dacts .ddel {{ border-color:var(--warn); color:var(--warn); }}
</style></head>
<body>
<div id="wrap">
<nav id="side">
  <h1>WA2 Retranslation</h1>
  <div class="statuscard">
    <div class="sc-row"><span class="sc-k">Dialogue boxes</span><span class="sc-v">{box_total:,} total</span></div>
    <div class="sc-bar" title="translated dialogue boxes over the full extracted script">
      <span class="sc-deep" style="width:{box_pct}%"></span>
    </div>
    <div class="sc-row"><span class="sc-dot deep"></span><span class="sc-k">Translated</span><span class="sc-v">{box_match:,} · {box_pct}%</span></div>
    <div class="sc-row"><span class="sc-dot rem"></span><span class="sc-k">Remaining</span><span class="sc-v">{box_left:,} left</span></div>
    <div class="sc-sep"></div>
    <div class="sc-row"><span class="sc-k">Indexed slots</span><span class="sc-v">{slot_total:,}</span></div>
    <div class="sc-bar" title="deep RE + first-pass of all script slots">
      <span class="sc-deep" style="width:{_pct(slot_deep)}%"></span>
      <span class="sc-fp" style="width:{_pct(slot_deep)+_pct(slot_fp)}%"></span>
    </div>
    <div class="sc-row"><span class="sc-dot deep"></span><span class="sc-k">Deep retranslation</span><span class="sc-v">{slot_deep:,} · {_pct(slot_deep)}%</span></div>
    <div class="sc-row"><span class="sc-dot fp"></span><span class="sc-k">First-pass (fit)</span><span class="sc-v">{slot_fp:,} · {_pct(slot_fp)}%</span></div>
    <div class="sc-row"><span class="sc-dot rem"></span><span class="sc-k">Untranslated</span><span class="sc-v">{slot_remaining:,} left</span></div>
    <div class="sc-sep"></div>
    <div class="sc-row"><span class="sc-k">Guide areas</span><span class="sc-v">{done_areas+fp_areas}/{total_areas} started</span></div>
    <div class="sc-bar" title="{done_areas} deep + {fp_areas} first-pass of {total_areas} guide areas">
      <span class="sc-deep" style="width:{round(100*done_areas/total_areas) if total_areas else 0}%"></span>
      <span class="sc-fp" style="width:{round(100*(done_areas+fp_areas)/total_areas) if total_areas else 0}%"></span>
    </div>
    <div class="sc-row"><span class="sc-dot deep"></span><span class="sc-k">Deep</span><span class="sc-v">{done_areas}</span></div>
    <div class="sc-row"><span class="sc-dot fp"></span><span class="sc-k">First-pass</span><span class="sc-v">{fp_areas}</span></div>
    <div class="sc-row"><span class="sc-dot rem"></span><span class="sc-k">Complete (no clean-JP left)</span><span class="sc-v">{areas_complete}</span></div>
    <div class="sc-note">{box_pct}% of all {box_total:,} dialogue boxes have insert-ready text · updated {now}</div>
  </div>
  <a class="nav-special" id="nav-comments" href="#comments">💬 My Comments <span class="cnt" id="nav-ccount">0</span></a>
  <a class="nav-special" id="nav-scenes" href="#top">📖 Back to scenes</a>
  {nav_html}
</nav>
<main id="main">
  <div id="top"></div>
  <div class="topbar"><h1>Wild Arms — 2nd Ignition · Retranslation</h1></div>
  <div class="stats">{done_areas} areas fully translated + {fp_areas} first-pass = {done_areas+fp_areas}/{total_areas} covered · {total_boxes} deep + {fp_boxes} first-pass boxes · mapped to the Syonyx GameFAQs walkthrough spine</div>
  <div class="controls">
    <span>View:
      <label><input type="radio" name="mode" value="both" checked> Both</label>
      <label><input type="radio" name="mode" value="cols"> Columns</label>
      <label><input type="radio" name="mode" value="game"> Game preview</label>
    </span>
    <span>Columns:
      <label><input type="checkbox" id="t-jp" checked> JP</label>
      <label><input type="checkbox" id="t-lit" checked> Literal</label>
      <label><input type="checkbox" id="t-en" checked> EN</label>
      <label><input type="checkbox" id="t-gs" checked> Script placeholders</label>
      <span style="color:var(--re)">RE always shown</span>
    </span>
  </div>
  <section id="comments-dash">
    <h2>💬 My Comments</h2>
    <div class="dashbar">
      <span><span id="dash-count">0</span> saved comment(s), stored in this browser.</span>
      <button class="save" id="dash-export">Export feedback</button>
      <button class="del" id="dash-clear">Delete all</button>
    </div>
    <div id="dash-list"></div>
    <p id="dash-empty" class="dash-empty">No comments yet. Click 💬 comment on any translation box to add feedback.</p>
  </section>
  {body}
  <footer>
    Generated by <code>tools_wa2/build_wiki.py</code> on {now}. Re-run after each mission to update.<br>
    Columns: <span style="color:var(--jp)">JP</span> = decoded Japanese ·
    <span style="color:var(--lit)">LIT</span> = literal ·
    <span style="color:var(--en)">EN</span> = original US localization ·
    <span style="color:var(--re)">RE</span> = our retranslation (inserted text).
    {unreg_html}
  </footer>
</main></div>
<div id="cbar" class="empty">
  <span><span class="cnum" id="ccount">0</span> comment(s)</span>
  <button id="cexport">Export feedback</button>
  <button class="clear" id="cclear">Clear all</button>
</div>
<div id="exportmodal">
  <div class="card">
    <div style="margin-bottom:8px;color:var(--dim);font-size:13px;">Copy this and hand it back to Claude to apply the fixes. Each entry carries the exact file + box id.</div>
    <textarea id="exporttext" readonly></textarea>
    <div class="er">
      <button class="save" id="ecopy">Copy to clipboard</button>
      <button id="eclose">Close</button>
    </div>
  </div>
</div>
<script>
function bind(id, cls) {{
  var el = document.getElementById(id);
  el.addEventListener('change', function() {{ document.body.classList.toggle(cls, !el.checked); }});
}}
bind('t-jp','hide-jp'); bind('t-lit','hide-lit'); bind('t-en','hide-en'); bind('t-gs','hide-gs');
document.querySelectorAll('input[name=mode]').forEach(function(r) {{
  r.addEventListener('change', function() {{
    document.body.classList.remove('mode-both','mode-cols','mode-game');
    document.body.classList.add('mode-' + r.value);
  }});
}});
document.body.classList.add('mode-both');

/* ---------------- comments (localStorage-backed) ---------------- */
var CK = 'wa2wiki.comments.v1';
function load() {{ try {{ return JSON.parse(localStorage.getItem(CK) || '{{}}'); }} catch(e) {{ return {{}}; }} }}
function save(o) {{ localStorage.setItem(CK, JSON.stringify(o)); }}
function count() {{ return Object.keys(load()).length; }}
function refreshBar() {{
  var n = count();
  var cc = document.getElementById('ccount'); if (cc) cc.textContent = n;
  var bar = document.getElementById('cbar'); if (bar) bar.classList.toggle('empty', n === 0);
  var nav = document.getElementById('nav-ccount'); if (nav) nav.textContent = n;
  // NOTE: do NOT auto-call renderDash here — callers that are in the dashboard call it explicitly.
  // (Avoids double-render + recursion risk.)
}}
function buildFeedback(s) {{
  var keys = Object.keys(s).sort();
  var out = 'WA2 TRANSLATION FEEDBACK (' + keys.length + ' item(s)) — generated ' + new Date().toISOString().slice(0,16).replace('T',' ') + '\\n';
  out += 'Apply each fix to the given file + box id.\\n' + '='.repeat(64) + '\\n\\n';
  keys.forEach(function(k) {{
    var c = s[k]; var parts = k.split('#');
    out += 'FILE: insert/' + parts[0] + '\\n';
    out += 'BOX:  #' + (parts.slice(1).join('#')) + (c.spk ? '  (' + c.spk + ')' : '') + '\\n';
    if (c.re) out += 'CURRENT RE: ' + c.re + '\\n';
    if (c.editRe) out += 'PROPOSED RE (edited on site, sample names shown): ' + c.editRe + '\\n';
    if (c.text) out += 'FEEDBACK: ' + c.text + '\\n';
    out += '-'.repeat(50) + '\\n\\n';
  }});
  return out;
}}
function renderDash() {{
  var list = document.getElementById('dash-list');
  var empty = document.getElementById('dash-empty');
  var dc = document.getElementById('dash-count');
  if (!list) return;                       // roadmap/scene view: nothing to render
  var s = load(); var keys = Object.keys(s).sort();
  if (dc) dc.textContent = keys.length;
  list.innerHTML = '';
  if (empty) empty.style.display = keys.length ? 'none' : 'block';
  keys.forEach(function(k) {{
    var c = s[k]; var parts = k.split('#'); var file = parts[0]; var box = parts.slice(1).join('#');
    var el = document.createElement('div'); el.className = 'ditem';
    var kind = c.editRe ? (c.text ? 'edit + comment' : 'edited text') : 'comment';
    el.innerHTML =
      '<div class="dhead"><span class="dkey">' + esc(file) + ' &middot; #' + esc(box) + ' <span class="dkind">[' + kind + ']</span></span>' +
        '<span class="dts">' + esc(c.ts||'') + '</span></div>' +
      (c.spk ? '<div class="dspk">speaker: ' + esc(c.spk) + '</div>' : '') +
      (c.re ? '<div class="dre">orig RE: ' + esc(c.re) + '</div>' : '') +
      (c.editRe ? '<div class="dre edited">NEW RE: ' + esc(c.editRe) + '</div>' : '') +
      (c.text ? '<div class="dtext">' + esc(c.text) + '</div>' : '') +
      '<div class="dacts"><button class="djump">Jump to box</button><button class="ddel">Delete</button></div>';
    el.querySelector('.djump').addEventListener('click', function() {{
      showScenes();
      var target = document.querySelector('.box[data-key="' + cssEsc(k) + '"]');
      if (target) {{ target.scrollIntoView({{behavior:'smooth', block:'center'}});
                     target.style.outline='2px solid var(--acc)'; setTimeout(function(){{target.style.outline='';}},1800); }}
    }});
    el.querySelector('.ddel').addEventListener('click', function() {{
      var st = load(); delete st[k]; save(st); renderSaved(k); refreshBar(); renderDash();
    }});
    list.appendChild(el);
  }});
}}
function showComments() {{ document.body.classList.add('view-comments'); renderDash(); window.scrollTo(0,0); }}
function showScenes() {{ document.body.classList.remove('view-comments'); }}
function renderSaved(key) {{
  var wrap = document.querySelector('.cwrap[data-key="' + cssEsc(key) + '"]');
  if (!wrap) return;
  var store = load(), c = store[key];
  var box = wrap.closest('.box');
  var editorOpen = wrap.querySelector('.ceditor');
  wrap.querySelectorAll('.csaved').forEach(function(e) {{ e.remove(); }});
  if (c && c.text) {{
    if (box) box.classList.add('has-comment');
    var d = document.createElement('div');
    d.className = 'csaved';
    d.innerHTML = '<div class="meta">' + esc(key) + ' — ' + esc(c.ts) + '</div>' + esc(c.text);
    if (editorOpen) wrap.insertBefore(d, editorOpen); else wrap.appendChild(d);
  }} else {{
    if (box) box.classList.remove('has-comment');
  }}
  applyEdit(key);
}}
/* paint any saved edited-RE back into the in-game textbox */
function applyEdit(key) {{
  var box = document.querySelector('.box[data-key="' + cssEsc(key) + '"]');
  if (!box) return;
  var gt = box.querySelector('.gtext'); if (!gt) return;
  var gwin = box.querySelector('.gwin');
  var store = load(), c = store[key];
  if (c && c.editRe) {{
    box.classList.add('has-edit');
    if (gwin) gwin.classList.add('edited');
    // only overwrite display if not currently being edited
    if (gt.getAttribute('contenteditable') !== 'true') gt.innerHTML = reToHtml(c.editRe);
  }} else {{
    box.classList.remove('has-edit');
    if (gwin) gwin.classList.remove('edited');
    if (gt.getAttribute('contenteditable') !== 'true') {{
      var orig = gt.getAttribute('data-orig') || '';
      gt.innerHTML = orig ? reToHtml(applyNames(orig)) : gt.innerHTML;
    }}
  }}
}}
var NAMEMAP = {{'{{0}}':'Ashley','{{1}}':'Brad','{{2}}':'Lilka','{{3}}':'Marina','{{5}}':'Liz','{{6}}':'Ard'}};
function applyNames(s) {{ Object.keys(NAMEMAP).forEach(function(k){{ s = s.split(k).join(NAMEMAP[k]); }}); return s; }}
function reToHtml(s) {{ return s.split(' / ').map(esc).join('<br>'); }}
/* read the editable textbox back to a " / "-joined RE string */
function htmlToRe(gt) {{
  var html = gt.innerHTML.replace(/<div>/gi,'\\n').replace(/<\\/div>/gi,'').replace(/<br\\s*\\/?>/gi,'\\n');
  var tmp = document.createElement('div'); tmp.innerHTML = html;
  var txt = tmp.textContent || '';
  return txt.split('\\n').map(function(x){{return x.trim();}}).filter(function(x){{return x;}}).join(' / ');
}}
function esc(s) {{ return String(s == null ? '' : s).replace(/[&<>]/g, function(m) {{ return {{'&':'&amp;','<':'&lt;','>':'&gt;'}}[m]; }}); }}
function cssEsc(s) {{ return s.replace(/"/g,'\\\\"'); }}

document.querySelectorAll('.cbtn').forEach(function(btn) {{
  btn.addEventListener('click', function(e) {{
    e.stopPropagation();
    var key = btn.getAttribute('data-key');
    var wrap = document.querySelector('.cwrap[data-key="' + cssEsc(key) + '"]');
    var existing = wrap.querySelector('.ceditor');
    if (existing) {{ existing.remove(); btn.classList.remove('on'); return; }}
    btn.classList.add('on');
    var store = load(), cur = (store[key] && store[key].text) || '';
    var ed = document.createElement('div');
    ed.className = 'ceditor';
    ed.innerHTML = '<textarea placeholder="What should change about this translation? Be specific — I read this verbatim as the fix instruction.">' + esc(cur) + '</textarea>' +
      '<div class="crow"><button class="save">Save</button><button class="del">Delete</button>' +
      '<span style="color:var(--dim);font-size:11px">saved locally in your browser</span></div>';
    wrap.insertBefore(ed, wrap.firstChild);
    var ta = ed.querySelector('textarea'); ta.focus();
    ed.querySelector('.save').addEventListener('click', function() {{
      var v = ta.value.trim(); var s = load();
      if (v) {{ s[key] = {{ text: v, ts: new Date().toISOString().slice(0,16).replace('T',' '),
                            re: btn.getAttribute('data-re'), spk: btn.getAttribute('data-spk') }}; }}
      else {{ delete s[key]; }}
      save(s); ed.remove(); btn.classList.remove('on'); renderSaved(key); refreshBar();
    }});
    ed.querySelector('.del').addEventListener('click', function() {{
      var s = load(); if (s[key]) {{ delete s[key].text; if (!s[key].editRe) delete s[key]; }} save(s); ed.remove(); btn.classList.remove('on'); renderSaved(key); refreshBar();
    }});
  }});
}});

/* ---------------- edit the in-game textbox directly ---------------- */
document.querySelectorAll('.ebtn').forEach(function(btn) {{
  btn.addEventListener('click', function(e) {{
    e.stopPropagation();
    var key = btn.getAttribute('data-key');
    var box = document.querySelector('.box[data-key="' + cssEsc(key) + '"]');
    var gt = box && box.querySelector('.gtext');
    if (!gt) return;
    var editing = gt.getAttribute('contenteditable') === 'true';
    if (editing) {{ cancelEdit(box, gt, btn); return; }}
    // enter edit mode: make the textbox editable in place
    btn.classList.add('on');
    gt.setAttribute('contenteditable', 'true');
    gt.focus();
    // controls under the game window
    var game = box.querySelector('.game');
    var bar = document.createElement('div'); bar.className = 'erow';
    bar.innerHTML = '<button class="save">Save edit</button><button class="revert">Revert to original</button>' +
      '<button class="cancel">Cancel</button>' +
      '<span class="ehint">edits save as feedback in this browser · name codes shown as sample names</span>';
    game.appendChild(bar);
    var hint = document.createElement('div'); hint.className='ehint'; hint.textContent='Editing — type directly in the box above. Line breaks = new textbox line.';
    game.appendChild(hint);
    bar.querySelector('.save').addEventListener('click', function() {{
      var v = htmlToRe(gt); var s = load();
      var orig = applyNames(gt.getAttribute('data-orig') || '');
      if (v && v !== orig) {{
        s[key] = s[key] || {{}}; s[key].editRe = v;
        s[key].ts = new Date().toISOString().slice(0,16).replace('T',' ');
        s[key].re = btn.getAttribute('data-re'); s[key].spk = btn.getAttribute('data-spk');
      }} else if (s[key]) {{ delete s[key].editRe; if (!s[key].text) delete s[key]; }}
      save(s); finishEdit(box, gt, btn, bar, hint); renderSaved(key); refreshBar();
    }});
    bar.querySelector('.revert').addEventListener('click', function() {{
      var s = load(); if (s[key]) {{ delete s[key].editRe; if (!s[key].text) delete s[key]; }}
      save(s); finishEdit(box, gt, btn, bar, hint); renderSaved(key); refreshBar();
    }});
    bar.querySelector('.cancel').addEventListener('click', function() {{ cancelEdit(box, gt, btn, bar, hint); }});
  }});
}});
function finishEdit(box, gt, btn, bar, hint) {{
  gt.removeAttribute('contenteditable'); btn.classList.remove('on');
  if (bar) bar.remove(); if (hint) hint.remove();
}}
function cancelEdit(box, gt, btn, bar, hint) {{
  gt.removeAttribute('contenteditable'); btn.classList.remove('on');
  var g = box.querySelector('.game');
  if (!bar) {{ var b=g.querySelector('.erow'); if(b) b.remove(); var hs=g.querySelectorAll('.ehint'); hs.forEach(function(h){{h.remove();}}); }}
  else {{ bar.remove(); if (hint) hint.remove(); }}
  applyEdit(box.getAttribute('data-key'));   // repaint saved/original
}}

/* export: build a readable feedback block Claude can act on */
function openExport() {{
  document.getElementById('exporttext').value = buildFeedback(load());
  document.getElementById('exportmodal').classList.add('show');
}}
document.getElementById('cexport').addEventListener('click', openExport);
document.getElementById('dash-export').addEventListener('click', openExport);
/* nav + dashboard controls */
document.getElementById('nav-comments').addEventListener('click', function(e) {{ e.preventDefault(); showComments(); }});
document.getElementById('nav-scenes').addEventListener('click', function(e) {{ e.preventDefault(); showScenes(); window.scrollTo(0,0); }});
document.getElementById('dash-clear').addEventListener('click', function() {{
  if (!confirm('Delete ALL saved comments? This cannot be undone.')) return;
  localStorage.removeItem(CK);
  document.querySelectorAll('.box.has-comment').forEach(function(b){{ b.classList.remove('has-comment'); }});
  document.querySelectorAll('.box.has-edit').forEach(function(b){{ b.classList.remove('has-edit'); var g=b.querySelector('.gtext'); if(g){{var o=g.getAttribute('data-orig')||''; if(o) g.innerHTML=reToHtml(applyNames(o));}} }});
  document.querySelectorAll('.csaved').forEach(function(e){{ e.remove(); }});
  refreshBar(); renderDash();
}});
document.getElementById('eclose').addEventListener('click', function() {{ document.getElementById('exportmodal').classList.remove('show'); }});
function clearAllFeedback() {{
  localStorage.removeItem(CK);
  document.querySelectorAll('.box.has-comment').forEach(function(b){{ b.classList.remove('has-comment'); }});
  document.querySelectorAll('.box.has-edit').forEach(function(b){{ b.classList.remove('has-edit'); var g=b.querySelector('.gtext'); if(g){{var o=g.getAttribute('data-orig')||''; if(o) g.innerHTML=reToHtml(applyNames(o));}} }});
  document.querySelectorAll('.csaved').forEach(function(e){{ e.remove(); }});
  refreshBar(); renderDash();
}}
document.getElementById('ecopy').addEventListener('click', function() {{
  var t = document.getElementById('exporttext'); t.select();
  try {{ navigator.clipboard.writeText(t.value); }} catch(e) {{ document.execCommand('copy'); }}
  this.textContent = 'Copied!'; var b=this; setTimeout(function(){{b.textContent='Copy to clipboard';}}, 1500);
  if (count() > 0 && confirm('Copied. Clear your saved feedback from this browser now?')) {{
    clearAllFeedback();
    document.getElementById('exportmodal').classList.remove('show');
  }}
}});
document.getElementById('cclear').addEventListener('click', function() {{
  if (!confirm('Delete ALL saved comments? This cannot be undone.')) return;
  localStorage.removeItem(CK);
  document.querySelectorAll('.box.has-comment').forEach(function(b){{ b.classList.remove('has-comment'); }});
  document.querySelectorAll('.box.has-edit').forEach(function(b){{ b.classList.remove('has-edit'); var g=b.querySelector('.gtext'); if(g){{var o=g.getAttribute('data-orig')||''; if(o) g.innerHTML=reToHtml(applyNames(o));}} }});
  document.querySelectorAll('.csaved').forEach(function(e){{ e.remove(); }});
  refreshBar();
}});

/* on load: paint existing saved comments */
Object.keys(load()).forEach(renderSaved);
refreshBar();

/* highlight the nav link for whichever area section is currently in view */
(function() {{
  var navById = {{}};
  document.querySelectorAll('.nav-scene[href^="#"]').forEach(function(a) {{
    navById[a.getAttribute('href').slice(1)] = a;
  }});
  var sections = Array.prototype.slice.call(document.querySelectorAll('section.scene[id]'));
  if (!sections.length) return;
  var current = null;
  function setActive(id) {{
    if (id === current) return;
    if (current && navById[current]) navById[current].classList.remove('active');
    current = id;
    var link = navById[id];
    if (link) {{
      link.classList.add('active');
      // keep the active link visible in the (scrollable) nav
      var nav = link.closest('nav');
      if (nav) {{
        var above = link.offsetTop < nav.scrollTop;
        var below = link.offsetTop > nav.scrollTop + nav.clientHeight;
        if (above || below) link.scrollIntoView({{block:'nearest'}});
      }}
    }}
  }}
  var obs = new IntersectionObserver(function(entries) {{
    // pick the top-most section currently intersecting the viewport
    var visible = entries.filter(function(e) {{ return e.isIntersecting; }});
    if (visible.length) {{
      visible.sort(function(a,b) {{ return a.boundingClientRect.top - b.boundingClientRect.top; }});
      setActive(visible[0].target.id);
    }}
  }}, {{ rootMargin: '-80px 0px -60% 0px', threshold: 0 }});
  sections.forEach(function(s) {{ obs.observe(s); }});
  // clicking a nav link highlights immediately (don't wait for scroll)
  document.querySelectorAll('.nav-scene[href^="#"]').forEach(function(a) {{
    a.addEventListener('click', function() {{ setActive(a.getAttribute('href').slice(1)); }});
  }});
}})();
</script>
</body></html>'''

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, 'w', encoding='utf-8').write(doc)
    return dict(scenes=total_scenes, boxes=total_boxes, out=OUT, unregistered=unregistered)

if __name__ == '__main__':
    r = build()
    print(f"wiki built: {r['out']}")
    print(f"  {r['scenes']} scenes, {r['boxes']} insert-ready boxes")
    if r['unregistered']:
        print(f"  WARN unregistered FINAL files: {r['unregistered']}")
