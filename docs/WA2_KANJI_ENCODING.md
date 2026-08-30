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

- **`tools/wa2_kanji_map.py`**
  - `KANJI` — the **global** map (`0x8801`–`0x8a37` only). ~376 solved. **Never** put a `>=0x8a38`
    code here; the decoder ignores it and it will mislead any tool that reads `KANJI` directly.
  - `LEGACY_LOCAL` — 60 archived readings that were solved for *one block's* context before we
    understood the two-tier split. Each is probably right for **one** block, wrong as a global.
    Leads only (see §5). The decoder never reads this dict.
- **`font_work/block_tables.json`** — the **block-local** subtables: `{ "<block>": { "<code>": "<kanji>" } }`.
  ~1,540 solved across ~58 blocks. Codes here are always `>=0x8a38`.
- **`tools/wa2_jp_decode.py`** — `decode_block(bytes, block)` is the decoder. It intercepts
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

### Step 2 — twin propagation (`tools/twin_merge.py`)
WA2 reuses whole scripts across blocks. Solving a local code in one twin solves it in all — if the
byte **context fingerprint** (2 bytes before + 2 after) matches. Known clusters:
```
{8, 9, 11}        {41, 42, 64, 87}     {78, 83, 90}
{82, 102}         {96, 109, 115}       {73, 99, 100, 103, 105, 106, 107, 112, 119}
```
Run it **after** solving (it multiplies fresh solves). Conflicts (same code+context, different
reading) are **removed**, never guessed.

### Step 3 — witness solver (`tools/block_solve_v2.py`)
Statistical: twin-line propagation + compound witnesses to a fixpoint. Plateaus quickly. **It now
MERGES** into `block_tables.json` (it was once destructive and wiped 1,151 solves — fixed; existing
readings win on conflict). Re-run after a global round exposes new context.

### Step 4 — LEGACY_LOCAL leads
Recover an archived reading into a block **only** where it forms a whitelisted 2-kanji compound
with an already-solved neighbor *in that specific block* (守る, 味方, 岩場, 勝負, 乗り, 周囲, 勇気,
仲間). Never blanket-apply a legacy reading across the blocks a code appears in.

### Step 5 — residue: solve-during-translation, or glyph-render
Single-occurrence local codes with no witness are solved by hand while translating their scene.
The last resort is reading the glyph bitmap from the font (`SY0.BIN`, `tools/wa2_font_extract.py`),
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

## 6. The `0xf0xx` glyph block (NOT kanji — solved separately)

`0xf0` is a lead byte for a **typographic glyph block**, unrelated to the two kanji tiers. It is
decoded by the `F0` table in `tools/wa2_jp_decode.py`, and unsolved codes print as `<f0xx>` — the
same shape as an unsolved global kanji, which is why it spent a long time miscounted as kanji work.

**Ellipsis run — `f040 [f041 ...] f042`, one `…` cell each.** The game draws `……` as a bracketed
multi-cell run (left / repeatable middle / right) so the dots space evenly. Evidence over all 120
blocks: `f040`→`f042` 763×, `f040`→`f041` 159×, `f041`→`f042` 178×; **913/925 (98.7%) of `f040`
runs close on `f042`**; run lengths are 2 cells (763), 3 cells (147), 4–6 cells (3). `f040` is
preceded by `「` 452× and by clause-final `は`/`て`/`が`; after `f042` normal kana resumes or the
box ends. Substituting one `…` per cell yields grammatical Japanese in every sampled box:

```
「……でも、今回の体験版では 残念ながら使用することができません
「………ほうほう、空を元に戻す為に レイポイントなるモノを探していると？
「あれも魔法みたいなものよ ……わかる？
```

One cell = one `…` — that keeps the rendered **width** right, which the insertion budget depends on.

**`f045` = `ー`** (long-vowel dash in hiragana context; katakana `ー` is the single byte `0xb0`).
Evidence: `う<f045>ん`, `うぇ<f045>×5ん`, `ふぎゃ<f045>×15ッ！`, `ぐが<f045>×4んッ！`.

Together these were **2,310 occurrences**, and solving them took the `f0xx` tail from 111 codes /
2,869 occ to **40 codes / 321 occ**.

