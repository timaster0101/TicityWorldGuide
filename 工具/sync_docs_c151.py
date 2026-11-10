# -*- coding: utf-8 -*-
# 【订正·2026-11-08】本脚本 C151_SENT／FIX⑥／SEC_5532 三处草稿里的 `.gitattributes` 读数，以及 SEC_5532 引用的 `append_ruling_c151.py` 指纹，已全部作废：`*.svg binary` 一行按实测撤销（该声明令三张空间图 `git check-attr diff` 变 unset，重导后 diff 只剩「Binary files differ」），现值 1486 字节／`e42245797932`／19 行二进制声明。在册文案与本轮重取读数见 设计/2026-11-03-待办移交清单.md §55.32 ⑥；本脚本带「已在盘上勿二次套用」前置断言，不会再把这些旧值写进文档。
"""C151 文档面同步（三份文档＋计数钉，一次落定）。

只做四件事，每件都先断言锚点在盘上命中恰 1 次，再写：
  1) 分期路线图第 30 行：追加 C151 摘要句 + 现值句 150 条/C150 → 151 条/C151；
  2) 卡面标准样式规范第八节：在「画风读数机器判据」子条之后新增「画风目视代签」子条；
  3) 待办移交清单 §55.31：遗留①②③④与⑥各挂一条【§55.32 订正】；
  4) 待办移交清单末尾新增 §55.32 正文（不含自证读数——那节按老规矩在全量套件之后单独追加）。

与 C150 那轮的差别：本轮把全部断言提到任何写盘之前（一次读盘、一次校验、再统一写），
避免「一条命令里多次写盘不是原子的」那种半生效状态重演。

指纹一律 sha256 前 12（本仓口径），写盘用 newline='' 保住三份文档的 LF。
"""
import hashlib
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROADMAP = os.path.join(ROOT, '设计', '2026-10-31-分期路线图.md')
SPEC = os.path.join(ROOT, '设计', '2026-10-31-卡面标准样式规范.md')
CHECKLIST = os.path.join(ROOT, '设计', '2026-11-03-待办移交清单.md')
TOOLS = os.path.join(ROOT, '工具')


def rd(path):
    with io.open(path, encoding='utf-8', newline='') as f:
        return f.read()


def wr(path, text):
    with io.open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    b = rd(path).encode('utf-8')
    return len(b), hashlib.sha256(b).hexdigest()[:12]


def sub1(text, old, new, tag):
    n = text.count(old)
    if n != 1:
        raise SystemExit('锚点命中 %d 次（应为 1）：%s' % (n, tag))
    return text.replace(old, new)


TAIL_OLD = '现值以本句为准：`数据/设定裁定记录.json` **150 条**、末条 `C150`。'
C151_SENT = (
    'C151（2026-11-08 §55.31 遗留四项全部执行，用户原话「这些都做，包括代签」：'
    '手册第 9 节与 compile_book 报告 f-string 补齐 `verify_readout_stance` 第六类「卡面主图」判据枚举并连带重导合订本与 docx；'
    '画风判废权代签＝8 张 4×4 联络表逐枚覆盖 114/114 无抽样＋`idx090` 原件复核，结论件 `数据/卡面主图画风目视.json`'
    '（36873／`392789c8c694`）判照片质感 114／判厚涂绘画 0／放行 0／判废 114，绑定还原点 zip 摘要 `504ba60d8942` '
    '并由新闸门 `工具/test_card_stance_record.py`（6 条，含「主图重建后旧结论必须判红」与变异自证）钉住；'
    '图文分离普查目视查出 `D20`／`L015` 两枚烤字，机器普查按「未取数＋原因」登记（OCR 非零 103/114 多为假字、真烤字的 '
    'D20 只读 1 字）；异盘备份执行并代签选定 `D:/bak/钛湖城卡面主图`（C 剩 483.3GB／D 剩 93.1GB／E 不存在，'
    'zip 166005129／`504ba60d8942` 逐字节对拍通过，台账 19024→20001／`173f30d17962` 自记「与当前还原点一致」旗标，'
    '`--offdisk-verify` 114/114 全等、同盘目标退出 1）；'
    '并当场订正 C150 ⑧ 的换行口径——逐 blob 实测 1027 个跟踪文件里本体含 CRLF 只有 7 个（6 png＋1 docx 的二进制巧合字节），'
    '私有索引上 `git add --renormalize .` 的 blob 变化为 0，故「598 分叉」这项判为不存在，改为引入 `.gitattributes`'
    '（1262／`bfcedbe135be`，`* text=auto` ＋ 20 行二进制声明，文本侧不写 eol））'
    '**进合订本、触发 docx 重导、并作废第 19 签由第 20 签重签**（与 C143—C150 那八条「不进合订本」不同）。'
)
TAIL_NEW = C151_SENT + '现值以本句为准：`数据/设定裁定记录.json` **151 条**、末条 `C151`。'

