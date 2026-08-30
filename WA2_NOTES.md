# Wild Arms 2 (USA) — Reverse-Engineering Notes

> **Kanji encoding + decoding method: see [WA2_KANJI_ENCODING.md](WA2_KANJI_ENCODING.md)**
> (the two-tier global/block-local model, boundary 0x8a38, and the solving loop).

## Disc
- 2 discs. Serial **SCUS_944.84** (Sony US). MODE2/2352, standard ISO9660, volume "WILDARMS2".
- Disc 1 ~515 MB at `games/Wild Arms 2/Game Files/Wild Arms 2 (USA) (Disc 1)/`.

## File system (Disc 1)
| Path | File | Size | Contents |
|---|---|---|---|
| /EXE/ | WILDARM2.EXE | 940 KB | **main exe — item/ARM/skill names + stat tables + formulas** |
| /EXE/ | OPENING.EXE | 285 KB | intro |
| /SYS/ | MONSTER.BIN | 6.3 MB | enemy data |
| /SYS/ | CH0.BIN | 1.2 MB | character data? |
| /SYS/ | SCR.BIN | 688 KB | script? |
| /SYS/ | MENU.OVR, UTIL.OVR | | overlays |
| /BTL/ | BATL/BATLOVR/BATLSND | 38/26/1.8 MB | battle |
| /STG/ | STGMAP/STGEVT/OUTMAP | 185/10/15 MB | maps + events (dialogue) |
| /IXA/ | E00–E15.IXA | | packed archives |
| /STR/ | WA2*.STR | | standard PS1 STR movies (jpsxdec-readable) |

## Key facts
- **Text is uncompressed ASCII** in the exe — item/weapon/skill names & descriptions are directly editable, NO custom font table.
- **PS-EXE header:** text loads at RAM **0x80011124**; file offset 0x800 = that RAM addr.
  Conversion: `RAM = 0x80011124 + (fileoffset - 0x800)`, and `fileoffset = RAM - 0x80011124 + 0x800`.

## Name pool (WILDARM2.EXE)
Contiguous null-terminated ASCII name pool at **~0x20B1–0x2DD7**: items, berries, crests, guns, knuckles, armor, hats, robes, accessories, guardians (Grudiev, Schturdark…), skills.

## Ashley's kit — located
### ARM firing modes (8) — name-pointer table at file **0x92A4** (4-byte RAM pointers, in order):
| # | Mode | Name string (file off) | FP cost |
|---|---|---|---|
| 0 | ShotWeapon | 0x9CA8 | 6 |
| 1 | MultiBlast | 0x9CB3 | 10 |
| 2 | BoltAction | 0x9CBE | 16 |
| 3 | DeadOrAlive | 0x9CC9 | 20 |
| 4 | ShockSlide | 0x9CD5 | 24 |
| 5 | FantomFang | 0x9CE0 | 30 |
| 6 | Blast 'Em | 0x9CEB | 40 |
| 7 | RisingNova | 0x9CF5 | 50 |

(A second copy of these names is in the item name-pool at 0x2D8F.)
The pointer table continues past ARM7 (0x92C4+) — it's the **full battle-skill name-pointer list** for all characters' abilities.

### Force abilities (block ~0xA329):
Accelerator (0xA329), Combine (0xA335), Full Clip (0xA33D), Access (0xA347)

### Knight Blazer attacks (block ~0xA2EC):
Hot Fencer (0xA2EC + upgraded 0xA300), Banisher (0xA2F7, 0xA315), Last Burst (0xA31E)

## Still TODO
- **Find the numeric stat table** (FP cost/power/target/element per ARM mode). FP costs 6/10/16/20/24/30/40/50 are NOT a contiguous byte array → stats are fixed-size records elsewhere, indexed parallel to the name-pointer table. Locate by: (a) finding the code that reads 0x92A4, or (b) RAM-search in an emulator for a known FP cost, then trace to disc.
- Character base stats / level curves (likely in WILDARM2.EXE or CH0.BIN).
- Item stats (prices, effects) parallel to the 0x20B1 name pool.

