#!/usr/bin/env python3
"""
Character VOICE PROFILES — built independently from the English and the Japanese, so the two
can be compared and drift caught.

WHY TWO SIDES
  docs/WA2_CHARACTER_ROSTER.md already proposes a voice for each character, but every entry is
  marked draft / "needs sign-off" — it is a hypothesis. This tool does not propose anything: it
  MEASURES each character's register from the shipped script, once from the EN and once from the
  JP, and reports where the two disagree. A disagreement is the localization having flattened or
  changed that character, which is exactly what the retranslation exists to fix.

WHY THE MEASUREMENTS ARE MEANINGFUL
  Japanese marks speaker register overwhelmingly in KANA — first-person pronoun, second-person
  pronoun, politeness (です/ます), sentence-final particles, copula. Our decoder solves kana
  completely even where kanji are still unsolved (<b:xxxx>), so register survives the decode
  intact. Validated against a documented fact: Marivel is recorded in WA2_NAME_DICTIONARY.md as
  わらわ/〜じゃ speech, and this tool independently measures わらわ×14 and じゃ×42 for her.

DATA QUALITY — READ THIS BEFORE TRUSTING A PROFILE
  * The SPEAKER label is hand-annotated (from the *_FINAL.txt files) — reliable.
  * The EN text on a row is the shipped English for that box — reliable.
  * The JP text on a row was attached by the ALIGNER, which docs/WA2_INSERTION_MODEL.md records
    as drifting. So a minority of rows carry the wrong Japanese. Two mitigations:
      1. `lit_backed` counts rows where a human wrote a literal translation, i.e. someone read
         that JP against that slot. `en_lit_agreement` then checks, per row, whether that literal
         and the shipped English still share content words.
      2. Register stats are aggregates, so a minority of bad rows shifts them but rarely inverts
         them. Every profile therefore ships EVIDENCE LINES — verify before acting.
  Profiles below `--min` lines are emitted but marked low-sample.

USAGE
  python3 tools/build_voices.py            # write data/voices.json (+ --md for a readable doc)
  python3 tools/build_voices.py --show Brad
"""
import os, sys, json, re, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB   = os.path.join(ROOT, 'data', 'script', 'wa2_db.json')
OUT  = os.path.join(ROOT, 'data', 'voices.json')
MD   = os.path.join(ROOT, 'docs', 'WA2_VOICE_PROFILES.md')

# Speaker labels that are bookkeeping or a crowd, not a character with a voice to keep.
JUNK = re.compile(r'propagated|SKIPPED|^system|^\s*$|^\?+$', re.I)
# Labels that are a ROLE (many different mouths) rather than one person. Still profiled — a
# consistent "villager" register is useful — but flagged so nobody treats them as a character.
ROLE = re.compile(r'^(townsperson|townswoman|villager|crew ?member.*|chateau npc|kid|elder|chief|'
                  r'miner|scholar|student|soldier|party|guard|merchant|sailor|nurse|innkeeper|'
                  r'npc|shopkeeper|bartender|receptionist|engineer|pilot|worker|woman|man|boy|girl|'
                  r'.*panel.*|.*prompt.*|.*scroll.*|lore.*|examine.*|tutorial.*|.*npc.*)$', re.I)

def S(r, k):
    v = r.get(k)
    return v if isinstance(v, str) else ''

_W = re.compile(r"[a-z']{4,}")
def en_lit_agree(r):
    """Do this row's shipped English and its human literal say the same thing?

    A human wrote `lit` from the row's Japanese, so lit is a faithful gloss of that JP. `en` is
    the shipped localization on the same row. Shared content words => the two are the same line.

    Read the negative case carefully: DISAGREEMENT HAS TWO CAUSES and this check cannot separate
    them — (a) the aligner attached the wrong Japanese to this slot, or (b) the localization
    rewrote the line so heavily that nothing survives, which the divergence audit records as the
    dominant failure mode. Both matter here, so a low score is a "read the evidence" signal
    rather than proof of misalignment. Marivel is the type case: she scores low, yet her わらわ
    (used by nobody else) appears 14 times, so the Japanese really is hers and it is the ENGLISH
    that walked away from it.
    Catches e.g. Tim US#4134: JP 「ボクは、イヤだッ！」 / lit "I won't have it!" vs a shipped EN
    about "abilities as great as his".
    """
    lit, en = S(r, 'lit').lower(), S(r, 'en').lower()
    if not lit or not en: return None                 # unknowable, not counted either way
    a, b = set(_W.findall(lit)), set(_W.findall(en))
    if not a or not b: return None
    return len(a & b) / min(len(a), len(b)) >= 0.25

