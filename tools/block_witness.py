"""Block-scoped witness solver for local-tier codes (>=0x8a38).
For each block, for each local code: collect bigram contexts where the OTHER side is a
GLOBAL solved kanji (or kana okurigana patterns). Match against a compound lexicon ->
candidate reading per (block, code). High-agreement candidates become solves.
"""
import sys, json, collections
sys.path.insert(0,'tools')
import importlib, wa2_kanji_map
importlib.reload(wa2_kanji_map)
from wa2_jp_decode import readfile
K = wa2_kanji_map.KANJI
GLOBAL = {int(k,16):v for k,v in K.items() if int(k,16)<0x8a38}
JD = readfile('Game Files/JP/Wild Arms - 2nd Ignition (Japan) (Disc 1)/Wild Arms - 2nd Ignition (Japan) (Disc 1).bin',12601,13271040)
JBLK=110592; BOUND=0x8a38
CTRL2={0xf0,0x05,0x0a,0x0b,0x10,0x11,0x13,0x16,0x17,0x18}
KHI={0x88,0x89,0x8a,0x8b}

# compound lexicon: common 2-kanji words, keyed by (known_char, position) -> {candidate_char: word}
# position: 'L' = known char on left (known+X), 'R' = known char on right (X+known)
LEX = {}
WORDS = '''世界 人間 時間 仲間 瞬間 空間 magic 魔法 魔力 魔神 存在 現在 自分 自信 自由 自身
場所 場合 戦場 戦争 戦闘 戦士 作戦 戦力 部隊 部分 部屋 全部 隊長 隊員 軍隊 兵隊 込 必要 重要
需要 要求 遺跡 奇跡 軌跡 足跡 解放 開放 追放 放題 放棄 液体 身体 全体 体力 大切 大変 大丈夫
気持 気分 空気 元気 勇気 人気 本気 病気 意味 意識 意志 意義 意見 注意 用意 得意 決意 好意
記憶 記録 日記 一緒 感情 感覚 感謝 予感 直感 事件 事実 事情 事態 仕事 無事 返事 大事 用事
理由 理解 理想 無理 料理 心理 修理 管理 命令 運命 生命 使命 寿命 情報 報告 報酬 警報 予報
機械 機能 機会 機体 危機 通信 通路 交通 普通 共通 開発 発見 発射 発生 発動 発表 爆発 出発
攻撃 衝撃 撃退 目撃 反撃 砲撃 射撃 破壊 壊滅 崩壊 倒壊 準備 装備 予備 守備 整備 設備 警備
防衛 防御 護衛 衛星 記念 残念 信念 概念 執念 疑念 願望 希望 展望 絶望 失望 野望 欲望 人望
未来 将来 以来 本来 由来 到来 過去 去年 最後 最初 最強 最高 最終 最悪 最大 最小 目標 目的
目前 注目 面目 駄目 役目 確認 確保 確信 確実 正確 的確 明確 世代 交代 時代 現代 古代 代表
代償 攻略 侵略 戦略 省略 計略 計画 計算 時計 設計 合計 統計 命中 集中 中心 中央 中止 途中
連中 夢中 集合 場合 都合 具合 試合 結合 総合 結果 結局 結束 結婚 結界 完結 団結 効果 成果
因果 果実 王国 国王 国民 国境 帝国 天国 地獄 地面 地図 地下 大地 土地 基地 現地 各地 聖地
墓地 家族 民族 貴族 一族 血族 液体 血液 血統 純血 出血 流血 王家 実家 作家 国家 大家 専門家
騎士 兵士 武士 闘士 剣士 力士 修行 実行 飛行 行動 移動 行方 一行 旅行 進行 通行 尾行 素行
運行 銀行 犯行 奉行 平和 和平 調和 違和 温和 柔和 平気 平安 平等 平凡 平原 平地 水平 太平
公平 不平 地平 平面 平静 静寂 冷静 安静 動静 静止 停止 中止 禁止 阻止 制止 廃止 休止 防止
抑止 終止 血止 波止 一時 当時 同時 常時 臨時 戦時 幼時 日時 潮時 何時 時期 時刻 時限 期限
制限 極限 限界 限定 無限 有限 門限 権限 場面 画面 表面 正面 方面 反面 内面 外面 仮面 洗面
書面 直面 一面 全面 半面 側面 断面 図面 文面 誌面 誌 地方 遠方 前方 後方 上方 下方 左方
右方 東方 西方 南方 北方 双方 味方 相方 敵方 親方 行方 仕方 夕方 朝方 大方 目方 貴方 彼方
何方 此方 其方 味覚 味見 意味 興味 趣味 賞味 吟味 加味 正味 気味 中味 後味 甘味 辛味 苦味
酸味 塩味 旨味 風味 隠味 薬味'''.split()
for w in WORDS:
    if len(w)!=2: continue
    a,b=w[0],w[1]
    LEX.setdefault((a,'L'),{}).setdefault(b,[]).append(w)   # known a on left -> X=b
    LEX.setdefault((b,'R'),{}).setdefault(a,[]).append(w)   # known b on right -> X=a

