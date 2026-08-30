"""v2: combine twin-line propagation + block-witness + kana-okurigana patterns, iterate to
fixpoint. Every solve propagates through twin clusters, enabling more witness matches."""
import sys, json, collections
sys.path.insert(0,'tools')
import importlib, wa2_kanji_map
importlib.reload(wa2_kanji_map)
from wa2_jp_decode import readfile
K=wa2_kanji_map.KANJI
GLOBAL={int(k,16):v for k,v in K.items() if int(k,16)<0x8a38}
JD=readfile('Game Files/JP/Wild Arms - 2nd Ignition (Japan) (Disc 1)/Wild Arms - 2nd Ignition (Japan) (Disc 1).bin',12601,13271040)
JBLK=110592; BOUND=0x8a38
CTRL2={0xf0,0x05,0x0a,0x0b,0x10,0x11,0x13,0x16,0x17,0x18}
KHI={0x88,0x89,0x8a,0x8b}
def msgs(d):
    o=[];i=0
    while True:
        i=d.find(b'\x10\x0c',i+1)
        if i<0 or i+2>=len(d):break
        o.append(i)
    return o
jm=msgs(JD)
def blk(i): return jm[i]//JBLK
def raw(i):
    e=jm[i+1] if i+1<len(jm) else len(JD)
    return JD[jm[i]:e].split(b'\x00')[0]

# ---------- tokenize all messages once ----------
MSGS=[]   # (block, seq) where seq = list of ('G',char)|('L',code)|('U',code)|('K',byte)|('C',)
for mi in range(len(jm)):
    seg=raw(mi)
    seq=[];j=0
    while j<len(seg):
        c=seg[j]
        if c in KHI and j+1<len(seg):
            code=(c<<8)|seg[j+1]
            if code>=BOUND: seq.append(('L',code))
            elif code in GLOBAL: seq.append(('G',GLOBAL[code]))
            else: seq.append(('U',code))
            j+=2
        elif c in CTRL2 and j+1<len(seg):
            seq.append(('C',c)); j+=2
        else:
            seq.append(('K',c)); j+=1
    MSGS.append((blk(mi),seq))

# ---------- twin clusters (union-find) ----------
def skel_of(seq):
    out=[]
    for t,v in seq:
        if t=='L': out.append('L')
        elif t=='G': out.append('G'+v)
        elif t=='U': out.append(f'U{v:04x}')
        elif t=='K': out.append(f'K{v:02x}')
        else: out.append(f'C{v:02x}')
    return '|'.join(out)
groups=collections.defaultdict(dict)
for b,seq in MSGS:
    locs=[v for t,v in seq if t=='L']
    if not locs or len(seq)<6: continue
    s=skel_of(seq)
    groups[s].setdefault(b,locs)
parent={}
def find(x):
    r=x
    while parent.get(r,r)!=r: r=parent[r]
    while parent.get(x,x)!=x: parent[x],x=r,parent[x]
    return r
def union(a,b):
    ra,rb=find(a),find(b)
    if ra!=rb: parent[ra]=rb
for s,bs in groups.items():
    items=list(bs.items())
    if len(items)<2: continue
    b0,l0=items[0]
    for b2,l2 in items[1:]:
        if len(l2)!=len(l0): continue
        for x,y in zip(l0,l2): union((b0,x),(b2,y))

