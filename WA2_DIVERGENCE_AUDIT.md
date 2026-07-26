# WA2 — EN/JP Localization Divergence Audit

Systematic scan of all 7,766 aligned message pairs using the v6 linebreak-sequence
alignment (`tools_wa2/align_v6.py`, HIGH-confidence tier ~93% accurate). Method: compare
JP content-length vs EN word-count per pair; flag extreme ratios; manually verify each
HIGH-confidence hit against readable JP + surrounding EN.

⚠️ **Confidence note:** findings below are from HIGH-confidence aligned pairs only. MED/LOW
pairs produce false positives (alignment micro-drift maps a line to a nearby demo/menu
string), so they are excluded. Numbers are conservative.

---

## CONFIRMED COMPRESSIONS (JP says more; EN drops content) — 14 HIGH-conf lines

These are places where the Japanese carries specific content the English flattened or cut.

### High-value (story/lore content lost)
- **JP#3107** — JP: *"I still can't believe it... Meria, Sylvaland, and Guildgrade too..."* + a line about the enemy destroying the mutual **Live Reflector**. EN: generic *"What!? How can that be? It's not my fault. What should we do?"* → **three named nations + a plot mechanism dropped** for filler panic.
- **JP#4165** — JP explains what a 「周見」(**Contactee**) is: one who receives a Guardian's [vision] in [dream] form, and describes the vision "the sky [will fall]..." EN: *"I can't do that... Not me..."* → **a lore definition of a key concept compressed to vague dialogue.**
- **JP#7205 / #7228** — JP explains the **Extend rune's** intended dual use (offensive magic to raise power/steal, defensive magic to preserve). EN keeps "a result of all my research" but **drops the mechanical explanation.**
- **JP#6556** — JP: the shrine's katakana-styled greeting *"WELCOME, YOU WHO SUMMON THE ANCIENT [MAGESS]... this is where your sleeping [memory/spirit] is called..."* — EN preserves the opening but **truncates the mystical description.**

### Character-voice / thematic
- **JP#6418** — Brad: *"But more importantly — that not a single one of us is missing, that we all come back here."* (ties to the game's 仲間/no-sacrifice theme). EN keeps the gist but clips the emphatic construction.
- **JP#5394** — a prisoner's cynical speech about being *"useless bums who'll never amount to heroes even outside"* — EN softens/shortens.
- **JP#7012 / #7016** — **Liz & Ard's** villain-intro bombast (ブルコギドン, "savage and miraculous symbol of destruction") — confirms the earlier hand-finding that their comic density is systematically compressed. Now auto-detected.
- **JP#5982** — a menacing taunt about being "blasted by Gias" — EN clips the follow-up.

---

## EXPANSIONS / ADDED CONTENT (EN says more than JP)

The reverse scan flags ~200 pairs where EN is much longer, BUT most are **single-box-vs-
multibox artifacts** (a JP empty/short box aligns to the start of a longer EN box chain),
not true additions. Genuine additions must be checked case-by-case. Known real ones from
prior manual work (not caught by length alone because they substitute rather than add):
- **Irving funding-file scene** — EN prints *"Vold Valeria... Why is his name here?"*; JP withholds the name (「この名前」). *(documented in WA2_CHARACTER_ROSTER.md)*
- **Caina "That Man" council line** — EN adds Caina's hidden-backer callback; JP has no equivalent. *(documented)*
- These are **substitutions/insertions of equal length**, so a length-ratio scan misses them — they require the semantic pass.

---

## METHODOLOGICAL FINDINGS (what the audit taught us)

1. **The localization's dominant failure mode is COMPRESSION, not mistranslation.** Where it
   diverges, it usually *drops specificity* (named places, lore terms, mechanical detail,
   comic rhythm) rather than getting things wrong. This matches the community reputation
   ("literal but not streamlined / drops connective tissue").
2. **Proper nouns and lore terms are the most frequent casualties** — JP#3107 (3 nations),
   #4165 (Contactee), #7205 (Extend) all lose *named/technical* content.
3. **Comic characters (Liz & Ard) are compressed hardest** — their density is the point, and
   it's flattened. Reinforces the retranslation priority already in WA2_RETRANS_LizArd.md.
4. **True ADDITIONS are rare and are substitutions** (Irving/Caina) — the EN didn't pad
   length, it changed *what* is revealed. These need semantic review, not length metrics.

## RETRANSLATION PRIORITY (from this audit)
1. Restore dropped proper nouns / lore terms (#3107, #4165, #7205, #6556) — cheap, high-fidelity wins.
2. Liz & Ard comic density (#7012, #7016 + the earlier scenes).
3. Semantic-substitution fixes (Irving/Caina reveals) — align EN to JP's intended pacing.

## SEMANTIC-SUBSTITUTION PASS (name-mismatch scan) — results

Scanned HIGH-conf pairs for (a) EN naming a proper noun the aligned JP lacks, and
(b) JP using a withholding phrase (この名前/あの方/その人) while EN reveals a name.

**Findings:**
- **No NEW systematic withhold-then-reveal divergences** beyond the two already documented
  by hand (Irving funding-file, Caina "That Man"). The one candidate (JP#6263) was a false
  positive — the JP names Vinsfeld in the same line. So the Irving-style spoiler is a **rare,
  deliberate device, not a pervasive pattern** — good to know for scope.
- **Bonus discovery:** the scan revealed that 『<8ace>の<8ab1><8ab2>』 is the **JP written
  form of "Blaze of Disaster" / Lord Blazer** (the game's ultimate threat). It aligns 1:1 to
  EN "Blaze of Disaster." The three codes are dual-sense (8ace also 報酬, 8ab1 also 惑星,
  8ab2 also 大気圏), so the name can't be cleanly glyph-solved without breaking those words —
  but we now know that quoted term = Lord Blazer wherever it appears (~10+ lines, mostly the
  Crimson Nobles / Noble Red exposition around JP#866-1011).
- Method limit: a name-mismatch scan mostly surfaces **translation-equivalences** (JP writes
  a name in kanji/katakana, EN romanizes it) rather than true additions. True substitutions
  are equal-length and semantically divergent — they require line-by-line human review, which
  the audit can *prioritize* (flag HIGH-conf pairs where EN and JP proper-noun sets differ)
  but not fully automate.

## TOOLING
- `tools_wa2/align_v6.py` — the alignment (linebreak-sequence, HIGH ~93%).
- Re-run this audit: scan HIGH pairs, flag EN-words/JP-chars ratio <0.4 (compression) or
  the semantic pass for substitutions. Exclude demo/menu lines and MED/LOW tiers.
