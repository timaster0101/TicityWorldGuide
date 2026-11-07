# -*- coding: utf-8 -*-
"""开图图片资产核验回归。只读已落盘产物与真实图集，不生成、不修改任何图片。

跑法：python 工具/test_image_assets.py（工作目录＝设定集根）
"""
import json
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '工具'))


CELL_PAT = re.compile(r'(?:替换上一格|替换第(\d+)格) (\S+?\.(?:png|jpg))')
VNN_IN_ROW = re.compile(r'重投第[一二三四五六七八九十]+投（(v\d+)）')

# 占格读数按轮次抬头取最新一条。为什么不能只认 C123 那轮：C133／C138 两轮重投替换的是同一格，
# 只按 C123 抬头选行会让判据在新轮占格之后仍然要求「那一格必须是 C123 档」——
# 那是一条恒红，而把它改成不看新轮又成了恒绿。档串与批次后缀都从选中的那一行现读。
ROUNDS = (
    (re.compile(r'^C123新串([A-Z]+\d+)重投'), 'C123新串', 'vnn'),
    (re.compile(r'^C133冻结重投([A-Z]+\d+)（v01）'), 'C133冻结重投', 'fixed'),
    (re.compile(r'^C138主向重投([A-Z]+\d+)（v01）'), 'C138主向重投', 'fixed'),
)

ARCHIVE_ROOT = 'backup/'


def unrooted(path):
    """去掉 B 前置裁定的归档镜像前缀，返回读数侧一贯使用的无前缀写法。
    为什么判据按无前缀比对：`数据/开图清单.json` 的 image_file 在过渡期整体挂 backup/ 路径，
    303 条重投后还要整体切回原路径（移交清单 §50.3），而人工读数是按文件名原样记录的。
    认这个前缀等于让同一批断言在切回那天再红一次。"""
    return path[len(ARCHIVE_ROOT):] if path.startswith(ARCHIVE_ROOT) else path


def on_disk(path):
    """清单挂 backup/、读数挂无前缀，两侧任一处落盘即算在盘上。"""
    bare = unrooted(path)
    return (ROOT / bare).is_file() or (ROOT / ARCHIVE_ROOT / bare).is_file()


def head_re(token):
    return [h for h, t, m in ROUNDS if t == token][0]


def round_row(eid, rows, token):
    """取指定某一轮的那条占格读数（按抬头，不按位置）。"""
    hits = [r for r in rows if head_re(token).match(r)]
    return hits[-1] if hits else ''


def cell_row(eid, rows):
    """取该 ID 最新一轮的占格读数，返回（读数、档串名、后缀口径）。

    为什么不按位置：同一 ID 在重投后还会被追加复看补写（2026-11-05 那轮 6 条牌面缺口补写就是把
    读数追加到末尾），rows[-1] 会指到补写上，判据查的其实一直是重投那条。
    为什么按轮次取最新而不是固定查 C123：C133／C138 替换的是同一格，清单里那一格早已换成本轮的图，
    查 C123 那条会让判据恒红；反过来只查最新一轮而不留 C123 的历史条目，历史断言就没有承载。"""
    for head, token, mode in reversed(ROUNDS):
        hits = [r for r in rows if head.match(r)]
        if hits:
            return hits[-1], token, mode
    return '', None, None


def registered_file(row, token):
    """从占格读数里取它自己点名的本轮文件名——判据要求读数自带出处，所以取得到，不必另抄名单。"""
    hits = re.findall(r'(?:backup/)?vibe_images/\S*?%s-\S+?\.(?:png|jpg)' % re.escape(token), row)
    return hits[0] if hits else ''


def as_of_round(item, rows, token):
    """把清单＋读数回退到指定那一轮刚占格时的样子，返回（清单副本，读数副本）。

    为什么测试里需要这个视图：后一轮（C133冻结重投）替换掉的正是前一轮那一格，现清单只反映最新一轮；
    前一轮的档位后缀（v01／v02 同串多投）与投次抬头只有在这个还原视图上才还能被打红——
    直接删掉那几条负测等于把「抬头写 vNN 但批次没换」这类真实做过的错法重新放过去。
    还原只用读数自己写明的东西（本轮文件名、替换第N格、抬头里的 vNN），不抄第二份真源。"""
    row = round_row(item['id'], rows, token)
    idx = [i for i, (h, t, m2) in enumerate(ROUNDS) if t == token][0]
    files = list(item.get('image_file') or [])
    m = CELL_PAT.search(row)
    slot = (int(m.group(1)) if m.group(1) else len(files)) if m else 1
    files[slot - 1] = registered_file(row, token)
    item = json.loads(json.dumps(item))
    item['image_file'] = files
    vnm = VNN_IN_ROW.search(row)
    item['batch'] = '%s-%s%s-%s' % (item['type'], item['id'], token,
                                    (vnm.group(1) if vnm else 'v01') if token == 'C123新串' else 'v01')
    later = [t for i, (h, t, m2) in enumerate(ROUNDS) if i > idx]
    rows = [r for r in rows if not any(head_re(t).match(r) for t in later)]
    return item, rows


def check_cell_registration(item, rows):
    """最新一轮重投的占格判据，返回违例清单（空＝达标）。判据本身写在这里，闸门与负测共用一份。

    为什么是替换而不是追加：上一格出成于旧档串，其后画风锚点换到 C122、背景授权又随 C123 收回，
    基准连换两档；两版并排占格会把「这格图存在」读成「两版都可用」。
    为什么不绑摘要：image_prompt_sha256 的绑定属人工验收动作，脚本代签等于把未经复验的图洗成已验收。
    占格口径由读数自己声明（替换上一格／替换第N格／本条此前无格为首占），判据拿声明去核清单实际格数，
    两边对不上就判红——这样第9批两轮的替换格与首占格共用一条判据，不必按批次分叉。
    档串名与批次后缀都从选中的那一行现读（见 ROUNDS 注释），判据里不写死任何一轮的档串。"""
    bad = []
    eid = item['id']
    row, token, mode = cell_row(eid, rows)
    files = item.get('image_file') or []
    if not row:
        return ['本轮重投读数不在档']
    if item.get('status') != '待复验':
        bad.append('状态不是待复验')
    if len(files) != len(set(files)):
        bad.append('清单里有重格')
    slot = None
    old = None
    m = CELL_PAT.search(row)
    if m:
        slot = int(m.group(1)) if m.group(1) else len(files)
        old = m.group(2)
    elif '为首占' in row:
        slot = 1
    else:
        bad.append('读数未写明占格口径（替换上一格／替换第N格／为首占）')
    if slot is not None:
        if not (1 <= slot <= len(files)):
            bad.append('读数声明的格号越出清单（读数%d格，清单%d格）' % (slot, len(files)))
        elif len([f for f in files if token in f]) != 1:
            bad.append('本轮新格不止一格（追加而非替换）')
        else:
            cell = files[slot - 1]
            if token not in cell:
                bad.append('声明的那一格不是%s档' % token)
            if unrooted(cell) not in row:
                bad.append('读数未写本轮占格文件名')
        if old:
            if unrooted(old) == unrooted(files[slot - 1]):
                bad.append('读数写的旧格与本轮新格同名，替换没落地')
            if not on_disk(old):
                bad.append('被替换的旧文件已不在盘上（口径是不删）')
    # 批次后缀跟着读数抬头走：C123 那轮同一档串走过 v01／v02 多投，抬头写「重投X投（vNN）」的必须落 -vNN；
    # C133／C138 两轮的档串名自带唯一后缀（抬头正则已钉死（v01）），所以按轮次表里的口径取固定档号。
    # 为什么不由脚本按 ID 名单判：同一批里 v01 与 v02 并存，名单一抄就成第二份真源，
    # 抬头是人工读数的原文，拿它当依据才能把「图换档了但批次没换」这类错法测红。
    # 为什么按 vNN 抽而不是按「第二投」判：同一 v02 串已经走过第二投（19 条那轮）与第三投（15 条那轮），
    # 写死投次中文数字会让第三投的红字全是假绿。
    vnm = VNN_IN_ROW.search(row)
    want = '%s-%s' % (token, (vnm.group(1) if vnm else 'v01') if mode == 'vnn' else 'v01')
    if not str(item.get('batch') or '').endswith(want):
        bad.append('batch 未随本轮换档（读数抬头要求 %s）' % want)
    bound = str(item.get('image_prompt_sha256') or '')
    if bound:
        # 「已绑摘要即不占格」这条禁则已被用户 2026-11-07 的 R1 回填裁定（「全部 264 都占格」）推翻，
        # 推翻的是占格、不是签署：摘要一律由人工绑，脚本既不写也不撤。所以这里不再要求「无绑定」，
        # 改为要求读数把「维持原绑定＋那串摘要已过期」写明并复述前 12 位——
        # 少了这句，占格就把一份绑在旧文件上的过期验收洗成在册验收，下一轮无人能察觉。
        if '维持原绑定' not in row:
            bad.append('已绑定摘要的条目占格却没申报摘要过期')
        elif bound[:12] not in row:
            bad.append('摘要过期申报没复述被维持的那串前 12 位')
    for token_ in ('sha12=', 'caBX=', 'iTXt=', '待复验', '不代签验收'):
        if token_ not in row:
            bad.append('读数缺要素:' + token_)
    if 'image_prompt_sha256 留空' not in row and '维持原绑定' not in row:
        bad.append('读数未交代 image_prompt_sha256 的去向（留空／维持原绑定）')
    if '不回填' in row:
        bad.append('读数写成不回填，与替换占格矛盾')
    return bad


ROD_PIXEL_RE = re.compile(r'约\s*\d+\s*像素')
ROD_HEIGHT_RE = re.compile(r'[杆针]高')


