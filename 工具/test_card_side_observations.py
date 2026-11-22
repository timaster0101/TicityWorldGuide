# -*- coding: utf-8 -*-
"""卡面「附带观察」三条复验的读数件闸门（`数据/卡面附带观察复验.json`）。

这一支守两件事：
① 复验用的串面事实与盘面身份由真源现算，和读数件里那段散文分叉就判红——否则读数件会慢慢变成
   一份没人能复核的叙述（三条观察里已经有一条被复验推翻了，正是因为它当初只凭印象判断「四条都没写禁则」）；
② 复验不改画风轴：签署件 `数据/卡面主图画风目视.json` 的逐枚行与汇总不因本件变动。
"""
import glob
import hashlib
import io
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.dont_write_bytecode = True
RECORD = os.path.join(ROOT, '数据', '卡面附带观察复验.json')
STANCE = os.path.join(ROOT, '数据', '卡面主图画风目视.json')
LAND = os.path.join(ROOT, '数据', '卡面主图提示词3x4', '主图3x4落点.json')
PROMPTS = os.path.join(ROOT, '数据', '卡面主图提示词3x4')
SUN_IDS = ('D09', 'L009', 'L025', 'L046')
DIGIT_IDS = ('idx086', 'idx097')


def _jload(p):
    with io.open(p, encoding='utf-8') as fp:
        return json.loads(fp.read())


def prompt_of(cid):
    hits = sorted(glob.glob(os.path.join(PROMPTS, '%s-*.txt' % cid)))
    assert len(hits) == 1, (cid, hits)
    with io.open(hits[0], encoding='utf-8') as fp:
        return fp.read()


def landing_of(cid):
    land = _jload(LAND)
    key = str(int(cid[3:])) if cid.startswith('idx') else cid
    return os.path.join(ROOT, land[key].replace('/', os.sep))


class RecordBindsTheFace(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rec = _jload(RECORD)
        cls.stance = {r['id']: r for r in _jload(STANCE)['逐枚']}

    def test_a_every_observed_id_is_the_signed_image(self):
        """复验的七枚必须就是签署件里那一枚：盘面现读 sha12 与 `落盘sha12` 逐枚相等。"""
        for cid in SUN_IDS + DIGIT_IDS + ('L027',):
            with io.open(landing_of(cid), 'rb') as fp:
                cur = hashlib.sha256(fp.read()).hexdigest()[:12]
            self.assertEqual(cur, self.stance[cid]['落盘sha12'], cid + ' 盘面已不是签署件那一枚')

    def test_b_record_shape_and_that_the_style_axis_is_untouched(self):
        self.assertEqual(len(self.rec['复验']), 3)
        self.assertEqual(self.rec['汇总']['复验条数'], len(self.rec['复验']))
        self.assertEqual(self.rec['汇总']['画风轴改判'], 0)
        self.assertEqual(self.rec['汇总']['本轮付费调用'], 0)
        self.assertEqual(_jload(STANCE)['汇总']['判废'], 0,
                         '签署件的画风轴结论被牵动了＝复验越过了自己的轴')

    def test_c_sun_clause_matrix_is_the_one_the_record_claims(self):
        """「四条都没写禁日盘」只对中文那句成立：英文出画句在 D09／L009／L046 里在位，只有 L025 两条都无。"""
        zh = {cid: ('不出现太阳本体' in prompt_of(cid)) for cid in SUN_IDS}
        en = {cid: ('keep the sun disc' in prompt_of(cid)) for cid in SUN_IDS}
        self.assertEqual(zh, {cid: False for cid in SUN_IDS}, '中文禁日盘句的出现面变了，复验结论要重做')
        self.assertEqual([cid for cid in SUN_IDS if en[cid]], ['D09', 'L009', 'L046'],
                         '有出画句的名单与复验记录不一致')
        self.assertFalse(en['L025'], 'L025 是「唯一串面无日盘禁则、日盘合法」的那条，这条前提变了')

    def test_d_digit_cards_name_the_value_ban_and_have_no_sun(self):
        for cid in DIGIT_IDS:
            txt = prompt_of(cid)
            self.assertIn('编号、数值', txt, cid + ' 的串里找不到数值禁令，① 的判据前提没了')
            self.assertIn('不出现太阳本体', txt)

    def test_e_framing_naming_matches_the_two_content_observations(self):
        """L027 只点名「远景平顶退台」；塔吊在这三条串里只出现在禁令句里，没有任何一条点名它。"""
        self.assertIn('远景平顶退台', prompt_of('L027'))
        for cid in ('D09', 'L009', 'L027', 'L046'):
            txt = prompt_of(cid)
            self.assertEqual(txt.count('塔吊'), 1, cid + ' 的塔吊出现次数变了：禁令句或点名单动过')
            self.assertIn('未点名的现代高层群、玻璃塔群与塔吊一律不入画', txt)
        self.assertIn('real supertall', prompt_of('L046'), 'L046 的真实超高层禁令句不在了')


if __name__ == '__main__':
    unittest.main()
