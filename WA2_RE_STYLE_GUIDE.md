# Wild Arms 2 — RE (Retranslation) Style Guide

**The single source of truth for how we write the `RE:` line in every insert FINAL file.**
Supersedes the scattered rules in WA2_RETRANSLATION_NOTES.md (editorial), insert/README.md
(mechanical), and the memory reference. When those disagree with this file, this file wins.

**Goal:** move the English closer to the Japanese meaning and clarify what the rushed original
localization made confusing — without over-localizing, going stiffly literal, or reinventing a
line that already reads fine.

---

## 0. The prime directive: don't reinvent a good translation

**If the LIT (JP literal) already reads clearly and fits the box, use it verbatim as the RE.**
We are not chasing a "better" phrasing for its own sake. Only rewrite when the literal has a
*major* issue:
- it's confusing / ambiguous in English,
- it breaks the display budget (>3 lines or >35 chars/line),
- it flattens a nuance the scene needs (register, speaker voice, a plot term),
- it contains an em dash or a run-on comma chain (see below),
- it uses the wrong glossary name/term.

If none of those apply, **copy LIT into RE and move on.** A sufficient translation is done.
Effort goes to the lines that actually need it.

Order of preference for the RE:
1. **LIT verbatim** (if clear + fits) — the default.
2. **LIT lightly trimmed** to fit the box or fix one issue.
3. **A fresh line from the JP** — only when LIT genuinely fails.
The current EN localization is a *cross-check only*, never the base (it's the thing we're fixing).

**Precedence: the formatting rules (§1–§2) beat the prime directive.** "Use LIT verbatim" means
*after* it satisfies the hard rules, never in violation of them. If the LIT ends in a comma, has
an em dash, runs on, or overflows the box, apply the fix (e.g. trailing comma → `...`) and use the
fixed text — don't copy the raw LIT and don't count that as "reinventing." A directive and a rule
should never disagree on the same box; if they do, the rule wins.

### Traps when using LIT as RE (learned applying this at scale)
- **A LIT is sometimes a translator NOTE, not the line.** e.g. a babble line whose LIT reads
  `Ge-ge-ge... (Ard can only say his own name)` — the real dialogue is the RE, and copying that
  LIT would destroy it. Skip any LIT that is empty, `pending`, `__LIT_TODO__`, starts with
  `(literal ...`, or contains a parenthetical note like `(... can only ... )`, `(sfx ...)`,
  `(lit. ...)`. `prefer_lit_re.py` already guards these; keep the guard if you extend it.
- **Never let a LIT overwrite intentional non-dialogue.** Fixed NPC names spelled in the LIT are
  fine to keep literal (Ard is an NPC, not a renameable party member).
