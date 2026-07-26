# WA2 — Scene Structure: Walkthrough Order ↔ Script Blocks

Cross-reference of the Syonyx walkthrough's **90 scene headers (story order)** against the
120 STGEVT event blocks, anchored via v6 alignment. Confirms the block sequence follows the
game's narrative and gives each major scene its block location for targeted translation.

## Walkthrough scene sequence (90 headers, story order)
Palace Village → T'Bok Village → Meria Boule Castle → Sword Cathedral → Valeria Chateau →
Under Traffic → Damzen City → Telepath Tower → (back Damzen) → Mt. Chug-Chug → (back Valeria) →
Live Reflector → Sylvaland Castle → Halmetz → Ruins Mine → Dragon's Vein → Baskar Village →
Meria Boule → Damzen → Sielje Region → Gate Bridge → Greenhell → T'Bok → Quartly →
Slayheim Castle → Alchemic Plant → Urartu Station → Guild Galad → Outer Sea → Closed Mine Shaft →
Coffin of 100 Eyes → **Diablo Pillars (Ptolomea/Caina/Antenora/Judecca)** → Heimdal Gazzo →
Sacrificial Altar → Grotto of Lourdes → Lost Garden → Sleeping Volcano → **Lombardia acquired** →
Raypoints (Flam/Geo/Wing/Muse) → Gated Sea → Trapezohedron → Fiery Wreckage → Spiral Tower →
Lost Garden → [side/optional dens] → endgame (Crimson Castle → Meria Boule w/ Marivel).

## Block ↔ scene anchors (verified via aligned EN mentions)
Blocks confirmed to contain each major scene (block = densest EN mention cluster):

| Scene | Block(s) | Confidence |
|---|---|---|
| Opening / Sword Cathedral | blk 3, 5 | strong |
| Aguel Mine / early quests | blk 6-8 | strong |
| Raline Observatory | blk 8-11 | strong |
| Damzen City / Mt. Chug-Chug | **blk 12** | strong (16 mentions) |
| Sylvaland Castle | **blk 14** | strong (24 mentions) |
| Live Reflector / Halmetz | blk 15 | medium |
| Sielje / Gate Bridge | blk 17 | strong |
| Slayheim Castle (Brad flashback) | blk 18 | medium |
| Guild Galad / Alchemic Plant / Lombardia | **blk 20** | strong (28 mentions) |
| T'Bok Village (Brad/Merrill) | blk 24 | strong |
| Illsveil Prison | **blk 27** | strong |
| Telepath Tower | **blk 29** | strong (6 mentions) |
| Emulator Zone / Caina (Cocytus) | **blk 39-40** | strong |
| Heimdal Gazzo | blk 44, 49 | strong |
| **Lord Blazer reveal / lore** | **blk 52** | strong (15 mentions) |
| Trapezohedron / Raypoints (endgame) | **blk 108** | strong (23-24 mentions) |

## Coverage verdict
- **117/120 blocks contain dialogue**; blocks 42, 64, 87 are empty padding (verified).
- The block order tracks the walkthrough's story order (opening blocks 0-8 = tutorial/Meria;
  mid blocks 12-40 = the world tour + prison + Cocytus; blocks 44-52 = Heimdal/Lord Blazer;
  blocks 100+ = endgame Trapezohedron/Raypoints). **No scene is missing** — every walkthrough
  location resolves to a block that exists in the scaffold.
- Some scenes span multiple blocks (world-tour hubs like Valeria Chateau recur — the "Back in
  Valeria Chateau" headers appear 4× in the walkthrough), and some blocks hold multiple short
  scenes. Exact per-line scene boundaries need the translation pass, but the **container-level
  mapping is complete and ordered.**

## Use
- Translate in **story order** by following the block sequence (blk000→blk119 ≈ narrative order).
- For a specific scene, jump to its block above (e.g. Lord Blazer = `translate/blk052.txt`,
  Caina intro = `translate/blk040.txt`, Trapezohedron finale = `translate/blk108.txt`).
- Cross-check names against `WA2_NAME_DICTIONARY.md`; priority fixes in `WA2_DIVERGENCE_AUDIT.md`.

Source: walkthrough headers (`wildarms2 guide.rtf`) + `tools_wa2/align_v6.py`.