## Tooling notes
- Community: **no WA2 editor/docs exist.** `cebix/wa1tools` (Wild Arms 1) is a template; `cebix/psximager` is the recommended extract/rebuild tool (preserves XA media).
- Our common tools in `PS1/tools/` (psx_ecc.py, extract_from.py) work for reads and same-size reinsertion.
- Approach: use emulator RAM-search (DuckStation/no$psx) to find live values, then trace to file offsets.

---

# RETRANSLATION — reference (from research + gadesx notes)

## Prior art (WA2 text HAS been hacked)
- **gadesx** — complete Spanish translation (2014) + the ONLY public WA2 text doc:
  https://gadesxscene.blogspot.com/2014/04/wild-arms-2-info-for-translators.html
- **barleybap** — English retranslation in progress (since Dec 2023):
  https://barleybaptranslations.wordpress.com/2023/12/30/wild-arms-2-retranslation-project/
- No reusable WA2 toolchain released; both used generic tools + custom scripts.

## Text-bearing files (confirmed by gadesx + our analysis)
| File | Contents |
|---|---|
| STGEVT.BIN | main script + common messages (chests, repeated NPC lines) |
| UTIL.OVR | radio / Call-menu scripts |
| WILDARM2.EXE | items, skills, menus (the ASCII name pool we found) |
| SY0.BIN | font data |

## Control codes (hex)
- `0D` line break/jump
- `100C` start message; `100C2A` skill/feature explanation (2A='*')
- `40` speaker-name color marker
- `0B35` SELECT button, `0830` TOOL, `012E` BOOK
- `1131…1130` yellow-text wrapper (destination msgs)
- `163630` centering/blank-fill formatting (append for scene msgs)
- `0D13` scene-message jump
- Char IDs: `0530`=ASHL(Ashley) `0531`=BRAD `0532`=LILK(Lilka) `0533`=TIM `0534`=KANO(Kanon) `0535`=MRIV(Marivel)
  `0A30`=IRVN `0A31`=ALTA `0A32`=MARI `0A33`=COLE `0A34`=BILL `0A35`=TONY `0A36`=SCOT `0A37`=DOG `0A42`=TERR `0A43`=POKA
- String pattern: [CharID] + control codes + ASCII text + terminators.

## Recommended toolchain
- Extract/reinsert files: **CDmage** (gadesx) or **cebix/psximager** (psxrip/psxinject, XA-safe).
- Dump/reinsert text with auto-repointing: **Cartographer (dumper) + Atlas (inserter)**,
  or modern **HexString** (github.com/KodingBTW/hexstring). Handles variable-length + pointer recalc.
- Our PS1/tools/ (extract_from.py, psx_ecc.py) work for same-size reads/writes.

## JP FONT / ENCODING — investigation findings (this session)
- **SY0.BIN** (80KB, LBA 1369 JP / 1364 US) = font file. Header at 0x00 is a 6-entry RAM pointer table (base 0x801e0100); sections at file-offsets 0x100, 0x1800, 0x7cb4, 0xa8c8, 0xf1f0, 0x10edc.
- Sections 1–5 are **HIGH ENTROPY** (all 256 byte values present, only ~3% zeros) → the font glyphs are **COMPRESSED**, not raw 1bpp/4bpp tiles. Naive tile-rendering = noise (confirmed). Decompression needed before the font is readable → building a byte→glyph .tbl from bitmaps is blocked until the compression is identified.
- **KEY BREAKTHROUGH — JP and US STGEVT.BIN share IDENTICAL event bytecode structure.** Same control codes (100C msg-start, 0D linebreak), same char-ID bytes (0530/0531/0532), near-identical file headers, and matching code counts (JP slightly higher; JP file 13.27MB vs US 10.81MB because 2-byte JP text is longer). Only the TEXT bytes between control codes differ: US = ASCII, JP = custom 2-byte codes.
- **IMPLICATION: the US ASCII script is a Rosetta Stone.** We can align JP text runs to their English equivalents positionally via the shared bytecode WITHOUT decoding the font first. Two routes to actually READ the JP: (a) relative-search a known kana run to recover the table (standard romhack method), or (b) decompress SY0 font + OCR/identify glyph order. Route (a) is far cheaper and doesn't need the font.
- Extracted copies: `font_work/SY0_jp.bin`, `font_work/SY0_us.bin`. JP filetable: `filetable_jp_cd1.json`.