# ---- Japanese register markers (all kana-detectable, so unsolved kanji don't hide them) ----
JP_FIRST = [('俺', 'ore — rough masculine'), ('オレ', 'ore — rough masculine'),
            ('僕', 'boku — soft masculine'), ('ボク', 'boku — soft masculine'),
            ('私', 'watashi — neutral/formal'), ('わたし', 'watashi — neutral/formal'),
            ('わたくし', 'watakushi — very formal'), ('あたし', 'atashi — casual feminine'),
            ('わし', 'washi — elderly masculine'), ('わらわ', 'warawa — archaic noble feminine'),
            ('うち', 'uchi — regional/casual feminine')]
JP_SECOND = [('お前', 'omae — rough'), ('おまえ', 'omae — rough'), ('貴様', 'kisama — hostile'),
             ('あんた', 'anta — familiar/brusque'), ('君', 'kimi — familiar/soft'),
             ('あなた', 'anata — polite'), ('おぬし', 'onushi — archaic')]
# Sentence-final particles must actually be FINAL. Counting them anywhere in the string is what
# makes a naive pass call everyone archaic: bare じゃ matches modern じゃない / じゃあ / それじゃ,
# and さ/ね occur inside ordinary words. Each pattern below therefore anchors to a sentence end
# (。！？〜 / 」 / line end). Validated: this drops Lilka's spurious "archaic" reading while
# leaving Marivel's documented わらわ/のじゃ intact.
_END = r'(?=[。！？!?〜、」』\s]|$)'
JP_ENDER = [
    ('のじゃ',  'archaic/elderly',      r'のじゃ' + _END),
    ('じゃ',    'archaic copula',       r'(?<!ん)じゃ' + _END),      # excludes じゃない/じゃあ/…
    ('ぞ',      'assertive masculine',  r'ぞ' + _END),
    ('ぜ',      'assertive masculine',  r'ぜ' + _END),
    ('かしら',  'feminine musing',      r'かしら' + _END),
    ('のよ',    'feminine assertive',   r'のよ' + _END),
    ('だわ',    'feminine',             r'だわ' + _END),
    ('ですわ',  'refined feminine',     r'ですわ' + _END),
    ('わい',    'elderly masculine',    r'わい' + _END),
    ('ねぇ',    'drawn-out casual',     r'ねぇ' + _END),
]

def jp_features(text):
    n = max(len(text), 1)
    def hits(pairs):
        out = {}
        for tok, label in pairs:
            c = text.count(tok)
            if c: out[tok] = {'n': c, 'label': label}
        return out
    first, second = hits(JP_FIRST), hits(JP_SECOND)
    ender = {}
    for tok, label, pat in JP_ENDER:
        c = len(re.findall(pat, text))
        if c: ender[tok] = {'n': c, 'label': label}
    polite = len(re.findall(r'です|ます|ございま', text))
    return {
        'chars': len(text),
        'first_person': first, 'second_person': second, 'enders': ender,
        'polite_hits': polite,
        'polite_per_1k': round(polite / n * 1000, 1),
        'emphatic_tsu': text.count('ッ'),
        'exclaim': text.count('！') + text.count('!'),
        'ellipsis': text.count('〜') + text.count('…'),
    }

def jp_register(f):
    """Evidence-derived register labels. Only claims what the counts support."""
    out = []
    fp = sorted(f['first_person'].items(), key=lambda kv: -kv[1]['n'])
    if fp: out.append(f"1st person: {fp[0][0]} ({fp[0][1]['label']}) ×{fp[0][1]['n']}")
    sp = sorted(f['second_person'].items(), key=lambda kv: -kv[1]['n'])
    if sp: out.append(f"2nd person: {sp[0][0]} ({sp[0][1]['label']}) ×{sp[0][1]['n']}")
    if f['polite_per_1k'] >= 6: out.append(f"polite register (です/ます {f['polite_hits']}×)")
    elif f['polite_per_1k'] <= 1.5 and f['chars'] > 800: out.append('plain form (little です/ます)')
    for tok in ('のじゃ', 'じゃ', 'ぞ', 'ぜ', 'かしら', 'のよ'):
        e = f['enders'].get(tok)
        if e and e['n'] >= 5: out.append(f"ender 「{tok}」 ({e['label']}) ×{e['n']}")
    return out