# ---------- lexicon ----------
WORDS='''世界 人間 時間 仲間 瞬間 空間 魔法 魔力 魔神 存在 現在 自分 自信 自由 自身 場所 場合
戦場 戦争 戦闘 戦士 作戦 戦力 部隊 部分 部屋 全部 隊長 隊員 軍隊 兵隊 必要 重要 遺跡 足跡
解放 開放 追放 放題 放棄 身体 全体 体力 大切 大変 気持 気分 空気 元気 勇気 人気 本気 意味
意識 意志 意義 意見 注意 用意 決意 記憶 感情 感覚 感謝 事件 事実 事情 事態 仕事 無事 返事
大事 理由 理解 理想 無理 料理 心理 命令 運命 生命 使命 情報 報告 報酬 機械 機能 機会 機体
危機 通信 通路 交通 普通 開発 発見 発射 発生 発動 発表 爆発 出発 攻撃 衝撃 撃退 目撃 反撃
破壊 壊滅 崩壊 準備 装備 予備 守備 整備 設備 警備 防衛 防御 護衛 衛星 記念 残念 信念 疑念
願望 希望 絶望 失望 野望 欲望 未来 将来 以来 本来 由来 到来 過去 最後 最初 最強 最高 最終
最悪 最大 目標 目的 注目 確認 確保 確信 確実 正確 世代 交代 時代 現代 古代 代表 攻略 計画
計算 時計 設計 命中 集中 中心 中央 中止 途中 連中 夢中 集合 都合 具合 試合 結合 結果 結局
結束 結界 効果 成果 王国 国王 国民 国境 地面 地図 地下 大地 基地 現地 聖地 家族 民族 貴族
一族 血族 血液 血統 王家 実家 騎士 兵士 修行 実行 飛行 行動 移動 行方 一行 旅行 進行 通行
平和 調和 平気 平安 水平 地平 停止 禁止 阻止 制止 防止 一時 当時 同時 常時 戦時 時期 時刻
時限 期限 制限 限界 限定 無限 場面 画面 表面 正面 方面 内面 外面 一面 全面 図面 遠方 前方
後方 上方 下方 双方 味方 仕方 彼方 味覚 興味 趣味 気味 天使 天才 天候 天井 天然 天地 天空
運天 天罰 転生 回転 運転 逆転 転換 移転 気配 支配 配置 配達 心配 配下 手配 年配 配分 配役
勝利 勝負 勝手 優勝 必勝 決勝 連勝 圧勝 楽勝 辛勝 名前 以前 直前 寸前 目前 事前 手前 腕前
建前 気前 前進 前提 前線 前例 前半 前夜 前回 前後 少年 少女 少数 多少 少量 減少 希少 幼少
年少 青年 中年 老年 晩年 数年 毎年 来年 昨年 今年 去年 新年 豊年 凶年 学年 千年 万年 百年
永年 長年 若年 実験 経験 体験 試験 受験 験証 危険 冒険 保険 探険 険悪 険しい 陰険 保護 保存
保証 保持 保守 確保 保温 保安 保管 保養 担保 留保'''.split()
LEX={}
for w in WORDS:
    if len(w)!=2: continue
    a,b=w[0],w[1]
    LEX.setdefault((a,'L'),collections.Counter())[b]+=1
    LEX.setdefault((b,'R'),collections.Counter())[a]+=1

# ---------- iterate: witness -> cluster read -> re-witness ----------
cluster_read={}
# seeds from earlier validated block-local truths
for b,c,ch in [(0,0x8a38,'陣'),(0,0x8a39,'限'),(0,0x8a3d,'平'),(0,0x8a3e,'坦'),
               (0,0x8a53,'写'),(0,0x8a54,'真'),(0,0x8a55,'沿'),(0,0x8a56,'岸'),
               (0,0x8a57,'図'),(0,0x8a52,'加')]:
    cluster_read[find((b,c))]=ch
# NOTE 8a38 blk0: 発着魔法場 vs 魔法陣 — tutorial says 発着魔法陣 (Landing Pad = magic circle)? keep 陣 tentative.

for it in range(4):
    new=0
    votes=collections.defaultdict(collections.Counter)
    for b,seq in MSGS:
        n=len(seq)
        for k,(t,v) in enumerate(seq):
            if t!='L': continue
            r=find((b,v))
            if r in cluster_read: continue
            # neighbor known char (global OR solved local)
            for dk in (-1,1):
                kk=k+dk
                if 0<=kk<n:
                    tt,vv=seq[kk]
                    ch=None
                    if tt=='G': ch=vv
                    elif tt=='L':
                        rr=find((b,vv))
                        ch=cluster_read.get(rr)
                    if ch:
                        side='L' if dk==-1 else 'R'   # known on left / right
                        for x,w in LEX.get((ch,side),{}).items():
                            votes[r][x]+=1
    for r,cnt in votes.items():
        top=cnt.most_common(2)
        ch,nv=top[0]
        n2=top[1][1] if len(top)>1 else 0
        if nv>=4 and nv>=2*max(1,n2):
            cluster_read[r]=ch; new+=1
    print(f'iter {it}: +{new} cluster solves (total {len(cluster_read)})')
    if new==0: break

# materialize per-block tables
tables=collections.defaultdict(dict)
slots=set(parent.keys())
for b,seq in MSGS:
    for t,v in seq:
        if t=='L': slots.add((b,v))
solved=0
for s in slots:
    r=find(s)
    if r in cluster_read:
        b,c=s
        tables[b][f'{c:04x}']=cluster_read[r]; solved+=1
total_local_slots=len(slots)
print(f'\nlocal slots total: {total_local_slots}, solved: {solved} ({solved*100//total_local_slots}%)')
# MERGE into the existing table (do NOT overwrite — earlier runs destroyed 1000+ hand solves).
# Existing entries win on conflict; we only ADD codes this pass newly resolved.
import os
BT='font_work/block_tables.json'
existing=json.load(open(BT)) if os.path.exists(BT) else {}
added=0; conflicts=0
for b,t in tables.items():
    sb=str(b); existing.setdefault(sb,{})
    for c,ch in t.items():
        if c in existing[sb]:
            if existing[sb][c]!=ch: conflicts+=1
        else:
            existing[sb][c]=ch; added+=1
json.dump({k:dict(sorted(existing[k].items())) for k in sorted(existing,key=lambda x:int(x))},
          open(BT,'w'), ensure_ascii=False, indent=0)
print(f'merged into {BT}: +{added} new codes, {conflicts} conflicts kept as-existing, '
      f'total {sum(len(v) for v in existing.values())}')
