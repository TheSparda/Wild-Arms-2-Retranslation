# Story-block translation brief (shared by all story-fleet agents)

You are translating ONE chunk of Wild Arms 2's STORY dialogue (PS1 fan-retranslation).
Working dir: /Users/kgosschalk/Documents/SUI/PS1/games/Wild Arms 2/

This is character dialogue (party members, villains, key NPCs) — NOT the lore encyclopedia.
Character VOICE matters here. A flat literal that loses a character's register is a miss.

## STEP 1 — get your input
Run: `python3 tools_wa2/translate_agent_brief.py <BLOCK> <US_START> <US_END>`
It prints every content box: US#, decoded JP, aligned EN.

## STEP 2 — read these (read-only)
- `WA2_CHARACTER_ROSTER.md` — the VOICE GUIDE. Each character's tone/register. USE IT.
- `WA2_RE_STYLE_GUIDE.md` — prime directive + formatting + VOICE-LOCK rules.
- `WA2_NAME_DICTIONARY.md` — canonical names/terms. Use EXACTLY.
- One nearby DONE story file for format/tone, e.g. `insert/m1_meria_npc_FINAL.txt` or `insert/m_backstories_FINAL.txt`.

## CRITICAL — meaning source
- **JP is the ONLY reliable meaning source.** The aligned EN suffers heavy Rosetta drift in these
  blocks (it misaligns JP↔EN by several boxes — you will see JP about "Drifters/渡り鳥" paired with
  EN about a "steel arm", etc.). Use EN ONLY where it demonstrably matches the JP line in front of you.
- Story blocks are NOT twins — there is no twin block to cross-check. Solve from JP + context.
- If a box still has unsolved `<b:xxxx>` / `<xxxx>` kanji codes, translate the readable JP around
  them and mark the unreadable span inline as `[?]`. NEVER invent plot content from the drifted EN.

## VOICE (from WA2_CHARACTER_ROSTER.md — apply per speaker)
- **Ashley** (protagonist): earnest, dutiful, sincere; quietly heroic, NOT quippy. Real fear/doubt about Knight Blazer.
- **Lilka** (novice mage): bright, enthusiastic, a little insecure; warm, youthful; keep her 3rd-person "big sister" quirks. Not ditzy.
- **Brad** (ex-soldier): terse, gruff, weary, principled. Few words with weight.
- **Kanon** (cyborg hunter): cold, clipped, guarded; buried humanity. Rough first-person register.
- **Tim** (boy medium): gentle, precocious, kind; mature beyond his years; not baby-talk.
- **Marivel** (ancient vampire noble): archaic, theatrical, aristocratic; elevated/old-fashioned English, NO modern slang.
- **Vinsfeld** (villain, Brad's nemesis): grandiose.
- **Toka & Gě** (comic lizard duo): farcical, over-the-top, parody energy.
- Kids/townsfolk: plain, casual.
- **Drifters** = 渡り鳥 "migratory birds" — the wandering mercenaries. Use "Drifter(s)", AVOID "expedition/team/unit".
- Speaker per box comes from the brief's `(speaker)` tag / EN dump — do NOT infer a speaker to add drama. If unknown, mark it.

## FORMAT (match the sample DONE file exactly) — per box:
```
[US#XXXX] (speaker/context)
  JP : <decoded JP>
  LIT: <literal English of the JP>
  RE : <=3 lines, each <=35 chars
       <continuation if needed>
```

## RULES
- RE: max 3 lines x max 35 chars/line. NO em dashes or "--" (use commas/periods). No trailing comma
  on a box's FINAL line. Preserve player-name/slot codes `{0}` `{1}` `[05]` `[0a]` verbatim — never spell them out.
- `|word|` is the game's emphasis marker — preserve it where JP/EN emphasizes a term.
- Ellipses `...` are fine and in-voice.
- Prime directive: use the JP literal unless it reads badly in English; then voice it to moderate
  character register (restore rhythm + register; no invented gags, no added tics).
- If a whole box is pure garbage: `RE : [SKIP - unreadable]`. System/menu/demo boxes: one-line SKIPPED note.
- Account for ALL US# in your range (translated or explicitly SKIPPED). No gaps.
- Cap your tool calls to ~10. Do NOT run reflow_re.py or prefer_lit_re.py (coordinator does that).

## READ-ONLY on data
DO NOT edit `font_work/block_tables.json`, `wa2_kanji_map.py`, the DB, or any tool. Your ONLY write
is your one output file: `insert/story_blk<BLOCK>_<START>-<END>_FINAL.txt`.

## REPORT when done
box count, clean vs residual, boxes skipped, any codes you could not recover, and any speaker/voice
calls you were unsure about.