def check_c126_reading(text):
    """C126 两档判读的可核对性判据，返回违例清单（空＝达标）。

    为什么要有这条：C125 只写「桅杆／细针天线即判废」，上一轮 L067 又留了一句
    「细丝高度远小于可见塔身十二分之一即待观察」——两句并存，同一根杆的档位就取决于评审人的手气。
    C126 把阈值钉成数，判据跟着要求读数把数写出来：细杆分档必须带网格来源、杆高与可见塔身两个像素数、
    以及两者之比的分母；塔吊分档必须写明它落在街面施工层还是天际线远景带。
    只写结论不写数的读数判红，因为下一轮无从复核这一档是按阈值给的还是按印象给的。
    """
    bad = []
    if 'C126' not in text:
        return bad
    if ROD_HEIGHT_RE.search(text):
        if '网格' not in text:
            bad.append('细杆分档未写明网格测量来源')
        if len(ROD_PIXEL_RE.findall(text)) < 2:
            bad.append('细杆分档缺杆高与可见塔身两个像素数')
        if '分之一' not in text:
            bad.append('细杆分档缺杆高对可见塔身的分母')
    if '吊机' in text and not ('街面' in text or '天际线' in text):
        bad.append('塔吊分档未写明所在层')
    return bad


class ReviewNoteHistory(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / '数据' / '开图清单.json').read_text(encoding='utf-8'))
        self.items = {i['id']: i for i in self.manifest['items']}
        self.notes = json.loads((ROOT / '数据' / '开图验收备注.json').read_text(encoding='utf-8'))['备注']

    # 第3期从 git 809ed08 找回的 4 条长文本；C97 后追加 4 条回填备注（D03／D08／S02／S18）；
    # C105／C106 换档后子批①②的 7 张重出各记一条打表（L066／L083／F012／F039／R009，S02／S18 是第二条）。
    # C109 新串的竖幅建筑小批把 L061 也记进这一组：首投读的是当前串，但远景塔形有违例，只打表不占格。
    RECOVERED = ('D01', 'L007', 'L008', 'R043')
    BACKFILLED = ('D03', 'D08', 'S02', 'S18')
    RESHOT = ('L066', 'L083', 'F012', 'F039', 'R009', 'L061')
    # 子批③夜光批四条：R038 用真源串出图并回填，R053／R086 的达标图出自串外试投、只记打表，
    # S23 旧串两赌用尽判废（C109／C110 新串 v03 达标后回填第 5 格，见待办清单 §18）。
    VARIANT = ('S23', 'R038', 'R053', 'R086')
    # 子批③清晨批四条：全部出在 C107 换串之后，输入即当前真源串，故四张都允许回填第 5 格。
    # 夜光批只有 R038 一张回填（另三条串外或判废），清晨批四条一起进——这正是 C107 落进生成器的兑现。
    MORNING = ('L033', 'R076', 'R090', 'R098')
    # 子批③雨后批七条：R006／R063／R066／R116 四张在真源串上达标并回填；R015 的 v02 达标但串外
    # （tail 多了一句），R034 与 R054 旧串两赌用尽（右下角地面字母形签名、日面不可纳）。
    # C109／C110 新串重出后 R015／R034 达标回填，R054 仍因日面入画判废、不占格；C111 把日面禁令复述进
    # 锁定段末后按新串重投，R054 的日面失手点没有复现，达标回填第 5 格。
    RAIN = ('R006', 'R015', 'R034', 'R054', 'R063', 'R066', 'R116')
    # 子批③晴日批一条：v01 因投放时把「人群段」误写成「人群档」属串外，达标不回填；
    # v02 按当前真源串逐字重出后达标回填。同一条ID的两版只有一版能占格，这是串绑定的本意。
    SUNNY = ('R092',)
    # 第9批放量（L061—L108 共48条）里目视读数达标、可占格的 19 条。
    # 这一组占的格随基准走过两档：首投出成于 C118 档串（画风锚点其后换 C122、背景授权再随 C123 收回），
    # 2026-11-05 按 C123 新串重投后以新图替换旧格——替换不是追加，旧文件与旧备注都不删。
    # 两轮投放日志都记不了 image_prompt_sha256：绑定摘要属人工验收动作，脚本不代签，状态只派生到待复验。
    # 判废25＋标红待裁2（L063／L090）＋含标红风险的待复验2（L067／L076）＝29条不占格，
    # 见 工具/parallel_batch_2026_11_03/visual_notes.md 与 工具/reinject_2026_11_05/c123_measure.json。
    BATCH9 = ('L061', 'L062', 'L064', 'L066', 'L068', 'L069', 'L070', 'L071', 'L072', 'L074',
              'L077', 'L078', 'L079', 'L082', 'L084', 'L088', 'L091', 'L096', 'L098')
    # 第9批剩余 29 条按 C123 新串重投后无判废项的 12 条（2026-11-05）：其中 10 条此前无格、本轮首占，
    # R063／R066 是替换各自第 5 格。判废的 19 条不占格、状态维持待开图，读数只留在批次目录。
    BATCH9C = ('L063', 'L067', 'L073', 'L075', 'L076', 'L086', 'L087', 'L089', 'L097', 'L102',
               'R063', 'R066')
    # 第9批判废的 19 条按 C123/C125 同串第二投（v02，2026-11-05）后无判废项的 4 条，全部首占。
    # 其余 15 条仍判废（远景未点名体量带斜削冠／细针天线／桅杆／开洞／扭转），不占格、状态维持待开图，
    # 19 条的逐条读数留在 工具/batch9d_2026_11_05/readings_draft.json。
    # L080 由判废改备注档：屋面细杆按源码网格量得杆高约 20 像素、可见塔身约 360 像素（约十八分之一），
    # 且无横档／格构／灯球／斜削／开洞，落进上一轮 L067 立下的待观察口径，不再算记号档。
    BATCH9D = ('L080', 'L090', 'L092', 'L095')
    # 第9批 d 轮仍判废的 15 条，按同一条 C123/C125/C126 串第四投（2026-11-05）后无判废项的 3 条，全部首占。
    # 抬头写「第三投」而非「第四投」：序号从 C123 新串首投起算（v01 那轮＝首投，19 条那轮＝第二投，本轮＝第三投），
    # 与已落盘的 L080／L090 同一把尺；移交清单与批次目录那套序号把 2026-11-03 的 C118 放量也算成首投，
    # 故同一轮在文档里叫第四投——两个编号空间差一格，闸门只认抬头里的 vNN 后缀，不认中文数字。
    # 其余 12 条仍是远景记号档判废（斜削冠／细针天线／横档桅杆／冠部开洞／扭转塔身），不占格、状态维持待开图，
    # 15 条的逐张读数与 C126 两个像素数留在 工具/batch9e_2026_11_05/readings_draft.json。
    BATCH9E = ('L065', 'L104', 'L107')
    # 第9批 e 轮仍判废的 12 条待开图，按同一条 C123/C125/C126 串第五投（2026-11-06）后无判废项的 3 条，全部首占。
    # 抬头写「重投第四投」：序号从 C123 新串首投起算（v01＝首投、19 条＝第二投、15 条＝第三投、本轮＝第四投），
    # 与 L065／L104／L107 的「重投第三投」同一把尺往后接；移交清单与批次目录那套序号把 2026-11-03 的 C118 放量
    # 也算成首投，故同一轮在文档里叫第五投——两个编号空间差一格，闸门只认抬头里的 vNN 后缀。
    # 其余 9 条仍是远景未点名塔冠记号档判废（斜削冠＋细针天线，全部带 C126 网格量测两个像素数），
    # 不占格、状态维持待开图，12 条的逐张读数与像素数留在 工具/batch9f_2026_11_06/readings_draft.json。
    BATCH9F = ('L093', 'L101', 'L108')
    # 只有目视十项达标的才允许追加图格；判废与待复验的只记打表，不占 image_file。
    APPENDED = {'D03': 5, 'D08': 5, 'S02': 6, 'S18': 6, 'R009': 5, 'R038': 5,
                'L033': 5, 'R076': 5, 'R090': 5, 'R098': 5,
                'R006': 5, 'R063': 5, 'R066': 5, 'R116': 5, 'R092': 5,
                'R015': 5, 'R034': 5, 'S23': 5, 'R054': 5}

    # 2026-11-06 C项开图人工复看：L001—L006 首次落人工判废读数（新键），
    # L007／L008／D03／D08／L061／L066 是往已有键追加复看条。全部只记读数、不绑摘要、不改 status。
    C_ITEM_REREAD = ('L001', 'L002', 'L003', 'L004', 'L005', 'L006',
                     'L007', 'L008', 'D03', 'D08', 'L061', 'L066')

    def test_four_long_notes_recovered(self):
        # L061／L066 同时出现在 RESHOT 与 BATCH9（两轮各记一条），所以按键集合比而不是按元组长度比。
        # 2026-11-07 R1 回填那 264 条也各带一条登记备注。名单不手抄：
        # 从清单的 batch 后缀（回填脚本按档串写入）派生，键集合必须恰等于「历史钉住的批次 ∪ 本轮占格的条目」——
        # 多出来的键说明有人在清单之外造了备注，少掉的键说明某条占格没留出处，两种都判红。
        c138 = {i['id'] for i in self.manifest['items']
                if str(i.get('batch') or '').endswith('C138主向重投-v01')}
        self.assertEqual(len(c138), 264, 'R1 占格条目数不是 264，回填范围或档串换了')
        self.assertEqual(set(self.notes),
                         set(self.RECOVERED + self.BACKFILLED + self.RESHOT + self.VARIANT
                             + self.MORNING + self.RAIN + self.SUNNY + self.BATCH9 + self.BATCH9C
                             + self.BATCH9D + self.BATCH9E + self.BATCH9F + self.C_ITEM_REREAD) | c138)
        # 本轮实测：809ed08 的原始长度 518/226/231/151，各带一条同文派生原因，剥净后如下
        self.assertEqual({k: len(v[0]) for k, v in self.notes.items() if k in self.RECOVERED},
                         {'D01': 204, 'L007': 491, 'L008': 199, 'R043': 124})
        for eid, rows in self.notes.items():
            self.assertTrue(all(r.strip() for r in rows), eid)
            self.assertNotIn('图片对应的基准提示词已变化', rows[-1], f'{eid} 手工源里混入了派生原因')

    def test_backfill_notes_name_the_appended_cell_and_refuse_to_sign(self):
        """回填批次必须自带出处：文件名、容器口径、目视判读与「不代签」四要素缺一，
        下一轮就查不到这格图是哪一批、按哪条裁定计进来的。"""
        for eid, cells in self.APPENDED.items():
            with self.subTest(eid=eid):
                item = self.items[eid]
                # 按内容取登记条，不按位置取：同一 ID 之后还会被追加别的类别的人工读数
                # （2026-11-06 C项复看就把 D03／D08 的登记条从末位挪开），
                # rows[-1] 会指到后写的复看条上，判据查的其实一直是登记那条——同 c123_row 的理由。
                cell = unrooted(item['image_file'][-1])
                rows = [r for r in self.notes[eid] if cell in r]
                self.assertTrue(rows, '%s 找不到点名本格文件的登记备注' % eid)
                row = rows[-1]
                self.assertIn('vibe_images/', row)
                # C97 认的是「PNG 走 caBX·C2PA 容器」这条口径：旧档备注按裁定号复述一句，
                # C123 重投档的抬头直接写容器读数 caBX=1、iTXt=0，同一口径两种写法都算交代过。
                self.assertTrue('C97' in row or 'caBX=' in row, '%s 未交代标识容器口径' % eid)
                self.assertIn('待复验', row)
                self.assertIn('不代签验收', row)
                self.assertEqual(len(item['image_file']), cells, eid)
                self.assertTrue(cell.startswith('vibe_images/'), eid)
                self.assertEqual(item['status'], '待复验', eid)
                self.assertFalse(item.get('image_prompt_sha256'), '%s 已绑定摘要，不该再追加格' % eid)

    def test_appended_cell_selector_reds_when_the_registration_note_is_gone(self):
        """违例负测：上面那条改成了按内容选取，选取本身必须能被坏数据打红，
        否则「找不到登记备注」的 assertTrue(rows) 就是假绿。
        样本取自本轮真实风险：把点名本格文件的登记条整条删掉（等于回填没留出处）。"""
        eid = 'D03'
        cell = unrooted(self.items[eid]['image_file'][-1])
        picked = lambda rows: [r for r in rows if cell in r]
        self.assertTrue(picked(self.notes[eid]), '基线必须先证明选取命中')
        stripped = [r for r in self.notes[eid] if cell not in r]
        self.assertTrue(stripped, '违例夹具不该把本条 ID 的备注全删空')
        self.assertEqual(picked(stripped), [], '删掉登记条后选取仍命中，说明注入没落地')

    def test_rejected_and_borderline_rereads_name_the_file_but_take_no_cell(self):
        """子批①里判废与待复验的四条只留打表、不占 image_file；子批③的 R053／R086 同口径——
        图是串外试投出的，回填等于把未经当前真源串复验的图洗成该串产物。
        C109／C110 新串重出的 R054 也进过这一组：判达标与否只看人工读数，判废就不占格，换串不改变这条。
        C111 把日面禁令复述进锁定段末后重投，读数达标，它才从这一组移进 APPENDED 占第 5 格——进出都由读数定。
        C109 新串的竖幅建筑小批两条（L083 v01、L061 v02）都进这一组：九条判据有达标读数，
        但两条都在「未点名远景塔不得有冠部／桅杆／开洞」上失手（L083 是 L066 屋顶短桅、L061 是两栋背景楼的细桅），
        2/2 命中同一条款，说明这句只写在 tail 里压不住模型——要不要按 C111 的路子段内复述，属新裁定候选。
        一旦让这类图也追加格，「有图＝生成过」的口径就会把废图混进交付面。
        L061／L066 已从这一组移出：第9批 C118 新串重投的人工读数达标，占格的是那一版新文件，
        本组只继续管它们上一轮串外试投那条「不回填」的历史结论还在不在。
        F012／F039／R053／R086 同口径移出：2026-11-07 R1 按台账串逐字重投后占的是本轮那一格，
        「串外不占格」这条禁则已被用户「全部 264 都占格」的裁定推翻——推翻的是当轮不占格，
        不是那句历史结论：不回填那条读数仍须原样留在备注里，由下面 second 那段按抬头逐条查。"""
        expect = {'L083': ('待开图', 0)}
        for eid, (status, cells) in expect.items():
            with self.subTest(eid=eid):
                row = self.notes[eid][-1]
                self.assertIn('vibe_images/', row)
                self.assertIn('不回填', row)
                item = self.items[eid]
                self.assertNotIn('vibe_images/', json.dumps(item['image_file'], ensure_ascii=False), eid)
                self.assertEqual(item['status'], status, eid)
                got = item['image_file']
                self.assertEqual(len(got) if isinstance(got, list) else (1 if got else 0), cells, eid)
        # 移出组的历史结论不能被「新一轮把旧读数盖掉」静默抹平：四条各留一条写明不回填的旧读数，
        # 且最新一轮（C138）那一格是真占了的——两边同时成立才叫「推翻的是当轮、留的是沿革」。
        for eid in ('F012', 'F039', 'R053', 'R086'):
            with self.subTest(eid=eid):
                self.assertTrue([r for r in self.notes[eid] if '不回填' in r],
                                '%s 的串外试投「不回填」读数被改写或删掉了' % eid)
                self.assertEqual(check_cell_registration(self.items[eid], self.notes[eid]), [], eid)
                self.assertTrue(any('C138主向重投%s（v01）' % eid in r for r in self.notes[eid]), eid)

    def test_batch9_cells_are_registered_but_not_signed(self):
        """第9批 41 格（前一轮 19 条替换旧格、第二轮 12 条里 10 条首占＋2 条替换第5格、
        第三轮 19 条判废重投的 v02 里 4 条首占、第四轮 15 条判废重投的 v02 里 3 条首占、
        第五轮 12 条待开图重投里 3 条首占）。
        占格必须自带出处（本轮文件名、被替换的旧格名、sha12、容器读数），
        又必须自带不签署的口径（无 image_prompt_sha256、写明绑定留空与不代签验收）。
        少了前一组，下一轮查不到这格是哪批；少了后一组，待复验会被读成已验收。"""
        for eid in self.BATCH9 + self.BATCH9C + self.BATCH9D + self.BATCH9E + self.BATCH9F:
            with self.subTest(eid=eid):
                self.assertEqual(check_cell_registration(self.items[eid], self.notes[eid]), [], eid)
        # 本轮 12 条的读数抬头与批次字段：首占 10 条只有一格，替换 2 条仍是五格
        for eid in self.BATCH9C:
            with self.subTest(eid=eid):
                expect = 5 if eid in ('R063', 'R066') else 1
                self.assertEqual(len(self.items[eid]['image_file']), expect, eid)
        # v02 四条都是首占：此前无格，所以清单里只许有一格。
        # 那一格现在挂的是最新一轮的图（C133 冻结重投替换的就是它），所以 v02 档只能查 C123 那条读数
        # 自己点名的文件与它是否还在盘上——按抬头取、不按位置取，同 cell_row 的理由。
        for eid in self.BATCH9D:
            with self.subTest(eid=eid):
                self.assertEqual(len(self.items[eid]['image_file']), 1, eid)
                row = round_row(eid, self.notes[eid], 'C123新串')
                self.assertIn('-v02_', row, eid)
                self.assertTrue(on_disk(registered_file(row, 'C123新串')), '%s 的 C123 v02 产物已不在盘' % eid)
        # 第四轮 v02 三条同样都是首占，且抬头必须写明本轮是第三投（C123 新串起算）——
        # 写错投次会让下一轮把「隔了几轮」读错，进而误判串档
        for eid in self.BATCH9E:
            with self.subTest(eid=eid):
                self.assertEqual(len(self.items[eid]['image_file']), 1, eid)
                row = round_row(eid, self.notes[eid], 'C123新串')
                self.assertIn('-v02_', row, eid)
                self.assertTrue(on_disk(registered_file(row, 'C123新串')), '%s 的 C123 v02 产物已不在盘' % eid)
                self.assertIn('重投第三投（v02）', row, eid)
                self.assertIn('本条此前无格，为首占', row, eid)
        # 第五轮（12 条待开图重投）3 条同样首占，抬头必须写第四投——C123 新串起算的第四投。
        # 这一轮与上一轮共用 v02 档串（提示词模板没换、prompt_sha256 变更 0/312），
        # 所以批次后缀仍是 v02；若把投次写成第五投就会和文档那套编号混起来。
        for eid in self.BATCH9F:
            with self.subTest(eid=eid):
                self.assertEqual(len(self.items[eid]['image_file']), 1, eid)
                row = round_row(eid, self.notes[eid], 'C123新串')
                self.assertIn('-v02_', row, eid)
                self.assertTrue(on_disk(registered_file(row, 'C123新串')), '%s 的 C123 v02 产物已不在盘' % eid)
                self.assertIn('重投第四投（v02）', row, eid)
                self.assertIn('本条此前无格，为首占', row, eid)
        # L061／L066 本轮占的是新串新文件，上一轮串外试投的「不回填」结论必须还在历史里。
        # 按内容存在性判而不是按倒数第几条：这条历史每被追加一次读数，位置就往后挪一格，
        # 抄位置等于把「追加了几类备注」钉进测试（2026-11-06 C项复看又追加了一类，位置已从 -2 漂到 -4）。
        for eid in ('L061', 'L066'):
            self.assertTrue(any('不回填' in r for r in self.notes[eid]),
                            '%s 的串外试投「不回填」结论在历史里查不到' % eid)

    def test_r1_backfill_is_registered_but_not_signed(self):
        """R1 回填 264 条的交付面：每条都要自带出处（本轮文件名、被替换的旧四向格、sha12、容器读数），
        又都不许被脚本签成已验收（status 待复验、acceptance 未动、摘要只有人工绑过的那 4 条才有）。

        为什么单列一条而不是并进 BATCH9 那条：BATCH9 管的是「按 C123 串重投的 41 条」，
        R1 是「按 C138 主向串放量 264 条」，两轮占的是同一格的两个版本，名单与档串都不同。
        名单不手抄：由清单 batch 后缀派生，派生出 264 这一数本身就是读数。"""
        c138 = sorted(i['id'] for i in self.manifest['items']
                      if str(i.get('batch') or '').endswith('C138主向重投-v01'))
        self.assertEqual(len(c138), 264)
        bound = [eid for eid in c138 if self.items[eid].get('image_prompt_sha256')]
        self.assertEqual(sorted(bound), ['D01', 'L007', 'L008', 'R043'],
                         '「全部占格」例外通道命中的条目变了，须先复核裁定再改名单')
        for eid in c138:
            with self.subTest(eid=eid):
                item = self.items[eid]
                self.assertEqual(check_cell_registration(item, self.notes[eid]), [], eid)
                self.assertEqual(item['status'], '待复验', eid)
                row = round_row(eid, self.notes[eid], 'C138主向重投')
                if eid in bound:
                    self.assertIn('维持原绑定', row, eid)
                else:
                    self.assertFalse(item.get('image_prompt_sha256'), eid)
                    self.assertIn('image_prompt_sha256 留空', row, eid)

    def test_r1_bound_summary_declaration_is_not_inert(self):
        """违例负测：新加的「已绑摘要占格须申报过期」判据必须能被坏数据打红。
        两个坏样本都取本轮真实会犯的错：占格时忘了申报（等于把旧验收洗成在册）、
        申报了但没复述那串摘要的前 12 位（下一轮无从查是哪一份绑定被维持）。"""
        eid = 'D01'
        item, rows = self.items[eid], self.notes[eid]
        sel = round_row(eid, rows, 'C138主向重投')
        self.assertTrue(sel, '基线：D01 的 C138 读数不在档')
        self.assertEqual(check_cell_registration(item, rows), [])
        bound = str(item['image_prompt_sha256'])
        for label, repl in (('漏申报', lambda r: r.replace('维持原绑定 %s' % bound[:12], 'image_prompt_sha256 留空')),
                            ('申报了但没复述前12位', lambda r: r.replace(bound[:12], ''))):
            with self.subTest(case=label):
                mutated = [(repl(r) if r == sel else r) for r in rows]
                self.assertNotEqual(mutated, rows, '%s 的替换没落地，负测无效' % label)
                self.assertTrue(check_cell_registration(item, mutated), label)

    def test_cell_registration_gate_reds_on_each_violation(self):
        """违例负测：占格判据的每一条都要能被造出来的坏数据打红，否则闸门是假绿。
        故障样本取自两轮真实做过的错法：留着旧格不替换、脚本替人工绑摘要、读数漏掉容器、
        batch 还停在上一档串、首占格数写错、旧格名与本轮新格同名。
        负测跑在两个视图上：最新一轮（2026-11-07 R2 回填后＝C133冻结重投）用现清单，
        C123 那轮的档位后缀与投次抬头用 as_of_round 还原视图——后一轮替换掉的是同一格，
        现清单里已经没有 C123 的产物可查，直接在现清单上跑这批负测会做成恒绿。"""
        base = self.items['L062']
        rows = self.notes['L062']
        sel = cell_row('L062', rows)[0]
        self.assertEqual(check_cell_registration(base, rows), [])
        cases = [
            ('追加不替换', lambda it: it['image_file'].append(it['image_file'][0]), rows),
            ('脚本代签绑摘要', lambda it: it.__setitem__('image_prompt_sha256', 'deadbeef' * 8), rows),
            ('状态洗成已验收', lambda it: it.__setitem__('status', '已验收'), rows),
            ('batch 停在旧档串', lambda it: it.__setitem__('batch', '标志性建筑-L062C118新串-v01'), rows),
        ]
        for label, mutate, note_rows in cases:
            with self.subTest(case=label):
                item = json.loads(json.dumps(base))
                mutate(item)
                self.assertTrue(check_cell_registration(item, note_rows), label)
        for repl, label in ((lambda r: r.replace('caBX=', ''), '读数漏容器'),
                            (lambda r: re.sub(r'替换(上一格|第\d+格)', '', r), '读数漏出处'),
                            (lambda r: r.replace('image_prompt_sha256 留空', ''), '读数漏绑定口径'),
                            (lambda r: r.replace('待复验', ''), '读数漏状态口径')):
            with self.subTest(case=label):
                mutated_rows = [(repl(r) if r == sel else r) for r in rows]
                self.assertNotEqual(mutated_rows, rows, '%s 的替换没落地，负测无效' % label)
                self.assertTrue(check_cell_registration(base, mutated_rows), label)
        # 本轮两种新口径各自的坏数据（C123 还原视图）
        first, first_rows = as_of_round(self.items['L063'], self.notes['L063'], 'C123新串')
        self.assertEqual(check_cell_registration(first, first_rows), [])
        with self.subTest(case='首占却占了两格'):
            item = json.loads(json.dumps(first))
            item['image_file'].append(item['image_file'][0])
            self.assertTrue(check_cell_registration(item, first_rows), '首占却占了两格')
        with self.subTest(case='首占读数不写口径'):
            mutated = json.loads(json.dumps(first_rows))
            mutated[-1] = mutated[-1].replace('本条此前无格，为首占', '')
            self.assertNotEqual(mutated, first_rows, '首占口径没抽干净，负测无效')
            self.assertTrue(check_cell_registration(first, mutated), '首占读数不写口径')
        fifth, fifth_rows = as_of_round(self.items['R063'], self.notes['R063'], 'C123新串')
        self.assertEqual(check_cell_registration(fifth, fifth_rows), [])
        with self.subTest(case='替换格号写成追加'):
            item = json.loads(json.dumps(fifth))
            item['image_file'].append(item['image_file'][-1])
            self.assertTrue(check_cell_registration(item, fifth_rows), '替换格号写成追加')
        with self.subTest(case='旧格名写成本轮新格'):
            mutated = json.loads(json.dumps(fifth_rows))
            mutated[-1] = mutated[-1].replace('vibe_images/R063-雨谷花园-B6雨后批-v01_1793684292566_98aa282d.png',
                                              registered_file(fifth_rows[-1], 'C123新串'))
            self.assertTrue(check_cell_registration(fifth, mutated), '旧格名写成本轮新格')
        with self.subTest(case='被替换的旧文件已不在盘'):
            mutated = json.loads(json.dumps(fifth_rows))
            mutated[-1] = mutated[-1].replace('R063-雨谷花园-B6雨后批-v01_1793684292566_98aa282d.png',
                                              'R063-雨谷花园-B6雨后批-v01_0000000000000000.png')
            self.assertTrue(check_cell_registration(fifth, mutated), '被替换的旧文件已不在盘')
        # v02 轮的坏数据：抬头写第二投却把批次留在 v01，等于把两版混读成一版
        v02, v02_rows = as_of_round(self.items['L090'], self.notes['L090'], 'C123新串')
        self.assertEqual(check_cell_registration(v02, v02_rows), [])
        self.assertIn('重投第二投（v02）', round_row('L090', self.notes['L090'], 'C123新串'),
                      'L090 抬头未写明第二投')
        with self.subTest(case='第二投读数配 v01 批次'):
            item = json.loads(json.dumps(v02))
            item['batch'] = item['batch'].replace('-v02', '-v01')
            self.assertTrue(check_cell_registration(item, v02_rows), '第二投读数配 v01 批次')
        # 同一 v02 串的第二投与第三投共用判据：抬头换投次、vNN 没换，批次仍该是 v02。
        # 这条负测钉的是「判据按抬头里的 vNN 走」而不是「判据认第二投」——
        # 判据若还写死「重投第二投」，L065 这类第三投读数会被要求成 v01、当场假红。
        v02b, v02b_rows = as_of_round(self.items['L065'], self.notes['L065'], 'C123新串')
        self.assertEqual(check_cell_registration(v02b, v02b_rows), [], '第三投读数在 v02 批次上应达标')
        self.assertIn('重投第三投（v02）', round_row('L065', self.notes['L065'], 'C123新串'),
                      'L065 抬头未写明第三投')
        with self.subTest(case='第三投读数配 v01 批次'):
            item = json.loads(json.dumps(v02b))
            item['batch'] = item['batch'].replace('-v02', '-v01')
            self.assertTrue(check_cell_registration(item, v02b_rows), '第三投读数配 v01 批次')
        with self.subTest(case='抬头换档号但批次没换'):
            mutated = json.loads(json.dumps(v02b_rows))
            mutated[-1] = mutated[-1].replace('重投第三投（v02）', '重投第三投（v03）')
            self.assertTrue(check_cell_registration(v02b, mutated), '抬头写 v03 但批次仍是 v02')
        # 第五轮（12 条待开图重投）与第四轮同用 v02：投次中文数字涨了、档号没涨，判据仍该认 v02。
        # 这条负测钉的是「闸门按抬头里的 vNN 取档号」——若有人把判据改成按投次中文数字分叉，
        # 第四投读数会被要求成 v03 批次、当场假红。
        v02c, v02c_rows = as_of_round(self.items['L093'], self.notes['L093'], 'C123新串')
        self.assertEqual(check_cell_registration(v02c, v02c_rows), [], '第四投读数在 v02 批次上应达标')
        self.assertIn('重投第四投（v02）', round_row('L093', self.notes['L093'], 'C123新串'),
                      'L093 抬头未写明第四投')
        with self.subTest(case='第四投读数配 v01 批次'):
            item = json.loads(json.dumps(v02c))
            item['batch'] = item['batch'].replace('-v02', '-v01')
            self.assertTrue(check_cell_registration(item, v02c_rows), '第四投读数配 v01 批次')
        # 还原视图自己也要能被证伪：as_of_round 若没把后一轮的读数剔干净，选中的就不是 C123 那条，
        # 上面这批「C123 抬头要求 vNN 批次」的负测会失去承载（判据查的是另一轮的批次串）。
        for eid in ('L090', 'L065', 'L093', 'L063', 'R063'):
            with self.subTest(case='还原视图选中行仍是 C123 抬头 ' + eid):
                item, view = as_of_round(self.items[eid], self.notes[eid], 'C123新串')
                self.assertTrue(cell_row(eid, view)[0].startswith('C123新串%s重投' % eid), eid)
                self.assertEqual(view[-1], cell_row(eid, view)[0], eid)

    def test_c126_rod_and_crane_tiering_carries_its_measurements(self):
        """C126 两档读数的达标面：占格的条目在备注里，判废的条目只活在批次读数稿里，两边都要查。
        判废条目不回填真源，所以闸门直接读 工具/batch9d…／batch9e…/readings_draft.json——
        那条阈值管的是全部按 C126 判过的读数，不因条目没占格就免检。
        两轮各自把「哪些读数提到细杆」钉成名单：名单涨了说明新一轮又出现了需量阈值的条目，
        漏量就判红；名单少了说明有人把阈值项从读数里删掉了，同样判红。"""
        rounds = {
            'batch9d_2026_11_05': (['L080', 'L107', 'L108'], ['L095']),
            # 第四投 15 条里 13 条提到屋面细杆／细针，只有 L065 之外的 L104／L107 两条写明「阈值项不适用」
            'batch9e_2026_11_05': (['L065', 'L081', 'L083', 'L085', 'L093', 'L094', 'L099', 'L100',
                                    'L101', 'L103', 'L105', 'L106', 'L108'], []),
            # 第五投 12 条里 9 条提到远景塔冠细针／屋面细杆并给了两个像素数（全部判废、不回填真源），
            # 达标 3 条（L093／L101／L108）画面里没有过阈值线的细杆，因此不进名单。
            'batch9f_2026_11_06': (['L081', 'L083', 'L085', 'L094', 'L099', 'L100', 'L103',
                                    'L105', 'L106'], []),
            # 第六投 8 张读数全部判废，判废依据是 C123「未点名独立远景对象入画」——栋数与冠部直读即可复核，
            # 本轮没有按 C126 量杆高比值（自动量杆的两版脚本在玻璃亮塔与云背景下给出的比值互相矛盾，不采信），
            # 因此两份名单都必须是空；涨了说明有人补了阈值读数却没登记，少了说明这份口径被删了。
            'batch9g_2026_11_06': ([], []),
        }
        registered = {'batch9d_2026_11_05': self.BATCH9D, 'batch9e_2026_11_05': self.BATCH9E,
                      'batch9f_2026_11_06': self.BATCH9F, 'batch9g_2026_11_06': ()}
        for folder, (expect_rod, expect_crane) in rounds.items():
            draft = json.loads((ROOT / '工具' / folder / 'readings_draft.json')
                               .read_text(encoding='utf-8'))
            rod = sorted(k for k, v in draft.items() if 'C126' in v and ROD_HEIGHT_RE.search(v))
            crane = sorted(k for k, v in draft.items() if 'C126' in v and '吊机' in v)
            self.assertEqual(rod, expect_rod, folder)
            self.assertEqual(crane, expect_crane, folder)
            for eid, text in list(draft.items()):
                with self.subTest(case=folder + ' 读数稿' + eid):
                    self.assertEqual(check_c126_reading(text), [], eid)
            for eid in registered[folder]:
                with self.subTest(case=folder + ' 备注' + eid):
                    for row in self.notes[eid]:
                        self.assertEqual(check_c126_reading(row), [], eid)
        # 违例负测：把量出来的数从读数里抽掉，判据必须判红——只剩结论的读数无法复核档位来源
        draft9d = json.loads((ROOT / '工具' / 'batch9d_2026_11_05' / 'readings_draft.json')
                             .read_text(encoding='utf-8'))
        base = draft9d['L080']
        self.assertEqual(check_c126_reading(base), [])
        for token, label in (('约 360 像素', '抽掉可见塔身'), ('网格', '抽掉网格来源'),
                             ('分之一', '抽掉分母')):
            with self.subTest(case=label):
                self.assertTrue(check_c126_reading(base.replace(token, '')), label)
        with self.subTest(case='塔吊不写所在层'):
            mutated = draft9d['L095'].replace('街面', '').replace('天际线', '')
            self.assertTrue(check_c126_reading(mutated), '塔吊不写所在层')
        # 本轮占格条目（L065）同型负测：本轮的数与备注是同一份文本，抽掉任一项都得判红
        draft9e = json.loads((ROOT / '工具' / 'batch9e_2026_11_05' / 'readings_draft.json')
                             .read_text(encoding='utf-8'))
        base9e = draft9e['L065']
        self.assertEqual(check_c126_reading(base9e), [])
        for token, label in (('约 440 像素', '本轮抽掉可见塔身'), ('约 15 像素', '本轮抽掉杆高'),
                             ('网格', '本轮抽掉网格来源'), ('分之一', '本轮抽掉分母')):
            with self.subTest(case=label):
                self.assertTrue(check_c126_reading(base9e.replace(token, '')), label)
        # 第五投的读数同型负测：本轮把「占比 N%」之外补成了「塔身只有杆高的 K 倍」，
        # 抽掉来源网格图、两个像素数或对十二分之一线的倍数比较，任一项都得判红。
        draft9f = json.loads((ROOT / '工具' / 'batch9f_2026_11_06' / 'readings_draft.json')
                             .read_text(encoding='utf-8'))
        base9f = draft9f['L081']
        self.assertEqual(check_c126_reading(base9f), [])
        for token, label in (('约 70 像素', '第五投抽掉杆高'), ('约 310 像素', '第五投抽掉可见塔身'),
                             ('网格', '第五投抽掉网格来源'),
                             ('十二分之一', '第五投抽掉阈值分母')):
            with self.subTest(case=label):
                self.assertTrue(check_c126_reading(base9f.replace(token, '')), label)

    def test_batch9g_rejected_all_eight_and_left_the_manifest_untouched(self):
        """第六投 8 张全判废、真源一字未动：这条把「判废即不占格」与「读数自带切片出处」钉住。

        为什么单独钉这一轮：前几轮总有救回项，回填脚本一跑就会动清单；本轮救回 0 条，
        任何一条读数被误派生成干净项都会往清单里塞一格、把状态刷成待复验。
        判废句的派生口径直接 import 回填脚本，测试里不抄第二份 HARD/SOFT。
        """
        sys.path.insert(0, str(ROOT / '工具' / 'batch9g_2026_11_06'))
        import backfill_batch9g as g9
        folder = ROOT / '工具' / 'batch9g_2026_11_06'
        draft = json.loads((folder / 'readings_draft.json').read_text(encoding='utf-8'))
        self.assertEqual(sorted(draft), ['L081', 'L083', 'L085', 'L094', 'L099', 'L100',
                                         'L103', 'L105'], '第六投只有带内 8 张有读数')
        mea = json.loads((folder / 'batch9g_measure.json').read_text(encoding='utf-8'))
        rows = mea['rows'] if isinstance(mea, dict) else mea
        self.assertEqual(sorted(r['id'] for r in rows), sorted(draft))
        for eid, text in sorted(draft.items()):
            with self.subTest(case='第六投读数' + eid):
                self.assertFalse(g9.is_clean(text), '%s 被派生成干净项' % eid)
                self.assertIn('本条只记人工读数，不代签验收。', text)
                self.assertIn('crops/%s_网格_' % eid, text, '%s 未交代切片出处' % eid)
                self.assertEqual(check_c126_reading(text), [], eid)
        # 清单侧：9 条（含第 9 次发起被服务端 403 code 112 拒了、无产物的 L106）一律维持待开图
        for eid in sorted(draft) + ['L106']:
            item = self.items[eid]
            with self.subTest(case='第六投未占格' + eid):
                self.assertEqual(item['status'], '待开图', eid)
                self.assertFalse(item.get('image_file'), eid)
                self.assertFalse(item.get('image_prompt_sha256'), eid)
                self.assertFalse([r for r in self.notes.get(eid, []) if '重投第五投（v02）' in r],
                                 '%s 的判废读数进了真源备注' % eid)
        # 违例负测：把 L081 的判废句抽掉，派生名单立刻涨出一条「干净项」，
        # 而它在清单里既无格也无重投读数——占格判据必须判红，不许脚本替它补一格。
        stripped = re.sub(r'判废：[^。]*。', '', draft['L081'], count=1)
        self.assertTrue(g9.is_clean(stripped), '判废句没抽干净，负测无效')
        with self.subTest(case='第六投抽掉判废句即判红'):
            mutated = dict(draft)
            mutated['L081'] = stripped
            self.assertEqual([k for k, v in sorted(mutated.items()) if g9.is_clean(v)], ['L081'])
            self.assertEqual(check_cell_registration(self.items['L081'], self.notes.get('L081', [])),
                             ['本轮重投读数不在档'])

    def test_reread_appended_after_registration_does_not_move_the_cell_verdict(self):
        """复看补写往同一 ID 追加读数后，占格判据仍查重投那条：按位置取会指到补写上、把达标判成违例。
        2026-11-05 那轮 6 条牌面缺口补写就是这种数据形态（L064 现档即如此）。
        2026-11-07 R2 回填把本轮抬头追加到了末位，所以这条改成注入式：
        在选中的那条之后再挂一条复看补写，判据必须仍达标；只看 rows[-1] 的写法会当场判红。"""
        eid = 'L064'
        rows = self.notes[eid]
        sel, token, mode = cell_row(eid, rows)
        self.assertEqual(check_cell_registration(self.items[eid], rows), [], eid)
        self.assertGreater(len(rows), 2, eid)
        injected = list(rows) + ['复看补写（不动占格）：牌面亮度复看，未换图、未换格。']
        self.assertEqual(check_cell_registration(self.items[eid], injected), [], eid)
        self.assertNotEqual(injected[-1], sel, '注入条没落在选中条之后，这条负测无效')
        pos_rows = list(rows[:rows.index(sel)]) + [injected[-1]]
        self.assertTrue(check_cell_registration(self.items[eid], pos_rows),
                        '按位置取没有代价，说明这条负测没测到选取本身')

    def test_history_survives_and_note_still_derives(self):
        # 308 条没有人工长文本，历史是空数组：判"键在不在"而不是"值真不真"；键随名录扩到312条
        self.assertEqual(sum(1 for i in self.items.values() if 'review_note_history' in i), 312)
        # 带人工长文本的条数不抄第二份：以 数据/开图验收备注.json 的 ID 数为真源对拍，
        # 顺带兜住「备注里写了但没镜像进清单」和「备注里有清单外 ID」两种断链。
        # 沿革：第9批五轮回填到 67 条；2026-11-06 C项复看为 L001—L006 新记 6 条判废读数，那时 73 条；
        # 2026-11-07 R1 回填 264 条各追加一条登记备注，现为 304 键。键数不抄第二份，判据拿 len(self.notes) 现算。
        self.assertEqual(sum(1 for i in self.items.values() if i['review_note_history']), len(self.notes))
        self.assertTrue(set(self.notes) <= set(self.items),
                        '备注里有清单外的 ID：%s' % sorted(set(self.notes) - set(self.items)))
        # 逐条对拍不按批次名单走：备注是唯一可编辑源，清单的 review_note_history 由生成器镜像，
        # 按名单循环等于每加一轮回填就要改一次名单，漏改那轮就是假绿（R1 回填 264 条时名单外全是盲区）。
        for eid in self.notes:
            hist = self.items[eid]['review_note_history']
            self.assertEqual(hist, self.notes[eid], eid)
            self.assertIn(self.notes[eid][-1], self.items[eid]['review_note'], eid)
        self.assertEqual(self.manifest['needs_review'], 303)
        self.assertEqual(self.manifest['accepted'], 0)
        self.assertEqual(self.manifest['generated'], 303)
        # 第9批 48 条放量走到第五投后：d 轮 19 条第二投里 4 条无判废项占了格，第四投里 15 条又有 3 条占了格，
        # 第五投（12 条待开图重投）里再有 3 条占了格。generated/needs_review 按有图的 303 条计，
        # pending 只留真正无图的 9 条——本轮仍判废的 9 条不占格，退回待开图。
        self.assertEqual(self.manifest['pending'], 9)


