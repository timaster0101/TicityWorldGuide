# -*- coding: utf-8 -*-
"""C139 代签脚本的轮次面派生判据：写死档串这一缺陷类的回归与违例负测（零付费、零落盘）。

2026-11-21 之前这里有两处写死：
  reshoot_cells 只认 C138主向重投／C133冻结重投两支档串，
  load_round_rows 只读 round_readings_r1.json／round_readings.json 两份读数件。
C154 那几轮的在册格因此一律取成空集，代签面被误报成「当前格早于重投期」，
闸门侧则把 291 条判成「申报没点名当前在册的格」——干跑读数是 331 格面里只命中 2 格、拒签 291。
现在两处都从 verify_round.GROUPS 现派生，本轮测试钉的就是「派生」这件事本身：
凡改回写死，(1) 与 (2) 里那两条变异自证会当场变红。

跑法：python -X utf8 -m unittest 工具.test_sign_acceptance -v
"""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CAMPAIGN = ROOT / '工具' / 'reshoot_campaign_2026_11_06'

_spec = importlib.util.spec_from_file_location('sign_acceptance_under_test', str(HERE / 'sign_acceptance.py'))
sa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sa)

SYS_NO_CELL = '本轮无该格投后核验读数'
SYS_NO_CELL_NEW = '须先在 verify_round.GROUPS 登记'
SYS_LIE_OLD = '当前格早于重投期'
CLIP_MISS_NEW = '画风表无该格读数'
CLIP_MISS_OLD = '不属 C138 主向重投面'
CLEAR_CLAIM = '原补充输入备案'