# ---- English register features ----
CONTRACT = re.compile(r"\b\w+'(?:t|ll|re|ve|m|d|s)\b", re.I)
def en_features(lines):
    text = ' '.join(lines)
    words = re.findall(r"[A-Za-z']+", text)
    sents = [s for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]
    n = max(len(lines), 1)
    caps = [w for w in words if len(w) > 2 and w.isupper()]
    return {
        'lines': len(lines), 'words': len(words),
        'avg_words_per_line': round(len(words) / n, 1),
        'avg_sentence_words': round(len(words) / max(len(sents), 1), 1),
        'avg_word_len': round(sum(len(w) for w in words) / max(len(words), 1), 2),
        'contractions': len(CONTRACT.findall(text)),
        'contractions_per_100w': round(len(CONTRACT.findall(text)) / max(len(words), 1) * 100, 1),
        'exclaim_per_line': round(text.count('!') / n, 2),
        'question_per_line': round(text.count('?') / n, 2),
        'ellipsis_per_line': round(text.count('...') / n, 2),
        'allcaps': len(caps),
    }

def en_register(f):
    out = [f"{f['avg_words_per_line']} words/line, {f['avg_sentence_words']} words/sentence"]
    if f['contractions_per_100w'] >= 8: out.append(f"heavily contracted ({f['contractions_per_100w']}/100w) — casual")
    elif f['contractions_per_100w'] <= 2.5: out.append(f"few contractions ({f['contractions_per_100w']}/100w) — formal/stiff")
    if f['exclaim_per_line'] >= .5: out.append(f"exclamatory ({f['exclaim_per_line']}/line)")
    if f['question_per_line'] >= .4: out.append(f"questioning ({f['question_per_line']}/line)")
    if f['ellipsis_per_line'] >= .4: out.append(f"heavy ellipses ({f['ellipsis_per_line']}/line)")
    if f['avg_sentence_words'] <= 6: out.append('clipped sentences')
    elif f['avg_sentence_words'] >= 14: out.append('long, flowing sentences')
    return out

def _mean_sd(xs):
    n = len(xs) or 1
    m = sum(xs) / n
    v = sum((x - m) ** 2 for x in xs) / n
    return m, (v ** 0.5) or 1e-9

def comparable(jf, ef, paired_rows):
    """One predicate for "can these two sides be compared at all", used both to gate drift and
    to set the profile flag — they disagreed before, so a profile could be marked comparable and
    still carry a NOT-COMPARABLE notice."""
    return paired_rows >= 12 and jf['chars'] >= 400 and ef['words'] >= 120

