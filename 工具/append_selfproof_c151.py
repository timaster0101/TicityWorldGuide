# -*- coding: utf-8 -*-
"""§55.32 末尾追加「自证读数」九条（C151 轮收口）。

规则约束（本轮实测到的三条，都写在这里免得下一轮重新踩）：
1. 追加锚点必须是上一条「本节正文与自证读数的先后」那一行之后。§55.31 记过的那个坑在这里同样成立：
   插进条目主体与它的缩进续行之间，会让续行挂到错条目上。本脚本按行号定位后只往文件尾接，
   并在写前断言该行确实是最后一条内容行。
2. 本条写入后的指纹不写进本条（写进去即自指作废），只在会话里报，沿 §55.29/§55.30/§55.31 同一处置。
3. 所有数字只取本轮已落盘日志与本轮命令输出；历史 as-run 值只并注、不改写。
"""
import hashlib
import os
import subprocess
import sys

CHECKLIST = '设计/2026-11-03-待办移交清单.md'
ANCHOR_HEAD = '- **本节正文与自证读数的先后**：正文（含遗留清单五条）先落定；本轮的两处文档插入'
MARK = '- **自证读数（全量单测，落盘日志 `_scratch_cardref/fullsuite_c151.log`'

BEFORE = 707558
BEFORE_SHA = 'd6170e96c4bb'