def jpeg(segments):
    """按 marker＋body 拼一段合法 JPEG：size 字段＝2＋body 长度，含 size 自身。
    夹具里的段长必须由这个函数算出来，不能手写常数——手写 40／56 会让核验器在长度不符时
    提前 break，把「XMP 缺 TC260」误判成「缺XMP段」，测的就不是那条判据了。"""
    body = b'\xff\xd8'
    for marker, payload in segments:
        body += marker + (len(payload) + 2).to_bytes(2, 'big') + payload
    return body + b'\xff\xd9'


def write_jpeg(name, segments):
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    (tmp / name).write_bytes(jpeg(segments))
    return tmp


XMP_NS = b'http://ns.adobe.com/xap/1.0/\x00'


def png(caBX_payload=None, ihdr=True, itxt_payload=None):
    """拼一个真 PNG 外壳：IHDR＋可选 caBX＋可选 iTXt＋IEND。块长度字段必须实算，
    写死常数会让核验器在长度不符时提前退出，测的就不是 caBX 那条判据了。
    iTXt 是 C136 补的第二条 PNG 容器支路，夹具与 caBX 走同一个 _chunk，避免两种壳只有一种被真读过。"""
    out = b'\x89PNG\r\n\x1a\n'
    if ihdr:
        out += _chunk(b'IHDR', bytes(13))
    if caBX_payload is not None:
        out += _chunk(b'caBX', caBX_payload)
    if itxt_payload is not None:
        out += _chunk(b'iTXt', itxt_payload)
    return out + _chunk(b'IEND', b'')


