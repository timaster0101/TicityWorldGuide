# -*- coding: utf-8 -*-
"""C151 入库前复核订正：`.gitattributes` 撤销 `*.svg binary` 一行，六处旧读数同步。

起因：给 `.gitattributes` 入库做二进制安全验证时实测 `git check-attr diff text merge -- 全域卫星聚落图.svg`
在 `*.svg binary` 在位时给 `diff: unset`／`text: unset`／`merge: unset`（binary 宏一次关掉三项），撤销该行后给
`diff: unspecified`／`text: auto`。三张空间图是纯文本 XML、每次 compile_book 重导都会变，声明 binary 等于把它们
在 `git diff` 里退化成「Binary files differ」，提交评审读不出改了什么——这是新属性自己引入的回归，不是它要防的
那件事，故撤销。

现值：`.gitattributes` 已在盘上 1486 字节／`e42245797932`，34 个非空行＝14 行注释＋1 行 `* text=auto`＋19 行二进制声明。

第一次实跑（2026-11-08）挂在写后哨兵上：期望表把 `sync_docs_c151.py` 的旧字面量按「三处」写，而其中 FIX⑥ 那处
在 Python 源码里跨行拼接、整串匹配命中 0，实为 2 处。那次五份文件已全部写成功、只有期望表错，故按
`_scratch_cardref/bak_fix_svg/` 的备份整份回滚后重跑本版；本版把哨兵拆成 `--verify` 支路，期望表错不再需要回滚重跑。

改动面（断言全部先于写盘；`newline=''` 读写 ⇒ 盘上字节＝内存 UTF-8 字节，故各件最终读数写前预测、写后逐字节复核）：
  1) `数据/设定裁定记录.json` 的 C151 ⑥（就地改，条数仍 151／末条仍 C151，含撤销理由与作废原值）；
  2) `工具/append_ruling_c151.py` 的同一段草稿；
  3) 路线图第 30 行 C151 摘要句；
  4) 移交清单：§55.31 遗留⑥ 的【§55.32 订正】行、§55.32 正文⑥ 的数字；正文⑥ 后挂复核子行，
     「裁定与计数钉」行后挂回滚重跑后的重取读数行（两份草稿文件的新指纹并注，as-run 值不改写）；
  5) `工具/sync_docs_c151.py`：只在文件头加一条作废标注（三处草稿字面量有两处跨源码行拼接，逐串拆补易引入新错；
     该脚本带「已在盘上勿二次套用」前置断言，不会再把这些旧值写进文档）。
"""
import hashlib
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, '工具')
ROADMAP = os.path.join(ROOT, '设计', '2026-10-31-分期路线图.md')
CHECKLIST = os.path.join(ROOT, '设计', '2026-11-03-待办移交清单.md')
RULINGS = os.path.join(ROOT, '数据', '设定裁定记录.json')
APPEND = os.path.join(TOOLS, 'append_ruling_c151.py')
SYNC = os.path.join(TOOLS, 'sync_docs_c151.py')
GITATTR = os.path.join(ROOT, '.gitattributes')

GITA_BYTES, GITA_SHA = 1486, 'e42245797932'

OLD_FULL = '（**1262 字节／`bfcedbe135be`**，33 个非空行＝12 行说明注释＋1 行 `* text=auto`＋20 行二进制声明）'
NEW_FULL = ('（**%d 字节／`%s`**，34 个非空行＝14 行说明注释＋1 行 `* text=auto`＋19 行二进制声明；'
            '入库前复核撤销 `*.svg binary` 一行——实测该声明把三张空间图的 diff/text/merge 一并置 unset，'
            '重导后在 `git diff` 里只剩「Binary files differ」，原值 1262／`bfcedbe135be`／20 行作废）' % (GITA_BYTES, GITA_SHA))
OLD_DOC = '（**1262 字节／`bfcedbe135be`**，33 个非空行＝12 行注释＋1 行 `* text=auto`＋20 行二进制声明）'
NEW_DOC = ('（**%d 字节／`%s`**，34 个非空行＝14 行注释＋1 行 `* text=auto`＋19 行二进制声明，'
           '`*.svg` 一行按实测撤销）' % (GITA_BYTES, GITA_SHA))
OLD_SHORT = '（1262／`bfcedbe135be`，`* text=auto` ＋ 20 行二进制声明，文本侧不写 eol）'
NEW_SHORT = ('（%d／`%s`，`* text=auto` ＋ 19 行二进制声明，`*.svg` 撤销声明，文本侧不写 eol）' % (GITA_BYTES, GITA_SHA))
OLD_TIGHT = '（1262／`bfcedbe135be`，`* text=auto`＋20 行二进制声明）'
NEW_TIGHT = '（%d／`%s`，`* text=auto`＋19 行二进制声明）' % (GITA_BYTES, GITA_SHA)
OLD_LITERALS = (OLD_FULL, OLD_DOC, OLD_SHORT, OLD_TIGHT)