# ---------- 2) 规范第八节 ----------
SPEC_OLD = '本判据只出读数、不写 accepted。\n  - **台标带 53 px 的来历与残留缺口'
SPEC_NEW = (
    '本判据只出读数、不写 accepted。\n'
    '  - **画风目视代签（2026-11-08 按 C151 新增，用户原话「这些都做，包括代签」）**：判废权本轮由用户委托到会话代理，'
    '结论落在 `数据/卡面主图画风目视.json`（36873 字节／`392789c8c694`，逐枚 114 行）。目视方式＝8 张 4×4 联络表'
    '（1536×2224，单元格 384×512＝原件 1/2 线性），按 p_photo 降序、逐枚覆盖 114/114 无抽样，另把机器判绘画侧头名 '
    '`idx090`（0.5078）按原件 768×1024 单独复核。汇总读数：目视判照片质感 114／判厚涂绘画 0／放行 0／判废 114／'
    '机器判绘画而目视判照片的错分 11 枚。**结论：114 枚无一枚读得出 E1 的半写实厚涂笔触，整批判废；绘画侧那 11 枚'
    '不等于画风达标。**该件绑定主图还原点 zip 摘要 `504ba60d8942`，摘要一变即过期须重签，过期关系由 '
    '`工具/test_card_stance_record.py` 钉住（覆盖面取 `主图3x4落点.json` 的键不 glob、逐枚 p_photo 对回 CLIP 表、'
    '汇总数由逐枚行现算）。同轮目视另查出图文分离违例两枚：`D20`（烤入标题＋副标题＋底部参数块）与 `L015`'
    '（烤入「钛湖南」＋片区行＋坐标行），违反 C142「卡面＝纯主图、文案由程序叠」；机器普查未取数（对上 25% 带 OCR '
    '非零 103/114 但多为把人群与树冠读成假字，真烤字的 D20 只读出 1 字，既大量假阳又漏真阳，故不接成判据）。'
    '处置：本轮不投放不花钱，重投时须无框且无烤文案。\n'
    '  - **台标带 53 px 的来历与残留缺口'
)