BLOCK = [
    '- **自证读数（全量单测，落盘日志 `_scratch_cardref/fullsuite_c151.log` 70865 字节；该轮走后台执行，故不采信后台通知的 exit code 作唯一依据，改以日志本体判据：`^Ran` 与 `^OK` 各 1 行、`FAILED` 与行首 `ERROR` 各 0 命中）**：在 `工具/` 先 `rm -rf __pycache__`（§55.29 记过的「同长度改常数＋字节码仍有效」的坑），再 `python -X utf8 -m unittest discover -s . -t . -p "test_*.py"`＝**Ran 501 tests in 522.682s／OK**。同一日志里唯一一处「❌」是异盘备份闸门自己的「目标目录与仓库同盘即停手」负测输出（`%TEMP%\\taihoo_offdisk_*`，即同盘拒绝路径），属预期判红、不是套件失败。',
    '- **四个含计数钉文件的针对性复跑**（`_scratch_cardref/pinned_tests_c151.log` 2617 字节）：`python -X utf8 -m unittest test_costs test_occupations test_image_assets test_params`＝**Ran 184 tests in 323.231s／OK**。184 逐文件对平＝`test_costs` 38＋`test_occupations` 81＋`test_image_assets` 42＋`test_params` 23，与 §55.31 记的现值同一组，证明本轮 14 处替换只动字面量、没增删用例。',
    '- **新策略闸门首跑判红与当场订正**：`工具/test_gitattributes_policy.py` 首跑（`_scratch_cardref/gita_gate_c151.log` 1575 字节）**4/5 FAIL**，四处挂点全在同一条 `test_违例注入必须判红`。根因在闸门自身：它用定长 8192 字节切片判「像不像文本」，切片落在中文字符中间触发 `UnicodeDecodeError`，被 `looks_binary` 当成二进制，于是把真文本注入误判成不判红。改为「最多剥 4 个尾部字节再判」后复跑（`_scratch_cardref/gita_gate_c151b.log` 108 字节）**Ran 5 tests in 1.663s／OK**；`工具/test_doc_drift.py` 同轮 **Ran 4 tests in 0.007s／OK**（`docdrift_c151a.log` 107 字节）。这是假绿的另一种形态——闸门自己错、被守护文件无辜，所以订正落在闸门侧而不是放松判据。',
    '- **`.gitattributes` 字节链与两头对拍**：1262 字节／`bfcedbe135be`／20 行 binary（C151 ⑥ 原读数，本轮作废）→ **1486 字节／`e42245797932`／34 非空行＝14 注释＋1 生效的 `* text=auto`＋19 binary**。二进制一侧（属性会不会改坏固定资产）：`git hash-object <f>` 与 `git hash-object --no-filters <f>` 本轮按正路路径复核三例全等——`钛湖城城市设定集-完整合订本.docx` `b7e0cf123e42`、`数据/运行时资产/卡面专用图/L003.png` `b0e5841f86f3`、`全域卫星聚落图.svg` `166e22675116`；三张空间图在仓根不在 `分卷/原稿/`（首轮那次探针把路径猜成 `分卷/原稿/…`，`check-attr` 不校验存在性所以照样出数，改判前先按 `git ls-files \x27*.svg\x27` 取了真路径）。另在私有索引（`GIT_INDEX_FILE`＝`%TEMP%\\c151_renorm.idx`，先 `read-tree HEAD`）上重做 `git add --renormalize .`：与 HEAD 差异 **17 个文件＝本轮改动文件全集，本轮之外 0 个**；暂存出来的 `数据/设定裁定记录.json` blob **367337 字节、CR 0、CRLF 0**，工作区现值 368254／CRLF 917，两侧差 917 恰等于 CRLF 数。两侧口径必须都用 `-c core.quotepath=false` 打开再 `comm -23`，否则 `git diff --cached` 的八进制引号路径与 `git status` 不相等，首轮就造出过 10 条假「非本轮改动者」。文本一侧（撤销 `*.svg binary` 的收益）：`git check-attr diff text merge -- 全域卫星聚落图.svg` 在声明在位时给 `diff/text/merge` 三项 unset，撤销后给 `diff: unspecified`／`text: auto`／`merge: unspecified`——留着它等于让每次重导的三张索引图在 `git diff` 里退化成「Binary files differ」。',
    '- **就地订正脚本与「写后哨兵期望表错」的处置**：`工具/fix_gitattributes_svg_c151.py` 首轮（`_scratch_cardref/fix_svg_c151.log` 739 字节）**REAL_EXIT=1**，挂在写后哨兵的期望表上（`sync_docs_c151.py` 旧四合一实读 2、期望 3），原因是该草稿的 FIX⑥ 字面量跨 Python 源码行拼接、整串匹配不到；此时五份文件已写成功，故按 `_scratch_cardref/bak_fix_svg/` 的五份备份整份回滚，逐条复核回滚后指纹（json 368027／`448bd7f3721d`、路线图 81992／`00b46446cb1d`、清单 705890／`11e14cb2fc01`、append 16651／`66d31ee53676`、sync 26461／`8b214441f051`，旧字面量合计 8 处），再把哨兵拆成独立 `--verify` 支路（期望表写错从此不需要回滚重跑）并将 sync 草稿改为只加文件头作废标注，复跑（`_scratch_cardref/fix_svg_c151b.log` 1001 字节）**REAL_EXIT=0**。订正后五份现值＝`数据/设定裁定记录.json` 368254／`0b8d4a1edfe5`（条数仍 151、末条仍 C151）、`工具/append_ruling_c151.py` 16878／`6094c7c239bd`、`设计/2026-10-31-分期路线图.md` 82015／`732a13024e02`、`设计/2026-11-03-待办移交清单.md` 707558／`d6170e96c4bb`、`工具/sync_docs_c151.py` 27055／`e579ee5ae135`。',
    '- **文档面首挂与写后哨兵**：`工具/sync_docs_c151.py` 首次实跑 **REAL_EXIT=1**、零写盘（断言全在写盘之前）——`pins()` 用 `len(edits)` 当「替换处数」判定，而 `test_occupations.py` 是一条锚点命中 5 次，于是报「替换条数 1 与预期 5 不符」；改为按命中数累加 `hit` 后跑绿（`_scratch_cardref/sync_docs_c151.log` 603 字节）＝计数钉替换 **14 处**（13 处条数钉＋1 处末窗切片），三份文档指纹 路线图 81992／`00b46446cb1d`（锚点 11）、规范 34809／`8bce7b57ec1b`（锚点 1）、清单 705890／`11e14cb2fc01`（锚点 5），行尾三份全 **CRLF=0**（裸 LF 30／112／3383）。哨兵逐项确认：路线图现值句 1、规范「画风目视代签」1、§55.32 标题 1、订正行 grep 6＝行首 5＋散文 1。订正行宿主按行号打序列复核＝3348→3349、3350→3351、3352→3353、3354→3355（⑤ 无订正行），§55.31 的 ⑥ 为 3342→3343，无一条挂错条目——这正是 §55.31 记的「插进主体与续行之间」的坑的反面检查。',
    '- **收集数与 grep 口径本轮对平＋计时口径**：`工具/test_*.py` 现 25 个文件、`def test_` 现算 **497**；discover 报 **501**＝**492＋9**，其中 497＝492＋新闸门 `test_gitattributes_policy.py` 的 5 条，而这 5 条创建于 discover 那次跑之后，所以它们不在 501 内、只在单跑里（5/5、1.663s）。偏移 **9** 与 §55.28／§55.29／§55.30／§55.31 同值（`工具/test_sun_position.py` 垫片把子目录真身 9 例绑进顶层、垫片自身 0 条）。计时：本轮 522.682s 与 §55.31 的 376.341s、§55.30 的 386.821s、§55.29 的 341.269s 各为单次读数、**不许当平均用**，也没有冷启动／稳态两组对照。',
    '- **凭据扫描（按本轮待提交面现值重取，取代同轮早先那次以 23 条为面的读数）**：`git status --porcelain` 现 **25 条**（17 个 ` M`＋8 个 `??`）、展开 25 个文件、文本件 24。密钥值形态专扫 `sk-[A-Za-z0-9]{8}`／`AKIA[0-9A-Z]{16}`／`ghp_[A-Za-z0-9]{20}`／`Bearer <长串>`／`= "<24+ base64>"`＝**命中 0**；十六进制 32 位 **0**、手机号形态 **0**。宽松扫 `api[_-]?key|secret|token|password|…` 命中 **75** 处、逐条打开后全是标识符与散文自述（`test_image_assets.py` 41、本清单 17、`test_params.py` 11、`test_costs.py` 4、`数据/设定裁定记录.json` 2；形态为变量名 `token`、`SUN_ABSENT_BASELINE_TOKENS`，以及清单里「扫 `api_key|secret|passwd|password|token|bearer|auth`」这句自述），**真凭据 0**，故不触发「含明文密钥的文件不入库」那条。',
    '- **提交范围与推送状态**：本轮按主题分笔提交，范围即上面那 25 条（三份设计文档＋`.gitattributes`＋`数据/设定裁定记录.json`＋四个含计数钉测试＋两份本轮新脚本＋卡面主图与 HTML 产物面）。`git status` 与 `git rev-parse --short HEAD` 的本轮读数为 HEAD `81ab408`、领先 `origin/main` 8 笔；本条写入后这两个数即过期，下一轮按 `git rev-list --count origin/main..HEAD` 自取，不追修。**推送未获授权、本轮不执行**（用户当前口径「先提交就行了，推送稍后把」）。本条之后的读文档子集结果按上一条约定只写会话、不写进本节。',
]