def msgs(d):
    o=[];i=0
    while True:
        i=d.find(b'\x10\x0c',i+1)
        if i<0 or i+2>=len(d):break
        o.append(i)
    return o
jm=msgs(JD)
def blk(i): return jm[i]//JBLK

# per-block bigram contexts for local codes
cand=collections.defaultdict(collections.Counter)   # (block, code) -> Counter(candidate_char)
evid=collections.defaultdict(list)
for mi in range(len(jm)):
    b=blk(mi)
    e=jm[mi+1] if mi+1<len(jm) else len(JD)
    seg=JD[jm[mi]:e].split(b'\x00')[0]
    seq=[]  # list of ('G',char) ('L',code) ('K',byte) tokens
    j=0
    while j<len(seg):
        c=seg[j]
        if c in KHI and j+1<len(seg):
            code=(c<<8)|seg[j+1]
            if code>=BOUND: seq.append(('L',code))
            elif code in GLOBAL: seq.append(('G',GLOBAL[code]))
            else: seq.append(('U',code))
            j+=2
        elif c in CTRL2 and j+1<len(seg):
            seq.append(('C',0)); j+=2
        else:
            seq.append(('K',c)); j+=1
    for k in range(len(seq)):
        t,v=seq[k]
        if t!='L': continue
        # left neighbor global?
        if k>0 and seq[k-1][0]=='G':
            g=seq[k-1][1]
            for x,ws in LEX.get((g,'L'),{}).items():
                cand[(b,v)][x]+=1
                if len(evid[(b,v,x)])<3: evid[(b,v,x)].append(ws[0])
        if k+1<len(seq) and seq[k+1][0]=='G':
            g=seq[k+1][1]
            for x,ws in LEX.get((g,'R'),{}).items():
                cand[(b,v)][x]+=1
                if len(evid[(b,v,x)])<3: evid[(b,v,x)].append(ws[0])

# solve: candidate with count>=3 and 2x margin over runner-up
solves={}
for (b,code),cnt in cand.items():
    top=cnt.most_common(2)
    if not top: continue
    ch,n=top[0]
    n2=top[1][1] if len(top)>1 else 0
    if n>=3 and n>=2*max(1,n2):
        solves[(b,code)]={'char':ch,'n':n,'runner':n2,'ex':evid[(b,code,ch)]}
print(f'block-scoped candidates: {len(cand)} slots; confident solves: {len(solves)}')
bycount=collections.Counter(b for (b,c) in solves)
print('top blocks:', bycount.most_common(10))
json.dump({f'{b}:{c:04x}':v for (b,c),v in sorted(solves.items())},
          open('font_work/block_witness_solves.json','w'), ensure_ascii=False, indent=0)
# sample
for (b,c),v in list(sorted(solves.items()))[:25]:
    print(f'  blk{b:3d} {c:04x} = {v["char"]}  (n={v["n"]} vs {v["runner"]})  ex:{",".join(v["ex"])}')