- **Notes never live inside the RE body.** An inline `# ...` annotation belongs on its own comment
  line *after* the RE block, never appended to an RE line — the reflow will wrap it in and blow
  the box budget (this bit US#304's directions note).

### Automating the prime directive
`python3 tools_wa2/prefer_lit_re.py [--dry] [files...]` rewrites RE := reflowed LIT for every box
where the LIT is real and fits, keeps the existing RE when the LIT is over-budget, and leaves
EN-anchored boxes (no usable LIT) alone. It is idempotent and `--dry` reports before changing.
Name-code safety: it ports a spelled canonical name → `{n}` ONLY where the current RE already
contains that `{n}` (so it never invents a code or hard-codes a renameable character). Always run
`--dry` first, then re-run `reflow_re.py` + the validation checklist (§7) after applying.

**Tools must be idempotent and agree.** A second `--dry` right after an apply should report 0
changes. If it reports a change, two rules are fighting on that box (this happened: `prefer_lit_re`
kept reverting a `...` lead-in back to the comma-ending LIT). That's a tool bug, not a translation
choice — fix the tool so it applies the winning rule (per the precedence above), don't hand-patch
the box each run. `prefer_lit_re` and `reflow_re` should always converge on the same output.

---

## 1. Display / insertion budget (hard limits)

- **≤ 3 lines × ≤ 35 characters per line.** This is the on-screen ceiling.
- **Same byte-length as the original box is the insertion ceiling** — longer text needs pointer
  recalculation (the thing that broke two prior attempts). Shorter or equal is pointer-safe.
- Line breaks in a FINAL file's RE are the on-screen breaks. In the DB they join with ` / `.
- **Run `python3 tools_wa2/reflow_re.py insert/<file>` on every new/edited FINAL file** — it
  re-wraps RE to ≤3×35 and flags any US# that still can't fit. Don't hand-count characters.

## 2. Punctuation

- **No em dashes (`—`) and no `--`.** They read as machine output. Use commas or periods, or
  split into two sentences. Only keep a dash if the JP itself uses one meaningfully.
- **No run-on comma chains.** If a line strings clauses together with commas ("A, then B, then
  C, and D..."), break it into separate sentences or across the (up to 3) lines. Each RE line
  should read as clean, complete-feeling English, not a breathless list. Prefer a period over a
  comma when two independent clauses meet.
- **Never end a box on a trailing comma.** A comma implies the line continues on the same line,
  but the box closes there, so it reads as broken/truncated (even when the JP fragment genuinely
  runs into the next box). Fix it one of two ways:
  - if the box is a genuine lead-in that continues in the NEXT box → end with `...`
    (e.g. JP それでは / LIT "Well then," → RE **"Well then..."**; matches the game's own idiom —
    the EN localization rendered it "And so..."),
  - otherwise → restructure into a complete sentence ending in `.` / `!` / `?`.
  The same goes for other mid-clause enders (a dangling "and", "but", "so") — either `...` or
  restructure. A closed box should read as a finished thought or an obvious continuation.
- Ellipses (`...`) are fine and common in this game's voice.
- `|word|` is the game's emphasis marker (its version of quotes/italics) — preserve it exactly
  where the JP/EN emphasizes a term (`|hero|`, `|Pillar|`, `|Continue|`).

## 3. Control codes & names (verbatim, always)

- Preserve player-name codes exactly: `{0}`=Ashley `{1}`=Brad `{2}`=Lilka `{3}`=Marina
  `{4}`=Kanon `{5}`=Liz `{6}`=Ard. Never expand them to a literal name.
  - Vinsfeld's alias reuses Brad's slot: **`{1} Evans`** in the Slayheim scenes.
- Preserve any other control/formatting codes and the `*` examine-panel marker and `>` system
  markers as they appear in the source.
- Snore SFX `30...30...30` (JP ぐぉ〜) → render as `zzz...zzz...zzz`.

## 4. Meaning & voice (editorial)

- **Clarity over literalism, but preserve intent.** Functional accuracy beats word-for-word;
  never invent meaning that isn't in the JP.
- **Glossary is locked — use canonical names/terms** (see WA2_NAME_DICTIONARY.md): Drifters (not
  "expedition/team"), T'Bok (not Sebok), ARM, Knight/Lord Blazer, Argetlahm, Sword Magess,
  Guardian, Medium, Raypoint, Kuiper Belt, Trapezohedron, etc. Don't imply an organization
  (Squad/Posse/expedition) unless the JP does.
- **Preserve register** — religious/folklore/cultural cues (namusan) and each character's voice
  (Liz = pompous ham; Ard = one word; Vinsfeld = grandiose; the kids = plain). A sufficient LIT
  that already carries the voice needs no polish.
- **Verify grammatical number & speaker every line** — the original is full of 1st/3rd-person and
  singular/plural errors. The sister refers to herself in the 3rd person ("big sister"); keep it.
- **Restore dropped context lines** the old EN omitted when the JP has them.

## 5. Process discipline (the "verify" rules)

1. **Speaker comes from the EN-dump tags, never inferred.** A fabricated "dying ARMS Master" once
   came from inferring drama. If the speaker is unknown, mark it, don't guess.
2. **Positive control before trusting a failed grep** — confirm the harness works on a string
   known to exist before concluding something is absent.
3. **Grep absence ≠ fabrication** — unsolved-kanji placeholders can hide text; check raw bytes.
4. **Flag inferred kanji** — a JP reading that came from EN-Rosetta (not decoded bytes) is a
   hypothesis, mark it as such.
5. **Translate in story order**, one scene/block at a time; don't manufacture a "scene" for a
   hub/filler block that doesn't have one.

## 6. FINAL-file row format

```
[US#<n>] (Speaker)
  JP : <decoded JP, if clean>        # optional; omit when JP is coded/unavailable
  LIT: <literal translation>         # the JP meaning, plain
  EN : <original US localization>    # cross-check only
  RE : <line 1, <=35 chars>
       <line 2>
       <line 3>
```
- The DB (`game_script/wa2_db.json`) is the master; a FINAL file is ingested by `build_db.py`
  (add it to `SCENES` with its area + block). `RE` is what ships; `LIT`/`EN`/`JP` are reference.
- Repeated speeches (some endgame blocks repeat one speech 6× per party permutation) — author the
  canonical cycle ONCE and replicate by relative slot index; the RE is identical across cycles.

## 7. Quick checklist before committing a FINAL file
- [ ] Every RE is either LIT verbatim, LIT trimmed, or a justified fresh line (prime directive).
- [ ] No RE was overwritten by a LIT that was actually a translator note (babble/sfx lines).
- [ ] `reflow_re.py` reports all fit ≤3×35.
- [ ] No em dashes, no `--`, no run-on comma chains.
- [ ] No box ends on a trailing comma (use `...` for a lead-in, else make it a complete sentence).
- [ ] Name/control codes `{n}` preserved verbatim; no spelled-out renameable name where a code belongs.
- [ ] Any `#` annotation is on its own comment line, never inside an RE line.
- [ ] Speaker taken from EN tags, not inferred.
- [ ] Glossary names/terms correct.
- [ ] Anchored in `build_db.py` SCENES; DB + wiki rebuilt.

---

## Reference sources (unchanged)
- **swimmylionni "Through a Mirror Pale Dimly"** — line-by-line JP/EN commentary (prologues).
- **barleybap retranslation project** — community retranslation in progress.
- Local: `WA2_NAME_DICTIONARY.md` (canonical spellings), `WA2_INSERTION_MODEL.md` (byte/pointer
  constraints), `WA2_SCENE_STRUCTURE.md` (block↔scene), the memory reference
  `wa2-translation-format.md` (technical format + solved-kanji tables).
