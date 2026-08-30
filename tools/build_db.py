#!/usr/bin/env python3
"""
MASTER DATABASE builder — the single source of truth for the WA2 retranslation.

One row per US# slot (the `10 0c` message index in STGEVT). Every other tool (wiki, coverage,
gap-check, and eventually the inserter) should GENERATE from data/script/wa2_db.json instead of
re-deriving from scattered per-file maps. This kills the mapping-drift bug class.

Each row:
  us         int    US# slot index (0..N-1), the universal key
  block      int    STGEVT block = byte_offset // UBLK
  en         str    in-game English (localization) with {n} name-codes preserved  [from STGEVT]
  jp         str    block-decoded Japanese (residual <codes> possible)             [from JP disc]
  jp_clean   bool   True if jp has no unsolved <...> codes and contains kana/kanji
  is_examine bool   JP starts with the ＊/* examine marker (readable panel, no speaker)
  lit        str    literal translation           (migrated from insert file, "" if none)
  re         str    final retranslation, " / "-joined lines (migrated, "" if none)
  speaker    str    parsed speaker label          (migrated, "" if none)
  tier       int    1=story spine / 2=ambient-fit / 0=untriaged  (set by tier step later)
  status     str    deep | firstpass | placeholder
  src_file   str    insert file this row's translation came from ("" if none)
  area       str    guide-area code (from src_file mapping, "" if untranslated)

Usage:
  python3 tools/build_db.py             # rebuild data/script/wa2_db.json
  python3 tools/build_db.py --stats     # rebuild + print summary
"""
import os, re, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wa2_jp_decode as W

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INS  = os.path.join(ROOT, 'translation/insert')
OUT  = os.path.join(ROOT, 'data/script', 'wa2_db.json')

US_BIN = 'Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin'
US_LBA, US_SIZE, UBLK = 12586, 10813440, 90112

CJK = re.compile(r'[぀-ヿ㐀-鿿]')

# =========================================================================================
# SINGLE SOURCE OF TRUTH for ALL shared config. build_wiki / coverage_report / script_gap
# import these from here (no private copies) — that is what eliminates the mapping-drift bug
# class (the Kanon-1.15 and blk23 mis-maps). Edit a mapping ONCE, here.
# =========================================================================================

# ---- guide spine: authoritative area list (Syonyx GameFAQs walkthrough), in play order ----
GUIDE_AREAS = {
 1: [('WR','Withered Ruins'),('MP','Millennium Puzzle'),('BI',"Brad's Intro"),
     ('MR','Town of Meria'),('SC','Sword Cathedral'),('VC','Valeria Chateau'),
     ('IP','Illsveil Prison'),('UT','Under Traffic'),('DZ','Damzen City'),
     ('TT','Telepath Tower'),('CC','Mt. Chug-Chug'),('LR','Live Reflector'),
     ('GP','Golgotha Prison'),('SD','Sylvaland Castle'),('HM','Halmetz'),('HL','Holst'),
     ('AM','Aguel Mine Shaft'),('RO','Raline Observatory'),('BV','Baskar Village'),
     ('HT','Hidden Trial Arena'),('WV','Warwing Varukisas'),('TS','Tunnel to Sielje Region'),
     ('SR','Sielje Region'),('GB','Gate Bridge'),('GH','Greenhell'),('TB',"T'Bok Village"),
     ('QT','Quartly'),('SY','Slayheim Castle'),('AP','Alchemic Plant'),('EZ','Emulator Zone'),
     ('GG','Guild Galad'),('CM','Closed Mine Shaft'),('CE','Coffin of 100 Eyes'),
     ('DP','Diablo Pillar Ptolomea'),('DC','Diablo Pillar Caina'),('DA','Diablo Pillar Antenora'),
     ('LC','Lost City Archeim'),('DJ','Diablo Pillar Judecca'),('HG','Heimdal Gazzo')],
 2: [('MM','Memory Maze'),('MZ','Millennium Puzzle (2)'),('SA','Sacrificial Altar'),
     ('GL','Grotto of Lourdes'),('LG','Lost Garden'),('SV','Sleeping Volcano'),
     ('PV','Palace Village'),('RF','Raypoint Flam'),('RG','Raypoint Geo'),('RW','Raypoint Wing'),
     ('RM','Raypoint Muse'),('TZ','Trapezohedron'),('FW','Fiery Wreckage'),('ST','Spiral Tower'),
     ('GGa','Glaive Le Gable')],
 3: [('OD','Odd Headquarters'),('WT',"Wind Tiger's Den"),('TL','Thunder Lion Cage'),
     ('IO','Island Outpost'),('DR','Dark Reason'),('AI','Abandoned Icebox'),
     ('SG','Shining Garden'),('MC','Meteorite Crater'),('WD',"Werewolf's Den"),
     ('CS','Crimson Castle'),('PC','Promised Catacombs'),('GLo','The Guardian Lords'),
     ('GZ','Good Luck Zone'),('FL','Fab Science Lab'),('PW',"Pirate's Warren"),
     ('MA','Monster Album'),('SM','Sealed Monsters')],
}
DISC_LABEL = {1: 'DISC 1', 2: 'DISC 2', 3: 'OPTIONAL AREAS'}