### ENCODING CRACKED (mostly) — WA2 JP is ~90% standard Shift-JIS
Tested by decoding JP STGEVT text runs as SJIS + histogramming lead bytes across 400 messages:
- **Kanji, katakana, punctuation = STANDARD Shift-JIS** and decode correctly. Confirmed glyphs: 「(8175) 、(8141) plus kanji (0x88xx/0x89xx/0x8axx blocks). Lead-byte counts: 0x81=2554, 0x88=1576, 0x89=1144, 0x8a=1078, 0x83(katakana)=451 — all real SJIS ranges.
- **Hiragana is REMAPPED, not standard.** SJIS hiragana lead 0x82 is nearly ABSENT (86) while gaiji/user-defined lead **0xf0 is high (541)**. So hiragana glyphs were moved into the 0xf0xx (SJIS gaiji) block — that's why naive SJIS decode gave "~zero hiragana + garbage kana" earlier.
- **CONSEQUENCE:** we do NOT need to crack the LZSS font. We only need to recover the **hiragana remap table (~50-70 codes: 0xf0xx → あいうえお…)**. Everything else already decodes with Python's `shift_jis`.
- **How to recover the hiragana map cheaply:** the 0xf0xx codes almost certainly run in gojūon order (relative-search confirms this) — OR cross-reference against the toybox/tekeremu verbatim JP quotes (`jp_quotes/`) + the US Rosetta Stone (identical bytecode) to anchor a few known hiragana words and fill the rest by order. ~1-hour job, not a font-decompression sub-project.
- STATUS: hypothesis strongly evidenced; next step is to build & validate the 0xf0xx→hiragana .tbl, then dump the full JP script via SJIS+remap.

### ENCODING — CRACKED (this session, verified against dialogue). Decoder: `tools_wa2/wa2_jp_decode.py`
Correction to earlier 0xf0 guess. The real scheme (proven by decoding real 100C dialogue):
- **HIRAGANA = custom SINGLE-byte codes, gojūon order, base 0x28.** code c (0x28..0x7a) → SJIS hiragana glyph[c-0x28] where the glyph list is SJIS 0x829f..0x82f1 (ぁあぃい…をん, 83 glyphs). Found by brute-forcing the base and scoring common bigrams (です/ます/こと/…): base 0x28 wins decisively (score 981 vs noise), and decoded dialogue reads as natural Japanese (これさえあれば / できそうだな / あるうちのひとつは / では、かつては …). ✅ SOLVED.
- **KATAKANA = custom SINGLE-byte codes — SOLVED.** 46 basic katakana in gojūon order from ア=0xb1 (archaic ヰヱヲ dropped, so ワ=0xdc, ン=0xdd). Long-vowel ー=0xb0. Small/voiced kana ァィゥェォャュョッ at 0xa7..0xaf. Verified: ロンバルディア, フィールド, サーチシステム, ホバークラフト, ディスプレイ, ヴァレリア, メニュー all decode perfectly. ✅ SOLVED. (Solved via Rosetta anchors from known loanwords aligned to the US script.)
- **KANJI = remapped into custom 0x88xx-0x89xx (some 0x8axx) codes in the GAME'S OWN order** — NOT standard SJIS kuten (decode as wrong kanji / SJIS-invalid). ~416 distinct codes. ⏳ THE BULK REMAINING WORK. Top ~40 codes (880b,8816,8846,88bc,890b,886a,8853,884d,8899,8970,898b…) cover most occurrences but appear in kanji COMPOUNDS (adjacent unknowns), so single-glyph context-guessing is unreliable. Proper solve = full JP↔US line alignment (Rosetta) or recover the font glyph order from decompressed SY0.BIN.
- Punctuation (「」『』、。！？＊　) and katakana-with-dakuten (ガ=834b, ド=8368, ヴ=8394) decode as clean standard SJIS.
- **ROSETTA CONFIRMED:** JP & US STGEVT event bytecode is identical → JP message #N aligns to US message #N (both start with the same tutorial/menu sequence; verified through msg ~40). Enumerate with `messages()`; align to `english_script/disc1/STG_STGEVT.BIN.txt`.

