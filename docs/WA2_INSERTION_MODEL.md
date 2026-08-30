# WA2 — Insertion Model (the constraint that governs all translation work)

**GOAL: put retranslated English text into the EN (USA) ISO, reusing existing text boxes.**
We are NOT authoring new script structure — we fill the boxes the US game already has.
Every translation decision is bounded by this.

## The insertable unit = one 100C box
- The US STGEVT has **8,516 message boxes** (each starts with control code `10 0c`).
- **Exactly 1 box per message** (100C count = 1/msg, verified). So "message" = "box" = "the slot".
- Each box's text is plain ASCII, terminated by `00`, with control codes interspersed.

## Box control codes (raw bytes, from analysis)
| byte | meaning |
|---|---|
| `10 0c` | box start (message marker) |
| `0d` | line break within the box (11,188 uses) |
| `40` (@) | speaker-name / color marker |
| `0c` | (part of 100C / formatting) |
| `05 xx` | character-ID speaker tag (Ashley=0530, Brad=0531, …) |
| `17`,`18` | choice / prompt controls |
| `00` | text terminator |
Keep ALL control codes when editing — only the visible ASCII between them is translatable.

## WHERE THE "LIMIT" ACTUALLY COMES FROM (corrected)
A box is NOT length-prefixed and has NO stored per-box size cap. A message is simply the text
between one `10 0c` marker and the next, terminated by `00`; line breaks are MANUAL `0d` bytes
(the game does not auto-wrap). So the constraints are:

1. **FILE PACKING / POINTERS (the real hard limit).** Messages are packed back-to-back and the
   event bytecode points to each one's offset. Growing a message overruns the next → **every
   downstream pointer must be recomputed.** This is a whole-file constraint, NOT a per-box one.
   - **Same-size overwrite (≤ original byte length): free, no repointing.**
   - **Longer: needs the pointer-recalculating tool** (gadesx/CUE did this; naive offset edits
     froze the game — two prior tools failed). Then a box can be as long as the display allows.