# sync 草稿里 FIX⑥ 那处跨 Python 源码行拼接，整串匹配命中 0 ⇒ 实测 2 处，不是 3 处
EXPECT_OLD4 = {RULINGS: 0, APPEND: 0, ROADMAP: 0, CHECKLIST: 0, SYNC: 2}
EXPECT_OLD_SHA = {RULINGS: 1, APPEND: 1, ROADMAP: 0, CHECKLIST: 0, SYNC: 3}
EXPECT_NEW_SHA = {RULINGS: 1, APPEND: 1, ROADMAP: 1, CHECKLIST: 2, SYNC: 1}

EDITS = [
    (RULINGS, [(OLD_FULL, NEW_FULL, 1)]),
    (APPEND, [(OLD_FULL, NEW_FULL, 1)]),
    (ROADMAP, [(OLD_SHORT, NEW_SHORT, 1)]),
    (CHECKLIST, [(OLD_TIGHT, NEW_TIGHT, 1), (OLD_DOC, NEW_DOC, 1)]),
]

ANCHOR_6 = '- **⑥ 换行口径当场订正（C150 ⑧ 被推翻）**：'
ANCHOR_PIN = '- **裁定与计数钉**：C151 由 `工具/append_ruling_c151.py`'
SYNC_FIRST_LINE = '# -*- coding: utf-8 -*-'
SYNC_NOTE_HEAD = '# 【订正·2026-11-08】'
SYNC_NOTE = (SYNC_NOTE_HEAD + '本脚本 C151_SENT／FIX⑥／SEC_5532 三处草稿里的 `.gitattributes` 读数，'
             '以及 SEC_5532 引用的 `append_ruling_c151.py` 指纹，已全部作废：`*.svg binary` 一行按实测撤销'
             '（该声明令三张空间图 `git check-attr diff` 变 unset，重导后 diff 只剩「Binary files differ」），'
             '现值 1486 字节／`%s`／19 行二进制声明。在册文案与本轮重取读数见 设计/2026-11-03-待办移交清单.md §55.32 ⑥；'
             '本脚本带「已在盘上勿二次套用」前置断言，不会再把这些旧值写进文档。' % GITA_SHA)

PROBE = ('  - **入库前复核（本条订正的由来）**：验证「`* text=auto` 会不会改坏图与 docx」时顺手查了三张空间图，'
         '`git check-attr diff text merge -- 全域卫星聚落图.svg` 在 `*.svg binary` 在位时给 `diff: unset`／'
         '`text: unset`／`merge: unset`，撤销该行后给 `diff: unspecified`／`text: auto`——SVG 是纯文本 XML，'
         '留着它等于让每次重导的索引图在 `git diff` 里退化成「Binary files differ」。二进制安全一侧同时实测：'
         '`git hash-object <f>` 与 `git hash-object --no-filters <f>` 对 docx、`数据/运行时资产/卡面专用图/L003.png`、'
         '三张图之一的 svg 两侧全等（`b7e0cf123e42…`／`b0e5841f86f3…`／`166e22675116…`），'
         '扩展名普查 1027 个跟踪文件＝474 txt／166 html／163 py／111 json／94 md／6 png／4 tsv／3 svg／'
         '1 jsonl／1 docx／1 css／1 cjs／1 csv／1 gitignore，除 svg 外没有第二种「文本内容被声明为二进制」。')


def rd(path):
    with io.open(path, encoding='utf-8', newline='') as f:
        return f.read()


def fingerprint(text):
    b = text.encode('utf-8')
    return len(b), hashlib.sha256(b).hexdigest()[:12]


def wr(path, text):
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    b = text.encode('utf-8')
    with io.open(path, 'rb') as fp:
        if fp.read() != b:
            raise SystemExit('%s 写后逐字节复核不符' % path)
    return fingerprint(text)


def sub(text, old, new, want, tag):
    n = text.count(old)
    if n != want:
        raise SystemExit('%s 锚点命中 %d 次（应为 %d）：%s' % (tag, n, want, old[:48]))
    return text.replace(old, new)


def insert_after(lines, anchor, added, tag):
    hits = [k for k, x in enumerate(lines) if x.startswith(anchor)]
    if len(hits) != 1:
        raise SystemExit('%s 按行首命中 %d 行（应为 1）' % (tag, len(hits)))
    lines.insert(hits[0] + 1, added)