### CURRENT STATE (this session)
- Decoder `tools_wa2/wa2_jp_decode.py`: hiragana ✅ + katakana ✅ + SJIS punctuation ✅ + **117 custom kanji** ✅ + F0 glyph 〜 ✅.
- Kanji map lives in `tools_wa2/wa2_kanji_map.py` (auto-imported by the decoder), solved in batches from okurigana + compound context, each validated.
- **0xf0xx is a 2-BYTE glyph/DTE block**, NOT hiragana-0xf0+char. 0xf043=〜 (emphasis ender, 4024×) ✅. 0xf040+0xf042 paired DTE (unsolved). Handle 0xf0 as 2-byte lead.
- **92.1% of the script decodes to real text** (200 kanji; ~36k placeholders remain). Full decoded dump: `jp_script/disc1_STGEVT_decoded.txt`.
### SY0.BIN COMPRESSION — CRACKED (spike). Decompressor at EXE RAM 0x8009a074.
- SY0's 6 sections (after the 0x100 pointer header) are **standard LZSS (Okumura LZ77)**, confirmed by disassembling WILDARM2.EXE (capstone) — found the decompress loop at RAM **0x8009a074** (fileoff ~0x89774).
- Format: 4KB ring buffer, mask 0xFFF, init pos **0xFEE**, flag bit **1=literal / 0=match**. Match = 2 bytes: `offset = b1 | ((b2&0xf0)<<4)` (12-bit), `length = (b2&0x0f)+3` (3..18).
- Working Python impl (verified): decompresses all 6 sections cleanly. Total **185,377 bytes** decompressed from ~74KB. Section decompressed sizes: 16780/33497/32954/32661/33515/35970.
- **Autocorrelation says glyph stride = 18 bytes** (=144 bits = a 12×12 1bpp glyph, standard JP font cell). 185377/18 ≈ 10298 (too many — sections include non-glyph data / multiple font sizes; the 0x10edc section is an uncompressed index table of u16 offsets).
- PIXEL FORMAT — partially cracked: rendering decompressed bytes as **8px-wide, 18-byte-stride, row-major MSB-first** produces CLEAN glyphs for half-width chars — a 一-detector found 148 correct horizontal-bar glyphs this way. So the base packing is 1bpp, MSB-first, row-major, and half-width cells are 8×~16-18. FULL-WIDTH kanji are 16px wide, almost certainly stored as **two 8-wide byte-columns** (left col rows 0..h, then right col) — my paired-16 render was close but the exact stride/row-count/interleave for kanji cells isn't locked yet. The `0x10edc` u16 table (6290 entries, non-monotonic, many +18 and +0x1200/4608 diffs) indexes glyph data — decode it to get per-glyph offsets + the glyph-index→text-code map.
- REMAINING to finish font route: (1) lock kanji cell = confirm width16/height & the two-column layout + stride (est. 30-60 min, systematic); (2) decode 0x10edc index to map glyph#→0x88xx code; (3) read ~500 kanji (fast, validate vs the 200 already solved). Reusable LZSS decompressor (`tools_wa2/wa2_lzss.py`) + confirmed 1bpp/MSB/row-major packing are the spike wins.

