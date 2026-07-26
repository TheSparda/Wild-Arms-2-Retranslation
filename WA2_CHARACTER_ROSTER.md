# Wild Arms 2 — Character Roster & Voice Guide

Working document for the retranslation. Goal: agree on each character's **tone/voice** so
dialogue edits stay consistent. Names from WILDARM2.EXE name pool + script char-IDs.
Status legend: ✅ agreed · 🔶 draft (needs your sign-off) · ❓ needs JP/story confirmation.

Char-ID = the script marker byte-pair (gadesx table) that tags that character's lines in STGEVT.BIN.

---

## PARTY (main cast)

### Ashley Winchester — char-ID `0530` 🔶
- **Role:** Protagonist. Young ARMS (military) recruit who becomes the host/vessel of the demon **Knight Blazer**; his arc is fear of losing himself to that power vs. duty to protect.
- **Proposed voice:** Earnest, dutiful, sincere; a conscientious young man carrying a heavy burden. Quietly heroic, not quippy. Shows real fear/doubt about Knight Blazer — the original localization flattened this inner conflict.
- **Avoid:** flippant one-liners, over-cool "action hero" tone.
- **Open Q:** how tormented vs. steadfast? (biggest single tone decision in the game)

### Lilka Eleniak — char-ID `0532` 🔶
- **Role:** Novice sorceress, eager but clumsy; comic-relief-adjacent but sympathetic.
- **Proposed voice:** Bright, enthusiastic, a little insecure about her competence; warm and youthful. Keep her self-referential quirks (the "big sister"/3rd-person bits the original botched).
- **Avoid:** dumb/ditzy flanderization — she's earnest, not stupid.