def drift(jf, ef, base, paired_rows):
    """EN/JP mismatches worth a human look. NOT verdicts — leads.

    The absolute-threshold version of this was replaced. Measured across the whole cast, the
    English is nearly UNIFORM (contractions 4.7-5.9 per 100w and ~10-11 words/line for characters
    as different as Ashley 俺, Kanon あたし and Tim ボク+です/ます), while the Japanese separates them
    sharply. That flatness IS the localization's documented failure mode, and an absolute
    threshold can't see it. So drift is measured RELATIVE to the corpus: a character whose JP is
    distinctive but whose EN sits on the corpus mean has had their voice flattened."""
    d = []
    if not comparable(jf, ef, paired_rows):
        # Silence here would read as "no drift found", which is not what we know. Say plainly
        # that the comparison could not be made — for a character like Marivel that is itself
        # the interesting fact: her EN and the literals of her JP diverge on almost every row.
        return [f'NOT COMPARABLE — {paired_rows} same-row pairs / {ef["words"]} EN words. '
                f'Each side is still measured on what it has (see the columns), but no like-for-'
                f'like drift claim can be made. Low pairing means the English and the Japanese '
                f'diverge here, which is worth reading the evidence for.']

    # Selection-bias note, stated once here because it shapes how to read every flag below:
    # the paired rows are those where the English and the literal still share content words, i.e.
    # where the localization stayed close. That biases this measure toward finding LESS drift, so
    # a flag is a conservative floor, never an overstatement. Register (pronouns, politeness,
    # contraction rate) is largely independent of whether content words survived — a line can keep
    # its nouns and still drop わらわ entirely — so the bias is far weaker on register than on
    # meaning, which is why the comparison is still worth making.

    # how far this character's EN sits from the cast average, in standard deviations
    z = {}
    for k in ('contractions_per_100w', 'exclaim_per_line', 'avg_sentence_words', 'ellipsis_per_line'):
        m, sd = base[k]
        z[k] = (ef[k] - m) / sd
    en_distinct = max(abs(v) for v in z.values())

    # what makes this character's JP distinctive
    marks = []
    for tok in ('わらわ', 'わし', 'あたし', '俺', 'オレ', 'ボク', '僕', 'わたくし'):
        e = jf['first_person'].get(tok)
        if e and e['n'] >= 8: marks.append(f"{tok}×{e['n']}")
    for tok in ('のじゃ', 'じゃ', 'ぞ', 'ぜ', 'かしら', 'のよ', 'わい'):
        e = jf['enders'].get(tok)
        if e and e['n'] >= 6: marks.append(f"「{tok}」×{e['n']}")
    for tok in ('貴様', 'お前', 'おぬし'):
        e = jf['second_person'].get(tok)
        if e and e['n'] >= 8: marks.append(f"{tok}×{e['n']}")
    if jf['polite_per_1k'] >= 6 and jf['polite_hits'] >= 8:
        marks.append(f"です/ます×{jf['polite_hits']}")

    if marks and en_distinct < 0.75:
        d.append("JP is strongly marked (" + ", ".join(marks) +
                 f") but the EN sits within {en_distinct:.2f}σ of the cast average on every "
                 f"measure — this character reads generic in English")
    # specific, still useful
    archaic = sum(jf['enders'].get(t, {}).get('n', 0) for t in ('のじゃ', 'じゃ', 'わい')) \
              + jf['first_person'].get('わらわ', {}).get('n', 0) + jf['first_person'].get('わし', {}).get('n', 0)
    if archaic >= 8 and z['contractions_per_100w'] > 0:
        d.append(f"JP is archaic ({archaic} markers) yet the EN is MORE contracted than the cast "
                 f"average (z={z['contractions_per_100w']:+.2f}) — period register inverted")
    if jf['polite_per_1k'] >= 6 and jf['polite_hits'] >= 8 and z['contractions_per_100w'] > 0.5:
        d.append(f"JP is polite (です/ます {jf['polite_hits']}×) but the EN is unusually casual "
                 f"(z={z['contractions_per_100w']:+.2f})")
    return d

# Characters the annotators labelled under more than one name. Every entry is sourced from the
# project docs, not guessed — profiling one person twice splits their corpus and can produce two
# DIFFERENT measured voices for the same character (Irving was split three ways: 103 + 31 + 13
# rows, with different first-person readings in each).
ALIASES = {
    # WA2_NAME_DICTIONARY.md: "**Liz** (トカ/Toka — Lizardian talker; name-pun Liz+Ard=Lizard)"
    'toka': 'Liz',
    'lizardian': 'Liz',
    # WA2_NAME_DICTIONARY.md: "**Irving Vold Valeria** (ARMS commander …)"
    'vold valeria': 'Irving',
    'sir valeria / irving': 'Irving',
    'sir valeria': 'Irving',
    # WA2_CHARACTER_ROSTER.md: JP マリアベル (Mariabel) localized "Marivel"
    'mariabel': 'Marivel',
}

def canon(label):
    s = label.strip()
    s = re.sub(r'\s*\(.*?\)\s*$', '', s).strip()
    key = s.lower()
    if key in ALIASES: return ALIASES[key]
    # "Name / role" forms (Erwin / chief pilot) — keep the personal name
    if ' / ' in s:
        head = s.split(' / ')[0].strip()
        if head.lower() in ALIASES: return ALIASES[head.lower()]
        if re.match(r'^[A-Z][a-z]+$', head): return head
    return s

