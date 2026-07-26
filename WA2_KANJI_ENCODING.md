# Wild Arms 2 — Kanji Encoding & Decoding Guide

How WA2 stores kanji, why the same byte-code shows different characters in different places, and
the method we use to decode the remaining ones. This is the canonical reference; if the memory
note or a tool comment disagrees, this file wins.

---

## 1. The two-tier encoding (the core fact)

WA2 does **not** use standard Shift-JIS for its dialogue kanji. Each kanji is a 2-byte code in the
`0x88xx`–`0x8bxx` range, in the game's own custom order. There are **two tiers**, split at an
exact boundary:

| Tier | Code range | Behavior |
|---|---|---|
| **GLOBAL** | `0x8801` – `0x8a37` | One code = one kanji, **everywhere in the game**. Solve once, correct in all 118 blocks. |
| **BLOCK-LOCAL** | `0x8a38` and up (through `0x8bxx`) | Each STGEVT **block has its own subtable**. The *same* code is a *different* kanji in different blocks. |

**The boundary is exactly `0x8a38`.** Not "all of 8axx" — `0x8a00`–`0x8a37` is still global and
stable; only `0x8a38+` swaps per block.

### Proof (why we're sure)
Of 287 codes we've solved in 2+ blocks, **279 map to a different kanji per block** (97%). Example
— code `0x8a38`:

```
blk0=陣   blk3=父   blk5=英   blk12=闇   blk14=灯   blk23=着   blk27=使
```

The 8 codes that *don't* vary are all in blocks **8 / 9 / 11**, which are byte-identical copies of
the same lore text ("twins", see §4) — so identical subtables there is expected, not a
counterexample.

> A community observation put it as *"the 8axx part of the table is what seems to change,
> not sure how much."* Answer: from `0x8a38` onward, effectively the whole thing; one subtable
> per block.

---

## 2. Where the data lives

- **`tools_wa2/wa2_kanji_map.py`**
  - `KANJI` — the **global** map (`0x8801`–`0x8a37` only). ~376 solved. **Never** put a `>=0x8a38`
    code here; the decoder ignores it and it will mislead any tool that reads `KANJI` directly.
  - `LEGACY_LOCAL` — 60 archived readings that were solved for *one block's* context before we
    understood the two-tier split. Each is probably right for **one** block, wrong as a global.
    Leads only (see §5). The decoder never reads this dict.
- **`font_work/block_tables.json`** — the **block-local** subtables: `{ "<block>": { "<code>": "<kanji>" } }`.
  ~1,540 solved across ~58 blocks. Codes here are always `>=0x8a38`.
- **`tools_wa2/wa2_jp_decode.py`** — `decode_block(bytes, block)` is the decoder. It intercepts
  `>=0x8a38` **before** consulting the global map, looks the code up in that block's subtable, and
  emits `<b:xxxx>` if unsolved. Global codes not in `KANJI` emit `<xxxx>`. So in any decode:
  - `<b:8a5c>` = an unsolved **block-local** code
  - `<8946>` = an unsolved **global** code

---

## 3. Decoding method (priority order — highest payoff first)

The loop **compounds**: every global solve makes more surrounding text legible, which exposes more
solvable compounds in the next pass. Run the steps in order, repeat.

### Step 1 — GLOBAL tier (best ROI: one solve fixes every block)
Rank unsolved global codes by frequency across all decoded blocks, read the neighbor context, and
solve via **okurigana** (trailing kana) and **2-kanji compounds**. Examples we solved this way:
輝 集 遠 広 書 暗 渡 部 掘 許 故 概 恐 続 里 王 陸 原 領 政 品 団 構 断 駆 冒 願 起 完 礼 斬 告 記 録 救 視 期 逃 弱 認 緊.
Verify each against a real word before committing (e.g. `無[視]して` → 無視 ✓, `亡き[王]妃` → 王妃 ✓).

### Step 2 — twin propagation (`tools_wa2/twin_merge.py`)
WA2 reuses whole scripts across blocks. Solving a local code in one twin solves it in all — if the
byte **context fingerprint** (2 bytes before + 2 after) matches. Known clusters:
```
{8, 9, 11}        {41, 42, 64, 87}     {78, 83, 90}
{82, 102}         {96, 109, 115}       {73, 99, 100, 103, 105, 106, 107, 112, 119}
```
Run it **after** solving (it multiplies fresh solves). Conflicts (same code+context, different
reading) are **removed**, never guessed.

### Step 3 — witness solver (`tools_wa2/block_solve_v2.py`)
Statistical: twin-line propagation + compound witnesses to a fixpoint. Plateaus quickly. **It now
MERGES** into `block_tables.json` (it was once destructive and wiped 1,151 solves — fixed; existing
readings win on conflict). Re-run after a global round exposes new context.

