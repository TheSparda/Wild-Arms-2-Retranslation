# WA2 Insertion Workspace — README

**This is the primary workspace.** Everything here is oriented to the end goal: **inserting
retranslated English into the EN (USA) ISO by refilling existing text boxes.** Read
`../WA2_INSERTION_MODEL.md` first — it defines the hard constraints.

## Files
- `blk000.txt` … `blk117.txt` — 118 files, one per US event block, in game order. Each contains
  every translatable box in that block (control-only boxes are skipped).
- `SAMPLE_worked.txt` — a completed example (Marina, US#511-515) showing the fill process.

## Row format (one per US box = one insertable slot)
```
[US#<n>] budget=<X>ch/<Y>ln
  NOW: <current EN in the box>
  JP : JP#<m>[<aln>]: <the JP source mapped to this box>
  FIT: <<TODO — <=X chars, Y line(s), <=35/line>>
```

## The rule (why this frame)
We can only **refill boxes the US game already has** — we cannot create new boxes. So:
1. Each retranslation must **fit the box's budget** (`<=X` visible chars, `<=Y` lines, `<=35`/line)
   for a **same-size, pointer-safe** insert.
2. **Keep control codes / name-codes** ({0},{1} = player-set names) verbatim.
3. If the JP genuinely needs more room than the box holds (see `../WA2_DIVERGENCE_AUDIT.md`
   compression cases), either tighten the English or flag the box for the **repointer pass**
   (longer text needs pointer recalculation — gadesx-style — or it freezes the game).

## Translate from the JP, not the current EN
The `JP` line is the source of truth (via v6 alignment). The `NOW` line is the old localization
— use it as a cross-check only when `aln` is HIGH/MED; ignore it when LOW. Restore JP nuance the
old EN dropped, but always within the box budget.

## Tools
- `tools_wa2/build_insert.py` — (re)generate this workspace. `python3 tools_wa2/build_insert.py`
  for all blocks, or `... <us_lo> <us_hi> out.txt` for a range.
- `tools_wa2/check_fit.py <file>` — validate filled FIT fields against box budgets (flags
  over-length, too many lines, >35-char lines). Run before insertion. (Feed it clean FIT text —
  no inline annotations.)

## Insertion pipeline (when translation is done)
1. Translate FIT fields (this workspace), keeping within budget.
2. `check_fit.py` — confirm all slots fit.
3. Write FIT text back into the US STGEVT box bytes (same-size overwrite; keep control codes).
4. Recompute Mode-2 EDC/ECC per edited sector (see `ps1-disc-editing` method).
5. Reinsert STGEVT into the ISO (`cebix/psximager` psxinject, or CDmage).
6. Test in emulator; longer-than-budget boxes need the CUE-style repointer first.

## References
- `../WA2_INSERTION_MODEL.md` — constraints (READ FIRST).
- `../WA2_NAME_DICTIONARY.md` — canonical spellings.
- `../WA2_DIVERGENCE_AUDIT.md` — boxes where EN cut JP content (priority + likely over-budget).
- `../WA2_SCENE_STRUCTURE.md` — which block = which scene (translate in story order).
- `../translate/` — the JP-centric 4-column doc (companion; this insert/ workspace is EN-centric).

## Status
Workspace generated for all 118 blocks (~7,700 fillable slots). FIT fields are hand-translated
per scene, constrained to budget. Start with HIGH-confidence story blocks.