def build(min_lines=12):
    rows = json.load(open(DB))['rows']
    byspk = collections.defaultdict(list)
    for r in rows:
        sp = canon(r.get('speaker') or '')
        if not sp or JUNK.search(sp): continue
        byspk[sp].append(r)

    # cast-wide EN baseline, so drift can be measured relative to how the localization
    # actually writes rather than against numbers I picked.
    prelim = []
    for sp, rs in byspk.items():
        ok = [r for r in rs if en_lit_agree(r) is True]
        ls = [S(r, 'en').strip() for r in ok if S(r, 'en').strip()]
        if len(ls) >= min_lines: prelim.append(en_features(ls))
    base = {k: _mean_sd([p[k] for p in prelim])
            for k in ('contractions_per_100w', 'exclaim_per_line', 'avg_sentence_words', 'ellipsis_per_line')}

    profiles = []
    for sp, rs in byspk.items():
        en_lines = [S(r, 'en').strip() for r in rs if S(r, 'en').strip()]
        jp_rows  = [r for r in rs if S(r, 'jp').strip()]
        lit_rows = [r for r in jp_rows if S(r, 'lit').strip()]
        if len(en_lines) < min_lines and len(jp_rows) < min_lines: continue
        checked = [(r, en_lit_agree(r)) for r in jp_rows]
        ok_rows  = [r for r, v in checked if v is True]
        bad_rows = [r for r, v in checked if v is False]
        judged   = len(ok_rows) + len(bad_rows)
        # Measure the JP register on the rows that PASS the alignment check when we have enough
        # of them; otherwise fall back to everything and say so via jp_register_from.
        jp_src = ok_rows if len(ok_rows) >= 12 else jp_rows
        jp_text = ' '.join(S(r, 'jp') for r in jp_src)
        jf, ef = jp_features(jp_text), en_features(en_lines)
        # PAIRED corpora: the same rows on both sides. Comparing a filtered JP corpus against an
        # unfiltered EN one is not a like-for-like comparison of a character — it was measuring
        # Ashley's Japanese on 75 rows against his English on 195. Drift is computed from these.
        pj = jp_features(' '.join(S(r, 'jp') for r in ok_rows))
        pe = en_features([S(r, 'en').strip() for r in ok_rows if S(r, 'en').strip()])
        # prefer evidence from rows that pass the alignment check
        ev = sorted(rs, key=lambda r: (en_lit_agree(r) is not True, -len(S(r, 'en'))))[:6]
        profiles.append({
            'name': sp,
            'kind': 'role' if ROLE.match(sp) else 'character',
            'lines_en': len(en_lines), 'lines_jp': len(jp_rows),
            'lit_backed': len(lit_rows),
            'rows_checked': judged,
            'rows_agreeing': len(ok_rows),
            'jp_register_from': 'rows where EN and the literal agree' if jp_src is ok_rows else 'all rows (too few agreed)',
            'en_lit_agreement': round(len(ok_rows) / judged, 2) if judged else 0.0,
            'agreement_reliable': judged >= 8,
            'low_sample': len(en_lines) < 25,
            'en': ef, 'jp': jf,
            'paired_rows': len(ok_rows), 'en_paired': pe, 'jp_paired': pj,
            'en_register': en_register(ef),
            'jp_register': jp_register(jf),
            'drift': drift(pj, pe, base, len(ok_rows)),
            'comparable': comparable(pj, pe, len(ok_rows)),
            'evidence': [{'us': r.get('us'), 'en': S(r, 'en')[:220],
                          'jp': S(r, 'jp')[:160], 'lit': S(r, 'lit')[:220],
                          'agrees': en_lit_agree(r)} for r in ev],
        })
    profiles.sort(key=lambda p: (p['kind'] != 'character', -p['lines_en']))
    return profiles

