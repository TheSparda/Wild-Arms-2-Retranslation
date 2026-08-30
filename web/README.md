# WA2 Translation Editor (web)

**Hosted: <https://thesparda.github.io/Wild-Arms-2-Retranslation/>** (auto-deployed from `web/`
by `.github/workflows/pages.yml`). You can also run it locally — see below.


Serverless translation tool for Wild Arms 2 (PS1), modeled on the Suikoden III web editor:
a static site that runs entirely in your browser — discs are read locally, nothing is uploaded.

## Run

Double-click `Start Editor (Mac).command` / `Start Editor (Windows).bat`, or:

```bash
cd web && python3 -m http.server 8478   # then open http://localhost:8478/
```

## Use

1. **Load discs** — five slots: **US Disc 1 / Disc 2** (raw 2352-byte `.bin`; at least one
   required — these are the patch targets), **JP Disc 1 / Disc 2** (optional; enables the JP
   source column with alignment-confidence chips), and the **gadesx Spanish patch** (`.ppf`
   applied in-memory, or a pre-patched `.bin`) as the ground-truth reference column.

   > **Load both US discs.** `STGEVT.BIN` is byte-identical across disc 1 and disc 2 — verified
   > at the raw sector level, and asserted by `tests/core.test.mjs`. The script container is
   > simply duplicated on each disc, so a patch applied to only one disc leaves the other
   > running the original English. With both loaded the exporter emits a patch per disc; with
   > one, it says so in the export status. The same holds for JP: either JP disc supplies the
   > identical source script, so you only need whichever you have.

   Loading a second disc of the same language **cross-checks** it against the first and warns
   (with the byte offset) if the regions differ — that would mean an unexpected revision, and
   patching the pair would desync them.

   **Discs are remembered between sessions.** On Chromium the file handles are stored in
   IndexedDB, so returning to the editor offers *"Last session … Reload these"* — one click
   re-opens every disc (or none, if the origin still holds permission). Other browsers can't
   reopen files programmatically, so the bar lists the remembered names and the button re-opens
   the picker. *Forget* clears it. Translations autosave separately in localStorage.
2. **Edit** — a side-by-side view modeled on the project wiki: **JP · EN · ES** reference
   columns beside a live **in-game window preview** of your translation, rendered in the game's
   own textbox styling. Columns can be toggled individually, and the view switches between
   *Columns + preview*, *Columns only*, and *Game preview only* (remembered across sessions).

   Two **independent** budgets are shown live, because passing one does not mean passing the other:

   | budget | limit | why |
   |---|---|---|
   | **bytes** | the chunk's capacity on disc | chunk length is fixed; shorter text is space-padded before the NUL (the shipped gadesx model). Over-budget chunks are refused. |
   | **lines × columns** | 3 × 35 | the script carries **explicit** `\x0d` line breaks and the game does **not** auto-wrap, so text can fit the chunk and still run outside the visible window. 96.9% of shipped EN boxes sit inside 3×35 (asserted in `tests/core.test.mjs`). |

   Overflow is shown where it happens: the exact columns past 35 and any 4th line are highlighted
   inside the preview, and the window frame turns red.

   Speaker nameplates come from the `\x05 N` selector — the only reliable speaker signal in the
   disc bytes. Name codes (`{0}`) render with sample names in the preview *and* count at their
   expanded width, so `{0}, wait!` is measured as the 13 columns "Ashley, wait!" really occupies.
   Boxes with control codes the encoder can't rebuild are read-only. The *gadesx accents* toggle
   allows áéíóúñ¡¿ via his proven font slots (only readable on a font-patched disc).

   Blocks paginate at 60 boxes; search covers EN/JP/ES and your own text, and *only edited*
   filters to your work.

3. **Work offline (strings JSON)** — *Export strings JSON* writes the whole corpus as
   self-contained rows so it can be translated anywhere — a spreadsheet, a script, an LLM — and
   imported back. Scope it to all blocks, the current block, or only edited boxes, and optionally
   only untranslated ones. A full-disc export is 20,652 rows / ~7.9 MB and takes a few seconds.

   ```json
   { "key": "3:275139:0", "blk": 3, "off": 275139, "sub": 0,
     "en": "*It's empty!", "jp": "＊からっぽだ！", "jpConf": "approx", "es": "*¡Vacío!",
     "re": "",                          // <- the only field you edit
     "editable": true, "panel": true, "speaker": "1",
     "chunk": "3:275139", "chunkBytes": 12, "enDigest": "dd2aa166" }
   ```

   Rows sharing a `chunk` share `chunkBytes`; use `\n` in `re` for real line breaks (3 × 35
   ceiling). Import **validates rather than trusts** and reports counts for each outcome:
   applied, unchanged, blank, keys not on this disc, **read-only** boxes, rows now over the
   on-screen ceiling, and chunks now over their byte budget. `enDigest` guards the mapping —
   a row whose English source no longer matches is **refused**, so a JSON built against a
   different disc or extraction can't quietly write good-looking text into the wrong boxes.
   Re-importing an untouched export is a no-op. With existing work in the editor you're asked to
   merge or replace.

