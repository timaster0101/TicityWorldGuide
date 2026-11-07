# -*- coding: utf-8 -*-
"""投后核验的分组分流与 C136 容器判据——夹具全在仓库外临时目录，真源四件跑前跑后 sha 对拍。

verify_round.py 本轮从「只认 R2」改成按组取送入串台账与档串，所以这里钉三件事：
1. 两组各写各的读数与轮次台账；R1 一轮不许覆写 R2 的 round_readings.json／ledger.json。
2. 读错组（台账里的发名不带本组档串）必须在写盘之前停手，不停就会把别组的落盘算成本轮「已投」。
3. C136：caBX=0／iTXt=1 的合规真图必须放行——旧判据 `cabx == 1` 会把已投的 3 枚全判红
   （ledger.json 第 1 轮三行实测就是 0／1）。
"""
import hashlib
import importlib.util
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CAMPAIGN = ROOT / '工具' / 'reshoot_campaign_2026_11_06'
REAL_FILES = ('ledger.json', 'round_readings.json',
              'send_bodies_r1.json', 'send_bodies_r1_primary.json')
PREFIX = 'verify_round_neg_'

_spec = importlib.util.spec_from_file_location('verify_round_under_test', str(CAMPAIGN / 'verify_round.py'))
vr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vr)

FROZEN_MS = 1793972630057
FROZEN_TEXT = '2026-11-06 00:00:00'
SUFFIX = {g: vr.GROUPS[g]['suffix'] for g in vr.GROUPS}


def _real_shas():
    return {f: hashlib.sha256((CAMPAIGN / f).read_bytes()).hexdigest() for f in REAL_FILES}


def _measure(dims='1280x1024', container=None):
    cont = container if container is not None else {'cabx': 0, 'itxt': 1}

    def m(path):
        return {'dims': dims, 'bytes': (path.stat().st_size if path.exists() else 0),
                'sha256_12': 'ab' * 6, 'container': cont,
                'p99_lum': 200.0, 'fine_var_full': 100.0, 'sun_blob_px': 0}
    return m


