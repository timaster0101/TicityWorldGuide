# -*- coding: utf-8 -*-
"""文档侧两处写死计数的派生闸门（移交清单 §48.3 的 E 与 F 两条，本轮落笔）。

E：`设计/2026-11-03-待办移交清单.md` §4「追加一条裁定」那条链序说明里，裁定条数、末条编号与
   计数钉处数一律不得写死——写死就在下一条裁定落地时静默过期（§46.3 实测 §4:53 的「118 条／
   同步 6 处／test_occupations.py 三处」已漂整整两轮，而 §4 是接手方照着跑的那张表，过期比正文更贵）。
F：`设计/2026-10-31-分期路线图.md` 第 30 行末处「现值以本句为准：`数据/设定裁定记录.json` **N 条**、
   末条 `Cn`」必须等于该 JSON 的条数与末条编号（探针口径见 §46.7）；断更从此自己报红，不再等下一轮人肉扫。

两条各配违例负测：把过期串注回内存副本，判据必须抓到；全程不写盘、不动被守护的仓库文件。
跑法：python 工具/test_doc_drift.py（工作目录＝设定集根）
"""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CHECKLIST = ROOT / '设计' / '2026-11-03-待办移交清单.md'
ROADMAP = ROOT / '设计' / '2026-10-31-分期路线图.md'
RULINGS = ROOT / '数据' / '设定裁定记录.json'

# §4 的「追加一条裁定」bullet 里出现即算写死：条数、末条编号、计数钉处数三格。
# 只认这条 bullet 指向真源的那两种写法之外的一切数字形态，避免把「第6期」「C122 起」这类
# 正常的裁定编号引用一起卷进来——所以每条正则都必须锚在「现值／同步／N 处」这类计数措辞上。
STALE_PATTERNS = [
    ('裁定条数写死', re.compile(r'现值\s*\**\d{2,4}\s*条')),
    ('末条编号写死', re.compile(r'现值[^。；\n]{0,12}末条\s*\**C\d{2,4}')),
    ('计数钉处数写死', re.compile(r'同步\s*\**\d+\s*处')),
    ('测试文件后跟处数', re.compile(r'test_\w+\.py`?\s*[（(]?\s*(?:[一二三四五六七八九十]|\d+)\s*处')),
]

# 违例夹具：§4 第 53 行在 §46.3 登记时的原样三格（118 条／同步 6 处／三处）＋路线图末处的过期现值。
STALE_CHECKLIST_PROBE = '（现值 118 条，末条 C118）→ 同步 6 处 `len(rows)` 计数钉（`test_costs.py` 方法名、' \
                        '末条与末十条清单、`test_occupations.py` 三处、`test_image_assets.py`、`test_params.py` 两处）'

CURRENT_VALUE_RE = re.compile(
    r'现值以本句为准：`数据/设定裁定记录\.json` \*\*(\d{2,4}) 条\*\*、末条 `C(\d{2,4})`')


def section_four(text):
    """按标题切出 §4 本体（链序速查），不扫全文——§46 之后的补记里那些落盘时点读数按口径保留、不算违例。"""
    start = text.index('## 4. ')
    nxt = text.find('\n## ', start + 1)
    return text[start:] if nxt < 0 else text[start:nxt]


def stale_hits(block):
    out = []
    for name, pattern in STALE_PATTERNS:
        for m in pattern.finditer(block):
            out.append((name, m.group(0).replace('\n', ' ')[:60]))
    return out


class ChecklistCountsDerived(unittest.TestCase):
    def test_section_four_carries_no_hardcoded_ruling_counts(self):
        block = section_four(CHECKLIST.read_text(encoding='utf-8'))
        self.assertEqual(stale_hits(block), [], '§4 的链序说明里重新出现写死的裁定条数／末条／处数')

    def test_the_empty_hit_is_not_a_broken_regex(self):
        """空命中正测的对照：同一组正则作用在 §46.3 登记的原样过期串上必须四类全命中——
        否则上一条只是正则本身失效，不是文档变干净了。"""
        names = {n for n, _ in stale_hits(STALE_CHECKLIST_PROBE)}
        self.assertEqual(names, {n for n, _ in STALE_PATTERNS},
                         '违例夹具没能命中全部四类判据：%s' % sorted(names))


class RoadmapCurrentValueDerived(unittest.TestCase):
    def truth(self):
        rulings = json.loads(RULINGS.read_text(encoding='utf-8'))
        return len(rulings), int(re.match(r'C(\d+)', rulings[-1]['编号']).group(1))

    def test_last_declared_value_equals_the_ruling_log(self):
        hits = CURRENT_VALUE_RE.findall(ROADMAP.read_text(encoding='utf-8'))
        self.assertTrue(hits, '路线图一处「现值以本句为准」的现值句都没有，判据无从对账')
        count, last = self.truth()
        self.assertEqual((int(hits[-1][0]), int(hits[-1][1])), (count, last),
                         '路线图末处现值（%s 条／C%s）与 数据/设定裁定记录.json（%d 条／C%d）不一致：断更'
                         % (hits[-1][0], hits[-1][1], count, last))

    def test_a_stale_current_value_is_red(self):
        """违例负测：把末处现值在内存里改回 §46.2 落盘时的 131／C131，闸门必须仍然判红——
        证明这条断言抓的是「没回写」，不是「恰好等于」。"""
        text = ROADMAP.read_text(encoding='utf-8')
        count, last = self.truth()
        hits = list(CURRENT_VALUE_RE.finditer(text))
        stale = text[:hits[-1].start(1)] + str(count - 1) + text[hits[-1].end(1):hits[-1].start(2)] \
            + str(last - 1) + text[hits[-1].end(2):]
        self.assertNotEqual(stale, text, '过期夹具没有改动任何字节，判红无从谈起')
        got = CURRENT_VALUE_RE.findall(stale)[-1]
        self.assertEqual((int(got[0]), int(got[1])), (count - 1, last - 1), '夹具注入后正则没取到过期值')
        self.assertNotEqual((int(got[0]), int(got[1])), (count, last))


if __name__ == '__main__':
    unittest.main(verbosity=2)