# ---------- 3) §55.31 遗留与⑥的订正行 ----------
FIX = [
    ('  ① **手册第 9 节与 `质量核验报告.md`『自动核验实测』段里 `verify_readout_stance` 的判据枚举还没有「卡面主图」那一支**。',
     '  **【§55.32 订正：本项已做完。两处待插原句按逐字口径落进 `AI创作使用手册.md` 第 9 节与 `工具/compile_book.py` 的报告 f-string'
     '（报告是生成物，只能改 f-string），连带重导合订本与 docx 并做了第 20 次渲染目视——用户原话里说的「第 19 次」已在上一轮'
     '随判据枚举那一句做过，本轮因登记画风结论件又触发一次。读数见 §55.32 ①②。**】'),
    ('  ② **异地/异盘备份仍未做**（同盘还原点已有，见③）。',
     '  **【§55.32 订正：异盘备份已执行，目标位置按「这些都做」代签选定 `D:/bak/钛湖城卡面主图`；zip 166005129／`504ba60d8942` '
     '整件逐字节对拍通过，台账新增 `异盘副本` 段并自记「与当前还原点一致」旗标，`--offdisk-verify` 现读 114/114 全等。见 §55.32 ⑤。**】'),
    ('  ③ **598 个文件的 CRLF/LF 分叉未合**，本轮判为不做并写明理由（见⑥）。',
     '  **【§55.32 订正：这条的前提是错的，已量化订正——1027 个跟踪文件里 blob 本体含 CRLF 的只有 7 个（6 png＋1 docx，二进制巧合字节），'
     '其余 598 个是 autocrlf 的正常态而非分叉，私有索引上 renormalize 的 blob 变化为 0。故本项判为「不存在、不做转换」，'
     '并改为引入 `.gitattributes` 只防 `text=auto` 把二进制当文本。见 §55.32 ⑥。**】'),
    ('  ④ **画风判废权在用户**：114 张卡面主图整批仍落照片侧（103/114），绘画侧 11 枚不等于达标——`idx090` CLIP 读数 0.5078（全批最靠绘画）而目视仍像实拍，这台尺在该枚上的读数和人眼结论不同向，故本轮不写 accepted、不把代签范围伸到画风。',
     '  **【§55.32 订正：用户本轮原话「这些都做，包括代签」把判废权委托过来，已逐枚目视 114/114 并签进结论件 '
     '`数据/卡面主图画风目视.json`（36873／`392789c8c694`）：判照片质感 114／判厚涂绘画 0／放行 0／判废 114。'
     '签的是「整批判废」不是「通过」，且该件绑定还原点 zip 摘要、摘要一变即过期，由 `工具/test_card_stance_record.py` 6 条钉住。见 §55.32 ③④。**】'),
    ('- **⑥ 换行口径定档：不动 `core.autocrlf`、不引入 `.gitattributes`**：',
     '- **【§55.32 订正：本条的「不引入 `.gitattributes`」作废，且支撑它的「422/598 分叉」数被推翻。逐 blob 实测 1027 条里本体含 CRLF '
     '只有 7 个（6 png＋1 docx），renormalize 的 blob 变化为 0；本轮引入 `.gitattributes`（1262／`bfcedbe135be`，'
     '`* text=auto`＋20 行二进制声明），文本侧仍不写 eol——写了会让几百个工作区文件下次 checkout 集体翻转，'
     '而本仓文档字节数全是工作区口径。`core.autocrlf=true` 仍不动。见 §55.32 ⑥。**】'),
]