def main():
    a = sys.argv
    mn = int(a[a.index('--min') + 1]) if '--min' in a else 12
    profs = build(mn)
    if '--show' in a:
        want = a[a.index('--show') + 1].lower()
        for p in profs:
            if p['name'].lower() != want: continue
            print(f"== {p['name']} ({p['kind']}) — EN {p['lines_en']} lines, JP {p['lines_jp']} "
                  f"({p['lit_backed']} human-read, EN/JP agree {p['en_lit_agreement']}) ==")
            print(" JP register:"); [print("   -", x) for x in p['jp_register']]
            print(" EN register:"); [print("   -", x) for x in p['en_register']]
            if p['drift']:
                print(" DRIFT:"); [print("   ! " + x) for x in p['drift']]
            print(" evidence:")
            for e in p['evidence'][:3]:
                print(f"   US#{e['us']}  EN {e['en'][:70]}")
                if e['jp']: print(f"              JP {e['jp'][:50]}")
        return
    if '--verify' in a:
        # Ground-truth regression guard. WA2_NAME_DICTIONARY.md records Marivel as わらわ/〜じゃ
        # speech; if the register detector ever stops finding that, it is broken.
        ok = True
        mv = next((p for p in profs if p['name'] == 'Marivel'), None)
        def chk(cond, msg):
            nonlocal ok
            print(('  ok: ' if cond else '  FAIL: ') + msg)
            ok = ok and cond
        chk(mv is not None, 'Marivel profiled')
        if mv:
            chk(mv['jp']['first_person'].get('わらわ', {}).get('n', 0) >= 10,
                'Marivel uses わらわ (documented in WA2_NAME_DICTIONARY.md)')
            chk(mv['jp']['enders'].get('じゃ', {}).get('n', 0) >= 8,
                'Marivel uses the 〜じゃ copula (same doc)')
        lil = next((p for p in profs if p['name'] == 'Lilka'), None)
        if lil:
            chk(lil['jp']['enders'].get('じゃ', {}).get('n', 0) <= 4,
                'Lilka is NOT read as archaic (bare じゃ must not match じゃない/じゃあ)')
        tim = next((p for p in profs if p['name'] == 'Tim'), None)
        if tim:
            # thresholds are set against the AGREEMENT-FILTERED corpus (smaller than the raw
            # rows), so they track what the tool actually measures rather than the pre-filter counts
            chk(tim['jp']['polite_per_1k'] >= 6, 'Tim reads as polite (です/ます density)')
            chk('ボク' in tim['jp']['first_person'], 'Tim uses ボク')
        ash = next((p for p in profs if p['name'] == 'Ashley'), None)
        if ash:
            fp = ash['jp']['first_person']
            top = max(fp.items(), key=lambda kv: kv[1]['n'])[0] if fp else None
            chk(top == '俺' and fp['俺']['n'] >= 25, 'Ashley\'s dominant first person is 俺')
        kan = next((p for p in profs if p['name'] == 'Kanon'), None)
        if kan:
            fp = kan['jp']['first_person']
            top = max(fp.items(), key=lambda kv: kv[1]['n'])[0] if fp else None
            chk(top == 'あたし', "Kanon's dominant first person is あたし (casual feminine)")
        chk(all(0 <= p['en_lit_agreement'] <= 1 for p in profs), 'agreement scores in range')
        chk(all(p['rows_agreeing'] <= p['rows_checked'] for p in profs), 'agreement counts are consistent')
        print(('\nVERIFY OK' if ok else '\nVERIFY FAILED'))
        sys.exit(0 if ok else 1)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump({'version': 1, 'source': 'data/script/wa2_db.json',

               'caveat': 'Speaker labels and EN text are hand-annotated and reliable. The JP on '
                         'each row was attached by the aligner, which drifts, so some rows carry '
                         'the wrong Japanese. en_lit_agreement is a per-row check: the share of '
                         'rows whose human-written literal shares content words with the shipped '
                         'English. A LOW score means the EN and the Japanese diverge on that row '
                         '-- either the aligner mispaired it OR the localization rewrote the line '
                         'past recognition, and this check cannot tell those apart. Either way it '
                         'means read the evidence. Where enough rows agree, the JP register is '
                         'measured from those rows only (see jp_register_from).',
               'profiles': profs}, open(OUT, 'w'), ensure_ascii=False)
    chars = [p for p in profs if p['kind'] == 'character']
    print(f"wrote {OUT}: {len(profs)} profiles ({len(chars)} characters, {len(profs)-len(chars)} roles)")
    cmpable = [p for p in profs if p['comparable']]
    print(f"  comparable (>=12 same-row pairs): {len(cmpable)} of {len(profs)}")
    print(f"  measured voice drift: {sum(1 for p in cmpable if p['drift'])}")
    print(f"  not comparable (EN and JP diverge / too few rows): {len(profs) - len(cmpable)}")

if __name__ == '__main__':
    main()
