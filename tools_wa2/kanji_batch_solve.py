#!/usr/bin/env python3
"""
BATCH kanji candidate-solver — step 3 of the workflow.

For each unsolved block-local code (>=0x8a38 not in that block's table), gather ALL its
in-block contexts, decode the surrounding kana/known-kanji, pull the ALIGNED English from the
master DB for the slots the code appears in, and emit RANKED kanji candidates for human confirm.

Two evidence sources, combined:
  1) OKURIGANA / COMPOUND: known neighbor char + position matched against a compound lexicon
     (reused/extended from block_witness.py). e.g. code sits right of 世 -> likely 界 (世界).
  2) EN SEMANTIC HINT: the aligned EN line(s) for the code's slots — surfaced verbatim so the
     confirmer sees "this box says 'kidnapping'" next to a code in 誘_ context.

Output: a per-block worklist (most-evidence-first). You confirm; confirmed solves are written
with kanji_batch_solve.py apply <block> <code> <kanji> (appends to block_tables.json), then
rebuild the DB.

  python3 tools_wa2/kanji_batch_solve.py <block> [limit]   # ranked worklist for one block
  python3 tools_wa2/kanji_batch_solve.py apply <block> <code_hex> <kanji>
  python3 tools_wa2/kanji_batch_solve.py top [n]            # blocks ranked by solvable-evidence
"""
import sys, os, json, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wa2_jp_decode as W

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BT_PATH = os.path.join(ROOT, 'font_work', 'block_tables.json')
DB_PATH = os.path.join(ROOT, 'game_script', 'wa2_db.json')
UBLK = 90112
BOUND = 0x8a38

# self-contained compound lexicon (no side-effecting import). Common 2-kanji words; index by
# (known_char, side) where side 'L' = known char is LEFT of the code (known+X, X=right member),
# 'R' = known char is RIGHT of the code (X+known, X=left member).
WORDS = '''世界 人間 時間 仲間 瞬間 空間 魔法 魔力 魔神 存在 現在 自分 自信 自由 自身
場所 場合 戦場 戦争 戦闘 戦士 作戦 戦力 部隊 部分 部屋 全部 隊長 隊員 軍隊 兵隊 必要 重要
遺跡 奇跡 軌跡 足跡 解放 開放 追放 放題 放棄 液体 身体 全体 体力 大切 大変 大丈夫
気持 気分 空気 元気 勇気 人気 本気 病気 意味 意識 意志 意義 意見 注意 用意 得意 決意 好意
記憶 記録 日記 一緒 感情 感覚 感謝 予感 直感 事件 事実 事情 事態 仕事 無事 返事 大事 用事
理由 理解 理想 無理 料理 心理 修理 管理 命令 運命 生命 使命 寿命 情報 報告 報酬 警報 予報
機械 機能 機会 機体 危機 通信 通路 交通 普通 共通 開発 発見 発射 発生 発動 発表 爆発 出発
攻撃 衝撃 撃退 目撃 反撃 砲撃 射撃 破壊 壊滅 崩壊 倒壊 準備 装備 予備 守備 整備 設備 警備
防衛 防御 護衛 衛星 記念 残念 信念 概念 執念 疑念 願望 希望 展望 絶望 失望 野望 欲望 人望
未来 将来 以来 本来 由来 到来 過去 去年 最後 最初 最強 最高 最終 最悪 最大 最小 目標 目的
目前 注目 面目 駄目 役目 確認 確保 確信 確実 正確 的確 明確 世代 交代 時代 現代 古代 代表
代償 攻略 侵略 戦略 省略 計略 計画 計算 時計 設計 合計 統計 命中 集中 中心 中央 中止 途中
連中 夢中 場合 都合 具合 試合 結合 総合 結果 結局 結束 結婚 結界 完結 団結 効果 成果
因果 果実 王国 国王 国民 国境 帝国 天国 地獄 地面 地図 地下 大地 土地 基地 現地 各地 聖地
墓地 家族 民族 貴族 一族 血族 血液 血統 純血 出血 流血 王家 実家 作家 国家 大家
騎士 兵士 武士 闘士 剣士 力士 実行 飛行 行動 移動 行方 一行 旅行 進行 通行 尾行 素行
運行 銀行 犯行 平和 和平 調和 違和 温和 柔和 平気 平安 平等 平凡 平原 平地 水平 太平
公平 不平 地平 平面 平静 静寂 冷静 安静 動静 静止 停止 禁止 阻止 制止 廃止 休止 防止
終止 当時 同時 常時 臨時 戦時 幼時 日時 何時 時期 時刻 時限 期限
制限 極限 限界 限定 無限 有限 門限 権限 場面 画面 表面 正面 方面 反面 内面 外面 仮面 洗面
書面 直面 全面 半面 側面 断面 図面 文面 地方 遠方 前方 後方 上方 下方 左方
右方 東方 西方 南方 北方 双方 味方 相方 敵方 親方 仕方 夕方 朝方 大方 目方 貴方 彼方
何方 此方 其方 味覚 味見 興味 趣味 賞味 吟味 加味 正味 気味 中味 後味 甘味 辛味 苦味
酸味 塩味 旨味 風味'''.split()
LEX = {}
for w in WORDS:
    if len(w) != 2: continue
    a, b = w[0], w[1]
    LEX.setdefault((a, 'L'), {}).setdefault(b, []).append(w)   # known a on left -> X = b (right)
    LEX.setdefault((b, 'R'), {}).setdefault(a, []).append(w)   # known b on right -> X = a (left)

