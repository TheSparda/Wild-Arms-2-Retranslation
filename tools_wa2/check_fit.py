"""
Validate filled FIT fields in insert/ workspace files against box budgets.
Reads a blkNNN.txt (or SAMPLE), extracts each [US#n] budget=Xch/Yln and its FIT lines,
reports any that exceed char budget, line count, or 35-char line width.
Usage: python3 tools_wa2/check_fit.py insert/blk004.txt
"""
import sys, re
path = sys.argv[1]
txt = open(path).read()
blocks = re.split(r'\n(?=\[US#\d+\])', txt)
problems = 0; checked = 0
for b in blocks:
    m = re.search(r'\[US#(\d+)\] budget=(\d+)ch/(\d+)ln', b)
    if not m: continue
    us, budget, lines = m.group(1), int(m.group(2)), int(m.group(3))
    fm = re.search(r'FIT:\s*(.+?)(?=\n\[|\Z)', b, re.S)
    if not fm or '<<TODO' in fm.group(1): continue
    checked += 1
    # extract the actual text lines (strip trailing (nn) annotations and arrows)
    fit = fm.group(1)
    fit = re.sub(r'\(\d+\)', '', fit); fit = re.sub(r'->.*', '', fit)
    flines = [l.strip() for l in fit.split('\n') if l.strip()]
    chars = sum(len(l) for l in flines)
    over = []
    if chars > budget: over.append(f'chars {chars}>{budget}')
    if len(flines) > lines: over.append(f'lines {len(flines)}>{lines}')
    wide = [l for l in flines if len(l) > 35]
    if wide: over.append(f'{len(wide)} line(s) >35ch')
    if over:
        problems += 1
        print(f'  US#{us}: ' + '; '.join(over))
print(f'checked {checked} filled slots, {problems} over budget')