class VerifyRoundGroups(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = _real_shas()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix=PREFIX))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.here = self.tmp / 'here'
        self.here.mkdir()
        self.root = self.tmp / 'root'
        (self.root / '数据').mkdir(parents=True)
        (self.root / '数据' / '提示词基准冻结.json').write_text(
            json.dumps({'frozen_at': FROZEN_TEXT, 'frozen_at_ms': FROZEN_MS}, ensure_ascii=False),
            encoding='utf-8')
        self.img = self.tmp / 'vibe_images'
        self.img.mkdir()
        self.jsonl = self.tmp / 'session.jsonl'
        self.jsonl.write_text('', encoding='utf-8')

    # ── 夹具构造 ────────────────────────────────────────────────────────────
    def ref(self, group, eid='L001', body='正文甲'):
        return {'id': eid, 'send_name': '%s-钛湖市民议事厅-%s' % (eid, SUFFIX[group]),
                'body': body, 'size': '1280x1024',
                'replaced_cell': 'backup/数据/图集/开图/%s/旧格.jpg' % eid,
                'status_before': 'needs_review'}

    def put_ledger(self, group, refs):
        (self.here / vr.GROUPS[group]['bodies']).write_text(
            json.dumps({r['id']: r for r in refs}, ensure_ascii=False, indent=1), encoding='utf-8')

    def sent(self, ref, ts=FROZEN_MS + 1000, body=None, size='1280x1024'):
        """按名＋串写进会话 jsonl，并落一枚带时间戳的 png（文件名口径照 ImageGen）。"""
        with io.open(self.jsonl, 'a', encoding='utf-8', newline='\n') as fp:
            fp.write(json.dumps({'type': 'tool_use', 'name': 'ImageGen',
                                 'input': {'name': ref['send_name'],
                                           'prompt': ref['body'] if body is None else body,
                                           'size': size}}, ensure_ascii=False) + '\n')
        (self.img / ('%s_%d_abcd1234.png' % (ref['send_name'], ts))).write_bytes(b'\x89PNG\r\n')

    def run_group(self, group, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return vr.run(group, str(self.jsonl), here=str(self.here), root=str(self.root),
                          img_dir=str(self.img), measure=_measure(**kw))

    def ledger_rounds(self, group):
        p = self.here / vr.GROUPS[group]['ledger']
        return json.loads(p.read_text(encoding='utf-8'))['rounds'] if p.exists() else []

    # ── 正检 ───────────────────────────────────────────────────────────────
    def test_a_r1_round_writes_only_its_own_pair(self):
        r = self.ref('R1')
        self.put_ledger('R1', [r])
        self.sent(r)
        self.assertEqual(self.run_group('R1'), 0)
        self.assertTrue((self.here / 'round_readings_r1.json').exists())
        self.assertTrue((self.here / 'ledger_r1.json').exists())
        self.assertFalse((self.here / 'round_readings.json').exists(), 'R1 一轮覆写了 R2 的读数')
        self.assertFalse((self.here / 'ledger.json').exists(), 'R1 一轮往 R2 的轮次台账追加了记录')
        row = json.loads((self.here / 'round_readings_r1.json').read_text(encoding='utf-8'))
        self.assertEqual((row['统计面']['组别'], row['统计面']['档串']), ('R1', SUFFIX['R1']))
        self.assertEqual(row['统计面']['送入串台账'], 'send_bodies_r1_primary.json')
        got = self.ledger_rounds('R1')[0]
        self.assertEqual((got['轮次'], got['组别'], got['档串']), (1, 'R1', SUFFIX['R1']))

    def test_b_r2_round_keeps_legacy_filenames(self):
        r = self.ref('R2')
        self.put_ledger('R2', [r])
        self.sent(r)
        self.assertEqual(self.run_group('R2'), 0)
        self.assertTrue((self.here / 'round_readings.json').exists())
        self.assertTrue((self.here / 'ledger.json').exists())
        self.assertFalse((self.here / 'round_readings_r1.json').exists())
        self.assertEqual(self.ledger_rounds('R2')[0]['档串'], SUFFIX['R2'])
        decl = json.loads((self.here / 'ledger.json').read_text(encoding='utf-8'))['declaration']
        self.assertEqual(decl, vr.LEDGER_DECL['R2'], 'R2 台账抬头被改——与在盘那份不是同一句话')

    # ── 违例注入 ───────────────────────────────────────────────────────────
    def test_c_wrong_group_ledger_stops_before_any_write(self):
        r = self.ref('R2')
        self.put_ledger('R1', [r])          # R1 组读的台账里装着 R2 的发名
        self.sent(r)
        with self.assertRaises(AssertionError) as cm:
            self.run_group('R1')
        self.assertIn('不带本组档串', str(cm.exception))
        for fn in ('round_readings_r1.json', 'ledger_r1.json'):
            self.assertFalse((self.here / fn).exists(), '停手那轮仍落了笔：%s' % fn)

    def test_d_same_name_sent_twice_is_red(self):
        r = self.ref('R1')
        self.put_ledger('R1', [r])
        self.sent(r)
        self.sent(r)
        self.assertEqual(self.run_group('R1'), 1)
        self.assertEqual(self.ledger_rounds('R1')[0]['落盘与回绑'], [])

    def test_e_two_cells_inside_frozen_band_is_red(self):
        r = self.ref('R1')
        self.put_ledger('R1', [r])
        self.sent(r)
        self.sent(r, ts=FROZEN_MS + 2000)
        self.assertEqual(self.run_group('R1'), 1)

    def test_f_container_with_no_aigc_marker_is_red(self):
        r = self.ref('R1')
        self.put_ledger('R1', [r])
        self.sent(r)
        self.assertEqual(self.run_group('R1', container={'cabx': 0, 'itxt': 0}), 1)

    def test_g_c136_itxt_only_is_green(self):
        r = self.ref('R1')
        self.put_ledger('R1', [r])
        self.sent(r)
        self.assertEqual(self.run_group('R1', container={'cabx': 0, 'itxt': 1}), 0)
        cont = self.ledger_rounds('R1')[0]['落盘与回绑'][0]['container']
        self.assertEqual((cont['cabx'], cont['itxt']), (0, 1))
        self.assertIs(cont['cabx'] == 1, False, '这条夹具没打在新旧容器口径的分界上，负测失去对象')

    def test_h_sent_prompt_drifted_is_red(self):
        r = self.ref('R1')
        self.put_ledger('R1', [r])
        self.sent(r, body=r['body'] + '乙')
        self.assertEqual(self.run_group('R1'), 1)
        self.assertFalse(self.ledger_rounds('R1')[0]['落盘与回绑'][0]['逐字相等'])

    def test_i_wrong_size_is_red(self):
        r = self.ref('R1')
        self.put_ledger('R1', [r])
        self.sent(r)
        self.assertEqual(self.run_group('R1', dims='1024x1536'), 1)

    def test_j_argv_default_is_r2_and_unknown_group_exits_2(self):
        keep = sys.argv
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                sys.argv = ['verify_round.py']
                self.assertEqual(vr.main(), 2, '零参数不该放行')
                sys.argv = ['verify_round.py', 'a.jsonl', 'R9']
                self.assertEqual(vr.main(), 2, '不认识的组别必须停在用法上')
                sys.argv = ['verify_round.py', 'a.jsonl', 'b.jsonl']
                self.assertEqual(vr.main(), 2, '参数多于 2 个必须停在用法上')
        finally:
            sys.argv = keep

    def test_z_real_sources_untouched_and_no_fixture_left(self):
        self.assertEqual(_real_shas(), VerifyRoundGroups.before, '夹具跑动碰了仓库里的真源')
        # 本条自己 setUp 建的夹具还在盘（cleanup 在方法之后才跑），残留口径必须排除它，否则恒红。
        residue = [d for d in os.listdir(tempfile.gettempdir())
                   if d.startswith(PREFIX) and d != self.tmp.name]
        self.assertEqual(residue, [], '临时夹具残留：%s' % residue[:5])
        # 自证这条扫描不是空转：现造一个同前缀目录，必须被数到。
        probe = Path(tempfile.mkdtemp(prefix=PREFIX))
        try:
            seen = [d for d in os.listdir(tempfile.gettempdir()) if d.startswith(PREFIX)]
            self.assertIn(probe.name, seen, '残留扫描本身在空转，"残留 0" 不成立')
        finally:
            shutil.rmtree(probe, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