def load_bt(): return json.load(open(BT_PATH))

# ---- cached heavy reads (loaded once, reused across all blocks) ----
_JD = None; _DB = None; _FIRST = None
def _jd():
    global _JD
    if _JD is None: _JD = W.load_jp()
    return _JD
def load_db():
    global _DB
    if _DB is None: _DB = {r['us']: r for r in json.load(open(DB_PATH))['rows']}
    return _DB

def block_jp_offsets(blk):
    seg = W.block_bytes(_jd(), blk)
    jm = []; i = -1
    while True:
        i = seg.find(b'\x10\x0c', i+1)
        if i < 0: break
        jm.append(i)
    return seg, jm

def us_first_by_block():
    """block -> first US# in that block (for JP<->US alignment). Cached."""
    global _FIRST
    if _FIRST is not None: return _FIRST
    ud = W.readfile('Game Files/Wild Arms 2 (USA) (Disc 1)/Wild Arms 2 (USA) (Disc 1).bin', 12586, 10813440)
    offs = []; i = -1
    while True:
        i = ud.find(b'\x10\x0c', i+1)
        if i < 0: break
        offs.append(i)
    first = {}
    for us in range(len(offs)):
        b = offs[us]//UBLK
        if b not in first: first[b] = us
    _FIRST = first
    return first

def decoded_pairs(seg, s, e, blk, tab, glob):
    """Walk a slot's bytes, yielding (char_or_code, is_solved) so we can see a code's neighbors."""
    out = []; j = s
    while j < e-1:
        w = (seg[j] << 8) | seg[j+1]
        if 0x8801 <= w <= 0x8a37:          # global
            out.append((glob.get(f"{w:04x}", f"<{w:04x}>"), True)); j += 2; continue
        if 0x8a38 <= w <= 0x8bff:          # local
            hx = f"{w:04x}"
            if hx in tab: out.append((tab[hx], True))
            else: out.append((('CODE', hx), False))
            j += 2; continue
        b = seg[j]
        if 0x20 <= b < 0x7f: out.append((chr(b), True)); j += 1; continue
        # kana via decode_block single char? fall back: use decode_block on the 2-byte window
        dec = W.decode_block(seg[j:j+2], blk)
        if dec and not dec.startswith('<'):
            out.append((dec[0], True)); j += 1; continue
        j += 1
    return out

_GLOB = None
def _glob_map():
    global _GLOB
    if _GLOB is None:
        K = __import__('wa2_kanji_map').KANJI
        _GLOB = {k: v for k, v in K.items() if int(k, 16) < BOUND}
    return _GLOB

def analyze_block(blk, limit=None):
    bt = load_bt(); db = load_db()
    tab = bt.get(str(blk), {})
    glob = _glob_map()
    seg, jm = block_jp_offsets(blk)
    firstb = us_first_by_block().get(blk)
    # gather, per unsolved code: contexts (neighbors) + the US# slots it appears in
    info = collections.defaultdict(lambda: {'ctx': collections.Counter(), 'slots': [], 'n': 0})
    for k in range(len(jm)):
        s = jm[k]+2; e = jm[k+1] if k+1 < len(jm) else s+400
        pairs = decoded_pairs(seg, s, min(e, s+400), blk, tab, glob)
        for idx, (val, solved) in enumerate(pairs):
            if solved or not isinstance(val, tuple): continue
            hx = val[1]
            left = pairs[idx-1][0] if idx > 0 and pairs[idx-1][1] else None
            right = pairs[idx+1][0] if idx+1 < len(pairs) and pairs[idx+1][1] else None
            left = left if isinstance(left, str) else None
            right = right if isinstance(right, str) else None
            info[hx]['n'] += 1
            if left:  info[hx]['ctx'][('L', left)] += 1   # known char on LEFT of code
            if right: info[hx]['ctx'][('R', right)] += 1   # known char on RIGHT of code
            if firstb is not None:
                us = firstb + k
                if us in db and db[us]['en']: info[hx]['slots'].append(us)
    # rank codes: more contexts with a known kanji neighbor = more solvable
    def candidates(hx):
        c = collections.Counter()
        for (side, ch), cnt in info[hx]['ctx'].items():
            # known char on LEFT of code => code is the RIGHT member (known+X): LEX[(ch,'L')]
            key = (ch, 'L') if side == 'L' else (ch, 'R')
            for cand, words in LEX.get(key, {}).items():
                c[cand] += cnt
        return c.most_common(4)
    rows = []
    for hx, d in info.items():
        cands = candidates(hx)
        ens = [db[u]['en'][:70] for u in d['slots'][:2]]
        score = sum(n for _, n in cands)
        rows.append((score, hx, d['n'], cands, list(d['ctx'].items())[:4], ens))
    rows.sort(key=lambda r: (-r[0], -r[2]))
    return rows[:limit] if limit else rows