# ---- scene registry: deep FINAL file -> (area, subtitle, block). Order within area = list order. ----
SCENES = [
 ('ashley_opening_FINAL.txt','WR',"Withered Ruins prologue → rail-gun standoff",'70'),
 ('ashley_intro_ruins_FINAL.txt','WR',"Inside the ruins: Musketeer push + the kidnapper gang",'23'),
 ('wr_ambient_gang_FINAL.txt','WR',"Withered Ruins inline/ambient: musketeers, medic, kidnapper gang",'23'),
 ('lilka_intro_FINAL.txt','MP',"Magic Lesson with her sister",'25'),
 ('brad_intro_FINAL.txt','BI',"Fugitive in the Rain",'24'),
 ('m1_meria_FINAL.txt','MR','Ceremony morning','3'),
 ('m1_meria_npc_FINAL.txt','MR','Town NPCs & ambient (bakery, kids, inn, tutorials, Ashley/Marina argument)','3'),
 ('m1_swordcathedral_lore_FINAL.txt','SC',"Argetlahm / Sword Magess legend (readable panels)",'5'),
 ('m1_swordcathedral_FINAL.txt','VC',"King of Meria Boule — recurring throne-room audience (spans whole game)",'5'),
 ('m1_library_history_FINAL.txt','VC',"Library history books — the war-criminal hero + 3 nations",'5'),
 ('m1_crimson_noble_FINAL.txt','VC',"Crimson Noble lore panel (Isabel Graceland / Marivel's clan)",'5'),
 ('m1_chateau_hub_FINAL.txt','VC',"Ambient hub chatter (132 recurring NPC/King lines — light-touch fit pass)",'5'),
 ('m_summit_tablets_briefing_FINAL.txt','WV',"Filgaia Summit + Data Tablets briefing (launches the mid-game)",'5'),
 ('m_summit_debate_FINAL.txt','WV',"The 71st Summit conference debate (cross-border rights / Treaty of Iscariot)",'63'),
 ('m2_telepathtower_FINAL.txt','TT','Odessa hijack','29'),
 ('m2_telepath_lore_FINAL.txt','TT','Empathite lore scrolls','29'),
 ('m3_livereflector_FINAL.txt','LR','Startup (intro)','31'),
 ('m3_livereflector_cont_FINAL.txt','LR','Medium awakening','31'),
 ('m4_halmetz_FINAL.txt','HM','The Odessa trap','32'),
 ('m_slayheim_backstory_FINAL.txt','SY',"Liberation Army backstory — Vinsfeld's betrayal + the true hero",'18'),
 ('m_caina_taunt_FINAL.txt','LG',"Caina's taunt + hollow victory (Odessa broadcast / Frozen Lake)",'53'),
 ('m_raline_lizard_FINAL.txt','RO',"Liz & Ard rescue + the Germatron / Odessa reveal (comic scene)",'38'),
 # ---- Disc 2 endgame spine (STGEVT is one whole-game file, byte-identical on both discs) ----
 ('m_swordmagess_truth_FINAL.txt','GGa',"The Sword Magess Anastasia's truth: desire, Lucied, Lord Blazer",'92'),
 ('m_vinsfeld_farewell_FINAL.txt','GGa',"Vinsfeld's farewell blow (|Heroes| don't die) boss taunt",'91'),
 ('m_lordblazer_credo_FINAL.txt','GGa',"Lord Blazer's mockery + the party's 'we don't need a hero' credo",'113'),
 ('m_final_heroes_prayer_FINAL.txt','GGa',"Before the Final Battle: the |heroes| prayer (come back safely)",'111'),
 ('m_anastasia_meeting_FINAL.txt','GGa',"Ashley meets the Sword Magess Anastasia between life and death",'116'),
 ('m_kanon_pillar_FINAL.txt','GGa',"Kanon / Vinsfeld's hero philosophy / Marina refuses the Pillar",'117'),
 ('m_summit_maneuver_FINAL.txt','GGa',"The Live Reflector maneuver to seize the Kuiper Belt (broadcast)",'108'),
 ('m_demon_summoning_FINAL.txt','GGa',"The Demon Summoning reveal + the party's resolve (Kuiper Belt)",'112'),
 ('m_swordmagess_memory_FINAL.txt','GGa',"Sword Magess memory: power/sacrifice; Lord Blazer sealed, Marivel's pledge",'62'),
 ('m_guardian_hearts_FINAL.txt','GGa',"Guardian Lords of the heart: Raftina (love), Justine (courage), Zephyr (hope)",'55'),
 ('m_trust_resolve_FINAL.txt','GGa',"Trust & resolve: doubt breaks a party; drive the demon out of Ashley",'104'),
 ('m_backstories_FINAL.txt','GGa',"Party backstories: Tim, Kanon's sky promise, Marivel's solitude, Ashley's words",'89'),
 ('m_slayheim_recruits_lore_FINAL.txt','SY',"Slayheim front-line recruits + the <Sword Magess> lore panels",'118'),
 ('m_ashley_lilka_bond_FINAL.txt','RM',"Ashley & Lilka aboard Lombardia: 'are you still you?'",'41'),
 ('m_kuiper_split_FINAL.txt','GGa',"Vinsfeld's confession + the four-way split into the Kuiper Belt",'66'),
 ('m_lucied_desire_FINAL.txt','GGa',"Lucied, Guardian of Desire, lends Ashley his power",'77'),
 ('m_vinsfeld_manifesto_FINAL.txt','SY',"Vinsfeld's Odessa manifesto broadcast",'88'),
 ('m_pillar_trial_FINAL.txt','SA',"Sacrificial Altar trial: Marina + Pooka, the |Combine|, the |Pillar|",'34'),
 ('m_guildgalad_magic_FINAL.txt','GG',"Guild Galad Crest Sorcery: |Extend| + High Magic sidequest",'67'),
 # ---- previously-unmapped Disc-1 areas, now located + translated ----
 ('m_aguel_mine_FINAL.txt','AM',"Aguel Mine Shaft: Aguelite/Germatron crystal lore",'33'),
 ('m_closed_mine_FINAL.txt','CM',"Closed Mine Shaft: Kanon confrontation (Sword Magess blood / the Demon)",'43'),
 ('m_tbok_village_FINAL.txt','TB',"T'Bok Village: Brad wakes; Merrill + the dog; the Vinsfeld/Slayheim reveal",'2'),
 # ---- Disc-2 story spine (anchored + translated) ----
 ('m_memory_maze_FINAL.txt','MM',"Memory Maze: Kanon's memory trial + the Argetlahm/Lord Blazer lore",'52'),
 ('m_millennium_puzzle2_FINAL.txt','MZ',"Millennium Puzzle (2): tuning the Switchblocks to reach the other world",'50'),
 ('m_lombardia_FINAL.txt','PV',"Palace Village / Lombardia: the Dragon-Dimension refugees + the Wing's test",'54'),
 ('m_gaia_altar_FINAL.txt','GL',"Grotto of Lourdes / Gaia: the Other World, the |Pillar|, Marina's refusal",'51'),
 ('m_raypoint_lilka_FINAL.txt','RF',"Raypoint trial (Lilka): magic belongs to anyone",'56'),
 ('m_raypoint_brad_FINAL.txt','RG',"Raypoint trial (Brad): expose the truth",'57'),
 ('m_raypoint_pooka_FINAL.txt','SV',"Raypoint trial (Pooka): reveal your reason to fight",'58'),
 ('m_raypoint_kanon_FINAL.txt','RW',"Raypoint trial (Kanon): shed your confusion; a hero isn't blood",'59'),
 ('m_crimson_sanctuary_FINAL.txt','SM',"Crimson Nobles' Sanctuary: Ragu/Sealed-Monster lore + Marivel's solitude",'60'),
 # ---- Track A: NPC/ambient/system sweep ----
 ('m_system_tutorials_FINAL.txt','WV',"System & vehicle tutorials (Lombardia/Hovercraft/Search System) + Sylvaland chatter",'0'),
 ('m_halmetz_npc_FINAL.txt','HM',"Halmetz NPCs post-liberation (Bell Tower, 'hero of justice' kids) + Cocytus ambush",'15'),
 ('m_palace_village_npc_FINAL.txt','PV',"Palace Village NPCs: wheat-field monster panic, sacrifice rumor, comet lore, Lilka's admirer",'1'),
 # ---- Lore-encyclopedia cluster (blocks 6-11: recurring Chateau/@-lore script; twins) ----
 ('lore_blk6_900-1010_FINAL.txt','VC',"Lore blk6 a: Altaecia/Amy/crew + Chateau boarding",'6'),
 ('lore_blk6_1121-1230_FINAL.txt','VC',"Lore blk6 c: disaster panels, Irving intro, escort briefing",'6'),
 ('lore_blk6_1231-1278_FINAL.txt','VC',"Lore blk6 d: KnightBlazer/Argetlahm/Valeria lore",'6'),
 ('lore_blk6_gaps_FINAL.txt','VC',"Lore blk6 gaps: Ley Line/Glaive Le Gable/hero-legend",'6'),
 ('lore_blk7_1280-1390_FINAL.txt','VC',"Lore blk7 a: war-council, ARMS ops, butcher banter",'7'),
 ('lore_blk7_1391-1460_FINAL.txt','VC',"Lore blk7 b: hero/bionic lore, Marivel mapscope",'7'),
 ('lore_blk7_1461-1526_FINAL.txt','VC',"Lore blk7 c: Summit / EMMA motor / Key-Pillar endgame",'7'),
 ('lore_blk8_1527-1637_FINAL.txt','VC',"Lore blk8 a: Irving/Altaecia strategy, Amy reports",'8'),
 ('lore_blk8_1638-1699_FINAL.txt','VC',"Lore blk8 b: Lombardia pilot, Palace Village, Diablo Pillar",'8'),
 ('lore_blk8_1700-1738_FINAL.txt','VC',"Lore blk8 c: Sir Valeria backstory, hero's-blood curse",'8'),
 ('lore_blk8_1739-1772_FINAL.txt','VC',"Lore blk8 d: Guardians/Blaze of Disaster, Mana/Ley Lines",'8'),
 ('lore_blk8_1773-1824_FINAL.txt','VC',"Lore blk8 e: hero-legend meditation, Marivel foreshadow",'8'),
 ('lore_blk8_1825-1885_FINAL.txt','VC',"Lore blk8 f: Heimdal tactics, Marivel makeover, panels",'8'),
 ('lore_blk8_1886-1949_FINAL.txt','VC',"Lore blk8 g: Heimdal assault briefing, Gias reveal",'8'),
 ('lore_blk9_2321-2364_FINAL.txt','VC',"Lore blk9 unique: Ashley rescue, decay debrief, LB confession",'9'),
 ('lore_blk10_2368-2478_FINAL.txt','VC',"Lore blk10 a: strategy/Chateau lines",'10'),
 ('lore_blk10_2479-2587_FINAL.txt','VC',"Lore blk10 b: hero-legend, Palace/Raypoint, summit panels",'10'),
 ('lore_blk10_2588-2620_FINAL.txt','VC',"Lore blk10 c: Grauswein/Lord Blazer confrontation",'10'),
 ('lore_blk10_2621-2655_FINAL.txt','VC',"Lore blk10 d: Ashley/Lilka 'Welcome home' farewell",'10'),
 ('lore_blk10_2656-2696_FINAL.txt','VC',"Lore blk10 e: Irving's dragon briefing (Lombardia/Kuiper)",'10'),
 ('lore_blk11_3069-3110_FINAL.txt','VC',"Lore blk11 a: Kuiper Belt council, Trapezohedron failure",'11'),
 ('lore_blk11_3112-3144_FINAL.txt','VC',"Lore blk11 b: human-Vessel reveal, Demon Summoning",'11'),
 # ---- twin-propagated boxes (auto-filled by tools/propagate_twins.py; JP+RE only) ----
 ('lore_blk6_PROPAGATED.txt','VC',"Lore blk6 propagated (twin auto-fill)",'6'),
 ('lore_blk8_PROPAGATED.txt','VC',"Lore blk8 propagated (twin auto-fill)",'8'),
 ('lore_blk9_PROPAGATED.txt','VC',"Lore blk9 propagated (twin auto-fill)",'9'),
 ('lore_blk10_PROPAGATED.txt','VC',"Lore blk10 propagated (twin auto-fill)",'10'),
 ('lore_blk11_PROPAGATED.txt','VC',"Lore blk11 propagated (twin auto-fill)",'11'),
 # ---- disc-1 completion sweep (2026-07-27): deep RE for every remaining disc-1 story block ----
 ('story_blk1_86-159_FINAL.txt','PV',"Palace Village opening: Lilka, wheat-field monster, comet lore, boss mechanics",'1'),
 ('story_blk3_294-489_FINAL.txt','MR',"Town Meria opening: ceremony, gratitude, tutorials, Ashley's awakening",'3'),
 ('story_blk4_493-600_FINAL.txt','MR',"Town Meria homecoming part 1: Marina, the kids, town warmth",'4'),
 ('story_blk4_601-702_FINAL.txt','MR',"Town Meria part 2: Ashley/Marina heart-to-heart",'4'),
 ('story_blk12_3147-3229_FINAL.txt','DZ',"Damzen City part 1: town NPCs & ambient",'12'),
 ('story_blk12_3230-3313_FINAL.txt','DZ',"Damzen City part 2: doctor, bar, miners' loyalty",'12'),
 ('story_blk12_3314-3379_FINAL.txt','DZ',"Damzen City part 3: sailor, Marivel's Hob & Nob, waitress Luca",'12'),
 ('story_blk12_3380-3444_FINAL.txt','DZ',"Damzen City part 4: legends, Ley Points, Marivel's tip",'12'),
 ('story_blk13_3446-3558_FINAL.txt','UT',"Holst mining town + Kanon's clinic scene",'13'),
 ('story_blk14_3560-3660_FINAL.txt','SD',"Sylvaland Castle part 1: knights, bell tower, Queen's court",'14'),
 ('story_blk14_3661-3759_FINAL.txt','SD',"Sylvaland part 2: nation lore panels, Queen's audience",'14'),
 ('story_blk15_3764-3850_FINAL.txt','HM',"Halmetz aftermath + the empty town + Judecca ambush",'15'),
 ('story_blk16_3854-3960_FINAL.txt','BV',"Baskar Village: the |Key| sacrifice arc, part 1",'16'),
 ('story_blk16_3961-4060_FINAL.txt','BV',"Baskar part 2: Sabrina's story, Glaive Le Gable panels",'16'),
 ('story_blk16_4061-4147_FINAL.txt','BV',"Baskar part 3: dream-seer, Tim's choice, the trial betrayal",'16'),
 ('story_blk17_4149-4250_FINAL.txt','TS',"Sielje Region part 1: magic academy, Mr. Day, sleepy students",'17'),
 ('story_blk17_4251-4350_FINAL.txt','TS',"Sielje part 2: McGregor scientist, Irving's past, tutorials",'17'),
 ('story_blk17_4351-4447_FINAL.txt','TS',"Sielje part 3: study panels, Lilka's sister, data-tablet chatter",'17'),
 ('story_blk18_4449-4592_FINAL.txt','SY',"Quartly/Slayheim: Eliza's grudge, hero-legend truth, spy rumors",'18'),
 ('story_blk19_4595-4645_FINAL.txt','SY',"Slayheim ruins: Angel Halo / Iscariot Treaty lore + Brad's memory + Kanon",'19'),
 ('story_blk20_4649-4755_FINAL.txt','GG',"Guild Galad part 1: tech-pride NPCs, Master's apology",'20'),
 ('story_blk20_4756-4860_FINAL.txt','GG',"Guild Galad part 2: Grauswein counter-plan",'20'),
 ('story_blk21_4865-4952_FINAL.txt','VC',"Crimson Noble lore scrolls + Marivel's recruitment (Map Scope)",'21'),
 ('story_blk22_4955-5014_FINAL.txt','TB',"Meria Boule subway station: Noel escort, Merc chatter, Crimson Noble lore",'22'),
 ('story_blk26_5133-5236_FINAL.txt','VC',"ARMS barracks + Argetlahm/Sword Magess lore + the sword-taking scene",'26'),
 ('story_blk27_5239-5297_FINAL.txt','IP',"Illsveil Prison + Brad's recruitment / jailbreak",'27'),
 ('story_blk28_5302-5316_FINAL.txt','UT',"Map-system tutorial + weapon lore",'28'),
 ('story_blk30_5354-5366_FINAL.txt','CM',"Dungeon puzzle: prism gem for Marina + weapon lore",'30'),
 ('story_blk32_5408-5459_FINAL.txt','HM',"Halmetz trap dungeon: captives, Judecca's public-execution plot, rescue",'32'),
 ('story_blk35_5565-5592_FINAL.txt','WV',"Varukisas raid: mission briefing + Brad vs Odessa + crash escape",'35'),
 ('story_blk36_5596-5636_FINAL.txt','GB',"Gate Bridge puzzle + Liz & Ard boss banter",'36'),
 ('story_blk37_5639-5647_FINAL.txt','CE',"Diablo Tower lore inscriptions + Lilka's ghost-banishing quip",'37'),
 ('story_blk39_5743-5853_FINAL.txt','DP',"Alchemic Plant infiltration + Odessa command + Brad's Gias sacrifice",'39'),
 ('story_blk40_5855-5913_FINAL.txt','DC',"Emulator Zone train + Caina vs Kanon showdown",'40'),
 ('story_blk44_6022-6069_FINAL.txt','HG',"Diablo Pillar / Heimdal Gazzo intel + Wire Hook + Liz & Ard rematch",'44'),
 ('story_blk45_6073-6089_FINAL.txt','LC',"Diablo Pillar approach: Tim's resolve + Antenora's last stand",'45'),
 ('story_blk46_6092-6131_FINAL.txt','LC',"Antenora boss scene: her revenge on Vinsfeld's killer",'46'),
 ('story_blk47_6139-6157_FINAL.txt','LC',"Dying rebel officer: trust, justice, and a hero's send-off",'47'),
 ('story_blk48_6163-6192_FINAL.txt','DJ',"Judecca boss scene + Kanon's hero-blood awakening",'48'),
 ('story_blk49_6206-6341_FINAL.txt','HG',"Heimdal Gazzo climax: escape pods, Vinsfeld showdown",'49'),
 ('story_blk53_6494-6530_FINAL.txt','LG',"Mental Jamming dungeon + Kanon's revenge on Ashley",'53'),
 ('story_blk61_6816-6881_FINAL.txt','GGa',"Bulkogidon / Lizardian alien comedy scene",'61'),
 ('story_blk63_6930-6968_FINAL.txt','WV',"Area 51 interception + Baskar-village decision + peers' debate",'63'),
 ('story_blk65_6974-6989_FINAL.txt','GGa',"Guardian rune-verse inscriptions + Flare/weapon lore",'65'),
 ('story_blk67_7034-7145_FINAL.txt','GG',"Extend-magic researcher NPC + magic lore panels",'67'),
 ('story_blk68_7148-7190_FINAL.txt','GG',"Monster-Card album collector + name-change + shop hub",'68'),
 ('story_blk69_7192-7208_FINAL.txt','DP',"Ptolomea's Cocytus ambush at the mountains",'69'),
 ('story_blk71_7237-7248_FINAL.txt','IP',"Post-Illsveil rendezvous: no-more-pawns + safe reunion",'71'),
 ('story_blk72_7250-7264_FINAL.txt','IP',"Ruins evacuation stand: buy time for the trapped team",'72'),
 ('story_blk74_7274-7301_FINAL.txt','WV',"Living-bomb monsters + Gull Wing air-battle briefing",'74'),
]