4. **Export patches** — one patch file per loaded US disc (`…_EN1.ppf`, `…_EN2.ppf`).
   **PPF3** (with undo data), **xdelta** (VCDIFF; `xdelta3 -d -s original.bin patch out.bin`),
   **in-place write** (desktop Chromium, needs the file opened via the picker), or a streamed
   **patched copy**. Every modified sector gets its Mode 2 Form 1 **EDC/ECC recomputed**.

## Architecture / provenance

| file | what | verified against |
|---|---|---|
| `wa2-core.js` | sector geometry, EDC/ECC codec, PPF2/3 parse+build+apply, chunk parse/rebuild, EN/ES text codec | `tests/core.test.mjs`: EDC/ECC recompute is byte-identical to the US disc (256/256 sectors); EN+gadesx PPF reproduces his patched disc **byte-for-byte**; chunk parse→rebuild is identity on every chunk of block 3; disc 1 ≡ disc 2 script region (EN and JP) |
| `wa2-jp.js` | JP decoder (kanji map + per-block tables + kana/DTE) and the EN↔JP DP aligner | `tests/jp.test.mjs`: output identical to `tools/wa2_jp_decode.py` / `extract_boxes.py` on the golden blocks (3, 24) |
| `vcdiff.js` | RFC 3284 xdelta synthesis from known edits (shared with the Suikoden III editor) | S3 editor test suite |
| `data/jp_tables.json` | generated tables — **regenerate with `python3 web/gen_tables.py`** whenever `tools/wa2_kanji_map.py` or `font_work/block_tables.json` change | golden fixture regenerated by the same script |

Tests run from the repo root (they read your local discs; skipped when absent):

```bash
node web/tests/core.test.mjs && node web/tests/jp.test.mjs
```

## What the research docs taught this editor

The editor encodes decisions already made and verified in `docs/` — it is not re-deciding them.

- **The byte budget is not a hard box limit.** `WA2_INSERTION_MODEL.md` corrects an earlier
  assumption: a box has no stored size cap. The chunk length is the ceiling for a *pointer-safe*
  same-size overwrite; longer text is possible with a pointer-recalculating pass. The editor
  therefore labels boxes **pointer-safe** or **needs repointer** rather than pretending the limit
  is absolute. (Export still refuses over-budget boxes — no repointer exists yet.)
- **3 × 35 is the real on-screen ceiling** and is independent of the byte budget (same doc,
  verified there and re-measured here across all 21,644 boxes).
- **House style is enforced live.** `WA2_RE_STYLE_GUIDE.md` §1–§3 are the project's hard rules;
  the editor lints each line against them as you type — no em dashes or `--`, no box ending on a
  comma or dangling conjunction, no run-on comma chains, balanced `|emphasis|` markers, `{n}`
  codes instead of spelled-out renameable names, glossary decisions
  (`Mercs` → `|Wandering Crows|`, `Sebok` → `T'Bok`), no `#` notes inside the box body, and the
  `*` examine-panel marker preserved.
- **The JP pairing is corroborated, not just guessed.** The DP aligner scores only digit runs and
  length ratio, so it marks **9 of 15,732** pairs (0.1%) as anchored and the rest `approx`.
  `verifyPairs` checks each pairing against the hand-verified katakana↔EN glossary
  (`GUIDE_ANCHORS` + the character roster): **550 pairs** are now corroborated (`term`, 61× more
  than before) and **78** are flagged `conflict` with a suggested box. Sampled conflicts were all
  genuine drift of −3 to +20 boxes. Use *problems only* to review them.

  > A note on method: the docs propose romanizing katakana and fuzzy-matching it to English. That
  > was implemented and measured — it both over-fires (`otona` → skeleton `tn` collides with
  > unrelated words) and under-fires (`damutsen` never reaches `damzen`), and every sampled
  > "conflict" it produced was actually the DP being right. It was dropped in favour of the exact
  > curated glossary, which trades recall for precision. A chip you can't trust is worse than none.
- **`{4}` = Kanon.** The style guide (§3, canonical) and `WA2_NAME_DICTIONARY.md` disagree on
  `{2}`/`{3}` and the dictionary omits `{4}`; the style guide's own precedence rule settles it.

## Known limits (v1)

- EN↔JP pairing inherits the aligner's honest ~38%-within-±1 accuracy. `approx` still means
  *verify before trusting*; `term`/`anchor` are corroborated; `conflict` is probably misaligned.
  Only ~3.5% of pairs can be corroborated at all — the glossary is 39 terms against 15,732 boxes.
- Boxes containing item-ref/control opcodes (`07 30 11 …`) are read-only for now.
- Text longer than a chunk needs pointer relocation (gadesx-style) — not yet supported; the
  editor refuses over-budget chunks rather than corrupting the event stream.

Characters / Abilities tabs are stubs for the planned expansion.
