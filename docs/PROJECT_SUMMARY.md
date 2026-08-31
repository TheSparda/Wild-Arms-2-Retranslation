# Wild Arms 2 — Retranslation & Translation Toolkit

### ▶ **[Open the editor](https://thesparda.github.io/Wild-Arms-2-Retranslation/)**

Runs entirely in your browser. You load your own disc images, nothing is uploaded, and no
game data ships with the project.

---

## What this is

Two goals, in order.

**1. A tool to edit the English ISO.** A serverless web editor for the Wild Arms 2 (PS1) US
release. Drop in your `.bin` disc images and you get every text box in the game, editable,
with a live preview in the game's own textbox styling and an export back out as a patch.
That part is the point. Even if the retranslation never finishes, the editor stands on its
own for anyone who wants to change the script — a fix pass, a joke hack, a different
localization philosophy, whatever.

**2. Ship a retranslation, drafted by AI, sourced from the Japanese script.** The US
localization is famously loose. The Japanese disc is the source of truth, and the tooling
here pairs JP boxes to their English counterparts so a retranslated line can be written
against what the original actually said instead of against a paraphrase of a paraphrase.

A third thing quietly holds the whole thing up: **gadesx's Spanish fan translation**. It
patched the US disc in place, so it's a shipped, hardware-proven example of what a working
patch of this game looks like. It's the ground truth the insertion model was reverse
engineered from — chunk byte-length is preserved, shorter text is space-padded before the
NUL — and it's a reference column in the editor.

## The editor, concretely

- **Five disc slots** — US disc 1 and 2 (the patch targets), JP disc 1 and 2 (optional; adds
  the Japanese source column), and gadesx's Spanish PPF applied in memory as a reference.
  Loading a second disc of the same language cross-checks it against the first and warns, with
  the byte offset, if they differ. Chromium remembers your discs between sessions.
- **Side-by-side JP · EN · ES** columns next to a live in-game window preview of your line.
- **Two independent budgets, shown live.** The chunk's byte capacity on disc, and the 3 × 35
  on-screen ceiling. They're not the same limit and passing one doesn't mean passing the other:
  the script carries explicit line breaks and the game does *not* auto-wrap, so text can fit
  the chunk perfectly and still run off the visible window. Overflow is highlighted exactly
  where it happens.
- **House style linted as you type**, from the project's own style guide — no em dashes, no
  box ending on a dangling conjunction, balanced emphasis markers, glossary decisions enforced.
- **Name codes measured at their expanded width**, so `{0}, wait!` is counted as the 13 columns
  "Ashley, wait!" really occupies.
- **Offline workflow** — export the whole corpus as a strings JSON (20,652 rows), translate it
  anywhere (spreadsheet, script, an LLM), import it back. Import *validates rather than trusts*:
  every row carries a digest of its English source, and a row whose source no longer matches is
  refused. A JSON built against a different disc can't quietly write good-looking text into the
  wrong boxes.
- **Export** as PPF3, xdelta (VCDIFF), an in-place write, or a streamed patched copy — one patch
  per loaded disc, with Mode 2 Form 1 EDC/ECC recomputed on every modified sector.
- **Characters tab** — voice profiles for 54 characters plus 29 role buckets, with the Japanese
  and the English measured *independently*, so where they disagree you can see the localization
  changing the character. That divergence is the argument for the retranslation, made with
  numbers rather than vibes.

Everything above is checked by a test suite that runs against real discs: the EDC/ECC recompute
is byte-identical to the US disc, the English plus gadesx's PPF reproduces his patched disc
byte-for-byte, and chunk parse → rebuild is the identity function on every chunk of a block.

## Where the translation actually stands

Measured, not estimated:

| | |
|---|---|
| editable boxes | 17,294 |
| translated | 6,012 (34.8%) |
| untranslated | 11,282 (65.2%) |
| …with a usable JP source via the alignment | 8,494 |
| …of which exact 1:1 pairings, workable today | 1,426 |
| …no JP mapped at all | 2,788 |

By story section: 40 sections, of which 6 are done, 4 partial, 11 have a first pass, and 19 are
still placeholders. 97.3% of the existing translated text already fits without needing a
pointer-relocating pass.

The honest caveat: the DP aligner that pairs Japanese to English is only ~38% accurate within
±1 box on its own, so most pairings are marked `approx` — verify before trusting. A separate
anchored alignment, hold-out tested at 78.5% exact / 94.3% within ±1, is what actual translation
work is done against. 550 pairs are corroborated against a hand-verified glossary, and 78 are
flagged as probable conflicts with a suggested correction.

The first real translation batch went in recently: 49 boxes in the Tunnel to Sielje / magic
school area. It was deliberately narrow — of 157 candidate boxes there, only 49 had Japanese
with *no* unresolved kanji. The other 108 have placeholders sitting in load-bearing nouns, and
guessing at those produces confident nonsense. Those wait for more decoder work.

That's the standing rule for the AI-drafted side, and it's the one I care most about: **a line
gets written only where the source is trustworthy.** Fluent, plausible, wrong is the worst
possible output for a project like this, and it's exactly what an LLM will hand you if you let
it translate against a bad pairing.

## Also in the repo

- A Python pipeline for box extraction, JP decoding (the game uses a custom encoding with
  per-block kanji tables, documented in `docs/WA2_KANJI_ENCODING.md`), alignment, and insertion.
- Research notes on encoding, scene structure, the insertion model, chapter and scene maps, a
  name dictionary, a style guide, and a divergence audit.
- Raw script dumps in both languages, JP exported by area for reading.
- Font extraction work and per-block kanji tables.

## Status

I'm working on this slowly, in the gaps. It is not finished and it is not on a schedule.

All the code is open source. If you want to poke at it, fork it, fix the aligner, grind the
kanji tables, translate an area, or just load your own disc and rewrite one line to see it
render — please do. Nothing here needs my permission.

**Source: <https://github.com/TheSparda/Wild-Arms-2-Retranslation>**