# ---- first-pass registry: auto-generated files (localization reflowed, US#-verified) ----
FIRSTPASS = [
 ('blk27_IP_GP.txt',['IP','GP'],'27','Illsveil / Golgotha Prison'),
 ('blk12_DZ_CC.txt',['DZ','CC'],'12','Damzen City / Mt. Chug-Chug'),
 ('blk13_UT_HL.txt',['UT'],'13','Under Traffic'),
 ('blk14_SD.txt',['SD','HL'],'14','Sylvaland Castle / Holst'),
 ('blk16_BV_HT.txt',['BV','HT'],'16','Baskar Village / Hidden Trial Arena'),
 ('blk17_TS_SR_GB_GH.txt',['TS','SR','GB','GH'],'17','Tunnel to Sielje / Sielje / Gate Bridge / Greenhell'),
 ('blk18_SY.txt',['SY','QT'],'18','Slayheim Castle / Quartly (merc recruit)'),
 ('blk20_GG_AP.txt',['GG','AP'],'20','Guild Galad / Alchemic Plant'),
 ('blk38_CE.txt',['CE'],'38','Coffin of 100 Eyes'),
 ('blk39_DP.txt',['DP','DC','DA'],'39','Diablo Pillars (Ptolomea/Caina/Antenora)'),
 ('blk40_DC.txt',['DC','EZ'],'40','Diablo Pillar Caina / Emulator Zone (Caina/Noel)'),
 ('blk44_HG.txt',['HG'],'44','Heimdal Gazzo (part)'),
 ('blk45_LC.txt',['LC'],'45','Lost City Archeim (a)'),
 ('blk46_LC.txt',['LC'],'46','Lost City Archeim (b)'),
 ('blk47_LC.txt',['LC'],'47','Lost City Archeim (c)'),
 ('blk49_HG_DP.txt',['HG','DJ','DA'],'49','Heimdal Gazzo / Diablo Pillars'),
 ('blk69_DP.txt',['DP'],'69','Diablo Pillar Ptolomea (part)'),
]