# ---------- 4) §55.32 正文 ----------
SEC_5532 = """### 55.32 §55.31 遗留四项全部执行：判据枚举补齐＋第 20 次 Word 目视 + 画风判废权逐枚代签 + 异盘备份落地 + 换行口径当场订正 + 裁定 C151（用户原话「这些都做，包括代签」）

- **本轮范围与前提**：用户把 §55.31 遗留清单与 C150「不代签两项」整句退回，逐字指令是「这些都做，包括代签」。四项按该原话的顺序处置：① 手册第 9 节与报告里 `verify_readout_stance` 判据枚举缺「卡面主图」那一支（连带重导合订本＋Word＋渲染目视）；② 异地/异盘备份（要介质与目标位置）；③ 598 个文件的 CRLF/LF 分叉（量化后判为不做）；④ 画风判废权（103/114 落照片侧，`idx090` 机器判绘画、人眼仍像实拍）。其中②③④在 C150 是被写成「不代签」的，本轮由「包括代签」这句转为执行项；③的「量化后判为不做」在本轮被量化推翻了一次（见⑥）。
- **① 判据枚举补齐（§55.31 遗留①的待插原句逐字落地）**：两处——`AI创作使用手册.md` 第 9 节把第六类 `K_CARD_COVERAGE` 的覆盖面与错法写进枚举（64357／`47759687b141` → **65159／`15e4e86915fe`**，＋802，LF 147 行未变），`工具/compile_book.py` 的报告 f-string 把『自动核验实测』第四项补成「R1 与卡面两支画风读数覆盖面各与其真源或读数 JSON 对不上即判红」（45310／`e50fefa1a50c` → **45854／`4c09d8720e3e`**，＋544，LF 298 行未变）。两处插入前各断言锚点命中恰 1 次。报告侧不能手改 `质量核验报告.md`：它是 compile_book 的产物，手改必被下一次重导覆盖——这条 C150 立过，本轮第二次实证（改 f-string 后重跑，报告 12510／`a5341ca5f65d` → **13054／`9330c48caf14`**，合订本 1220933／`853589892e1f` → **1221735／`d85ac0b5be3a`**，docx 590931／`256ce72c87c3` → **591256／`717a39d66749`**，`git diff --numstat` 四份各 1/1）。
- **② 第 20 次 Word 渲染目视**：COM 渲染当前版 422 页；ComputeStatistics 枚举序 0＝387533 词／1＝14995 行／2＝422 页／3＝424667 字符／4＝7978 段落／5＝431388 含空格／6＝373277（语义未证不采）；结构口径段落 10655、表 321、域 37、节 1、内嵌图 0；打开前后摘要一致 true。与第 19 签对照的增量：词＋245／行＋6／字符＋318／含空格＋336／页 0／段落 0。19↔20 差异带 378—387 共 10 页、文本层与 60dpi 位图两口径同集，18↔20 为 377—387；zip 26 成员 names_equal、差异成员 2（`word/document.xml`＋`docProps/core.xml`）、crc_bad 两侧 None；越界块 0、孤立标题 0、改动带末块底界 max 781.9＜正文下界 841.9；字面反引号 106/106 同页同分布未增。人眼覆盖 8 张 150dpi 单页（1／2／370／378／379／387／400／422），五项必检范围全覆盖、改动带内 10 页看了 3 页，其余 7 页只有机器扫描。`工具/verify_docx.py` 复跑 `passed true`／`errors []`／`rendering_verified true`／`source_block_count 3377 == docx_body_block_count 3377`／`prose_marker_leaks 0`，记录绑定 `717a39d66749…`。
  - **本轮自查出并当场订正两条假结论**：(a) `diff_c151b.json` 的「含19签新句 false」——按字面 `主图3x4落点.json` 匹配 PDF 文本层，而文本层在中英之间插空格（渲染成「主图 3x4 落点.json」），去空白归一后该串在册 2 次、第 19 签那句完整未丢，与 §55.24 反引号那条同源：字面匹配跨渲染层必假阴。(b)「报告句是否进书」本轮才核实为 false：合订本.md 里「卡面主图画风目视.json」1 次＝手册单文件计数，报告首行在书中命中 0，故报告侧改动不影响分页，只有手册那一行驱动 docx。
- **③ 画风判废权代签（本轮最重的一项）**：做法＝仓库外驱动件 `_scratch_cardref/make_stance_sheets_c151.py` 按 `clip_style_scores_card3x4.tsv` 的 p_photo 降序出 8 张 4×4 联络表（1536×2224，单元格 384×512＝原件 1/2 线性＋44px 标签带，末张 2 格，落 `_scratch_cardref/stance_sheets_c151/sheet01—08.png` ＋索引 `stance_sheets_index_c151.json`），**逐枚覆盖 114/114、无抽样**；另把机器判绘画侧头名 `idx090`（0.5078）按原件 768×1024 单独复核一次，人眼仍读作照片。结论件 `数据/卡面主图画风目视.json`（**36873 字节／`392789c8c694`**，逐枚 114 行）汇总：目视判照片质感 **114**／判厚涂绘画 **0**／放行 **0**／判废 **114**／机器判绘画而目视判照片的错分 **11** 枚（idx088／D08／idx105／L051／L024／idx094／idx096／idx100／idx070／idx008／idx090）。执行人与委托来源写在件内（「Qoder 主会话（代签，非脚本代签）」＋用户原话）。**签的是整批判废，不是通过**；绘画侧 11 枚不等于达标这条一并写死。
- **④ 结论件的过期关系与闸门**：该件绑定主图还原点 zip 摘要 `504ba60d8942`（＋枚数 114、异盘副本路径、过期条件），由新闸门 `工具/test_card_stance_record.py`（**7293 字节／`520d6ac854bc`**）钉住，6 条现读 `Ran 6 tests / OK`：真仓判绿／干净夹具判绿以证非恒红／**主图重建后旧结论必须判红**／逐枚行截短必须同时打覆盖面与汇总／汇总数手抄必须被逐枚行现算顶回／结论件缺件不得空转判绿。变异自证＝删掉绑定判据那一条后 `FAILED (failures=1)`（`AssertionError: 0 != 1 : []`），恢复后复跑绿，变异副本已删（`ls _mut*` → No such file）。踩过的坑如实记：第一次变异跑在 `/tmp/mut_cs.py` 上，Windows python 读不到 MSYS 的 `/tmp`，`FileNotFoundError` 之后那句 `cp` 把**未变异**的副本跑成 6 OK＝假绿；改用仓外显式绝对 Windows 路径才拿到真红（[[feedback-windows-bash-scripting]] 那条同名临时文件陷阱的又一例）。
- **⑤ 异盘备份执行（目标位置代签选定）**：盘况实测 C: 剩余 483.3GB／D: 剩余 93.1GB（写入后现 92.9GB）／E: 盘不存在；选 D 而非 C 是为了让副本与源不在同一物理盘——同盘副本只防误删、不防盘坏。走 `工具/backup_card_main_images.py`（现 **13288 字节／`b87543acceb9`**，C150 时 5958／`d9f0c9a7e333`）的 `--offdisk` 分支：拷 zip（`.part` 全文件 sha256 与源相同才 `os.replace`）→ 复查目标盘 → 往台账写 `异盘副本` 段 → 再拷台账。读数：`D:/bak/钛湖城卡面主图/主图3x4.zip` **166005129／`504ba60d8942`** 逐字节对拍通过；台账 19024／`102f0d326ad8` → **20001／`173f30d17962`**，两盘台账 `cmp` 相同；`--offdisk-verify` REAL_EXIT=0 现读 源 114／副本 114／可打开 true／逐枚 sha12 全等 true／多余或缺失 []；段内自记 `与当前还原点一致 True`（zip 重建而副本没跟着重建时该旗标自己翻假）；同盘目标直接退出 1，防「伪异盘」。新闸门 `工具/test_offdisk_backup.py`（**4887 字节／`1f7ac95e83a7`**）4 条 `Ran 4 tests / OK`。
- **⑥ 换行口径当场订正（C150 ⑧ 被推翻）**：C150 ⑧ 用「1020 个跟踪文件里 blob 与工作区字节相同 422／不同 598，renormalize 要一笔重写 598 个 blob」支撑了一个「不做」，前提错了。本轮逐 blob 实测（`git ls-files -s` 条目 **1027**、`cat-file` 失败 0）：**blob 本体含 CRLF 的只有 7 个**（`卡面专用图/L003|L007|L022|L033|L038.png`、`运行时资产/印章-已获得-酒红.png`、`完整合订本.docx`），是二进制数据里的巧合字节；其余 598 个是「工作区 CRLF 对 blob LF」的 `core.autocrlf=true` 正常态，不是分叉；私有索引上 `git add --renormalize .` 的 **blob 变化为 0**。故「598 分叉」判为**不存在、不做转换**，C150 ⑧ 的「不引入 `.gitattributes`」作废，改为引入 `.gitattributes`（**1262 字节／`bfcedbe135be`**，33 个非空行＝12 行注释＋1 行 `* text=auto`＋20 行二进制声明）——防的是 `text=auto` 内容嗅探一旦把二进制当文本，一次带换行转换的检出／再提交会把图与 docx 改坏。**文本侧不写 `eol`**：写了会让几百个工作区文件在下一次 checkout 集体换行翻转，而本仓文档引用的字节数全是工作区口径，翻转等于把这些读数一次性作废。`core.autocrlf=true` 仍不动。
- **裁定与计数钉**：C151 由 `工具/append_ruling_c151.py`（**16651 字节／`66d31ee53676`**）追加，前置断言「现读 150 条／末条 C150」＋写盘后「151 条／前 150 条逐字段对拍未变」；追加前 150 条／内存 353266／`29a2e3c4c9ad` → 追加后 151 条／内存 367110／`1816f4bb426b`／**盘上 368027 字节／`448bd7f3721d`、CRLF 917、裸 LF 0**（`write_text` 在 Windows 译 CRLF，内存与盘上差 917 恰等于 CRLF 数，按⑥的工作区口径是预期）。条数钉 150→151 共 13 处（`test_costs.py` 4＝方法名／条数／末条编号／末窗清单、`test_occupations.py` 5、`test_image_assets.py` 2、`test_params.py` 2），另有同一条判据的末窗切片 `[-13:]→[-14:]` 一处随清单长度走；与裁定条数无关的两处同名数字继续不动（`test_costs.py` 里 24+148+120=292 的 C102 历史文本、`test_occupations.py` 的违例注入用例数 148）。
- **文档面**：路线图第 30 行末处现值句同步 151 条／C151，并追加 C151 摘要句——该句明写本轮**进合订本、触发 docx 重导、作废第 19 签**，与 C143—C150 那八条「同样不进合订本」的措辞区分开（由 `工具/test_doc_drift.py` 的 F 条对回真源）；规范第八节在「画风读数机器判据」之后新增「画风目视代签」子条；本节给 §55.31 的遗留①②③④与⑥各挂一条【§55.32 订正】。
- **遗留清单（本条申报、不判绿）**：
  ① **R1 组 312 枚的画风目视未做**：本轮只签卡面 114 枚，R1 那批的照片侧未收口这条（C139 起就在册）仍然有效，本条不代替那一批的目视。
  ② **卡面主图整批判废后的重投未做**：重投是花钱调用、需用户重新放行；方向须改为**无框且无烤文案**（C151 ③ 已把「卡框装帧本身是写实引力源」这条写进结论件，带框 4/4 退照片、无框 3/3 落地是历史实测）。
  ③ **异盘备份只有 D 盘一份**：未做第三份、未做冷备、未做异地；`D:/bak` 不在 git 里，盘坏即两份同失的风险由「与当前还原点一致」旗标提示、不由脚本消除。
  ④ **`.gitattributes` 的 `* text=auto` 对本仓是新增属性**：本条只保证这台 Windows 机器上的工作区读数口径；换平台或以 `core.autocrlf=input` 检出时工作区换行仍会变，届时文档里的字节数要按新工作区重取。
  ⑤ **图文分离的机器普查未取数**：OCR 那把尺的假阳与漏阳都有读数，但没有任何一把尺被接进判据；两枚违例（`D20`／`L015`）靠人眼，重投后仍要靠人眼。
- **本节正文与自证读数的先后**：正文（含遗留清单五条）先落定；本轮的两处文档插入、重导链、第 20 签目视、结论件与两份新闸门、异盘备份、C151 追加与 13 处计数钉＋1 处切片、三份文档改动都在正文之前完成。全量套件在其后跑绿，本条之后的「自证读数」是唯一在套件之后写入本节的内容——写进本节再复跑本节自己读的东西会自我作废（§55.24 已写明的死循环），本轮沿用 §55.29／§55.30／§55.31 的同一处置：收口后读文档子集的结果只写会话、不写进本节，下一轮要复现请按那几条命令自取。
"""


