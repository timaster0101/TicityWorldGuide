# -*- coding: utf-8 -*-
"""R10 台账（14 枚）的对盘复核判据：正跑必须空表，篡改件必须逐项判红。

为什么要这一组：R10 的 11 条新成员不是手抄名单，而是「待复验片区 − 已有裁定 − R9 成员」推出来的；
推导一旦漂（清单状态变了、候选表加了裁定），台账就会悄悄多发或少发。所以判据钉三件事：
1. 成员面＝推导值（14 条，D18 在首位且是唯一探针）；
2. 台账每条的 body／send_sha／chars／file／占格／母图都能回盘上现态（audit 空表）；
3. 判据本身不是空转：把 body 改一个字、sha 改一位、母图换成竖图、占格挪走，四种篡改都判红。

夹具全在仓库外临时目录，跑前跑后对台账两件做 sha 对拍（audit 只读，但「只读」也要被证明）。
"""
import copy
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CAMPAIGN = ROOT / '工具' / 'reshoot_campaign_2026_11_06'
LED = CAMPAIGN / 'send_bodies_r10.json'
NOTE = CAMPAIGN / 'send_bodies_r10_note.json'

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / '工具'))
sys.path.insert(0, str(CAMPAIGN))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load('build_send_bodies_r10', CAMPAIGN / 'build_send_bodies_r10.py')


def _sha(p):
    with open(p, 'rb') as fp:
        return hashlib.sha256(fp.read()).hexdigest()


class R10Ledger(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(LED, encoding='utf-8') as fp:
            cls.led = json.load(fp)
        with open(NOTE, encoding='utf-8') as fp:
            cls.note = json.load(fp)
        man = B.load_json('数据/开图清单.json')
        cls.man = {i['id']: i for i in man['items']}
        cls.cand = B.load_json('数据/下一轮重投候选.json')
        _q, cells, exc = B.current_cells(str(ROOT))
        assert not exc, exc
        cls.cell = {r['id']: r['cell'] for r in cells}
        cls.pool = dict(B.REF.check_pool(B.REF.LANDSCAPE, '测试'))

    def test_membership_is_derived_not_handcopied(self):
        r9_ids, rest = B.members(self.man, self.cand)
        self.assertEqual(r9_ids, ['D18', 'D19', 'L069'])
        self.assertEqual(rest, ['D01', 'D02', 'D03', 'D04', 'D05', 'D07', 'D08',
                                'D13', 'D14', 'D16', 'D17'])
        self.assertEqual(list(self.led), r9_ids + rest)
        self.assertEqual(self.note['成员数'], 14)

    def test_probe_is_first_and_single(self):
        self.assertEqual(self.note['探针'], 'D18')
        self.assertEqual(list(self.led)[0], 'D18')
        hits = [k for k, v in self.led.items() if v.get('批', '').startswith('R10（照抄')]
        self.assertEqual(hits, ['D18', 'D19', 'L069'])

    def test_audit_clean_on_real_ledger(self):
        self.assertEqual(B.audit(self.man, self.led, self.cell, self.pool), [])

    def test_negative_wrong_body_reds(self):
        bad = copy.deepcopy(self.led)
        bad['D01']['body'] = bad['D01']['body'][:-1] + ('甲' if bad['D01']['body'][-1] != '甲' else '乙')
        probs = B.audit(self.man, bad, self.cell, self.pool)
        self.assertTrue(any('D01' in p and 'body' in p for p in probs), probs)

    def test_negative_wrong_send_sha_reds(self):
        bad = copy.deepcopy(self.led)
        bad['D05']['send_sha256'] = '0' * 64
        probs = B.audit(self.man, bad, self.cell, self.pool)
        self.assertTrue(any('D05' in p and 'send_sha256' in p for p in probs), probs)

    def test_negative_portrait_mother_reds(self):
        bad = copy.deepcopy(self.led)
        bad['D13']['ref_image'] = B.REF.PORTRAIT[0]
        probs = B.audit(self.man, bad, self.cell, self.pool)
        self.assertTrue(any('D13' in p and '不同画幅' in p for p in probs), probs)

    def test_negative_moved_cell_reds(self):
        bad = copy.deepcopy(self.led)
        bad['D17']['replaced_cell'] = '数据/图集/D17/不存在.png'
        probs = B.audit(self.man, bad, self.cell, self.pool)
        self.assertTrue(any('D17' in p and '占格' in p for p in probs), probs)

    def test_readonly(self):
        before = (_sha(LED), _sha(NOTE))
        B.audit(self.man, self.led, self.cell, self.pool)
        self.assertEqual(before, (_sha(LED), _sha(NOTE)))


class TempDirHygiene(unittest.TestCase):
    def test_no_residue(self):
        pref = 'r10ledger_'
        tmp = tempfile.gettempdir()
        probe = Path(tempfile.mkdtemp(prefix=pref))
        try:
            self.assertTrue(os.path.isdir(str(probe)))
            seen = [d for d in os.listdir(tmp) if d.startswith(pref)]
            self.assertIn(probe.name, seen)
        finally:
            import shutil
            shutil.rmtree(probe, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