### FONT ROUTE — DISPROVEN as a bulk-solve path (RE agent, this session). See `tools_wa2/font_re_notes.md`.
The premise "SY0.BIN is the kanji font" is WRONG. Hard findings:
- LZSS decompressor confirmed by disassembly at RAM 0x8009a010; its setup reads width×height (`lh 4($s0)`,`lh 6($s0)`) → it decompresses **rectangular IMAGES, not a glyph table**.
- **SY0 sec4 = character PORTRAITS** (rendered 256px-wide 4bpp, faces visible in `font_work/rez_sec4_w256_lo.png`); secs1–4 entropy 5.4–6.4 = image data. SY0 is a graphics/portrait bank, NOT the kanji font.
- Fixed-stride rendering is noise at EVERY tested layout (1/2/4bpp × strides 16/18/24/32 × both bit orders × row/col-major). Anchor template-match (一大人生目) fails except trivial 一.
- The 0x10edc "index table" +0x12 pattern does NOT yield a flat glyph array (only 310/6289 clean steps; banked with 0x1200 jumps + resets) — addressing uncracked.
- **NEW lead: CH0.BIN** (/SYS/CH0.BIN, 1.2MB, same header+LZSS). Secs0–7 are 96–98.5% zeros (bitmap-font signature); **sec8 = 191969 B ≈ 7998×24 ≈ full JIS X 0208 count** = best remaining font candidate — but it too rendered as noise at all static layouts. Extracted to `font_work/CH0_jp.bin`.
- Draw routine uses a RUNTIME-loaded font pointer (no static immediate to grep), so the exact file/section/index-math is **NOT recoverable from static bytes**.
- **ONLY viable font-route next step: emulator trace** (pcsx-redux/no$psx) — breakpoint the VRAM glyph upload, send code 0x88eb (一) through the message box, read the live source address + stride. Until then, kanji stay on the CONTEXT-GRIND path (scene-by-scene).
- Tools written: `tools_wa2/wa2_font_extract.py`, `wa2_layout_search.py`, `wa2_anchor_solve.py`, `wa2_render_4bpp.py`, `wa2_render_overview.py`, `wa2_extract_sector.py`.

