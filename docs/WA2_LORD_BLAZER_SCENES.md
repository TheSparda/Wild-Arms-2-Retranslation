# WA2 — Lord Blazer / Blaze of Disaster: Complete Scene Map

All references to the game's ultimate threat, found via the v6 alignment
(`tools_wa2/align_v6.py`) + JP decode. Lord Blazer (ロードブレイザー) is the demon Ashley
hosts as **Knight Blazer**; it is the same entity the Crimson Nobles / lore call by a kanji
epithet the localization renders "Blaze of Disaster."

## The naming (key finding)
The JP uses **two distinct terms** that the English collapses into one ("Blaze of Disaster"):
- **ロードブレイザー (Lord Blazer)** — katakana, the entity/demon itself. 40 JP msgs.
- **『徽の魔王』/『滅の○○』 (kanji epithet)** — the *title* "Blaze of Disaster." 7 JP msgs
  (`『<8ace>の<8ab1><8ab2>』` in our decode — the 3 codes are dual-sense so not glyph-solved,
  but this quoted term = the Blaze-of-Disaster title wherever it appears).
- EN "Blaze of Disaster" appears **98×** — far more than either JP form, because it's used
  for both the entity and the title. A retranslation could restore the JP's two-name nuance
  (the being "Lord Blazer" vs. the epithet "Blaze of Disaster").
- #2386 gives the explicit equation: 「『もうひとりの俺』…ロードブレイザー…かつて『徽の
  [魔王]』と呼ばれた魔[倶]だ」 = *"the 'other me'… Lord Blazer… the Demon once called the
  'Blaze of Disaster'."*

## The 14 scenes (JP message ranges, block #, and what happens)

| # | JP msgs | Block | Scene |
|---|---|---|---|
| 1 | 1005-1010 | 6 | **Crimson Nobles lore** — Lord Blazer as a threat unlike the old 『Blaze of Disaster』; the <Sword Magess> vs. Blaze balance. |
| 2 | 1062 | 6 | eavesdropping NPC beat (minor). |
| 3 | 1078 | 6 | origin: *"<Sword Magess> came about when Blaze of Disaster was..."* |
| 4 | 2386-2403 | 9 | **★ The reveal** — Ashley names the "other self" inside him as Lord Blazer, "the Demon called Blaze of Disaster"; vows to use its power for Filgaia; Irving will research it. |
| 5 | 2602 | 10 | *"Lord Blazer is controlled by the desire..."* (its nature). |
| 6 | 2622-2623 | 10 | Grauswein (monster dragon) context near Blazer. |
| 7 | 2650 | 10 | *"Ashley's heart is no longer a cage that can hold him."* |
| 8 | 2673-2677 | 10 | **★ Knight Blazer crisis** — Ashley feels Blazer's thoughts; "he'll tear Filgaia apart"; *"bury me now while I hold him back, or all turns to ash."* |
| 9 | 2699-2706 | 10 | **★ Control debate** — "can we control such power without losing ourselves?"; Ashley: *"I understand, for I contain Lord Blazer... Blazer swells with the heat of each battle."* |
| 10 | 4993-4994 | 21 | Crimson Nobles: *"our brethren have been killed..."* (Blaze aftermath). |
| 11 | 6566 | 52 | shrine: *"I will awaken memories regarding Lord Blazer."* |
| 12 | 6592-6615 | 52 | **★ The full ancient-history lore dump** — 15 msgs on the distant past when Filgaia burned; the longest exposition. |
| 13 | 7062-7072 | 62 | Blazer-power exchange beat. |
| 14 | 7825-7837 | 92 | **★ Anastasia/Sword Magess** — *"that within you is Lord Blazer, the Blazing Demon who once tried to [burn] the world"*; her survival despite Blazer killing all hope. |

★ = story-critical (the reveal, the Knight Blazer crisis, the control debate, the lore dump,
the Magess confrontation).

## Alignment confidence
Most Lord-Blazer lines are HIGH-confidence aligned (verified: the katakana ロードブレイザー
matches "Lord Blazer" in the EN 1:1). A few tail lines (#2676-2677, #2699-2700, #2403) are
MED but content-confirmed. This scene set is reliable for translation work.

## Retranslation notes
- **Preserve the two-name distinction** (Lord Blazer = the demon; Blaze of Disaster = its
  epithet) that the EN flattened.
- Scenes 4/8/9 are Ashley's core Knight Blazer arc — the fear-of-losing-self-to-power theme
  (ties to the game's 英雄/sacrifice thesis in WA2_JP_SCRIPT_SUMMARY.md). Keep the weight.
- Scene 12 (#6592-6615) is the densest lore — heavy unsolved-kanji region; flag for careful
  work or emulator-font pass.

## Source
`tools_wa2/align_v6.py` for alignment; JP decode via `tools_wa2/wa2_jp_decode.py`.
Re-find: search JTX for 'ロードブレイザー' and for '<8ace>...<8ab1>...<8ab2>' quoted-term pattern.