### Step 4 — LEGACY_LOCAL leads
Recover an archived reading into a block **only** where it forms a whitelisted 2-kanji compound
with an already-solved neighbor *in that specific block* (守る, 味方, 岩場, 勝負, 乗り, 周囲, 勇気,
仲間). Never blanket-apply a legacy reading across the blocks a code appears in.

### Step 5 — residue: solve-during-translation, or glyph-render
Single-occurrence local codes with no witness are solved by hand while translating their scene.
The last resort is reading the glyph bitmap from the font (`SY0.BIN`, `tools_wa2/wa2_font_extract.py`),
which needs a code→glyph-offset mapping worked out per block — a real RE task, not yet wired up.

---

## 4. The twin blocks (script reuse)

Some STGEVT blocks hold the **same** text (the recurring `@`-lore encyclopedia, repeated
save/menu scaffolds, etc.). Byte-identical or near-identical → shared subtable. `twin_merge.py`
finds them by fingerprint overlap (≥90% on ≥30 shared codes) and unions them into clusters. The
big lore cluster is `{8, 9, 11}` (452 shared codes, 98% match; first 40 EN lines identical).

---

## 4b. Parallel-fleet solving (how to bulk-solve the local tier with many agents)

Proven workflow (one session cleared ~62 blocks, +575 local solves, 25%→30% clean-JP):

1. **Agents are READ-ONLY. Coordinator writes.** Each agent gets ONE block, proposes solves as
   text with witness snippets, and NEVER touches `block_tables.json` or `wa2_kanji_map.py`. The
   coordinator re-verifies every proposal against the real decode (substitute the kanji, grep the
   block, confirm 2 genuinely independent contexts) BEFORE writing. This is non-negotiable: if
   agents wrote directly they'd race on the shared files and slip guesses past the dual-witness bar.
   Real errors this caught: duplicate-line "dual witnesses" (one line, not two), single-witness
   overreach, and a legit dual-glyph (`8a47`&`8a70` both=捨) that looked like a conflict.
2. **Twin-first ordering is the highest-leverage move.** Solve one representative of a twin cluster
   (§4) FIRST, then run `twin_merge.py` — it propagates for free. Block 8 → +34 solves in 9/11.
   Cluster reps worth doing early: 8 (→9,11), 41 (→42,64,87), 96 (→109,115), 73 (→the 9-block set,
   but that one is mostly non-lexical).
3. **Bound the agent's INPUT, not just its prompt.** Dense blocks (>400 unsolved occ: 6,7,16,17…)
   time out if handed the full brief. `kanji_agent_brief.py` caps output for those (top 25 codes,
   60 rows) — cut brief size ~4× and retries succeeded in minutes. Give each agent that tool +
   "cap tool calls ~8".
4. **Concurrency ceiling is a hard 20 subagents.** Keep it saturated by firing a replacement the
   instant one finishes; excess launches error harmlessly.
5. **Diminishing returns are steep and legible.** First ~20 blocks average 8–20 solves; the tail is
   mostly COUNT:0 — and that's CORRECT discipline, not failure (control-byte padding, font tables,
   verbatim-repeated lines). Stop the fleet once zero-results dominate; don't dispatch obviously
   sparse blocks. The residue clears during per-scene translation.
6. **Aligned-EN cross-checks catch GLOBAL mis-solves that okurigana alone misses.** This session,
   block 15's EN "Defender of Justice" vs decode 新義 exposed `88e9` as 正 not 新 — a ~155-occurrence
   global error. Periodically audit the global map against EN, not just solve forward.

---

## 5. Hard rules (don't corrupt the corpus)

1. **A disputed or guessed decode is WORSE than an unsolved `<b:xxxx>`.** When twins disagree on the
   same code+context, remove it from all members until a real witness decides.
2. **Never place a `>=0x8a38` code in the global `KANJI` map** (or a `<0x8a38` code in a block table).
   `build_db.py`/decoder assume the boundary; violating it silently mis-decodes.
3. **Dual glyphs exist** — two different codes can be the same kanji (e.g. `0x8a18` and `0x88f8`
   both = 続). That's fine. What's *not* fine is one code = two kanji within one block.
4. **Suspected dups are held, not guessed.** Codes that look like a second glyph for a reading we
   already have (`89f9`≈者, `89ab`≈美, `89c1`≈特, `886f`≈追) stay unsolved until a witness confirms.

---

## 6. Current status (update as it moves)

- Global map: ~388 solved (+ 88e9 corrected 新→正, a ~155-occurrence fix). Low-frequency tail remains.
- Block-local: **~2,115 solved across ~76 blocks** (after the parallel-fleet run, §4b).
- Overall decodability (DB `jp_clean`): **~2,572 / 8,516 boxes (30%)**.

The remaining local tier is a genuine long tail (most slots occur once, or sit in control-byte /
font-table / duplicate-line regions that can't be dual-witnessed), so it clears fastest *during*
per-scene translation rather than by further bulk solving. The parallel fleet has already skimmed
the dual-witnessable content off every high-value block.