def _chunk(kind, payload):
    body = kind + payload
    import zlib
    return len(payload).to_bytes(4, 'big') + body + \
        zlib.crc32(body).to_bytes(4, 'big')


def write_png(name, caBX_payload=None, itxt_payload=None):
    import tempfile
    tmp = Path(tempfile.mkdtemp())
    (tmp / name).write_bytes(png(caBX_payload, itxt_payload=itxt_payload))
    return tmp


class AssetGate(unittest.TestCase):
    def setUp(self):
        import verify_image_assets as va
        self.va = va
        self.manifest = json.loads((ROOT / '数据' / '开图清单.json').read_text(encoding='utf-8'))
        self.report = json.loads((ROOT / '数据' / '图片资产核验.json').read_text(encoding='utf-8'))

    def test_paths_are_authoritative_and_unique(self):
        paths = [p for i in self.manifest['items'] if i.get('image_file') for p in i['image_file']]
        # 第五投首占 3 格后：1113＋3＝1116 格，有图条目 300＋3＝303 条
        self.assertEqual(len(paths), 1116)
        self.assertEqual(len(set(paths)), 1116)
        self.assertEqual(sum(1 for i in self.manifest['items'] if i.get('image_file')), 303)

    def test_report_all_green_and_disclaims(self):
        self.assertEqual(self.report['文件格数'], 1116)
        self.assertEqual(self.report['失败格数'], 0)
        self.assertEqual(self.report['通过格数'], 1116)
        # 回填的 E1 批次格必须真按容器计入，否则「认容器是识别」只写在裁定里、查不到证据。
        # C2PA 在位 2 格、iTXt 在位 58 格是 C136 那轮 R2 回填换档的结果；2026-11-07 R1 回填把
        # 264 个四向 jpg 格替换成同通道产物（逐枚现读 caBX=0／iTXt=1），iTXt 档因此 58→322。
        # 仍留在 caBX 档的只有阶段6首批 B3 样本 S02／S18 两格（早先归因里的 R009／夜光／清晨／雨后／晴日
        # 等批次格已被后续轮次的 image_file 替换覆盖，那串 57 格的构成注释到本轮已过期，故按明细重写）。
        self.assertEqual(self.report['C2PA在位格数'], 2)
        self.assertEqual(self.report['iTXt标识在位格数'], 322)
        self.assertNotIn('已验收', json.dumps(self.report, ensure_ascii=False))
        self.assertIn('结构合规不等于视觉验收', self.report['声明'])

    def test_c2pa_absent_on_gallery_is_expected_not_failure(self):
        # 图集那批只写 XMP·TC260，C2PA 缺位不判红也不催办；容器计数要与逐格结论对得上，不能各报各的。
        self.assertEqual(self.report['C2PA在位格数'], self.report['容器计数']['C2PA(caBX)'])
        self.assertEqual(self.report['iTXt标识在位格数'], self.report['容器计数']['iTXt·TC260'])
        self.assertEqual(sum(self.report['容器计数'].values()), self.report['通过格数'])

    def test_two_containers_are_the_delivery_criterion(self):
        # JPEG 走 XMP·TC260（C97），PNG 走 caBX·C2PA（C97）或 iTXt 字样（C136）；C83 的「不属交付判据」只对 JPEG 侧成立，
        # 这句必须在核验产物里写清，否则下一轮又会把 PNG 判成不合规或把 JPEG 放松。
        for token in ('两条被接受的标识容器（C97）', '不放松原 JPEG 路径', 'C136'):
            self.assertIn(token, self.report['判据'])
        for token in ('C83', 'C97', 'C136', '不得由脚本给图片补写元数据过闸'):
            self.assertIn(token, self.report['C2PA口径'])
        # C136 推翻的正是「无 caBX 一律判红」这句原话；旧口径留在产物里就会把 iTXt 档重新判红。
        self.assertNotIn('一律判红', self.report['C2PA口径'])
        self.assertIn('至少其一在位', self.report['判据'])
        self.assertIn('iTXt', self.report['提示口径'])
        self.assertIn('只记提示、不判红', self.report['提示口径'])
        self.assertNotIn('本期不改名', self.report['提示口径'])
        self.assertIn('rename_gallery_ext', self.report['提示口径'])

    def test_extension_mismatch_is_advisory(self):
        # 判据行为本身：字节对、元数据全，只扩展名不符 → 通过但记提示，绝不判红
        tmp = write_jpeg('真JPEG假扩展名.png', [(b'\xff\xe1', XMP_NS + b'<x:xmpmeta>TC260 AIGC</x:xmpmeta>')])
        got = self.va.check([{'id': 'X007', 'image_file': ['真JPEG假扩展名.png']}], root=tmp)
        self.assertEqual((got['通过格数'], got['失败格数'], got['提示格数']), (1, 0, 1))
        self.assertIn('扩展名', self.report['提示口径'])

    def test_gallery_extension_is_normalised(self):
        self.assertEqual(self.report['提示格数'], 0)
        self.assertEqual(self.report['失败格数'], 0)
        paths = [p for i in self.manifest['items'] if i.get('image_file') for p in i['image_file']]
        self.assertEqual(len(paths), 1116)
        # C82 的归一只管 图集/ 那批；E1 放量批次与 C105／C106 重出批次（C97 起认 caBX·C2PA 容器）
        # 是真 PNG，按字节与容器引用，不改名也不要求它变成 .jpg。
        # 不按根前缀而按子串分类：B 前置裁定后 image_file 过渡期整体挂在 backup/ 镜像路径（§50.3），
        # 303 条重投后还要整体切回 数据/图集/ —— 认子串两侧都不用再改这条断言。
        # 图集外 324 格＝R2 回填 58 格 ＋ 2026-11-07 R1 回填替换进来的 264 个主向格；
        # 图集侧那 1056 张 jpg 因此只剩 792，两个数恒该加起来等于总格数 1116，所以按和来钉、不各抄一份。
        gallery = [p for p in paths if '数据/图集/' in p]
        out_of_gallery = [p for p in paths if '数据/图集/' not in p]
        self.assertEqual(len(gallery) + len(out_of_gallery), 1116)
        self.assertEqual(len(out_of_gallery), 324)
        for p in gallery:
            self.assertTrue(p.lower().endswith(('.jpg', '.jpeg')), p)
            self.assertTrue((ROOT / p).is_file(), p)
        for p in out_of_gallery:
            self.assertTrue(p.lower().endswith('.png'), p)
            self.assertTrue((ROOT / p).is_file(), p)

    def test_out_of_gallery_extension_sweep_is_advisory(self):
        """图集外体检的两条支路分开钉：真盘面（归档后只剩定档后图片，实测零不符）＋夹具面（有过期扩展名必须抓到）。

        2026-11-06 实测教训：早于 E1 定档的 187 张按移交清单 §52 归档进 backup/ 后，原先那 46 张
        「.png 装 JPEG 字节」的卡面整体退出体检面（扫描数 232→45、不一致 46→0）。只把断言改成
        「等于 0」会把这段判据静默废掉——所以不符形态改由夹具现场喂给同一个函数自证，真盘侧只钉
        「扫到的文件数与独立走盘一致」这条非惰性读数。归档区无人核验的后果已申报在 §53.3／§53.6。
        """
        sweep = self.report['图集外扩展名体检']
        self.assertEqual(sweep['判红数'], 0)
        refs = {p for i in self.manifest['items'] if i.get('image_file') for p in i['image_file']}
        self.assertFalse(set(sweep['明细']) & refs)
        self.assertIn('按文件名引用', sweep['不改名口径'])
        self.assertIn('2026-11-06', sweep['不改名口径'])
        live = sum(1 for dp, dn, fn in os.walk(ROOT / '数据')
                   for f in fn if os.path.splitext(f)[1].lower() in self.va.IMG_EXT
                   and not (Path(dp) / f).relative_to(ROOT).as_posix().startswith('数据/图集'))
        self.assertEqual(sweep['扫描数'], live, '体检扫描面与独立走盘不一致，多半是排除规则或目录结构变了')
        self.assertGreater(sweep['扫描数'], 0)
        self.assertEqual(sweep['不一致数'], 0, '归档后 数据/ 下若再长出过期扩展名，先复核定档后批次再改这条')

        import shutil
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        bad_dir = tmp / '数据' / '视觉控制资产' / '卡牌'
        ok_dir = tmp / '数据' / '影像作品' / '素材'
        bad_dir.mkdir(parents=True)
        ok_dir.mkdir(parents=True)
        (bad_dir / '假PNG真JPEG.png').write_bytes(b'\xff\xd8\xff' + bytes(20))
        (bad_dir / '另一张假PNG真JPEG.png').write_bytes(b'\xff\xd8\xff\xe0' + bytes(15))
        (ok_dir / '真PNG.png').write_bytes(png())
        (ok_dir / '假JPG真PNG.jpg').write_bytes(png())
        got = self.va.sweep_extensions(tmp)
        self.assertEqual((got['扫描数'], got['不一致数'], got['判红数']), (4, 3, 0), got)
        for token in ('影像作品', '视觉控制资产'):
            self.assertIn(token, json.dumps(got['按目录'], ensure_ascii=False))
        self.assertEqual({Path(b).name for b in got['明细']},
                         {'假PNG真JPEG.png', '另一张假PNG真JPEG.png', '假JPG真PNG.jpg'})
        shutil.rmtree(tmp, ignore_errors=True)
        self.assertFalse(tmp.exists())

    def test_missing_file_fixture_red(self):
        import tempfile
        items = [{'id': 'X001', 'image_file': ['数据/图集/不存在-甲.png']}]
        bad = self.va.check(items, root=Path(tempfile.mkdtemp()))
        self.assertEqual(bad['失败明细'][0]['原因'], '文件缺失')

    def test_stripped_metadata_fixture_red(self):
        tmp = write_jpeg('无元数据.jpg', [(b'\xff\xe0', b'JFIF\x00' + bytes(10))])
        bad = self.va.check([{'id': 'X002', 'image_file': ['无元数据.jpg']}], root=tmp)
        self.assertEqual(bad['失败明细'][0]['原因'], '缺XMP段')

    def test_xmp_without_tc260_fixture_red(self):
        tmp = write_jpeg('有XMP无TC260.jpg', [(b'\xff\xe1', XMP_NS + b'<x:xmpmeta><a>TCAAA</a></x:xmpmeta>')])
        bad = self.va.check([{'id': 'X003', 'image_file': ['有XMP无TC260.jpg']}], root=tmp)
        self.assertEqual(bad['失败明细'][0]['原因'], 'XMP缺TC260标识')

    def test_xmp_without_aigc_fixture_red(self):
        tmp = write_jpeg('有TC260无AIGC.jpg', [(b'\xff\xe1', XMP_NS + b'<x:xmpmeta>TC260</x:xmpmeta>')])
        bad = self.va.check([{'id': 'X004', 'image_file': ['有TC260无AIGC.jpg']}], root=tmp)
        self.assertEqual(bad['失败明细'][0]['原因'], 'XMP缺AIGC标识')

    def test_bare_png_without_caBX_fixture_red(self):
        # C97 后 PNG 是被接受的容器，所以「PNG 但没标识块」必须从「非JPEG字节头」改判为容器缺位，
        # 而不是被旧口径误当成 JPEG 缺 XMP——两种原因对应的修法完全不同。
        # C136 起这条只在两档都缺位时才成立：iTXt 带着 TC260 字样就必须放行（见下面 iTXt 三条夹具）。
        tmp = write_png('无标识块.png')
        bad = self.va.check([{'id': 'X005', 'image_file': ['无标识块.png']}], root=tmp)
        self.assertEqual(bad['失败明细'][0]['原因'], 'PNG缺标识容器（无caBX，iTXt亦缺TC260／AIGC字样）')

    def test_neither_jpeg_nor_png_magic_fixture_red(self):
        import tempfile
        tmp = Path(tempfile.mkdtemp())
        (tmp / '假图.jpg').write_bytes(b'GIF89a' + bytes(24))
        bad = self.va.check([{'id': 'X011', 'image_file': ['假图.jpg']}], root=tmp)
        self.assertEqual(bad['失败明细'][0]['原因'], '字节头既非JPEG亦非PNG')

    def test_png_caBX_with_c2pa_declaration_passes(self):
        tmp = write_png('带C2PA.png', b'urn:c2pa:abcd jumb '
                        b'http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia')
        ok = self.va.check([{'id': 'X012', 'image_file': ['带C2PA.png']}], root=tmp)
        self.assertEqual((ok['通过格数'], ok['失败格数'], ok['提示格数'], ok['C2PA在位格数']), (1, 0, 0, 1))
        self.assertEqual(ok['逐格'][0]['标识容器'], 'C2PA(caBX)')

    def test_png_caBX_missing_generative_declaration_fixture_red(self):
        # 有 C2PA 清单但没有生成式来源声明＝容器在、标识不在，必须判红；
        # 这条就是「不得由脚本补写元数据过闸」的反面：判据认的是平台写进去的声明。
        tmp = write_png('有清单无声明.png', b'urn:c2pa:abcd jumb c2pa.actions.v2')
        bad = self.va.check([{'id': 'X013', 'image_file': ['有清单无声明.png']}], root=tmp)
        self.assertEqual(bad['失败明细'][0]['原因'], 'caBX缺生成式AI标识')

    def test_png_caBX_without_c2pa_manifest_fixture_red(self):
        tmp = write_png('有块无清单.png', b'trainedAlgorithmicMedia Generated with AI')
        bad = self.va.check([{'id': 'X014', 'image_file': ['有块无清单.png']}], root=tmp)
        self.assertEqual(bad['失败明细'][0]['原因'], 'caBX缺C2PA清单')

    def test_png_itxt_with_tc260_fixture_green(self):
        """C136 第二档的正检：无 caBX、只有带 TC260 字样的 iTXt，必须判通过并记进 iTXt·TC260 档。

        这条就是本轮改掉的那处假绿的正面证据——旧 sniff 的 PNG 分支只走 caBX，
        对这类字节读都不读就判红，R2 回填的 58 格全靠它撑着。
        """
        tmp = write_png('无块有iTXt.png',
                        itxt_payload=b'XML:com.adobe.xmp\x00<rdf:Description TC260:AIGC="true"/>')
        ok = self.va.check([{'id': 'X015', 'image_file': ['无块有iTXt.png']}], root=tmp)
        self.assertEqual((ok['通过格数'], ok['失败格数'], ok['提示格数']), (1, 0, 0))
        self.assertEqual(ok['逐格'][0]['标识容器'], 'iTXt·TC260')
        self.assertEqual(ok['容器计数']['iTXt·TC260'], 1)
        # iTXt 档不该被算进 C2PA 在位：两个计数各数各的，混了就等于把 C136 说成 C2PA 达标。
        self.assertEqual(ok['C2PA在位格数'], 0)
        self.assertEqual(ok['iTXt标识在位格数'], 1)

    def test_png_itxt_without_marks_fixture_red(self):
        # 负测：iTXt 块在位但里面没有 TC260／AIGC 字样＝容器在、标识不在，仍须判红；
        # 判据认的是字样，不是「有个 iTXt 就算过」。去掉这条会让任何带文本块的 PNG 蒙过闸。
        tmp = write_png('有iTXt无字样.png', itxt_payload=b'XML:com.adobe.xmp\x00<rdf:Description/>')
        bad = self.va.check([{'id': 'X016', 'image_file': ['有iTXt无字样.png']}], root=tmp)
        self.assertEqual(bad['失败明细'][0]['原因'], 'PNG缺标识容器（无caBX，iTXt亦缺TC260／AIGC字样）')

    def test_png_caBX_broken_does_not_relax_to_itxt_when_itxt_absent(self):
        # 两条 PNG 支路互不放松：caBX 在位但清单/声明缺一角时仍判红，不能因为「还有 iTXt 这条路」就放行。
        # 这条与下一条（caBX 坏 + iTXt 好）合起来钉住判据的先后：先看 caBX 整条链，缺位才退 iTXt。
        tmp = write_png('有块无清单也全无iTXt.png', b'urn:c2pa:abcd jumb')
        bad = self.va.check([{'id': 'X017', 'image_file': ['有块无清单也全无iTXt.png']}], root=tmp)
        self.assertEqual(bad['失败明细'][0]['原因'], 'caBX缺生成式AI标识')
        self.assertEqual(bad['容器计数']['C2PA(caBX)'], 0)

    def test_png_caBX_broken_with_good_itxt_passes_on_itxt(self):
        # C136 的「至少其一在位」按整块成立：caBX 那侧清单不全但 iTXt 带着 TC260 时按 iTXt 档放行。
        # 反过来若只按通道名推定（文本生图⇒caBX、图生图⇒iTXt），这一格就会被读成不合规，判据就退回去了。
        tmp = write_png('块坏iTXt好.png', b'urn:c2pa:abcd jumb',
                        itxt_payload=b'XML:com.adobe.xmp\x00TC260 AIGC')
        ok = self.va.check([{'id': 'X018', 'image_file': ['块坏iTXt好.png']}], root=tmp)
        self.assertEqual(ok['通过格数'], 1)
        self.assertEqual(ok['逐格'][0]['标识容器'], 'iTXt·TC260')

    def test_image_file_pngs_are_all_green_live(self):
        """真盘面：清单里每一个 PNG 格逐枚现读必须绿，且两档容器数与产物里的计数一致。

        读的是字节而不是 数据/图片资产核验.json——那产物本身可能过期（2026-11-06 那次假绿就是它停在
        旧判据上、报 1116 全通过而现读 58 判红），过期由 verify_asset_report_freshness 单独守；
        这条负责证明「现在的字节按现在的判据是绿的」。
        """
        paths = [p for i in self.manifest['items'] if i.get('image_file') for p in i['image_file']
                 if p.lower().endswith('.png')]
        # 324＝R2 回填的 58 格＋2026-11-07 R1 回填替换进来的 264 格；这条钉的是「PNG 交付面没被悄悄换小」，
        # 两档桶之和与它相等由下面那条对拍兜住，容器读数本身仍以现读字节为准。
        self.assertEqual(len(paths), 324)
        buckets = {'C2PA(caBX)': 0, 'iTXt·TC260': 0}
        for p in paths:
            with self.subTest(path=p):
                info = self.va.sniff(ROOT / p)
                self.assertIsNone(self.va.verdict(info), p)
                self.assertIn(info['标识容器'], buckets, p)
                buckets[info['标识容器']] += 1
        self.assertEqual(sum(buckets.values()), len(paths), '有 PNG 格没落进任一容器档，走盘与分档面不一致')
        self.assertEqual(buckets['C2PA(caBX)'], self.report['容器计数']['C2PA(caBX)'])
        self.assertEqual(buckets['iTXt·TC260'], self.report['容器计数']['iTXt·TC260'])

    def test_archived_e1_pngs_carry_the_accepted_container(self):
        # 真实夹具：归档的 E1 定档与重出图必须被新判据认下，不能只靠合成字节自证。
        import glob
        paths = sorted(glob.glob(str(ROOT / '数据' / '视觉控制资产' / 'E1定档-20261103' / '*.png')))
        self.assertEqual(len(paths), 12)
        for p in paths:
            with self.subTest(path=os.path.relpath(p, ROOT)):
                info = self.va.sniff(Path(p))
                self.assertEqual((info['PNG'], info['caBX'], info['C2PA'], info['AIGC声明']),
                                 (True, True, True, True))
                self.assertEqual(info['标识容器'], 'C2PA(caBX)')
                self.assertIsNone(self.va.verdict(info))

    def test_c2pa_box_fixture_does_not_turn_xmp_green(self):
        tmp = write_jpeg('带jumb.jpg', [(b'\xff\xeb', b'jumb' + bytes(20)),
                                        (b'\xff\xe1', XMP_NS + b'<x:xmpmeta>TC260 AIGC</x:xmpmeta>')])
        ok = self.va.check([{'id': 'X006', 'image_file': ['带jumb.jpg']}], root=tmp)
        self.assertEqual((ok['通过格数'], ok['C2PA在位格数']), (1, 1))

    def test_recheck_worksheet_lists_every_id(self):
        md = (ROOT / '数据' / '图片复验清单.md').read_text(encoding='utf-8')
        items = json.loads((ROOT / '数据' / '开图清单.json').read_text(encoding='utf-8'))['items']
        rows = len(re.findall(r'^\| [DFLRS]\d+ \|', md, re.M))
        # 工作单由 verify_image_assets 逐条遍历清单派生，所以行数必须等于清单条目数（含「无图」占位行）。
        # 2026-11-02 实测教训：2-A 扩到 312 条后没重跑这张下游表，它还停在 264 行旧禁则上，硬编码行数的旧断言反而看不见。
        self.assertEqual(rows, len(items), '图片复验清单未随开图清单重跑，属过期生成物')
        self.assertEqual(md.count('| 无图 |'), sum(1 for item in items if not item.get('image_file')))
        self.assertNotIn('第二座超两百米', md)
        for token in ('结构合规不等于视觉验收', '待人工复验', '不得由脚本代签', '图集外扩展名体检', '只报不办、不改名'):
            self.assertIn(token, md)

    def test_worksheet_missing_the_new_rows_would_fail_that_gate(self):
        # 负测：2-A 那轮的故障是清单已扩到 312 条而工作单还是扩容前的行数。
        # 用真渲染函数造一张 264 行的过期单，上面的行数判据必须判红，否则该闸门是假绿。
        stale = self.manifest['items'][:264]
        md = self.va.render_worksheet(self.va.check(stale), stale)
        rows = len(re.findall(r'^\| [DFLRS]\d+ \|', md, re.M))
        self.assertEqual(rows, 264)
        self.assertNotEqual(rows, len(self.manifest['items']))