The tail that remains splits in two, and only the first half is real:
- **Sentence-final punctuation glyphs** — `f044`, `f04a`, `f059`, `f05a`, `f05b`, `f046`. All sit
  after a sentence-ending particle (`ね`/`よ`/`わ`/`ッ`/`〜`/`ん`) and before end-of-box. `f059`
  follows `ッ`/`！` and is probably another styled `！` (cf. `f056`–`f058`). **Not guessed** — §5
  rule 1 applies; they need a witness.
- **Binary-region noise** — `f0ef`, `f05f`, `f02f`, `f010`, `f011`, `f012`, `f002`. Always preceded
  by the same mis-decoded byte (`繕`, `]`, `"`) inside a run full of `[a3]`-style escapes. These
  are not text; they belong to the extractor problem below, not to decoding.

---

## 7. The Shift-JIS trail-byte gate (tokenizer correctness)

Leads `0x81–0x9f` / `0xe0–0xef` are real Shift-JIS, so the trail byte **must** be legal
(`0x40–0x7e` or `0x80–0xfc`). The decoder originally consumed two bytes on the lead alone, which
swallowed **2,541 illegal pairs** — `91 06`, `98 10`, `e1 3c`, `96 10`, `8e 06` … Those are a
single-byte code followed by an **event opcode** (`0x06` = inline-box frame, `0x10` = control
lead), not text. Consuming them emitted plausible-looking kanji noise (`鶏`, `坐`, `剛`, `鮫`) that
let binary runs pass `extract_boxes.py`'s `cjk>=2` gate and inflated the unsolved-code count.

**The custom kanji block `0x88`–`0x8b` is exempt and must be matched first** — it is not Shift-JIS
and legitimately uses trail bytes below `0x40` (the global tier starts at `0x8801`, the block-local
tier at `0x8a38`). Getting that order wrong breaks every kanji decode.

This fix alone removed **4,536 phantom `<xxxx>` markers** (global unsolved 8,106 → 3,570).

---

## 8. Current status (update as it moves)

Measured on the corrected box model (`data/script/boxes.json`), not the superseded DB slots:

| | before | after §6+§7 |
|---|---|---|
| JP boxes fully clean | 6,204 / 14,319 (43.3%) | **7,668 / 14,328 (53.5%)** |
| unsolved global markers | 8,106 | **3,570** |
| unsolved block-local | 9,103 | 9,101 |

The older "30% / 8,516 boxes" figure came from the pre-migration DB and is superseded.

**Residue, with the 1,353 binary-garbage boxes (9.4%) excluded:**

| pile | size | how it closes |
|---|---|---|
| custom kanji, global tier | **169 codes / 2,476 occ** | §3 Step 1. Finite and closeable; one solve fixes all 118 blocks. Top: `88f7`×88, `8865`×59, `8a0b`×59, `89e2`×41 |
| block-local | 5,757 slots / 9,043 occ | §3 Steps 2–4 + §4b. **5,425 slots (95%) have their code already solved in some other block** — a lead pool, not blind guessing. 1,647 slots recur 2+× in their own block, so they clear the dual-witness bar |
| `f0xx` tail | 40 codes / 321 occ | §6 — half is punctuation needing a witness, half is not text |
| SJIS gaps | 73 codes / 127 occ | `0xedxx`/`0xeaxx` PUA-range glyphs; trivial tail |

Excluding the garbage boxes from the denominator too, clean coverage is **7,668 / 12,975 = 59.1%**.

### Known-open: control-opcode arguments are decoded as text

`decode_block`'s segment scanner treats `0x05 0a 0b 10 11 13 16 17 18` as **2-byte** opcodes, but
`decode()` does not — it emits `[16]` and then decodes the *argument* byte as kana. So a real box
keeps running past its text into event bytecode:

```
「生きて、帰るしかないんだッ！[16]くぉ[16]くぉ[16]くぉ[16]くぉ[16]くぉ[17]
```

This is why a byte-escape *density* filter is the wrong fix — it would drop genuine dialogue. The
right fix is to terminate the box where text ends, which needs the opcode widths established
first. Arg-byte distributions over whole blocks are too noisy to settle it (all leads show
~250 distinct args); it needs measurement restricted to in-text occurrences. **Not yet done.**
