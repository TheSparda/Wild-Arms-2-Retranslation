# WA2 Translation Working Docs (4-column)

120 block files (`blk000.txt` … `blk119.txt`) = the entire STGEVT script, one file per
event block, in game order. Total ~8,600 messages.

## Format (per message)
```
[JP#<n>] gaps=<k>  aln=<HIGH|MED|LOW>->US#<m>
  1|JP : <Japanese raw decode>          <- source of truth
  2|LIT: <<TODO>>                       <- hand: literal JP->EN gloss
  3|EN : <current localization>         <- auto, via v6 alignment
  4|RE : <<TODO>>                       <- hand: retranslation from JP
```

## How to use the `aln` flag (critical)
- **aln=HIGH** (57% of lines, ~93% accurate): col-3 EN is the correct match — trust it as a
  cross-check while translating col-4 from the JP.
- **aln=MED** (38%, ~81%): col-3 usually right; verify against JP content before relying on it.
- **aln=LOW** (6%): col-3 may be mismatched — **ignore it, translate col-4 purely from col-1 JP.**

## How to translate (cols 2 & 4)
These are hand work (a script can't author them). Per line:
1. Read col-1 JP (use the name dictionary for proper nouns; `<xxxx>` = unsolved kanji — infer
   from context or leave `[?]`).
2. col-2 = literal gloss.
3. col-4 = natural English **based on the JP**, cross-checked against col-3 when aln≥MED, made
   to read well and match the JP meaning/tone (per WA2_JP_SCRIPT_SUMMARY + retrans notes).

## References
- `WA2_NAME_DICTIONARY.md` — canonical proper-noun spellings (use these).
- `WA2_JP_SCRIPT_SUMMARY.md` — themes/voice to preserve.
- `WA2_DIVERGENCE_AUDIT.md` — where the EN cut content (priority fixes).
- `WA2_LORD_BLAZER_SCENES.md`, `WA2_SCENE_INDEX.md` — thread maps for context.
- `WA2_RETRANS_LizArd.md` — worked example of the retranslation philosophy.

## Regenerate
`python3 tools_wa2/build_4col.py`  (all blocks)  or  `... <lo> <hi> out.txt` (one range).
Alignment source: `tools_wa2/align_v6.py` -> `jp_us_alignment.json`.

## Status
Scaffold complete (cols 1+3+flags auto-filled for all 120 blocks). Cols 2+4 are translated
per-scene as the project proceeds; start with HIGH-confidence story blocks and the divergence-
audit priority scenes.