### Brad Evans — char-ID `0531` 🔶
- **Role:** Ex-soldier war hero turned fugitive; stoic veteran.
- **Proposed voice:** Terse, gruff, weary but deeply principled. Few words with weight. (His prologue was the best-translated — keep that grounded soldier's cadence.)
- **Avoid:** chattiness, sentimentality on the surface.

### Kanon — char-ID `0534` 🔶
- **Role:** Cyborg bounty hunter driven by vengeance; cool loner.
- **Proposed voice:** Cold, clipped, guarded; hardened with buried humanity that thaws slowly.
- **Open Q:** name — "Kanon" vs "Canon" (JP カノン); confirm against JP.

### Tim Rhymeless — char-ID `0533` 🔶
- **Role:** Young boy, Guardian medium.
- **Proposed voice:** Gentle, precocious, kind; a touch of melancholy/maturity beyond his years. Innocent but not baby-talk.

### Marivel Armitage — char-ID `0535` 🔶
- **JP name:** マリアベル (Mari**a**bel) — note the extra あ; canonical JP is *Mariabel*, localized "Marivel".
- **Role:** Ancient vampire noble; playful genius, joins later.
- **Proposed voice:** Archaic, theatrical, teasing; aristocratic flourish + centuries of dry, condescending wit. The most distinctly "voiced" character — leans formal/old-fashioned. **JP confirms:** she uses the archaic first-person **わらわ (warawa)** and sentence-ender **〜じゃ** — classic haughty-noble register. Preserve this with elevated/archaic English, not modern slang.
- **Avoid:** modern slang.

### Kanon / Aisha — char-ID `0534` 🔶
- **JP name:** カノン (Kanon); her original self is アイシャ・ベルデナット (Aisha Belldenat).
- **JP note:** uses rough first-person **あたし (atashi)** — tough, streetwise register. Her climactic reconciliation scene (Aisha↔Kanon dialogue about wanting "仲間" not "英雄") is fully transcribed in `jp_quotes/toybox_meigenshu.txt` — a key voice/tone anchor.

---

## SUPPORT / STORY (from exe name pool — tones draft, confirm with scenes)

| Name | Likely role | Draft tone | Status |
|---|---|---|---|
| Irving Vold Valeria | ARMS commander / party handler | Composed, authoritative, measured strategist | 🔶 |
| Anastasia | Princess / key figure | Regal, earnest | ❓ |
| Altaecia | Support NPC | TBD | ❓ |
| Marina | Support NPC | TBD | ❓ |
| Colette | Support NPC | TBD | ❓ |
| Billy / Tony / Scott | Kids / townsfolk | Casual, youthful | ❓ |
| Rassyu | Ally/NPC (romanization rough) | TBD | ❓ |
| Amy / Kate / Erwin / Terry | NPCs | TBD | ❓ |
| Pooka | Mascot/creature | Cute/simple | ❓ |
| Lucie | NPC | TBD | ❓ |

---

## VILLAINS ❓ (not in disc-1 exe name block — TO IDENTIFY)
- **Odessa** — the antagonist organization/terrorist group. Secretly created + funded by Irving (see localization note below).
- **アンテノーラ (Antenora)** — confirmed villain; JP quote page has a defiant line ("魔界柱を守るのではない…わたしが守るのはこの胸の想い"). Tragic/idealistic register.
- **カイーナ (Caina)** — one of コキュートス (Cocytus, Odessa's elite four; named for Dante's frozen hell-circles). Devoted to Vinsfeld (JP #6649: 「私が愛するヴィンスフェルト方」). ⚠️ **GENDER LOCALIZATION SHIFT:** in JP, Caina's confirmed lines use **masculine/neutral register** — first-person 私, 「お前」, blunt enders 「〜のだ／〜してやる／〜のさ」, and ZERO feminine markers (no わ/のよ/もの/かしら). The EN recast the character as clearly **feminine** ("object of my affection," coy deference). Devotion to Vinsfeld (愛する) is in both; only the gendered voice differs. Wields Guardian "ランドルフ / Randolph the Magic Key"; performs the demon-summoning. Firmly: JP has none of EN's feminine markers; whether JP intends male vs androgynous is unprovable from text alone.

## ⚠️ LOCALIZATION FINDING — Irving / Odessa "hidden backer" is MORE explicit in EN than JP (verified from primary text)
The EN foregrounds Irving-as-Odessa's-secret-backer at two points where the JP withholds it:
1. **Funding-file examine** — EN: *"Vold Valeria... Why is his name here?"* (prints the name). JP #7567-7569: 「何でこんなところに**この名前**があるんだ」 = "why is **this name** here?" — **name NOT printed**.
2. **Odessa council, after Vinsfeld's "leave the financing to me"** — EN: Caina: *"Is it |That Man| again?"* JP #5935→: **no such line** — flows straight into the tactical report. No あの方/That-Man reference.
CONTEXT (per online research): Irving genuinely IS Odessa's secret founder/funder (created both Odessa + ARMS to manufacture a unifying threat), and fans consider the early tip-off INTENDED dramatic irony — NOT a documented dub error. So this is a NOVEL finding: the EN *sharpens* the reveal (names him, adds the "That Man" emphasis) where the JP keeps a "whose name?!" mystery beat. Retranslation call: restore the JP's withheld-name suspense. This divergence is not documented anywhere online (verified).
- **ヴィンスフェルト・ラダマンティス (Vinsfeld Rhadamanthus)** — Brad's nemesis, named in Brad's JP speeches.
- Cocytus / the main villains — tone (menacing vs. tragic) is a major decision.
- ACTION: locate villain names in disc-2 files / other data; pull their JP lines.

## COMIC DUO
- **トカ & ゲー (Toka & Gě)** — recurring comic-relief mini-bosses (the "Tokage"/lizard pair). Deliberately absurd, over-the-top; JP puns hard (e.g. "ファルガイアの重力に魂引かれた" = Gundam parody). Tone: farcical, keep the parody energy. Transcribed scenes in `jp_quotes/tekeremu_goroku_*.txt`.
- **トニー & スコット (Tony & Scott)** — deadpan comedic pair; JP uses baseball-strike-zone metaphors as a running bit. Keep the odd, formal-but-absurd cadence.

---

## GLOBAL TERMINOLOGY GLOSSARY (lock before editing — inconsistency was a top failure)
| Term | Decision | Notes |
|---|---|---|
| ARM vs Gun | ❓ TBD | Weapons are "ARMs"; original mixes "ARM"/"gun". |
| Force / "Fever!" | ❓ TBD | The Force-gauge system naming. |
| Drifters | 🔶 keep | 渡り鳥 "migratory birds"; AVOID "expedition/team" (implies formal unit). |
| Knight Blazer | ✅ keep | Ashley's transformation. |
| Guardians / Mediums | ❓ TBD | summon system. |
| Village Elder vs Mayor | ❓ pick ONE | original used both for same person. |
| Place: T'Bok vs Sebok | ❓ pick ONE | name drift in original. |

---

## NEXT (once 3-way extractor finishes)
- Pull each party member's actual JP lines via their char-ID → tune voice profiles against real dialogue.
- Identify villains + their tone.
- Fill the terminology glossary from JP + Wild Arms wiki.