def sha12(data):
    return hashlib.sha256(data).hexdigest()[:12]


def main():
    raw = open(CHECKLIST, 'rb').read()
    text = raw.decode('utf-8')
    if MARK in text:
        raise SystemExit('自证读数已在盘上，勿二次套用')
    if '\r\n' in text:
        raise SystemExit('清单含 CRLF，本脚本的 LF 口径断言不适用')
    lines = text.split('\n')
    if lines[-1] != '':
        raise SystemExit('清单末尾不是空行收尾，追加位置不明：%r' % lines[-1][:40])
    content = [i for i, x in enumerate(lines) if x.strip()]
    last = content[-1]
    if not lines[last].startswith(ANCHOR_HEAD):
        raise SystemExit('最后一条内容行不是「本节正文与自证读数的先后」：%s' % lines[last][:60])
    if len(lines) != 3386 or last != 3384:
        raise SystemExit('清单行数/锚点行号与预期不符：%d 行，末条内容在第 %d 行' % (len(lines), last + 1))
    if len(raw) != BEFORE or sha12(raw) != BEFORE_SHA:
        raise SystemExit('改前指纹与预期不符：%d／%s（期望 %d／%s）' % (len(raw), sha12(raw), BEFORE, BEFORE_SHA))

    new = text + '\n'.join(BLOCK) + '\n'
    data = new.encode('utf-8')
    tmp = CHECKLIST + '.tmp-c151selfproof'
    with open(tmp, 'wb') as fh:
        fh.write(data)
    os.replace(tmp, CHECKLIST)

    after = open(CHECKLIST, 'rb').read()
    nl = after.decode('utf-8').split('\n')
    print('清单：%d 字节／`%s`／%d 行（写前 %d 字节／`%s`）' % (len(after), sha12(after), len(nl), len(raw), sha12(raw)))
    print('追加条目 %d 条，CRLF=%d 裸LF=%d' % (len(BLOCK), after.count(b'\r\n'), after.count(b'\n') - after.count(b'\r\n')))
    checks = {
        '自证读数标题': new.count('- **自证读数（全量单测，落盘日志 `_scratch_cardref/fullsuite_c151.log`'),
        '本轮日志引用': new.count('fullsuite_c151.log') + new.count('pinned_tests_c151.log') + new.count('gita_gate_c151b.log') + new.count('fix_svg_c151b.log'),
    }
    for k, v in checks.items():
        print('  哨兵 %s = %d' % (k, v))
    if checks['自证读数标题'] != 1:
        raise SystemExit('自证读数落点异常')
    git('status', '--porcelain', CHECKLIST)


def git(*args):
    return subprocess.run(['git', '-c', 'core.quotepath=false', *args],
                          capture_output=True, text=True, encoding='utf-8').stdout.strip()


if __name__ == '__main__':
    sys.exit(main())