- ⚠️ AUDIT LESSON: single-context guesses can be WRONG. Found a 8807/8893 swap (8807=事 not 切; 8893=切 not 事), caught because 無事(buji) decoded as 無切. ALWAYS verify a kanji reading holds across 2-3 DIFFERENT words before trusting; okurigana + a second compound is the check. Suspect any remaining odd decodes (e.g. 国人 should be 国民 → 8858 may be mis-set) and re-audit.
- Kanji codes are NOT in SJIS order (verified) — game's own font-glyph order. No linear extrapolation; each solved individually.
- Remaining (task #9): push to 95%. ~580 distinct codes still unsolved but LONG-TAIL (low freq each). Frequency-weighted: solving top ~150-200 codes → 95%+. Method: read `jp_script/disc1_STGEVT_decoded.txt` context + okurigana; verify with DUAL context before committing (several early guesses were wrong — always check 2+ occurrences); cross-check `english_script/disc1/STG_STGEVT.BIN.txt` for scene meaning.
- SOLVING TIPS: (1) solve isolated-position codes first (kana both sides); okurigana (き/って/う/た) reveals verb stems. (2) MANY remaining top codes are DUPLICATES of already-solved kanji (game reuses a kanji across multiple glyph slots) — if a code's context matches an existing kanji, it may just be a second slot; only add if confident. (3) compounds with 2+ adjacent unknowns are hardest — skip until neighbors solved.
- Known-hard/ambiguous codes deferred: 8853, 8910, 8a2e, 8838, 896d, 8a4c, 88ac, 88d3, 8a3d, 887a, 894a, 8a71/8a72(世界征服?), 898c(『鍵』?).

## EN/JP SCENE COMPARISON — built (`WA2_EN_JP_COMPARISON.txt`)
- 7,736 aligned EN↔JP message pairs, side-by-side. Built by enumerating 100C messages in BOTH bins and a **greedy text-presence aligner**: walk both, pair when both have real text, advance the side that has a control-only/empty message. Handles the count mismatch (US 8516 vs JP 8633 = local JP insertions, NOT a global scramble — alignment is exact through ~#47 then re-syncs).
- Reliability: strong for the bulk of the script; **mild drift accumulates in the deep tail** and around dense system-message clusters (can be off by 1-3). For precise work, confirm a scene by content, not by trusting the pair index blindly.
- Rebuild: `tools_wa2/` + the greedy aligner (charID/text-presence). JP col uses the 203-kanji decoder so unsolved kanji show as `<hex>`.
- VALUE: immediately surfaces localization divergences — e.g. the JP 『英雄』=『生け贄』 speech (hero-as-sacrifice, the game's thesis) sits where EN has a generic throwaway line. This is the tool for the retranslation's line-by-line pass.

## Script sources for 1:1 EN/JP guide
- EN: dump directly from our disc (most accurate) OR GameFAQs script id 46269 (~569KB), game id 913703.
- JP: NO clean dump online. Need the JP "2nd Ignition" disc to extract, or transcribe a JP playthrough.
  JP wiki (partial story): wikiwiki.jp/wild/
- No public EN/JP parallel comparison exists — would be new.

## Cheats/RAM: gamehacking.org/game/90142

---

# SPANISH PATCH (gadesx v1.01) — acquired & analyzed

Location: spanish_patch/  (4 PPF files: CD1/CD2 x normal/region-free + Léeme.txt)
Source: gadesx OneDrive (legit fan patch). PPF3 format, apply with PPF-o-matic 3.
Target discs (match ours): CD1 SCUS-94484 515,619,552 B (CRC 4321AA8D), CD2 SCUS-94498 562,311,456 B.

## KEY LEARNINGS from the readme (what worked / what didn't)
- Two earlier tools FAILED due to **pointer problems** (game froze):
  Hexplus "Inyector" (offset-based pointers) and skybladecloud's tool. **Pointers are the hard part.**
- gadesx's winning approach: **hand hex-editing** + a custom exe-text tool by "CUE" that
  **auto-recalculates pointers** for the executable's menu/item/object text (saved manual pointer math).
- Font was edited from the original using CUE's font extract/insert tool.
- "region free" variant = standard; "normal" variant differs ONLY in SCUS_944.84 (cd1)/SCUS_944.98 (cd2) exe.
- Anti-mod: includes Kalisto FIX (so old modchips/emulators boot it).
- Images NOT translated ("not possible right now").
- Save-file caveat: US saves mostly work but stored magic names etc. display wrong / can crash.

## PPF analysis (CD1 normal) — direct teaching tool
- PPF3, 2,536,799 bytes, desc "Wild Arms 2 CD1 spanish by gadesx".
- Records = {offset(8 LE), len(1), data[len]}. Changed-offset range 0x9299C .. 0x1DEFCEE.
- 0x9299C is very close to WILDARM2.EXE's item/skill text region — CONFIRMS text lives where we found it.
- NEXT: apply PPF to a COPY of our disc, then diff clean-vs-Spanish to see EXACTLY which bytes/pointers
  gadesx changed for each string. That reverse-maps the pointer format for free.

# SPANISH AS GROUND TRUTH (tools_wa2/extract_es.py)

gadesx patched the **US** disc in place, so Spanish pairs to English by raw `(offset, sub)` key —
**19,573 / 20,652 EN boxes (94.8%) join exactly**. No DP, no `conf` flag. This is the only exact
alignment in the project (EN↔JP is ~38% within ±1).

**Glyph slots gadesx proved repointable** — he reused unused ASCII symbol slots, not a font extension:

| byte | ASCII | glyph | | byte | ASCII | glyph |
|---|---|---|---|---|---|---|
| `0x5c` | `\` | ¡ | | `0x7c` | `\|` | ó |
| `0x5e` | `^` | ¿ | | `0x7d` | `}` | í |
| `0x5f` | `_` | ñ | | `0x7e` | `~` | é |
| `0x7b` | `{` | ú | | `0x7f` | DEL | á |

Uppercase accents are unmapped; gadesx wrote capitals unaccented.

**Fit budget (measured, `--fit`).** Median ES/EN length ratio **0.89**, p90 **1.02** — gadesx mostly
had to *compress*, which tempers the "Spanish is longer so we have room" assumption. But 14.3% of
boxes do exceed the English length and the longest shipped ES box is **359 chars**, so the EN length
is demonstrably not the ceiling.

**What ES cannot do:** it is a daughter of the English script. It carries zero Japanese information
and can never arbitrate an EN-vs-JP divergence.

**Segmentation audit (`--audit`).** The 5.2% of EN boxes with no ES box at the same key are leads on
our own extractor: the sample is dominated by mangled `{0}`→`00 acquired.` decodes and mid-sentence
fragments (`located in the forest.`, `forward, press the up directional button`). Worst blocks:
26, 118, 14, 67, 6, 111.

Input `WA2_CD1_spanish.bin` = US disc + gadesx PPF (PPF-o-matic 3). Both it and `spanish_patch/`
are gitignored — gadesx's patch is his work, not ours.
