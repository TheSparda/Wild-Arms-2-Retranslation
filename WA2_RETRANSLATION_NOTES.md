# Wild Arms 2 — Retranslation Guidance Notes

**Goal:** move the English script closer to the Japanese meaning, and clarify the parts the
original (rushed) localization made confusing — without over-localizing or going stiffly literal.

## Key sources
- **swimmylionni "Through a Mirror Pale Dimly"** — line-by-line JP/EN commentary series:
  - Part 1 (Ashley's Prologue): https://swimmylionni.substack.com/p/wild-arms-2-translation-commentary
  - Part 2 (Lilka's Prologue): https://swimmylionni.substack.com/p/wild-arms-2-translation-commentary-3b7
  - Part 3 (Brad's Prologue): https://swimmylionni.substack.com/p/wild-arms-2-translation-commentary-3f4
- **barleybap retranslation project** (in progress, 2023+): https://barleybaptranslations.wordpress.com/2023/12/30/wild-arms-2-retranslation-project/
  - Proof-of-concept video: https://www.youtube.com/watch?v=LPslTHyObQ8
  - Calls it "one of the weakest localisations of its era… actually incomprehensible in the denser passages."
- Community: r/JRPG threads (152enz7, 14nulph), GameFAQs board 80355718, Quote Compendium FAQ 81396.
- Reference wikis (names/terms): wildarms.fandom.com/wiki/KnightBlazer, /wiki/Odessa.

## Documented problems in the original translation (concrete)
- **渡り鳥 "migratory birds" → "Drifters"** (good). AVOID "expedition/team" — falsely implies an organized military unit.
- **第三班 = "3rd Squad/Team"** (parallel squads exist), NOT "our 3rd mission."
- **漢 (macho "REAL MAN") vs 男** nuance lost — flattened commander Gangal's characterization.
- **Anime cues deleted** — sweat-drops etc. dropped; decide a policy to keep or convey them.
- **Pronoun/person errors** — musketeer's "I screwed up" rendered as "you"; Lilka's internal monologue wrongly uses 2nd-person "your magic" (should be self-reference).
- **Omitted flashback-establishing line** in Lilka's prologue → the dungeon reads ambiguously (memory vs dimension). Restoring omitted context lines is high-value.
- **"big sister" 3rd-person self-reference** missed (sister refers to herself in 3rd person).
- **Name/title inconsistency** — Village Elder vs Village Mayor (same person); singular monster pluralized.
- **南無三 (namusan, Buddhist "God help me")** botched into gibberish "Nammi!" — preserve religious register.
- **"Escapee" should be "Fugitive"**; village **"Sebok" → "T'Bok"** (name drift); 追跡部隊 (pursuit team) → slangy "Posse".
- Brad's prologue is the *best*-translated of the three; Ashley's and Lilka's are worse.

## Editorial principles (lock before starting)
1. **Clarity over literalism, but preserve intent.** Functional accuracy > word-for-word; but don't invent meaning.
2. **Name/terminology glossary first.** Lock character names, place names (T'Bok vs Sebok), titles (Elder/Mayor),
   system terms (ARM vs gun, Force/"Fever!", Knight Blazer, Drifters) BEFORE editing — inconsistency was a top failure.
3. **Don't imply organizations** through word choice (Squad/Posse/expedition) unless the JP does.
4. **Preserve cultural/religious/folklore register** (namusan, tanuki-boat) with a consistent policy, not deletion.
5. **Verify grammatical number & speaker every line** — singular/plural and 1st/3rd-person errors are rampant.
6. **Restore dropped context lines** — some confusion is from omitted setup, not mistranslation.
7. **Be charitable to the original**; puns/pop-culture refs are easy to misread — flag uncertain lines rather than guess.

## Technical constraints (from our RE work — see WA2_NOTES.md)
- Same-length or shorter edits are safe; longer text needs pointer recalculation (the thing that broke 2 prior attempts).
- Text lives in STGEVT.BIN (script), UTIL.OVR (radio/menus), WILDARM2.EXE (items/skills/menus), font in SY0.BIN.
- We have JP disc (Shift-JIS) + US disc (EN) + Spanish patch — building a 3-way aligned map for reference.

## Still to decide/confirm
- Exact JP→EN character name spellings (from JP disc + wiki).
- ARM vs Gun terminology; Force system / "Fever!" naming.
- Honorific policy (keep -san etc. or not).
- Text-box width/line-break limits (test in-engine).