# ---- area -> STGEVT block(s), for areas ANCHORED but not yet translated (no insert file).
# These are real content gaps we've located; add an insert file + move to FIRSTPASS once done. ----
AREA_BLOCKS_EXTRA = {
 # (MM/MZ/PV/GL/RF/RG/RW/SV/SM now translated + registered in SCENES above.)
 # CONFIRMED dialogue-free (verified 2026-07-26): TZ Trapezohedron, FW Fiery Wreckage, ST Spiral
 # Tower — their names appear ONLY in shared lore blocks (6-11, 108); no dedicated scene text to
 # translate (navigation/combat dungeons). Likewise most OPTIONAL areas (OD/WT/TL/IO/DR/AI/SG/MC/
 # WD/CS/PC/GLo/GZ/FL/PW/MA) have no dedicated dialogue block. Left unmapped by design.
}

# ---- game-script section id -> guide-area codes it contains (placeholder + gap anchor) ----
SECTION_AREAS = {
 '1.01':['WR','MP','BI'],'1.02':['MR','SC'],'1.03':['VC'],'1.04':['VC'],'1.05':['IP','GP'],
 '1.06':['UT','DZ','CC'],'1.07':['TT','CC','LR'],'1.08':['SD','HL','SY'],'1.09':['AM','HM','BV','HT','WV'],
 '1.10':['BV','TB','GH','RO'],'1.11':['WV'],'1.12':['TS','SR'],'1.13':['GB'],'1.14':['GH','TB'],
 '1.15':['SY','CM'],'1.16':['AP'],'1.17':['GG','QT'],'1.18':['CM'],'1.19':['CE'],
 '1.20':['DP','DC','DA','DJ','LC'],'1.21':['HG'],
 '2.01':['MM','MZ'],'2.02':['MM'],'2.03':['SA','GL'],'2.04':['LG'],'2.05':['SV'],'2.06':['PV'],
 '2.07':['RF','RG','RW','RM'],'2.08':['TZ'],'2.09':['FW'],'2.10':['ST','GGa'],'2.11':['GGa'],'2.12':[],
 '0.1':['CS'],'0.2':['PC'],'0.3':['IO'],'0.4':['GLo'],'0.5':['WD'],'0.6':['GLo'],'0.7':['DR','FL'],
}
# extra area->section for areas the guide files under a differently-coded section
AREA_SECTION_EXTRA = {'FL':'0.7','GP':'1.05'}

