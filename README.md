# Wild Arms 2 — Retranslation & Translation Toolkit

### ▶ **[Open the Translation Editor](https://thesparda.github.io/Wild-Arms-2-Retranslation/)**

Runs entirely in your browser — load your own discs, nothing is uploaded. No game data is
included or served; you bring your own `.bin` images.


Tooling and research for a retranslation of Wild Arms 2 (PS1), patched onto the **US** release
using the **JP** script as source and the **gadesx Spanish fan translation** as ground truth for
what a shipped, hardware-proven patch of the US disc looks like.

## Layout

| dir | what |
|---|---|
| `web/` | **The translation editor** — serverless website (like the Suikoden III editor). Load your EN/JP discs + the Spanish PPF; edit boxes; export in-place patch / PPF3 / xdelta. |
| `tools/` | Python pipeline: box extraction (`extract_boxes.py`), Spanish ground truth (`extract_es.py`), JP decoding (`wa2_jp_decode.py` + kanji map), alignment, insertion, wiki build. Run from repo root. |
| `data/` | Derived, machine-readable: `script/` (boxes.json, es_boxes.json, wa2_db.json), filetables, string map, EN↔JP alignment. Regenerable from discs. |
| `translation/` | Human working area: `blocks/` (per-block worksheets), `insert/` (insertion workspace), `drafts/`, `dumps_en/` + `dumps_jp/` (raw script dumps), `jp_quotes/`, `showcase/`. |
| `docs/` | Research notes (`WA2_*.md`): encoding, scene structure, insertion model, style guide, character roster… |
| `font_work/` | Font extraction artifacts + `block_tables.json` (per-block kanji tables). |
| `wiki/` | Generated script-comparison wiki (`tools/build_wiki.py` → `wiki/index.html`). Local artifact; not published. |

## Not in the repo (gitignored, kept locally)

`Game Files/` (disc images), `WA2_CD1_spanish.bin` (US disc + gadesx PPF), `spanish_patch/`
(gadesx's PPF files — his work, not ours), `WILDARM2.EXE`, `*.BIN`.

## The three-disc model

- **EN (US disc)** — the patch target. Box/chunk byte layout is authoritative.
- **JP disc** — the retranslation source. Custom encoding (see `docs/WA2_KANJI_ENCODING.md`).
- **ES (gadesx)** — ground truth: patched the US disc in place, so it pairs to EN by raw
  (offset, sub) key — 94.8% exact. It proves the insertion model: **chunk byte-length is
  preserved; shorter text is padded with 0x20 spaces before the NUL.**
