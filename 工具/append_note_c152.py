# -*- coding: utf-8 -*-
"""§55.32 末尾补一条「补记」：⑥ 的「不写 eol」决定当场补上实测读数。

起因：C151 ⑥ 决定不写 `eol`，理由写的是「写了会让几百个工作区文件 checkout 集体翻转」——那句是推理不是读数。
本轮用 `git checkout-index --prefix=<仓库外临时目录>` 真检了一次，把翻转面和两个口径的关系都落成数，
并给 `工具/test_gitattributes_policy.py` 补三条判据把「翻完之后被下一轮误读成内容漂移」这条路堵掉。

写前断言：末条内容行必须是「提交范围与推送状态」那条（＝自证读数块的最后一行），行数与改前指纹逐一对平；
判据文件里的条数（现 8 条）只作本轮补记的读数，不新增计数钉——它跟着 `def test_` 走，不是裁定条数。
"""
import hashlib
import io
import os

CHECKLIST = '设计/2026-11-03-待办移交清单.md'
LAST_HEAD = '- **提交范围与推送状态**'
MARK = '- **补记·2026-11-08 收口后当日（⑥ 的「不写 eol」决定补上读数）**'

BEFORE_BYTES = 715902
BEFORE_SHA = 'bea7332c67b0'
BEFORE_LINES = 3395

NOTE = (
    MARK + '：该决定在正文里只有推理没有读数（「写了 eol 会让几百个工作区文件 checkout 集体翻转」），本轮真检补上。'
    '`git checkout-index --prefix=<仓库外临时目录>` 逐件检到：移交清单 715902→**719296**（CRLF 3394）、'
    '路线图 82015→**82045**（CRLF 30）、规范 34809→**34921**（CRLF 112）、'
    '`数据/设定裁定记录.json` 368254→**368254**（不翻，因工作区本就是 CRLF 917）、`工具/test_costs.py` 40041→**40618**（CRLF 577）。'
    '`git ls-files --eol` 现算 1027 个跟踪文件＝`w/lf` **287**（＝在 `core.autocrlf=true` 的机器上会被重新检出翻成 CRLF 的面）／'
    '`w/crlf` **597**／`w/none` **135**／`w/-text` **7**（生效二进制声明面，与本闸门「png 6＋docx 1」对平）／`w/mixed` **1**（'
    '`设计/2026-11-02-城市量级与天际线重构-design.md`）。结论分两层：'
    '**读数层**——被引用文档的工作区字节与索引 blob 此刻逐件相等（清单 blob 715902＝盘上 715902、路线图 82015＝82015、'
    '规范 34809＝34809、手册 65159＝65159），JSON 则是 blob 367337、盘上 368254，差 917 恰等 CRLF 数；'
    '所以本节记的三个文档字节数同时就是 blob 口径，翻不翻转都不算记错。'
    '**风险层**——翻完之后用 `wc -c` 直接重取会多得「行数」那么多，下一轮会把它误读成内容漂移，而这在此前没有任何判据看得见。'
    '故 `工具/test_gitattributes_policy.py` 本轮补三条判据（现 **8 条**，干净态整档 `Ran 8 tests in 2.690s／OK`）：'
    '①被引用的 6 个件行尾必须二态（CRLF 与裸 LF 不得并存），且相对索引干净时还必须满足「工作区字节 − blob 字节 == CRLF 数」——'
    '后半句在编辑态自动跳过并点名原因（盘上领先 blob 是正常态，把它算成违例就是假红），不做静默吞掉；'
    '②记为 LF 口径的四件文档必须仍 `w/lf`，离开即判红并给两种修法（`git -c core.autocrlf=false checkout` 把盘改回 LF，'
    '或整批改按 blob 口径重取并在节首写明口径已换）；③这两条各自的合成违例注入（假 `eol` 表＋假三元组，不碰被守护仓库）。'
    '检出临时目录 `%TEMP%\\c152_checkout_probe` 取数后删除，复核残留 0。'
    '**本轮不新增计数钉**：那 8 条跟着 `def test_` 走，与裁定条数无关，按 §4 的链序口径不进任何写死的数字。'
)


def sha12(data):
    return hashlib.sha256(data).hexdigest()[:12]


def main():
    with io.open(CHECKLIST, 'rb') as f:
        raw = f.read()
    text = raw.decode('utf-8')
    if MARK in text:
        raise SystemExit('补记已在盘上，勿二次套用')
    if b'\r\n' in raw:
        raise SystemExit('清单含 CRLF，本脚本的 LF 口径断言不适用')
    lines = text.split('\n')
    if lines[-1] != '':
        raise SystemExit('清单不是空行收尾：%r' % lines[-1][:40])
    content = [i for i, x in enumerate(lines) if x.strip()]
    if not lines[content[-1]].startswith(LAST_HEAD):
        raise SystemExit('末条内容行不是「提交范围与推送状态」：%s' % lines[content[-1]][:50])
    if len(lines) != BEFORE_LINES or len(raw) != BEFORE_BYTES or sha12(raw) != BEFORE_SHA:
        raise SystemExit('改前读数与预期不符：%d 字节／%s／%d 行（期望 %d／%s／%d）'
                         % (len(raw), sha12(raw), len(lines), BEFORE_BYTES, BEFORE_SHA, BEFORE_LINES))

    new = text + NOTE + '\n'
    data = new.encode('utf-8')
    tmp = CHECKLIST + '.tmp-c152note'
    with io.open(tmp, 'wb') as f:
        f.write(data)
    os.replace(tmp, CHECKLIST)

    with io.open(CHECKLIST, 'rb') as f:
        after = f.read()
    nl = after.decode('utf-8').split('\n')
    print('清单：%d 字节／`%s`／%d 行（补记前 %d／`%s`／%d）'
          % (len(after), sha12(after), len(nl), len(raw), sha12(raw), len(lines)))
    print('哨兵：补记标题 %d 处，CRLF=%d，末行=%r'
          % (after.decode('utf-8').count(MARK), after.count(b'\r\n'), nl[-1] == ''))
    last = [x for x in nl if x.strip()][-1]
    if not last.startswith(MARK):
        raise SystemExit('补记未落在末条：%s' % last[:50])


if __name__ == '__main__':
    main()