def apply_all():
    texts = {path: rd(path) for path, _edits in EDITS}
    texts[SYNC] = rd(SYNC)

    data = json.loads(texts[RULINGS])
    if len(data) != 151 or data[-1]['编号'] != 'C151':
        raise SystemExit('裁定件现值非 151 条／C151：%d 条／%s' % (len(data), data[-1]['编号']))
    for path, edits in EDITS:
        t = texts[path]
        for old, new, want in edits:
            t = sub(t, old, new, want, os.path.basename(path))
        texts[path] = t

    sync_lines = texts[SYNC].split('\n')
    if sync_lines[0] != SYNC_FIRST_LINE:
        raise SystemExit('sync_docs_c151.py 首行非编码声明：%r' % sync_lines[0][:40])
    if SYNC_NOTE_HEAD in texts[SYNC]:
        raise SystemExit('sync_docs_c151.py 的作废标注已在位，勿二次套用')
    sync_lines.insert(1, SYNC_NOTE)
    texts[SYNC] = '\n'.join(sync_lines)

    r_bytes, r_sha = fingerprint(texts[RULINGS])
    a_bytes, a_sha = fingerprint(texts[APPEND])
    s_bytes, s_sha = fingerprint(texts[SYNC])

    lines = texts[CHECKLIST].split('\n')
    pin = ('  - **本轮订正后的重取读数（as-run 值不改写，只并注）**：裁定件就地订正后盘上 %d 字节／`%s`，'
           '条数仍 151／末条仍 C151；`工具/append_ruling_c151.py` 订正后 %d 字节／`%s`（追加那一次跑的是 '
           '16651／`66d31ee53676`，见上一行）；`工具/sync_docs_c151.py` 加作废标注后 %d 字节／`%s`；'
           '本轮首次实跑挂在写后哨兵的期望表上（把 sync 草稿的旧字面量按 3 处写、实测 2 处，因 FIX⑥ 那处跨源码行拼接），'
           '五份文件按 `_scratch_cardref/bak_fix_svg/` 整份回滚后重跑，回滚后的指纹逐条复核见本脚本 docstring。'
           % (r_bytes, r_sha, a_bytes, a_sha, s_bytes, s_sha))
    # 倒序插入，避免前一次插入使后一次行号漂移
    insert_after(lines, ANCHOR_PIN, pin, '§55.32 裁定与计数钉')
    insert_after(lines, ANCHOR_6, PROBE, '§55.32 正文⑥')
    texts[CHECKLIST] = '\n'.join(lines)

    return [(path, texts[path]) for path, _edits in EDITS] + [(SYNC, texts[SYNC])]


def verify():
    """写后哨兵：逐文件对 (旧四项字面量, 旧摘要, 新摘要) 打表。可单独跑，期望表错不必回滚重跑。"""
    bad = []
    for path in (RULINGS, APPEND, ROADMAP, CHECKLIST, SYNC):
        t = rd(path)
        got = (sum(t.count(o) for o in OLD_LITERALS), t.count('bfcedbe135be'), t.count(GITA_SHA))
        want = (EXPECT_OLD4[path], EXPECT_OLD_SHA[path], EXPECT_NEW_SHA[path])
        print('哨兵 %s：旧四合一=%d 旧摘要=%d 新摘要=%d（期望 %r）'
              % (os.path.basename(path), got[0], got[1], got[2], want))
        if got != want:
            bad.append('%s 实 %r 期望 %r' % (os.path.basename(path), got, want))
    data = json.loads(rd(RULINGS))
    if len(data) != 151 or data[-1]['编号'] != 'C151':
        bad.append('裁定件条数/末条＝%d／%s，期望 151／C151' % (len(data), data[-1]['编号']))
    gita = rd(GITATTR)
    got_gita = fingerprint(gita)
    n_binary = sum(1 for ln in gita.split('\n') if ln.endswith(' binary'))
    print('.gitattributes：%d 字节／`%s`，binary 声明 %d 行，`*.svg binary` 在位=%s'
          % (got_gita[0], got_gita[1], n_binary, '*.svg binary' in gita))
    if got_gita != (GITA_BYTES, GITA_SHA) or n_binary != 19 or '*.svg binary' in gita:
        bad.append('.gitattributes 未达预期（%r／%d 行／含 svg 声明 %s）'
                   % (got_gita, n_binary, '*.svg binary' in gita))
    if bad:
        raise SystemExit('\n'.join(bad))
    print('哨兵通过：旧字面量按打表归零／留档，裁定件 151 条／末条 C151，`.gitattributes` 19 行二进制且不含 svg')
    return 0


def main(argv=None):
    if argv and '--verify' in argv:
        return verify()
    for path, text in apply_all():
        n, h = wr(path, text)
        print('%s：%d 字节／%s' % (os.path.basename(path), n, h))
    return verify()


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