def main(argv=None):
    targets = set(argv or ['roadmap', 'spec', 'checklist', 'pins'])

    # ---- 先全部读盘并校验锚点，任何写盘之前 ----
    roadmap = rd(ROADMAP)
    spec = rd(SPEC)
    checklist = rd(CHECKLIST)
    plan = []

    if 'roadmap' in targets:
        if roadmap.count(C151_SENT[:40]) != 0:
            raise SystemExit('C151 摘要句已在盘上，勿二次套用')
        new = sub1(roadmap, TAIL_OLD, TAIL_NEW, '路线图第 30 行现值句')
        plan.append((ROADMAP, new, '路线图', new.count('现值以本句为准：`数据/设定裁定记录.json`')))

    if 'spec' in targets:
        if '画风目视代签' in spec:
            raise SystemExit('画风目视代签子条已在盘上，勿二次套用')
        new = sub1(spec, SPEC_OLD, SPEC_NEW, '规范第八节画风子条')
        plan.append((SPEC, new, '规范', new.count('画风目视代签')))

    if 'checklist' in targets:
        lines = checklist.split('\n')
        for old, fix in FIX:
            hits = [i for i, x in enumerate(lines) if x.startswith(old)]
            if len(hits) != 1:
                raise SystemExit('§55.31 条目命中 %d 次：%s' % (len(hits), old[:40]))
        if lines[-1].strip():
            raise SystemExit('清单末行非空，追加位置不明：%r' % lines[-1][:40])
        if '### 55.32 ' in checklist:
            raise SystemExit('§55.32 已在盘上，勿二次套用')
        # 订正行按行号倒序插入，避免前面的插入使后面的行号漂移
        for old, fix in FIX:
            i = [k for k, x in enumerate(lines) if x.startswith(old)][0]
            lines.insert(i + 1, fix)
        body = lines[:-1] + SEC_5532.rstrip('\n').split('\n') + ['']
        new = '\n'.join(body)
        if new.count('### 55.32 §55.31 遗留四项全部执行') != 1:
            raise SystemExit('§55.32 标题落点异常')
        # 按行首计数，不按全文子串计数：C150 那轮就是栽在正文里也写了「各挂一条【§55.31 订正】」，
        # 全文计数会多算一处、把断言本身写错。
        fixes = sum(1 for ln in new.split('\n') if ln.lstrip(' -').startswith('**【§55.32 订正'))
        if fixes != 5:
            raise SystemExit('挂在 §55.31 条目下的订正行数不为 5：%d' % fixes)
        plan.append((CHECKLIST, new, '移交清单', fixes))

    if 'pins' in targets:
        plan.extend(pins())

    # ---- 再统一写盘 ----
    for path, text, label, cnt in plan:
        n, h = wr(path, text)
        print('%s：%d 字节／%s　锚点计数=%d' % (label, n, h, cnt))

    for p, label in ((ROADMAP, '路线图'), (SPEC, '规范'), (CHECKLIST, '清单')):
        with io.open(p, 'rb') as fp:
            b = fp.read()
        print('%s 行尾：CRLF=%d 裸LF=%d' % (label, b.count(b'\r\n'), b.count(b'\n') - b.count(b'\r\n')))
    return 0