2. **DISPLAY WINDOW (the true visual ceiling).** VERIFIED by counting 0d/0c across all 7744 on-screen
   boxes: the standard box is **3 lines × ~35 chars**. Distribution of lines-per-box:
   1L=1006, 2L=2333, **3L=4399**, 4L=1, 5L=5. So **≈99.9% of boxes are ≤3 lines**; only SIX boxes
   in the whole game exceed 3 (all US#6455+, the endgame Lord Blazer lore dump, at 4-5 lines).
   TREAT 3 LINES AS THE CEILING for normal dialogue; 4-5 is a rare exception, not a target.
   Beyond a box you page-break with `0c` (next sub-box).
3. **Line width ~35 chars** is a CONVENTION the localizer followed (manual `0d` placement). Verified
   width tail: 32ch=949, 33ch=986, 34ch=619, 35ch=522, 36ch=283, 37ch=5, one 42, one 44. So ~35-36
   is the practical max line; 37+ is essentially never used.

## OBSERVED SIZES (reference, not caps)
- Median box = 63 visible chars, 2-3 lines. Distribution: 0ch=770 (control-only, skip), 1-20=360,
  21-40=1059, 41-60=1807, 61-100=4341, 100+=179. Standard max = 3 lines / ~105 chars; the rare
  5-line outliers (US#6455+ endgame lore) reach ~166 chars but are NOT the norm.
- ~770 boxes are control-only — not translatable slots.

## TWO INSERTION MODES (pick per box)
1. **Same-size (safe, no tools):** retranslation ≤ original box byte length → overwrite in place.
   Fastest path; use where the JP fits the old EN box.
2. **Grow-to-window (needs repointer):** retranslation up to ~5 lines / 166 chars → requires the
   pointer-recalc tool, but is NOT limited to the original box's length. Use where restoring JP
   content (see WA2_DIVERGENCE_AUDIT compressions) needs more room than the old EN allowed.

⚠️ EARLIER-DOC CORRECTION: the per-box "budget" is only the ceiling for the *same-size* path. It
is NOT an inherent box limit. With the repointer, any box may grow up to the display-window max.

## CONSEQUENCE FOR TRANSLATION (the rule)
**Write each retranslated box to fit within the ORIGINAL EN box's char budget**, using the same
number of lines (respect `0d` breaks) and ≤~35 char lines. Where the JP meaning needs more room
than the EN box allows, either (a) tighten the English, or (b) flag the box for the repointer
pass. Do NOT split one JP idea across boxes that don't exist — we can only fill existing slots.

## PRACTICAL WORKFLOW
- The translation workspace is **EN-slot-centric**: one row per US box, showing the box's byte
  budget + line count, the JP source (via v6 alignment), and the retranslation constrained to fit.
- Budget check per line: `len(retranslation_ascii) <= original_box_visible_chars` (same-size), and
  each display line ≤ ~35 chars.
- Boxes where JP has more content than the EN box held (the divergence-audit "compressions") are
  exactly the ones that will need tightening or repointing — flag them.

## Pointer mechanics (from gadesx notes / WA2_NOTES)
- Two prior tools froze the game on naive offset insertion. gadesx succeeded via hand hex-edit +
  a custom exe-repointer by "CUE". For STGEVT same-size edits, raw hex overwrite is safe.
- PS1 Mode-2/2352 disc: after editing, recompute EDC/ECC per sector (see ps1-disc-editing method).
- Reinsert file with `cebix/psximager` (psxrip/psxinject, XA-safe) or CDmage.

## ⚠️ JP↔US SLOT ALIGNMENT — the unsolved insertion bridge (investigated, NOT yet built)

**The problem.** We insert into the US disc's English slots, indexed by US#. The US box-stream
index == the US# (verified: US#3155 = the 3155th `10 0c` box on the US disc), so the **US side needs
no alignment**. The open question is: *which JP box is the true source for each US slot?* The DB
(`build_db.py`) pairs them **positionally** (JP box k → US box k). That is correct only where the two
versions have the same box count/order. They often DON'T: the US localization cut/merged/reordered
boxes, so JP and US box counts differ per block:

| block | US boxes | JP boxes | diff |
|---|---|---|---|
| 5  | 194 | 194 | 0 (positional map is safe) |
| 4  | 213 | 214 | +1 |
| 16 | 295 | 297 | +2 |
| 6  | 380 | 377 | −3 |
| 12 | 298 | 328 | **+30 (positional map wrong past the first edit)** |

For any block with a nonzero diff, positional `jp` in the DB is misaligned to the US slot after the
first cut. So the `jp` field the translation agents read is only reliable for count-matched blocks;
elsewhere it's the right *scene* but can be off by a few boxes deep in the block.

**What does NOT work (all tried, all drift):**
- `align_v6.py` — fuzzy line-break-sequence match. ~93% only on early/short blocks; drifts hard in
  deep-tail + mid-game blocks (smears one JP across several EN slots).
- `align_anchored.py` — proper-noun LIS + interpolation. Only ~13% HIGH-confidence globally; uses
  only ~14 hardcoded nouns, so anchors are sparse and it interpolates (drifts) between them.
- `slot_align.py` (built this session) — local-window match on STRUCTURAL signals (examine marker,
  short/long, digits). Reports "95% HIGH" on block 12 but that confidence is FALSE: nearly every
  dialogue box is `@`-prefixed + medium-length, so the signals don't discriminate content. Spot-checks
  showed confidently-mapped slots that are semantically unrelated. **Do not trust its HIGH flags.**

**What DOES work (proven on block 12, the path to build):** align on **content tokens that survive
BOTH the kanji-coding and the localization** —
- **katakana loanwords** romanized to rough latin (ガーディアン→gaadian≈Guardian, メリアブール→meriabuuru
  = "Meria Boule"), fuzzy-matched against the EN box's words. Block 12 has **246/328 JP boxes with
  katakana/number tokens** — far denser than the 14 proper nouns `align_anchored` uses.
- **proper nouns + 2+ digit numbers** (same idea, exact match).
This found a genuine correct pairing that the structural method missed *and* correctly picked a local
offset (−8) different from the block's dominant (−6) — i.e. it detects real edit points.

**The correct algorithm (to build at insertion time, NOT before):**
1. Compute content-token sets (katakana-romaji + nouns + numbers) for every JP and US box in a block.
2. Anchor: match content-bearing boxes by token overlap → a scatter of (JP,US) index pairs.
3. Take the longest strictly-increasing subsequence of anchors (robust to a few mispairs).
4. Plain-dialogue runs BETWEEN two anchors inherit the offset of their bracketing anchors. A run whose
   two bracketing anchors AGREE on offset is safe; where they DISAGREE, an edit lies inside → flag for
   human review. (~75% of block-12 boxes are anchorable; the unanchored runs are short.)

**Status:** investigated + prototyped, not productionized. It does NOT block translation — agents
produce correct JP *meaning* regardless of slot mapping. This must be solved before the ISO patch.
Corrects line ~69 below: the EN-slot workspace's "JP source (via v6 alignment)" is unreliable for
mismatched blocks; the anchor-bracket method above is the real bridge.

Source: byte analysis of US STGEVT (`Wild Arms 2 (USA) (Disc 1).bin`, LBA 12586) + gadesx notes.