# ---- derived maps (do NOT hand-edit; computed from the registries above) ----
SCENE_AREA = {f: area for f, area, _sub, _blk in SCENES}
FP_AREAS   = {f: codes for f, codes, _blk, _label in FIRSTPASS}

# ---- STGEVT: EN text + block per US# slot ----
def us_slots():
    ud = W.readfile(US_BIN, US_LBA, US_SIZE)
    offs = []; i = -1
    while True:
        i = ud.find(b'\x10\x0c', i+1)
        if i < 0: break
        offs.append(i)
    return ud, offs

def uen(ud, offs, i):
    e = offs[i+1] if i+1 < len(offs) else len(ud)
    raw = ud[offs[i]:e].split(b'\x00')[0]
    out = []; j = 0
    while j < len(raw):
        b = raw[j]
        if b == 0x0a and j+1 < len(raw) and 0x30 <= raw[j+1] <= 0x39:
            out.append('{'+chr(raw[j+1])+'}'); j += 2; continue
        if 0x20 <= b < 0x7f: out.append(chr(b))
        elif b == 0x0d: out.append(' ')
        j += 1
    return ' '.join(''.join(out).split())

# ---- JP disc: decoded text per US# slot (same-index within block) ----
def jp_by_block():
    """Return {block: [decoded_jp per in-block slot]} for all blocks."""
    jd = W.load_jp()
    out = {}
    JBLK = W.JBLK
    nblocks = len(jd)//JBLK + 1
    for blk in range(nblocks):
        seg = W.block_bytes(jd, blk)
        jm = []; i = -1
        while True:
            i = seg.find(b'\x10\x0c', i+1)
            if i < 0: break
            jm.append(i)
        texts = []
        for k in range(len(jm)):
            s = jm[k]+2; e = jm[k+1] if k+1 < len(jm) else s+400
            texts.append(' '.join(W.decode_block(seg[s:min(e,s+400)], blk).replace('\n',' / ').split()))
        out[blk] = texts
    return out