def _jload(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


class RoundFaceIsDerived(unittest.TestCase):
    """(1) 档串面与读数件面确实从 GROUPS 派生，不是另一份手抄名单。"""

    @classmethod
    def setUpClass(cls):
        cls.man = _jload(ROOT / '数据' / '开图清单.json')['items']
        cls.notes = _jload(ROOT / '数据' / '开图验收备注.json')['备注']
        cls.rounds = sa.load_round_rows()

    def test_a_tokens_and_readings_equal_the_group_table(self):
        self.assertEqual(sa.round_cell_tokens(),
                         sorted({re.sub(r'-v\d+$', '', g['suffix']) for g in sa.vr.GROUPS.values()}),
                         '重投期档串与 GROUPS 的 suffix 分叉＝这里又抄了一份名单')
        self.assertEqual(sa.round_readings_files(),
                         list(dict.fromkeys(g['readings'] for g in sa.vr.GROUPS.values())),
                         '投后核验读数件与 GROUPS 的 readings 分叉＝新轮的读数永远读不到')
        # 派生必须真的覆盖到 C154 这几支：写死两支时这三条正是要命的那几轮
        for tok in ('C154母图重投', 'C154判废补重投'):
            self.assertIn(tok, sa.round_cell_tokens(), tok)

    def test_b_dropping_a_round_from_the_table_drops_its_cells(self):
        """变异自证：从 GROUPS 摘掉最新那一档，它的在册格必须从取法里消失，还原后跟着回来。

        写死名单的实现不会有任何变化，这条就会变红——它证明上面那条对拍不是同义反复。
        轮次不写死成 R7：R8 回填把 D18／D19／L069 那三格顶成了取景补重投枚，盘面上确实不再有 R7 的在册格，
        2026-11-22 全量套件实测这样会假红（与 5 号点单「轮次面写死」同一缺陷类，按 GROUPS 声明序取最新档）。"""
        order = list(sa.vr.GROUPS)
        group = order[-1]
        tok = re.sub(r'-v\d+$', '', sa.vr.GROUPS[group]['suffix'])
        led = _jload(CAMPAIGN / sa.vr.GROUPS[group]['bodies'])
        by_id = {i['id']: i for i in self.man}
        sample = by_id[sorted(led)[0]]
        self.assertTrue(sa.reshoot_cells(sample), '本轮在册格里没有一支认得出重投期档串，用例失去承载')
        self.assertTrue(any(tok in f for f in sa.reshoot_cells(sample)),
                        '用例失去承载：最新一轮 %s 的在册格没挂在清单上，负测会空转' % tok)
        keep = copy.deepcopy(sa.vr.GROUPS[group])
        try:
            del sa.vr.GROUPS[group]
            self.assertNotIn(tok, sa.round_cell_tokens())
            self.assertFalse(any(tok in f for f in sa.reshoot_cells(sample)),
                             'GROUPS 里已经没这一轮，取法却还认得它的格＝档串面其实是写死的')
        finally:
            sa.vr.GROUPS[group] = keep
        self.assertIn(tok, sa.round_cell_tokens(), '还原后档串面没跟着回来')
        self.assertTrue(any(tok in f for f in sa.reshoot_cells(sample)), '还原后取法没认回这一轮的格')

    def test_c_every_registered_cell_is_recognised_and_mostly_resolved(self):
        """在册格一枚都不许落进空集：这是 291 条误报的直接回归。"""
        sys.path.insert(0, str(CAMPAIGN))
        import current_cells as cc
        _q, rows, excluded = cc.current_cells(str(ROOT))
        self.assertEqual(excluded, [], '有 ID 取不到在册格，本用例覆盖面不足')
        by_id = {i['id']: i for i in self.man}
        miss = [r['id'] for r in rows if os.path.basename(r['cell'])
                not in [os.path.basename(f) for f in sa.reshoot_cells(by_id[r['id']])]]
        self.assertEqual(miss, [], '在册格没被认成重投期格 %s＝档串面又漏了轮次' % miss[:8])
        hit = sum(1 for r in rows if os.path.basename(r['cell']) in self.rounds)
        self.assertGreaterEqual(hit, len(rows) - 20,
                                '在册格在投后核验读数里命中 %d／%d，读数件面没跟上轮次' % (hit, len(rows)))


class RowsSayWhatActuallyHappened(unittest.TestCase):
    """(2) 取不到格／读不到数／没有补充输入时，申报行只许说当轮真发生的事。"""

    @classmethod
    def setUpClass(cls):
        cls.item = [i for i in _jload(ROOT / '数据' / '开图清单.json')['items'] if i['id'] == 'L001'][0]
        cls.bound = cls.item['prompt_sha256']
        cls.struct = {'格数': 4, '通过': 4, '失败': 0}

    def _row(self, item, rounds=None, clip=None, old=None):
        return sa.build_row(item, self.bound,
                            {} if rounds is None else rounds,
                            {} if clip is None else clip,
                            0.9023535, self.struct, old)

    def test_d_unregistered_round_is_named_as_unregistered(self):
        fake = copy.deepcopy(self.item)
        fake['image_file'] = ['数据/图集/L001/L001-钛湖市民议事厅-C999未来重投-v01_1799999999999_deadbeef.png']
        row = self._row(fake)
        self.assertIn(SYS_NO_CELL, row)
        self.assertIn(SYS_NO_CELL_NEW, row, '没登记的轮次没被指到 GROUPS，读的人只能猜是哪一环漂了')
        self.assertNotIn(SYS_LIE_OLD, row, '又写成「早于重投期」＝把筛子没跟上轮次说成历史事实')

    def test_e_missing_readings_reports_the_derived_file_count(self):
        fake = copy.deepcopy(self.item)
        orphan = '数据/图集/L001/L001-钛湖市民议事厅-C154母图重投-v09_1799999999999_deadbeef.png'
        fake['image_file'] = [orphan]
        row = self._row(fake, rounds={})
        self.assertIn('在 %d 份投后核验里都查不到' % len(sa.round_readings_files()), row,
                      '份数不再写死成「两份」，读数件增删时这句话才不会过期')

    def test_f_clip_miss_no_longer_blames_c138(self):
        fake = copy.deepcopy(self.item)
        base = os.path.basename(fake['image_file'][0])
        row = self._row(fake, rounds={base: ('round_readings_r4.json',
                                             {'逐字相等': True, 'size_match': True, 'dims': '1536x1024',
                                              'bytes': 1, 'sha256_12': 'a' * 12, '投次': 1,
                                              'container': {'cabx': 0, 'itxt': 1}}, 'R4'), }, clip={})
        self.assertIn(CLIP_MISS_NEW, row)
        self.assertNotIn(CLIP_MISS_OLD, row, '画风表覆盖面早就是 current_cells 现算的在册格，还写「不属 C138 面」是假话')

    def test_g_no_cleared_input_record_means_no_clearing_claim(self):
        old = {'image_prompt_sha256': 'b' * 64}
        row = self._row(self.item, old=old)
        self.assertIn('原过期绑定', row)
        self.assertNotIn(CLEAR_CLAIM, row, '本条没记过补充输入，申报行不得申报一次清空')
        with_input = dict(old, generation_input_file='数据/生成输入记录/L001.txt',
                          generation_input_sha256='c' * 64)
        row2 = self._row(self.item, old=with_input)
        self.assertIn(CLEAR_CLAIM, row2)
        self.assertIn('数据/生成输入记录/L001.txt', row2, '记过的原值必须逐字留在申报行，清空才有据')


class DryRunNeverSigns(unittest.TestCase):
    """(3) 干跑不落盘、不置已验收：accepted 面维持 0 是用户的常设裁定，改轮次面不许把它带红。"""

    def test_a_dry_run_leaves_the_two_truth_sources_untouched(self):
        man, notes = ROOT / '数据' / '开图清单.json', ROOT / '数据' / '开图验收备注.json'
        before = (_sha(man), _sha(notes))
        before_rows = sum(len(v) for v in _jload(notes)['备注'].values())
        signed_before = sum(1 for i in _jload(man)['items'] if i.get('status') == '已验收')
        buf = io.StringIO()
        argv = list(sys.argv)
        try:
            sys.argv = ['sign_acceptance.py']
            with contextlib.redirect_stdout(buf):
                rc = sa.main()
        finally:
            sys.argv = argv
        out = buf.getvalue()
        self.assertEqual(rc, 0, '干跑退出非零＝代签通道坏了：%s' % out[-400:])
        self.assertIn('（干跑，未落盘', out)
        self.assertEqual(before, (_sha(man), _sha(notes)), '干跑写盘＝越过硬闸')
        items = _jload(man)['items']
        # 2026-11-22 用户「2 真签」之后现清单本来就是 312 条已验收：这里不能钉「已验收＝0」，
        # 要钉的是「干跑不改变已验收面」——拿干跑前现读的计数对拍，状态面翻面时不用改判据。
        self.assertEqual(sum(1 for i in items if i.get('status') == '已验收'), signed_before,
                         '干跑之后已验收条数变了＝accepted 面被脚本翻过')
        self.assertEqual(sum(len(v) for v in _jload(notes)['备注'].values()), before_rows,
                         '干跑往备注追加了行')

    def test_b_no_item_is_rejected_for_declaration_shape(self):
        """缺陷类的正测收尾：整批代签面不许再出现「申报行不合规格」。

        结构核验失败那类拒签是真拒签，本用例不掩盖——只钉住这一支：轮次面派生化之后，
        依据行点不到当前在册格这件事不该再发生。"""
        buf = io.StringIO()
        argv = list(sys.argv)
        try:
            sys.argv = ['sign_acceptance.py']
            with contextlib.redirect_stdout(buf):
                sa.main()
        finally:
            sys.argv = argv
        bad = [l for l in buf.getvalue().split('\n') if '申报行不合规格' in l]
        self.assertEqual(bad, [], '拒签面又出现申报形状问题：%s' % bad[:3])

    def test_c_writes_are_reachable_only_through_execute(self):
        """静态自证：两份真源的 write_text 只出现在 --execute 那道早退之后。

        比的是「守卫之前有没有写盘」，不比 return 的位置——干跑分支自己就带一句 return 0，
        拿它当终点会把正常结构读成漏洞。"""
        src = (HERE / 'sign_acceptance.py').read_text(encoding='utf-8')
        guard = src.index('if not args.execute:')
        self.assertNotIn('write_text', src[:guard], '守卫之前出现了写盘调用＝--execute 不再是唯一入口')
        for w in ('NOTES.write_text', 'MANIFEST.write_text'):
            self.assertGreater(src.index(w), guard, '%s 落在干跑守卫之前' % w)


if __name__ == '__main__':
    unittest.main(verbosity=2)