class AssetRulings(unittest.TestCase):
    IDS = ['C82', 'C83', 'C84']

    def test_three_asset_rulings_recorded(self):
        rows = json.loads((ROOT / '数据' / '设定裁定记录.json').read_text(encoding='utf-8'))
        by_id = {r['编号']: r for r in rows}
        for cid in self.IDS:
            self.assertIn(cid, by_id)
            self.assertEqual(set(by_id[cid]), {'编号', '裁定', '原因', '影响'})
        self.assertEqual(len(rows), 138)
        self.assertEqual(rows[-1]['编号'], 'C138')
        self.assertIn('rename_gallery_ext', by_id['C82']['裁定'])
        self.assertIn('不是交付判据', by_id['C83']['裁定'])
        self.assertIn('不判红、不改名', by_id['C84']['裁定'])
        self.assertIn('按文件名引用', by_id['C84']['原因'])
        # C118 是本轮出图链的口径裁定，链上读数只有这条闸门能给出：数字被改回旧读数就说明产物没重跑。
        self.assertIn('分卷/原稿/*.md 零改动', by_id['C118']['裁定'] + by_id['C118']['影响'])
        self.assertIn('verify_image_assets 1077/1077 格通过、提示 0 条', by_id['C118']['影响'])
        # C126 是本轮把「手气档」收成阈值的那条：阈值数与它要收口的 tail 冲突句都只能在裁定记录里查
        self.assertIn('十二分之一', by_id['C126']['裁定'])
        self.assertIn('construction hoarding with a tower crane', by_id['C126']['原因'])
        self.assertIn('grid_crop', by_id['C126']['裁定'] + by_id['C126']['原因'])

    def test_c97_records_the_two_accepted_containers(self):
        """C97 是双容器交付判据的唯一出处：裁定措辞一旦被回退，核验脚本的判据文本与裁定记录就各说各话，
        所以把容器名单、判红边界与「补写即伪造」一起钉在这里。"""
        rows = json.loads((ROOT / '数据' / '设定裁定记录.json').read_text(encoding='utf-8'))
        by_id = {r['编号']: r for r in rows}
        self.assertEqual(set(by_id['C97']), {'编号', '裁定', '原因', '影响'})
        for token in ('caBX', 'trainedAlgorithmicMedia', '字节头既非 JPEG 也非 PNG 直接判红', '补写是伪造'):
            self.assertIn(token, by_id['C97']['裁定'])
        self.assertIn('通过 1056/1056', by_id['C97']['影响'])


if __name__ == '__main__':
    unittest.main()