def jp_clean(t):
    b = t.strip()
    return bool(b) and '<' not in b and bool(CJK.search(b))

# ---- migrate LIT/RE/speaker from an insert file, keyed by US# ----
def parse_insert(path):
    rows = {}
    cur = None
    for ln in open(path, encoding='utf-8').read().split('\n'):
        m = re.match(r'^\[US#(\d+)\]\s*(.*)$', ln)
        if m:
            cur = int(m.group(1))
            spk = m.group(2).strip()
            spk = re.sub(r'^\(', '', spk); spk = re.split(r'[)\[]', spk)[0].strip()
            rows[cur] = {'lit':'', 're':[], 'speaker':spk}; continue
        if cur is None: continue
        ml = re.match(r'^\s{2}LIT\s*:\s?(.*)$', ln)
        mr = re.match(r'^\s{2}RE\s*:\s?(.*)$', ln)
        if ml: rows[cur]['lit'] = ml.group(1).strip()
        elif mr: rows[cur]['re'].append(mr.group(1).rstrip())
        elif rows[cur]['re'] is not None and re.match(r'^\s{7}\S', ln) and not ln.lstrip().startswith(('JP','LIT','EN','#')):
            rows[cur]['re'].append(ln.strip())
    return rows

def main():
    ud, offs = us_slots()
    nslot = len(offs)
    jpb = jp_by_block()

    # migrate translations: build us -> (lit, re, speaker, src_file, status, area)
    tr = {}
    def ingest(path, status, area_of):
        recs = parse_insert(path)
        fn = os.path.basename(path)
        for us, r in recs.items():
            re_join = ' / '.join(x for x in r['re'] if x.strip())
            # deep beats firstpass if a slot appears in both
            if us in tr and tr[us]['status'] == 'deep' and status == 'firstpass':
                continue
            tr[us] = {'lit':r['lit'], 're':re_join, 'speaker':r['speaker'],
                      'src_file':fn, 'status':status, 'area':area_of(fn, us)}
    # deep first (so they win), then firstpass
    for fn, area in SCENE_AREA.items():
        p = os.path.join(INS, fn)
        if os.path.exists(p): ingest(p, 'deep', lambda f,u,a=area: a)
    for fn, areas in FP_AREAS.items():
        p = os.path.join(INS, 'firstpass', fn)
        if os.path.exists(p): ingest(p, 'firstpass', lambda f,u,a=areas: a[0])

    # cross-block cleanup files: one file spanning many blocks; area is looked up per-US by block.
    blk_area = {}   # block -> primary area (first area that claims it)
    for f, area, _s, blk in SCENES:
        for b in str(blk).split(): blk_area.setdefault(int(b), area)
    for f, codes, blk, _l in FIRSTPASS:
        blk_area.setdefault(int(blk), codes[0])
    for fn in ('disc1_cleanup_FINAL.txt', 'boilerplate_sweep_FINAL.txt', 'story_disc1_gapfill_FINAL.txt'):
        p = os.path.join(INS, fn)
        if os.path.exists(p):
            ingest(p, 'deep', lambda f, u: blk_area.get(offs[u] // UBLK, ''))

    rows = []
    for us in range(nslot):
        blk = offs[us] // UBLK
        # in-block index for JP alignment
        b_first = None
        # compute lazily: first slot whose block==blk
        # (cache per block)
        rows.append([us, blk])
    # build block->first-us cache
    first_us = {}
    for us in range(nslot):
        blk = offs[us]//UBLK
        if blk not in first_us: first_us[blk] = us

    db = []
    for us in range(nslot):
        blk = offs[us]//UBLK
        en = uen(ud, offs, us)
        k = us - first_us[blk]
        jp = jpb.get(blk, [])[k] if k < len(jpb.get(blk, [])) else ''
        t = tr.get(us, {})
        db.append({
            'us': us, 'block': blk,
            'en': en,
            'jp': jp[:400],
            'jp_clean': jp_clean(jp),
            'is_examine': jp.lstrip().startswith(('＊','*')),
            'lit': t.get('lit',''),
            're': t.get('re',''),
            'speaker': t.get('speaker',''),
            'tier': 0,
            'status': t.get('status','placeholder'),
            'src_file': t.get('src_file',''),
            'area': t.get('area',''),
        })
    json.dump({'nslot': nslot, 'rows': db}, open(OUT,'w'), ensure_ascii=False)
    print(f"wrote {OUT}: {nslot} rows")

    if '--stats' in sys.argv:
        deep = sum(1 for r in db if r['status']=='deep')
        fp   = sum(1 for r in db if r['status']=='firstpass')
        ph   = sum(1 for r in db if r['status']=='placeholder')
        clean= sum(1 for r in db if r['jp_clean'])
        haslit=sum(1 for r in db if r['lit'] and 'pending' not in r['lit'] and r['lit']!='__LIT_TODO__')
        print(f"  status : deep {deep} · firstpass {fp} · placeholder {ph}")
        print(f"  jp     : clean {clean}/{nslot} ({round(100*clean/nslot)}%)")
        print(f"  lit    : real literals {haslit}")
        print(f"  blocks : {len({r['block'] for r in db})}")

if __name__ == '__main__':
    main()