def cmd_block(blk, limit):
    rows = analyze_block(blk, limit)
    print(f"=== block {blk}: {len(rows)} unsolved codes (ranked by candidate evidence) ===\n")
    for score, hx, n, cands, ctx, ens in rows:
        cstr = ', '.join(f"{c}({n})" for c, n in cands) if cands else '(no lexicon hit)'
        print(f"  {hx}  x{n}  cand: {cstr}")
        if ctx: print(f"      ctx: {ctx}")
        for e in ens: print(f"      EN: {e}")

def cmd_apply(blk, code_hex, kanji):
    bt = load_bt()
    bt.setdefault(str(blk), {})[code_hex] = kanji
    json.dump(bt, open(BT_PATH, 'w'), ensure_ascii=False, indent=0)
    print(f"block {blk}: {code_hex} = {kanji}  (added; rebuild DB to propagate)")

def cmd_auto(min_ev, dry):
    """Auto-solve UNAMBIGUOUS codes across all blocks: candidates collapse to exactly ONE kanji
    with total evidence >= min_ev. These are safe (e.g. code always right of 同 with only 同時 in
    the lexicon -> 時). Ambiguous/no-hit codes are left for manual review. Writes to block_tables."""
    jd = W.load_jp(); JBLK = W.JBLK
    bt = load_bt()
    picked = []
    for blk in range(len(jd)//JBLK+1):
        for score, hx, n, cands, ctx, ens in analyze_block(blk):
            if not cands: continue
            # unambiguous = single distinct candidate char, evidence >= threshold,
            # and no rival within the lexicon hits
            # STRICT: only a SINGLE distinct candidate char with no rival at all. The "dominant
            # runner-up" heuristic proved risky (contexts like 同時 leak in), so those are left
            # for manual review, not auto-written to the shared table.
            if len(cands) == 1 and cands[0][1] >= min_ev:
                kanji = cands[0][0]
                if bt.get(str(blk), {}).get(hx): continue
                picked.append((blk, hx, kanji, cands[0][1]))
    print(f"auto-solvable (unambiguous, ev>={min_ev}): {len(picked)} (block,code)->kanji pairs")
    for blk, hx, kanji, ev in picked[:60]:
        print(f"  blk{blk:3} {hx} = {kanji}  (ev {ev})")
    if len(picked) > 60: print(f"  ... +{len(picked)-60} more")
    if not dry:
        for blk, hx, kanji, ev in picked:
            bt.setdefault(str(blk), {})[hx] = kanji
        json.dump(bt, open(BT_PATH, 'w'), ensure_ascii=False, indent=0)
        print(f"\nWROTE {len(picked)} solves to block_tables.json — rebuild DB to propagate.")
    else:
        print("\n(dry run — pass --write to apply)")

def cmd_top(n):
    # blocks with the most CANDIDATE-BEARING unsolved codes (best ROI to work first)
    bt = load_bt()
    jd = W.load_jp(); JBLK = W.JBLK
    scores = []
    for blk in range(len(jd)//JBLK+1):
        rows = analyze_block(blk)
        solvable = sum(1 for score, *_ in rows if score > 0)
        if rows: scores.append((solvable, len(rows), blk))
    scores.sort(reverse=True)
    print(f"{'BLOCK':6}{'SOLVABLE':>10}{'TOTAL':>8}")
    for solv, tot, blk in scores[:n]:
        print(f"{blk:6}{solv:10}{tot:8}")

if __name__ == '__main__':
    a = sys.argv
    if a[1] == 'apply': cmd_apply(int(a[2]), a[3], a[4])
    elif a[1] == 'top': cmd_top(int(a[2]) if len(a) > 2 else 20)
    elif a[1] == 'auto':
        min_ev = 2
        rest = [x for x in a[2:] if x != '--write']
        if rest: min_ev = int(rest[0])
        cmd_auto(min_ev, dry='--write' not in a)
    else: cmd_block(int(a[1]), int(a[2]) if len(a) > 2 else None)