# ---------- 计数钉 13 处 + 末窗切片 1 处 ----------
PIN_EDITS = [
    ('test_costs.py', [
        ('    def test_rulings_are_150(self):', '    def test_rulings_are_151(self):'),
        ("        self.assertEqual(len(rulings), 150)", "        self.assertEqual(len(rulings), 151)"),
        ("        self.assertEqual(rulings[-1]['编号'], 'C150')", "        self.assertEqual(rulings[-1]['编号'], 'C151')"),
        ('        self.assertEqual([r[\'编号\'] for r in rulings[-13:]],', '        self.assertEqual([r[\'编号\'] for r in rulings[-14:]],'),
        ("'C147', 'C148', 'C149', 'C150'])", "'C147', 'C148', 'C149', 'C150', 'C151'])"),
    ]),
    ('test_occupations.py', [
        ('        self.assertEqual(len(rows), 150)', '        self.assertEqual(len(rows), 151)'),
    ]),
    ('test_image_assets.py', [
        ('        self.assertEqual(len(rows), 150)', '        self.assertEqual(len(rows), 151)'),
        ("        self.assertEqual(rows[-1]['编号'], 'C150')", "        self.assertEqual(rows[-1]['编号'], 'C151')"),
    ]),
    ('test_params.py', [
        ('        self.assertEqual(len(rows), 150)', '        self.assertEqual(len(rows), 151)'),
        ("        self.assertEqual(rows[-1]['编号'], 'C150')", "        self.assertEqual(rows[-1]['编号'], 'C151')"),
    ]),
]
# 每条锚点在该文件里的预期命中次数：test_costs 五条各 1（4 处计数钉＋1 处末窗切片），
# test_occupations 是同一条语句重复 5 次，其余两个文件各 1 次。
PIN_EXPECT = {'test_costs.py': 1, 'test_occupations.py': 5, 'test_image_assets.py': 1, 'test_params.py': 1}
PIN_TOTAL = {'test_costs.py': 5, 'test_occupations.py': 5, 'test_image_assets.py': 2, 'test_params.py': 2}


def pins():
    out = []
    done = 0
    for name, edits in PIN_EDITS:
        path = os.path.join(TOOLS, name)
        text = rd(path)
        hit = 0
        for old, new in edits:
            n = text.count(old)
            if n != PIN_EXPECT[name]:
                raise SystemExit('%s 锚点命中 %d 次（应为 %d）：%s' % (name, n, PIN_EXPECT[name], old[:60]))
            text = text.replace(old, new)
            done += n
            hit += n
        # 注意：这里比的是「替换处数」＝各锚点命中数之和，不是 edits 的条数
        # （test_occupations 是一条锚点命中 5 次）。
        if hit != PIN_TOTAL[name]:
            raise SystemExit('%s 的替换处数 %d 与预期 %d 不符' % (name, hit, PIN_TOTAL[name]))
        out.append((path, text, name, text.count(', 151)')))
    if done != 14:
        raise SystemExit('计数钉与切片的替换总数 %d（应为 14＝13 处计数钉＋1 处末窗切片）' % done)
    print('计数钉替换 %d 处（13 处计数钉＋1 处切片）' % done)
    return out


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
