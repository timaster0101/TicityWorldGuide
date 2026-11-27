# -*- coding: utf-8 -*-
"""投后核验的分组分流与 C136 容器判据——夹具全在仓库外临时目录，跑前跑后对 REAL_FILES 逐件做 sha 对拍。

verify_round.py 本轮从「只认 R2」改成按组取送入串台账与档串，所以这里钉三件事：
1. 两组各写各的读数与轮次台账；R1 一轮不许覆写 R2 的 round_readings.json／ledger.json。
2. 读错组（台账里的发名不带本组档串）必须在写盘之前停手，不停就会把别组的落盘算成本轮「已投」。
3. C136：caBX=0／iTXt=1 的合规真图必须放行——旧判据 `cabx == 1` 会把已投的 3 枚全判红
   （ledger.json 第 1 轮三行实测就是 0／1）。
"""
import ast
import hashlib
import importlib.util
import contextlib
import copy
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CAMPAIGN = ROOT / '工具' / 'reshoot_campaign_2026_11_06'
REAL_FILES = ('ledger.json', 'round_readings.json',
              'send_bodies_r1.json', 'send_bodies_r1_primary.json',
              'send_bodies_r2_full.json', 'transcripts_r2.json',
              'send_bodies_r1_evidence.json', 'transcripts_r1.json',
              'send_bodies_r1_catchup.json', 'transcripts_r3.json',
              'send_bodies_r4.json', 'send_bodies_r4_evidence.json',
              'send_bodies_r4_note.json',
              'round_readings_r4.json', 'ledger_r4.json', 'transcripts_r4.json',
              'round_readings_r1.json', 'ledger_r1.json',
              'send_bodies_r7.json', 'send_bodies_r7_note.json',
              'round_readings_r7.json', 'ledger_r7.json',
              'send_bodies_r8.json', 'send_bodies_r8_note.json',
              'send_bodies_r8_evidence.json',
              'round_readings_r8.json', 'ledger_r8.json',
              'send_bodies_r9.json', 'send_bodies_r9_note.json',
              'send_bodies_r10.json', 'send_bodies_r10_note.json',
              'round_readings_r10.json', 'ledger_r10.json')
# 2026-11-22 R8 投后链跑完：`round_readings_r8.json`／`ledger_r8.json` 已落盘并钉进来，
# L069 那次 terminated 发起由 `send_bodies_r8_evidence.json` 承载（投次 2／作废发起 0），三件一起进清单。
# 上一窗留下的「R8 两件不许进来」豁免理由已过期——那两件的缺席当时是真的，现在不是了。
# 2026-11-22 晚 R9 台账（`send_bodies_r9.json`／`send_bodies_r9_note.json`）落盘，同一窗补钉；
# 补钉前 `test_y_real_ledgers_on_disk_are_all_pinned` 实测判红，属于「新轮次件落盘必须同笔进名单」。
# 2026-11-27 R10 台账（14 枚：R9 三条照抄 + 未裁定 11 条新出）落盘，同笔补钉两件；
# 该轮次的成员面与串面判据在 `工具/test_send_bodies_r10.py`，本清单只负责「改了要有人红」。
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


# 画风三处的行首（提示词正文里唯一允许随画风裁定变动的三行）。
STYLE_LINE_PREFIXES = ("【画风锚点】", "【全局硬设定】", "English tail:")


def style_only_diff(archived, current):
    """历史台账串面与现读正文的行级对拍：差异只许落在画风三处行上，返回违例清单（空＝达标）。

    为什么按行首内容判而不按行号判：行号 (0, 6, 8) 是 2026-11-09 实测，取景段或人群段增删一行就会挪，
    钉行号等于给下一轮埋一条假红。为什么还要求三处里至少变一处：台账与真源若整份相同，
    「差异都在画风行里」会被空集满足，判据就成了恒绿空转。"""
    a, b = archived.split('\n'), current.split('\n')
    if len(a) != len(b):
        return ['台账正文与现读正文行数不同构（%d≠%d），逐行对拍失去比对对象' % (len(a), len(b))]
    diff = {i for i, (x, y) in enumerate(zip(a, b)) if x != y}
    style = {i for i, l in enumerate(b) if l.startswith(STYLE_LINE_PREFIXES)}
    bad = []
    outside = sorted(diff - style)
    if outside:
        bad.append('画风三处以外的行也变了：行号 %s（%s）' % (outside, b[outside[0]][:40]))
    if not diff & style:
        bad.append('画风三处一行都没变，本对拍没有承载样本（判据空转）')
    return bad


def r2_member_face_violations(led, rnd, queue, snap, suffix):
    """R2 并轨台账的成员面三支对拍，返回违例清单（空＝达标）。

    为什么不再拿台账直接比现读队列：C153 于 2026-11-09 02:02 重钉基准后 queue.json 重导，
    R2_绑定关口 从 58 条长到 312 条（11-06～11-08 投的产物全成了「冻结前带时间戳格」），
    而 send_bodies_r2_full.json 是那一轮**实际发出去**的 58 串历史事实，不许跟着重导。
    两个不同冻结带比集合必然恒红；把断言删掉则「读取面少一条／多一条」与「派生队列过期」再没人管。
    所以拆成：①对历史本身（轮次台账登记的那一轮发起条目）②派生队列不过期 ③历史条目仍在现读清单里。"""
    sent = set(rnd.get('本轮发起条目') or [])
    if not sent:
        return ['轮次台账没登记「本轮发起条目」，成员面对拍没有比对对象（判据空转）']
    bad = []
    if set(led) != sent:
        bad.append('台账与 R2 那一轮登记的发起条目不同集合：少 %s／多 %s'
                   % (sorted(sent - set(led))[:5], sorted(set(led) - sent)[:5]))
    if rnd.get('档串') != suffix:
        bad.append('轮次台账末轮档串 %s 不是 R2 的 %s：取错了轮次' % (rnd.get('档串'), suffix))
    if int(queue.get('frozen_at_ms') or 0) != int(snap['frozen_at_ms']):
        bad.append('queue.json 停在旧冻结带（%s≠现读 %s）：派生队列过期'
                   % (queue.get('frozen_at_ms'), snap['frozen_at_ms']))
    owed = {e['id'] for e in queue['R2_绑定关口']['entries']}
    gone = sorted(set(led) - owed)
    if gone:
        bad.append('历史条目已从现读 R2 队列消失：%s' % gone[:5])
    return bad


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

    def put_ledger(self, group, refs, extra_refs=()):
        (self.here / vr.GROUPS[group]['bodies']).write_text(
            json.dumps({r['id']: r for r in refs}, ensure_ascii=False, indent=1), encoding='utf-8')
        extra = vr.GROUPS[group].get('bodies_extra')
        for extra_name in ([extra] if isinstance(extra, str) else list(extra or [])):
            (self.here / extra_name).write_text(
                json.dumps({r['id']: r for r in extra_refs}, ensure_ascii=False, indent=1), encoding='utf-8')

    def sent(self, ref, ts=FROZEN_MS + 1000, body=None, size='1280x1024', jsonl=None, write_file=True,
             images=None):
        """按名＋串写进会话 jsonl，并落一枚带时间戳的 png（文件名口径照 ImageGen）。
        images=None 表示这一发根本没挂参考图（R4 母图臂的裸串违例）；挂图时元素形态由调用方给，
        字符串数组与 {type,source} 对象数组两种都测——闸门读法必须两种都认，工具本身只收字符串。"""
        inp = {'name': ref['send_name'], 'prompt': ref['body'] if body is None else body, 'size': size}
        if images is not None:
            inp['images'] = images
        with io.open(jsonl or self.jsonl, 'a', encoding='utf-8', newline='\n') as fp:
            fp.write(json.dumps({'type': 'tool_use', 'name': 'ImageGen', 'input': inp},
                                ensure_ascii=False) + '\n')
        if write_file:
            (self.img / ('%s_%d_abcd1234.png' % (ref['send_name'], ts))).write_bytes(b'\x89PNG\r\n')

    def run_group(self, group, source=None, **kw):
        with contextlib.redirect_stdout(io.StringIO()):
            return vr.run(group, source or str(self.jsonl), here=str(self.here), root=str(self.root),
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

    # ── 并轨：R2 送入串面＝试点＋全量并集，投次是独立期望值 ─────────────────
    def test_k_r2_without_extra_ledger_stops_before_any_write(self):
        r = self.ref('R2')
        (self.here / vr.GROUPS['R2']['bodies']).write_text(
            json.dumps({r['id']: r}, ensure_ascii=False, indent=1), encoding='utf-8')
        with self.assertRaises(AssertionError) as cm:
            self.run_group('R2')
        self.assertIn('缺并集补充台账', str(cm.exception))
        for fn in ('round_readings.json', 'ledger.json'):
            self.assertFalse((self.here / fn).exists(), '缺全量台账那轮仍落了笔：%s' % fn)

    def test_l_same_id_diverging_body_stops(self):
        r = self.ref('R2', eid='L061')
        e = self.ref('R2', eid='L061', body='正文乙')
        self.put_ledger('R2', [r], extra_refs=[e])
        self.sent(r)
        with self.assertRaises(AssertionError) as cm:
            self.run_group('R2')
        self.assertIn('正文分叉', str(cm.exception))

    def test_m_resend_two_sends_one_cell_left_is_green(self):
        """复投的正检：投次 2、发起 2、被顶替那枚已删，落盘面仍恰 1 枚。"""
        r = self.ref('R2', eid='S02')
        r['投次'] = 2
        r['作废删除'] = ['S02-钛湖市民议事厅-%s_1_abcd1234.png' % SUFFIX['R2']]
        self.put_ledger('R2', [], extra_refs=[r])
        self.sent(r, write_file=False)
        self.sent(r, ts=FROZEN_MS + 5000)
        self.assertEqual(self.run_group('R2'), 0)
        row = self.ledger_rounds('R2')[0]['落盘与回绑'][0]
        self.assertEqual((row['投次'], row['逐字发起数'], row['非逐字发起数']), (2, 2, 0))
        rd = json.loads((self.here / 'round_readings.json').read_text(encoding='utf-8'))['统计面']
        self.assertEqual((rd['投次合计'], rd['复投条目数'], rd['本轮发图串条数']), (2, 1, 1))

    def test_n_expected_two_sends_but_one_found_is_red(self):
        r = self.ref('R2', eid='S18')
        r['投次'] = 2
        self.put_ledger('R2', [], extra_refs=[r])
        self.sent(r)
        self.assertEqual(self.run_group('R2'), 1)
        self.assertEqual(self.ledger_rounds('R2')[0]['落盘与回绑'], [])

    def test_o_drifted_send_needs_explicit_registration(self):
        r = self.ref('R2', eid='D08')
        r['投次'] = 2
        self.put_ledger('R2', [r], extra_refs=[dict(r, **{'作废发起': 1})])
        self.sent(r, write_file=False, body='正文甲乙')
        self.sent(r, ts=FROZEN_MS + 6000)
        self.assertEqual(self.run_group('R2'), 0, '登记了 1 枚作废发起就该放行')
        self.assertEqual(self.ledger_rounds('R2')[0]['落盘与回绑'][0]['非逐字发起数'], 1)

        self.put_ledger('R2', [r])          # 同一事实但不登记作废发起
        self.assertEqual(self.run_group('R2'), 1, '非逐字发起没登记也放行＝把发送侧字符损坏当投过')

    def test_p_registry_form_expands_and_counts_missing_sources(self):
        r = self.ref('R2', eid='L001')
        self.put_ledger('R2', [r])
        other = self.tmp / 'other.jsonl'
        other.write_text('', encoding='utf-8')
        self.sent(r, jsonl=other)           # 发起在另一份 transcript 里
        reg = self.tmp / 'reg.json'
        reg.write_text(json.dumps({'transcripts': {'a': str(other), 'b': str(self.jsonl)}}),
                       encoding='utf-8')
        self.assertEqual(self.run_group('R2', source=str(reg)), 0)
        rd = json.loads((self.here / 'round_readings.json').read_text(encoding='utf-8'))['统计面']
        self.assertEqual((rd['回绑源形态'], rd['回绑源在盘份数'], rd['回绑源缺失份数']),
                         ('transcript登记件', 2, 0))

        gone = str(self.tmp / 'no-such.jsonl')
        reg.write_text(json.dumps({'transcripts': {'a': str(other), 'x': gone}}), encoding='utf-8')
        self.assertEqual(self.run_group('R2', source=str(reg)), 1, '回绑源缺失仍放行＝拿缺失当通过')
        rd = json.loads((self.here / 'round_readings.json').read_text(encoding='utf-8'))['统计面']
        self.assertEqual(rd['回绑源缺失份数'], 1)
        self.assertEqual(rd['回绑源缺失清单'], [gone])

    def test_q_comma_separated_jsonl_list_binds_both_sends(self):
        r = self.ref('R1', eid='L002')
        r['投次'] = 2
        self.put_ledger('R1', [r])
        other = self.tmp / 'other2.jsonl'
        other.write_text('', encoding='utf-8')
        self.sent(r, jsonl=other, write_file=False)
        self.sent(r, ts=FROZEN_MS + 7000)
        self.assertEqual(self.run_group('R1', source='%s,%s' % (self.jsonl, other)), 0)
        self.assertEqual(self.ledger_rounds('R1')[0]['落盘与回绑'][0]['逐字发起数'], 2)

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

    # ── R4 母图臂：整串逐字 ＋ images 文件名 ＋ 双发投次 ─────────────────────
    # R4 接线时一条单测都没有，小样本（已投 14／395）才补上。三道判据各配违例负测：
    # 整串（前导声明一行＋正文）逐字、images 按台账 ref_image 文件名核、双发靠投次承载。
    LEAD4 = '图1 只作本条的画风母图：只借媒介与笔触，不借构图。\n'
    REF4 = '数据/视觉控制资产/E1定档-20261103/D03-母图.png'

    def ref4(self, eid='D13', body=None):
        r = self.ref('R4', eid=eid, body=(self.LEAD4 + '正文逐字。') if body is None else body)
        r['ref_image'] = self.REF4
        return r

    def test_r4_a_mother_image_string_form_is_green(self):
        r = self.ref4()
        self.put_ledger('R4', [r])
        self.sent(r, images=[self.REF4])
        self.assertEqual(self.run_group('R4'), 0)
        row = self.ledger_rounds('R4')[0]['落盘与回绑'][0]
        self.assertTrue(row['母图相符'])
        self.assertTrue(row['逐字相等'])

    def test_r4_b_mother_image_object_form_is_also_read(self):
        # 工具本身只收字符串数组，但 transcript 里留着对象形态那一发（D13 首送）：闸门读法两种都要认，
        # 否则那一发会被当成「没挂母图」，把一次参数校验失败误判成裸串违例。
        r = self.ref4()
        self.put_ledger('R4', [r])
        self.sent(r, images=[{'type': 'image', 'source': self.REF4}])
        self.assertEqual(self.run_group('R4'), 0)
        self.assertTrue(self.ledger_rounds('R4')[0]['落盘与回绑'][0]['母图相符'])

    def test_r4_c_empty_images_is_red(self):
        r = self.ref4()
        self.put_ledger('R4', [r])
        self.sent(r, images=[])
        self.assertEqual(self.run_group('R4'), 1, '漏挂母图＝投成裸串，探针实测裸串出照片质感')
        self.assertFalse(self.ledger_rounds('R4')[0]['落盘与回绑'][0]['母图相符'])

    def test_r4_d_images_field_absent_is_red(self):
        r = self.ref4()
        self.put_ledger('R4', [r])
        self.sent(r)                       # images=None → input 里根本没有这个键
        self.assertEqual(self.run_group('R4'), 1)
        self.assertFalse(self.ledger_rounds('R4')[0]['落盘与回绑'][0]['母图相符'])

    def test_r4_e_wrong_mother_is_red(self):
        r = self.ref4()
        self.put_ledger('R4', [r])
        self.sent(r, images=['数据/视觉控制资产/卡牌/主图3x4/L016.png'])
        self.assertEqual(self.run_group('R4'), 1, '挂错母图＝投的不是本轮那条路线')
        self.assertFalse(self.ledger_rounds('R4')[0]['落盘与回绑'][0]['母图相符'])

    def test_r4_f_bare_body_without_leading_line_is_red(self):
        r = self.ref4()
        self.put_ledger('R4', [r])
        self.sent(r, body='正文逐字。', images=[self.REF4])
        self.assertEqual(self.run_group('R4'), 1, '少前导一行＝裸串臂，不是本轮母图臂')
        row = self.ledger_rounds('R4')[0]['落盘与回绑'][0]
        self.assertFalse(row['逐字相等'])
        self.assertFalse(row['母图相符'], '母图列只在逐字命中的发起上核，串不符会连带判 False')

    def test_r4_g_two_verbatim_sends_zero_void_is_green(self):
        """D13 的真实形态：首发 images 写成对象数组被工具校验挡下（零产物），重发成功，
        两发 prompt 都逐字相等。作废在 images 轴上，不在串面轴上，所以「作废发起」登记 0。"""
        r = self.ref4()
        r['投次'] = 2
        r['复投'] = 'images 形态校验失败重发'
        self.put_ledger('R4', [r], extra_refs=[dict(r, **{'作废发起': 0})])
        self.sent(r, images=[{'type': 'image', 'source': self.REF4}], write_file=False)
        self.sent(r, ts=FROZEN_MS + 5000, images=[self.REF4])
        self.assertEqual(self.run_group('R4'), 0)
        row = self.ledger_rounds('R4')[0]['落盘与回绑'][0]
        self.assertEqual((row['投次'], row['逐字发起数'], row['非逐字发起数'], row['登记作废发起数']),
                         (2, 2, 0, 0))

    def test_r4_h_two_verbatim_sends_but_void_one_registered_is_red(self):
        """陷阱负测：把「作废发起」读成「作废掉的发次数」而填 1，drifted(0)≠known_drift(1) 必须判红。
        这一列只数串面不符的发次；填错不会洗绿，只会把一条本该绿的判红——两个方向都要钉住。"""
        r = self.ref4()
        r['投次'] = 2
        r['复投'] = 'images 形态校验失败重发'
        self.put_ledger('R4', [r], extra_refs=[dict(r, **{'作废发起': 1})])
        self.sent(r, images=[{'type': 'image', 'source': self.REF4}], write_file=False)
        self.sent(r, ts=FROZEN_MS + 5000, images=[self.REF4])
        self.assertEqual(self.run_group('R4'), 1)
        self.assertFalse(self.ledger_rounds('R4')[0]['落盘与回绑'][0]['逐字相等'])

    def test_r4_i_without_ref_image_the_mother_check_is_inert(self):
        """变异自证：台账不写 ref_image 时母图列恒 True，test_r4_c/d/e 全部失效。
        所以「R4 台账逐条必须带 ref_image」是一条真判据，由 test_r4_j 在真数据上钉住。"""
        r = self.ref4()
        r['ref_image'] = ''
        self.put_ledger('R4', [r])
        self.sent(r, images=[])
        self.assertEqual(self.run_group('R4'), 0, '母图判据已空转却仍判红＝test_r4_c 测的不是这一条')
        self.assertTrue(self.ledger_rounds('R4')[0]['落盘与回绑'][0]['母图相符'])

    def test_r4_j_real_ledger_every_entry_declares_its_mother(self):
        led = json.loads((CAMPAIGN / 'send_bodies_r4.json').read_text(encoding='utf-8'))
        note = json.loads((CAMPAIGN / 'send_bodies_r4_note.json').read_text(encoding='utf-8'))
        self.assertEqual(len(led), note['成员面']['本轮待重投'], '台账条数与轮次口径说明分叉')
        self.assertEqual([k for k, v in sorted(led.items()) if not v.get('ref_image')], [],
                         '有母图臂条目没写 ref_image＝母图判据对它恒绿（见 test_r4_i）')
        self.assertEqual([k for k, v in sorted(led.items())
                          if not v['body'].startswith(note['前导声明'])], [],
                         '有串面不带前导声明＝投出去的是裸串臂')

    def test_r4_k_evidence_record_is_self_consistent(self):
        main = json.loads((CAMPAIGN / 'send_bodies_r4.json').read_text(encoding='utf-8'))
        ev = json.loads((CAMPAIGN / 'send_bodies_r4_evidence.json').read_text(encoding='utf-8'))
        self.assertTrue(ev, '覆盖件空集＝并轨断言无样本')
        for eid, rec in sorted(ev.items()):
            with self.subTest(eid=eid):
                self.assertIn(eid, main, '覆盖件里出现主台账没有的条目＝串面出现第二条真源')
                self.assertEqual(rec['body'], main[eid]['body'], eid)
                self.assertEqual(rec['send_name'], main[eid]['send_name'], eid)
                self.assertGreaterEqual(int(rec['投次']), 2, '覆盖件只该登记多投条目')
                self.assertTrue(rec.get('作废删除') or rec.get('复投') or rec.get('点单'),
                                '%s 记了多投却没写任何一次投放事实' % eid)
                self.assertLessEqual(int(rec.get('作废发起', 0)), int(rec['投次']), eid)

    def test_r4_l_group_config_points_at_evidence_file(self):
        cfg = vr.GROUPS['R4']
        self.assertEqual(cfg['suffix'], 'C154母图重投-v01')
        self.assertEqual(cfg['bodies'], 'send_bodies_r4.json')
        self.assertEqual(cfg['bodies_extra'], ['send_bodies_r4_evidence.json'])
        for f in ((cfg['bodies'], cfg['readings'], cfg['ledger'], 'transcripts_r4.json')
                  + tuple(cfg['bodies_extra'])):
            self.assertTrue((CAMPAIGN / f).exists(), f)

    def test_r4_m_without_extra_ledger_stops_before_any_write(self):
        r = self.ref4()
        (self.here / vr.GROUPS['R4']['bodies']).write_text(
            json.dumps({r['id']: r}, ensure_ascii=False, indent=1), encoding='utf-8')
        with self.assertRaises(AssertionError) as cm:
            self.run_group('R4')
        self.assertIn('缺并集补充台账', str(cm.exception))
        for fn in ('round_readings_r4.json', 'ledger_r4.json'):
            self.assertFalse((self.here / fn).exists(), '缺双发证据那轮仍落了笔：%s' % fn)

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

    def test_y_real_ledgers_on_disk_are_all_pinned(self):
        """盘上已有的轮次件必须逐件钉进 REAL_FILES，豁免面只许留给真不存在的件。

        为什么要这条：REAL_FILES 是「夹具没写仓库侧」的唯一报警器，漏钉的那件即便被夹具改了也没人红。
        本窗实测盘上就有三件从未进清单（`round_readings_r1`／`ledger_r1`／`send_bodies_r4_note`，
        最后一件还是本文件 481 行自己读过的真源），说明"名单靠手记"这一条本身会漂。
        豁免名单现为空：R8 的 readings／ledger 已在 2026-11-22 落盘并钉进 REAL_FILES，
        上一窗那条「盘上没有所以豁免」的理由随之作废。R9 台账（send_bodies_r9 两件）同理，
        2026-11-22 晚落盘时未同笔进名单，本条当场判红，补钉后转绿——这正是它要起的作用。
        通道保留而不删——下一窗若又有轮次件未落盘，
        豁免只许按文件名逐条写死并要求其真不在盘上，一落盘这条当场判红，不许留成永远为真的空子。"""
        exempt = frozenset()
        pref = ('send_bodies_', 'ledger', 'round_readings_', 'transcripts_')
        on_disk = {p.name for p in CAMPAIGN.iterdir() if p.suffix == '.json' and p.name.startswith(pref)}
        self.assertEqual(sorted(on_disk - set(REAL_FILES)), [], '盘上已有却未钉进 REAL_FILES')
        still_there = sorted(f for f in exempt if (CAMPAIGN / f).exists())
        self.assertEqual(still_there, [], '豁免名单过期（该件已落盘，须钉进清单并删豁免）：%s' % still_there)


class MergedR2Ledger(unittest.TestCase):
    """仓内并轨台账与回绑源登记件对真源自证——串面一旦和 数据/开图提示词 分叉，闸门就白跑。

    字段分两支路：body/send_name/size/replaced_cell 可从真源重算（不等即缺陷，没有申报通道）；
    投次/作废发起/作废删除 是本轮投放事实的登记，只能对「登记自洽」负责，不能由仓库重算。
    """

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            'bs_under_test', str(CAMPAIGN / 'build_send_bodies.py'))
        cls.bs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.bs)
        cls.led = json.loads((CAMPAIGN / 'send_bodies_r2_full.json').read_text(encoding='utf-8'))
        cls.pilot = json.loads((CAMPAIGN / 'send_bodies_r1.json').read_text(encoding='utf-8'))
        cls.reg = json.loads((CAMPAIGN / 'transcripts_r2.json').read_text(encoding='utf-8'))
        # R2 投于 C153 换档之前，台账里那 58 串逐字属于**换档前**基准。现读正文自 C153 起画风三处已回退，
        # 所以「逐字等于现读正文」这条历史断言在换档后必然失效——留它等于每换一次档就要来改一次判据。
        # 换档前基准串取 C153 登记件的 before（长期留档，不随生成器重写）。
        dig = json.loads((ROOT / '工具' / 'reinject_2026_11_05' / 'prompt_digests_c153.json')
                         .read_text(encoding='utf-8'))
        cls.before = {k: v['before'] for k, v in dig['items'].items()}
        # 2026-11-22 C154 补记（8）：20 个片区的取景段换档，登记件里 changed 的那些条，
        # 现读正文的【取景指令】行与 R2 历史串不同是被裁定的换档，不是静默改动。
        reg = json.loads((ROOT / '工具' / 'reinject_2026_11_05' /
                          'prompt_digests_c154_framing.json').read_text(encoding='utf-8'))
        cls.framing_shift = {k for k, v in reg['items'].items() if v['changed']}
        assert cls.framing_shift, '换档登记件里没有变更条，本条豁免面为空＝判据会空转'
        cls.r2round = json.loads((CAMPAIGN / 'ledger.json').read_text(encoding='utf-8'))['rounds'][-1]
        cls.queue = json.loads((CAMPAIGN / 'queue.json').read_text(encoding='utf-8'))
        cls.snap = json.loads((ROOT / '数据' / '提示词基准冻结.json').read_text(encoding='utf-8'))

    def test_a_body_is_verbatim_from_prompt_source(self):
        """R2 台账的串面自证，拆成两支各管一段时间：
        ①对历史本身——台账记的 sha256 必须逐条等于 C153 换档前的基准串，正文长度对得上 chars：
          这一支证明「投出去的那一份」没被事后改写。
        ②对现读真源——现读正文与台账正文的行级差异只许落在画风三处行上（【画风锚点】／
          【全局硬设定】／English tail），别的行为改动一律点名。
          拿「逐字相同」当判据在 C153 之后是恒红，拿「不再比对」当修法则是把守卫删了：
          真源日后若改了科技层词、取景段或人群段，历史台账就再没人核对，正是这条要防的。"""
        for eid, rec in sorted(self.led.items()):
            with self.subTest(eid=eid):
                name, _src, cur = self.bs.body_of(str(ROOT), eid)
                self.assertEqual(name, rec['file'], eid)
                self.assertEqual(len(rec['body']), rec['chars'], eid)
                self.assertEqual(rec['sha256'], self.before[eid],
                                 '台账摘要不是 C153 换档前的基准串（历史串面被改写？）')
                bad = style_only_diff(rec['body'], cur)
                if eid in self.framing_shift:
                    bad = [b for b in bad if '【取景指令】' not in b]
                self.assertEqual(bad, [], '%s｜%s' % (eid, bad[:2]))
                self.assertTrue(rec['send_name'].endswith('-' + SUFFIX['R2']), eid)

    def test_style_only_diff_guard_is_not_inert(self):
        """违例负测：②那一支必须能被两种坏数据打红——画风行以外的行变了、以及画风三处一行都没变
        （后者防的是真源被整份复制回来、对拍退化成恒绿的空转）。全在内存里造，不写盘。"""
        # 承载件取「不在取景换档面里」的第一条：换档条的【取景指令】行与 R2 历史串本就不同，
        # 拿它当基线会读到豁免前的差异，负测就变成在验豁免而不是验守卫。
        eid, rec = next((k, v) for k, v in sorted(self.led.items())
                        if k not in self.framing_shift)
        name, _src, cur = self.bs.body_of(str(ROOT), eid)
        self.assertEqual(style_only_diff(rec['body'], cur), [], '基线：真实对拍本身必须先达标')
        lines = cur.split('\n')
        non_style = next(i for i, l in enumerate(lines) if not l.startswith(STYLE_LINE_PREFIXES))
        self.assertTrue(style_only_diff(rec['body'], '\n'.join(
            [(lines[non_style] + '（本轮悄悄加了半句）' if i == non_style else l)
             for i, l in enumerate(lines)])), '画风行以外的改动没被点名')
        self.assertTrue(style_only_diff(rec['body'], rec['body']), '画风三处一行都没变时没判红，对拍已空转')

    def test_b_member_face_matches_its_own_round_and_queue_is_fresh(self):
        """成员面三支对拍（口径与拆分理由见 r2_member_face_violations 的 docstring）。
        试点 4 条必须是并集子集且串面逐字相同——那一支不受冻结带影响，原样保留。"""
        bad = r2_member_face_violations(self.led, self.r2round, self.queue, self.snap, SUFFIX['R2'])
        self.assertEqual(bad, [], '｜'.join(bad))
        self.assertTrue(set(self.pilot) <= set(self.led), '试点 4 条不在并集里＝两份真源各说各话')
        for eid in set(self.pilot) & set(self.led):
            self.assertEqual(self.pilot[eid]['body'], self.led[eid]['body'], eid)
            self.assertEqual(self.pilot[eid]['send_name'], self.led[eid]['send_name'], eid)

    def test_b_negative_all_three_branches_and_the_inert_guard_go_red(self):
        """违例负测：三支各造一种坏数据，外加「轮次台账没登记发起条目」的空转形态。
        全在内存里改副本，不写盘；基线先自证真实对拍本身达标，否则下面每条红都可能是基线就红。"""
        args = (self.led, self.r2round, self.queue, self.snap, SUFFIX['R2'])
        self.assertEqual(r2_member_face_violations(*args), [], '基线：真实对拍本身必须先达标')

        led = dict(self.led)
        led.pop(sorted(led)[0])
        self.assertTrue(r2_member_face_violations(led, self.r2round, self.queue, self.snap, SUFFIX['R2']),
                        '①少一条没判红＝读取面缺条没人管')
        led = dict(self.led, **{'ZZZ_不存在': self.led[sorted(self.led)[0]]})
        self.assertTrue(r2_member_face_violations(led, self.r2round, self.queue, self.snap, SUFFIX['R2']),
                        '①多一条没判红')

        q = copy.deepcopy(self.queue)
        q['frozen_at_ms'] = int(self.snap['frozen_at_ms']) - 1
        self.assertTrue(r2_member_face_violations(self.led, self.r2round, q, self.snap, SUFFIX['R2']),
                        '②派生队列过期没判红')

        q = copy.deepcopy(self.queue)
        drop = sorted(self.led)[0]
        q['R2_绑定关口']['entries'] = [e for e in q['R2_绑定关口']['entries'] if e['id'] != drop]
        self.assertTrue(r2_member_face_violations(self.led, self.r2round, q, self.snap, SUFFIX['R2']),
                        '③历史条目从现读队列消失没判红')

        rnd = dict(self.r2round, **{'本轮发起条目': []})
        self.assertTrue(r2_member_face_violations(self.led, rnd, self.queue, self.snap, SUFFIX['R2']),
                        '空集被当成达标＝①整支空转')
        rnd = dict(self.r2round, **{'档串': SUFFIX['R1']})
        self.assertTrue(r2_member_face_violations(self.led, rnd, self.queue, self.snap, SUFFIX['R2']),
                        '取错轮次没判红')

    def test_c_round_evidence_fields_are_self_consistent(self):
        for eid, rec in sorted(self.led.items()):
            self.assertGreaterEqual(int(rec.get('投次', 1)), 1, eid)
            self.assertGreaterEqual(int(rec.get('作废发起', 0)), 0, eid)
            if int(rec['投次']) > 1:
                self.assertTrue(rec.get('作废删除') or rec.get('复投') or rec.get('点单'),
                                '%s 记了多投却没写任何一次投放事实' % eid)
            for f in rec.get('作废删除', []):
                self.assertFalse((ROOT.parent / 'vibe_images' / f).exists(),
                                 '%s 登记的作废枚仍在盘＝落盘面不是 1 枚' % eid)

    def test_d_transcript_registry_shape(self):
        self.assertEqual(self.reg['group'], 'R2')
        self.assertEqual(self.reg['suffix'], SUFFIX['R2'])
        self.assertTrue(self.reg['declaration'])
        vals = list(self.reg['transcripts'].values())
        self.assertEqual(len(set(vals)), len(vals), '登记件里有重复真源＝份数读数虚高')
        for v in vals:
            self.assertTrue(v.endswith('.jsonl'), v)
        subs = [v for v in vals if os.path.sep + 'subagents' in v or '/subagents/' in v]
        self.assertEqual(len(subs), len(vals) - 1,
                         '除恰一份主会话 jsonl 外，其余都必须显式是子代理 transcript')


class MergedR1Ledger(unittest.TestCase):
    """R1 组的并轨真源自证：证据台账不许开出第二条串面，登记件形状要与 R2 同口径。

    R1 的补充台账只装「发起次数≠1」的条目，正文逐字抄自主台账；
    transcript 路径在会话临时区，这里只钉形状与自洽，不钉存在（存在性由真轮核验负责）。
    """

    @classmethod
    def setUpClass(cls):
        cls.primary = json.loads((CAMPAIGN / 'send_bodies_r1_primary.json').read_text(encoding='utf-8'))
        cls.ev = json.loads((CAMPAIGN / 'send_bodies_r1_evidence.json').read_text(encoding='utf-8'))
        cls.reg = json.loads((CAMPAIGN / 'transcripts_r1.json').read_text(encoding='utf-8'))

    def test_a_evidence_bodies_are_copies_not_a_second_source(self):
        for eid, rec in sorted(self.ev.items()):
            self.assertIn(eid, self.primary, eid)
            self.assertEqual(rec['body'], self.primary[eid]['body'], eid)
            self.assertEqual(rec['send_name'], self.primary[eid]['send_name'], eid)
            self.assertTrue(rec['send_name'].endswith('-' + SUFFIX['R1']), eid)

    @staticmethod
    def _landed_name(rec_field, eid, label):
        """台账里的落盘登记串是「文件名｜字节｜sha256-12｜说明」四段装饰串，取第一段才是盘上的名字。

        Why: 2026-11-07 首版直接把整串拼进 `vibe_images/<整串>` 去 exists()，那路径永远不存在，
        「作废枚必须不在盘」就成了恒真判据（假绿）。名字取错段还会连带把留盘枚判成不在盘，
        所以取段本身也要钉形状，不许静默退化成另一个恒真／恒假。
        """
        parts = [p.strip() for p in str(rec_field).split('｜')]
        assert len(parts) == 4, (eid, label, parts)
        assert parts[0].endswith('.png') and '_' in parts[0], (eid, label, parts[0])
        assert parts[1].endswith('B') and parts[1][:-1].isdigit(), (eid, label, parts[1])
        assert parts[2].startswith('sha256-12 ') and len(parts[2]) == 22, (eid, label, parts[2])
        return parts[0]

    def test_b_only_multi_send_entries(self):
        want = sorted(k for k, v in self.ev.items() if int(v['投次']) > 1)
        self.assertEqual(sorted(self.ev), want, '证据台账里混进了单发条目＝主台账与证据各说各话')
        landing = ROOT.parent / 'vibe_images'
        for eid, rec in self.ev.items():
            sends = int(rec['投次'])
            drift = int(rec.get('作废发起', 0))
            self.assertTrue(sends >= 2 and 0 <= drift < sends, eid)
            self.assertTrue(rec.get('作废删除') or rec.get('复投'), '%s 记了多投却没写投放事实' % eid)
            for f in rec.get('作废删除', []):
                self.assertFalse((landing / self._landed_name(f, eid, '作废删除')).exists(),
                                 '%s 登记的作废枚仍在盘＝落盘面不是 1 枚' % eid)
            for f in rec.get('留盘枚') or []:
                self.assertTrue((landing / self._landed_name(f, eid, '留盘枚')).exists(),
                                '%s 登记的留盘枚不在盘＝落盘面读数为零' % eid)
            # 「落盘面恒为 1 枚」直接按盘面数，不依赖上面两串的登记形状。
            # 这一条同时是那两个 exists() 判据的非惰性证明：路径基底猜错时这里必红，
            # 而作废枚「不在盘」与留盘枚「在盘」不会同时被一个错基底糊过去。
            on_disk = sorted(p.name for p in landing.glob('%s-*-%s_*' % (eid, SUFFIX['R1'])))
            self.assertEqual(len(on_disk), 1, (eid, on_disk))

    def test_c_registry_shape_matches_r2_conventions(self):
        self.assertEqual(self.reg['group'], 'R1')
        self.assertEqual(self.reg['suffix'], SUFFIX['R1'])
        self.assertTrue(self.reg['declaration'])
        vals = list(self.reg['transcripts'].values())
        self.assertEqual(len(set(vals)), len(vals), '登记件里有重复真源＝份数读数虚高')
        subs = [v for v in vals if os.path.sep + 'subagents' in v or '/subagents/' in v]
        self.assertEqual(len(subs), len(vals) - 1,
                         '除恰一份主会话 jsonl 外，其余都必须显式是子代理 transcript')
        self.assertEqual(self.reg['条数'], len(self.primary))
        self.assertEqual(self.reg['发起合计'], sum(int(v['投次']) for v in self.ev.values())
                         + len(self.primary) - len(self.ev))

    def test_d_group_config_points_at_both_files(self):
        cfg = vr.GROUPS['R1']
        self.assertEqual(cfg['bodies'], 'send_bodies_r1_primary.json')
        # R1 的发送面已经有三份：264 主向全量 ＋ 复投证据 ＋ C139 后 48 条「非新画风／缺图」补投。
        # 这份断言按列表逐字钉住补充台账名单，少一份就是把补投过的条目当没投过（同 §55.21 的回绑口径）。
        self.assertEqual(cfg['bodies_extra'], ['send_bodies_r1_evidence.json', 'send_bodies_r1_catchup.json'])
        for f in (cfg['bodies'], 'transcripts_r1.json', 'transcripts_r3.json') + tuple(cfg['bodies_extra']):
            self.assertTrue((CAMPAIGN / f).exists(), f)


R6_VISUAL_HEAD = '2026-11-20 R6 组画风目视'
R7_VISUAL_HEAD = '2026-11-20 R7 组画风目视'


def _r6_failed_face(notes):
    """画风目视判废面：每条 ID 最后一条 R6 目视行里带「｜判废（」的那些年。

    这里与 build_send_bodies_r7.judged_failed() 各写一遍而不 import 它：
    共用一份实现的话，派生逻辑一漂，两条断言会一起变绿，接线自证就成了空转。"""
    face = []
    for eid, rows in notes.items():
        hits = [s for s in rows if R6_VISUAL_HEAD in s]
        if hits and '｜判废（' in hits[-1]:
            face.append(eid)
    return sorted(face)


class R7JudgedFailedReshoot(unittest.TestCase):
    """R7（R6 画风目视判废 3 枚同串同母图重抽）的接线自证：只读真源、不建夹具、不写盘。

    这一轮没有新增画风口径，所以判据是三组「不许漂」的等式：
    成员面＝备注里 R6 目视现算的判废面（名单不许手抄）；正文与母图＝R4 台账同条逐字节相等（否则那三笔钱买的不是「同串重抽」）；
    verify_round 的组配置与盘上真文件名互相指得上（哪一处漏接线，那一轮的读数就落在闸门看不见的地方）。
    """

    @classmethod
    def setUpClass(cls):
        cls.led = json.loads((CAMPAIGN / 'send_bodies_r7.json').read_text(encoding='utf-8'))
        cls.r4 = json.loads((CAMPAIGN / 'send_bodies_r4.json').read_text(encoding='utf-8'))
        cls.readings = json.loads((CAMPAIGN / 'round_readings_r7.json').read_text(encoding='utf-8'))
        cls.ledger = json.loads((CAMPAIGN / 'ledger_r7.json').read_text(encoding='utf-8'))
        cls.notes = json.loads((ROOT / '数据' / '开图验收备注.json').read_text(encoding='utf-8'))['备注']

    def test_a_group_config_points_at_this_rounds_own_files(self):
        cfg = vr.GROUPS['R7']
        self.assertEqual(cfg['suffix'], 'C154判废补重投-v01')
        self.assertEqual(cfg['bodies'], 'send_bodies_r7.json')
        for f in (cfg['bodies'], cfg['readings'], cfg['ledger'], 'send_bodies_r7_note.json'):
            self.assertTrue((CAMPAIGN / f).exists(), f)
        self.assertNotIn('bodies_extra', cfg,
                         'R7 无双发条目却配了并集补充台账＝verify_round 会在写盘前停手，读数永远落不下来')

    def test_b_member_face_is_derived_from_the_notes(self):
        self.assertEqual(sorted(self.led), _r6_failed_face(self.notes),
                         'R7 台账成员面与备注里 R6 目视判废现算结果分叉＝名单被手抄过或目视行改了写法')
        flipped = copy.deepcopy(self.notes)
        flipped['D18'] = [s.replace('｜判废（', '｜达标（') for s in flipped['D18']]
        self.assertNotIn('D18', _r6_failed_face(flipped),
                         '把「判废」改写成「达标」后 D18 仍被数到＝上一条断言在空转')

    def test_c_same_arm_as_r4_byte_for_byte(self):
        for eid, rec in sorted(self.led.items()):
            with self.subTest(eid=eid):
                base = self.r4[eid]
                self.assertEqual(rec['body'], base['body'], '两轮正文不等＝这笔钱买的不是「同串重抽」')
                self.assertEqual(rec['send_sha256'], base['send_sha256'], eid)
                self.assertEqual(rec['ref_image'], base['ref_image'], '两轮母图不等＝一次投放同时动了两个变量')
                self.assertIn('C154判废补重投-v01', rec['send_name'], eid)

    def test_d_readings_and_ledger_agree_on_the_three_sends(self):
        rows = self.readings['rows']
        self.assertEqual([r['id'] for r in rows], sorted(self.led), '读数行与台账条目不对面')
        for r in rows:
            with self.subTest(eid=r['id']):
                self.assertTrue(r['逐字相等'], '逐字回绑红了却已回填＝接线自证没进闸门')
                self.assertTrue(r['size_match'], '%s 送 %s 落 %s' % (r['id'], r['declared_size'], r['dims']))
                self.assertTrue(r['母图相符'], '%s 投放用的母图与台账登记不符' % r['id'])
                self.assertEqual(r['投次'], 1, '本组没有多投条目，投次>1 说明台账与落盘对不上')
                self.assertTrue(r['container']['itxt'] >= 1 and r['container']['aigc'],
                                '%s 容器判据 C136 红（caBX/iTXt）' % r['id'])
                self.assertTrue(r['container']['tc260'], '%s 缺 TC260 标识' % r['id'])
        rnd = self.ledger['rounds'][-1]
        self.assertEqual(rnd['组别'], 'R7')
        self.assertEqual(rnd['投次合计'], len(rows))
        self.assertEqual(rnd['复投条目'], [])

    def test_e_backfill_moved_the_registered_cell_and_kept_the_old_one(self):
        _cc = importlib.util.spec_from_file_location(
            'cc_r7', str(CAMPAIGN / 'current_cells.py'))
        cc = importlib.util.module_from_spec(_cc)
        _cc.loader.exec_module(cc)
        _q, rows, excluded = cc.current_cells(str(ROOT))
        cells = {r['id']: r for r in rows}
        self.assertEqual([e['id'] for e in excluded if e['id'] in self.led], [],
                         '本轮条目被 current_cells 剔出在册面＝目视与后续判据看不到交付的那一格')
        # 2026-11-22 订正（R8 落盘后本条判红 3 处，根因在本断言自己）：这里原先写死
        # 「在册格档串必须含 C154判废补重投」，那是把「R7 是最新一轮」当成永恒事实——R8 同串重抽把
        # 同一格换掉后，它判红判的不是「回填没接上」而是「后面又投了一轮」。与 5 号点单修的是同一缺陷类。
        # 换成随 GROUPS 声明序派生的「不许退回 R7 之前」，加一条 R7 交付枚本身仍在盘、仍被 R7 机械行点名。
        order = list(vr.GROUPS)
        r7_rank = order.index('R7')
        delivered = {r['id']: r['file'] for r in self.readings['rows']}
        for eid in sorted(self.led):
            with self.subTest(eid=eid):
                sfx = cells[eid]['档串']
                rank = max([i for i, g in enumerate(order)
                            if vr.GROUPS[g]['suffix'].split('-v')[0] in sfx], default=-1)
                # R10 走方舟 HTTP、不经 ImageGen 工具，故不进 GROUPS（GROUPS 是 jsonl 取数面），
                # 但它回填后确实占格，档串是「二次重投」「换档重投」两支之一——排序必须认它们为
                # 「比 GROUPS 里任何一轮都晚」，否则在册格一换，这条就假报「退回 R7 之前」。
                if any(t in sfx for t in vr.LATER_ROUND_SUFFIXES):
                    rank = len(order)
                self.assertGreaterEqual(rank, r7_rank,
                                        '在册格档串 %s 退回 R7 之前＝R7 之后的回填链断了，'
                                        '目视会打在没有交付的那一格上（不许把这条改回写死 R7 为最新）' % sfx)
                self.assertTrue(cells[eid]['在盘'], eid)
                self.assertTrue((ROOT / '数据' / '图集' / eid / delivered[eid]).is_file(),
                                'R7 交付枚本身不在盘＝后续轮次把它删了，重投只许替换不许抹旧')
                self.assertTrue(any(delivered[eid] in s for s in self.notes[eid]
                                    if s.startswith('C154判废补重投' + eid)),
                                'R7 机械行没点名自己那枚＝回填与备注分叉')
                self.assertTrue((ROOT / self.led[eid]['replaced_cell']).exists(),
                                '被替换的旧格删掉了＝「生成物永不手改／只追加」这条破了')
        self.assertEqual(sorted([e for e, v in self.led.items() if v['status_before'] == '待复验']),
                         sorted(self.led), '本组不许出现非待复验状态（重投不推进 status，推进归人工签署）')

    def test_f_visual_conclusion_is_a_separate_row_and_not_signed_by_script(self):
        heads = {eid: [s for s in rows if s.startswith(R7_VISUAL_HEAD)]
                 for eid, rows in self.notes.items()}
        judged = sorted([e for e, h in heads.items() if h])
        self.assertEqual(judged, sorted(self.led), 'R7 目视行的覆盖面与本轮成员面不一致')
        for eid in judged:
            with self.subTest(eid=eid):
                self.assertEqual(len(heads[eid]), 1, '同一条 R7 目视结论写了两遍＝追加面出现第二条真源')
                tail = heads[eid][0]
                self.assertIn('非脚本代签', tail, eid)
                self.assertIn('｜达标（', tail, eid)


R8_VISUAL_HEAD = '2026-11-22 R8 组目视（画风＋取景分栏）'


def _r7_framing_defect_face(notes):
    """R8 成员面＝R7 目视行里「取景与量级栏另记」记了缺陷的那几枚——现算，不手抄名单。

    判据只认另记段落里的缺陷动词（画入／量级不符／塔吊），并给一条显式豁免句
    「本条取景与量级合规」留负测通道：改写成合规即从面里掉出去，上一条断言就不许空转。
    """
    face = []
    for eid, rows in notes.items():
        for s in rows:
            if not s.startswith(R7_VISUAL_HEAD):
                continue
            body = s[s.find('取景与量级栏另记'):] if '取景与量级栏另记' in s else ''
            if body and '本条取景与量级合规' not in body \
                    and any(k in body for k in ('画入', '量级不符', '塔吊')):
                face.append(eid)
    return sorted(face)


class R8FramingReshoot(unittest.TestCase):
    """R8（R7 目视画风达标而取景与量级在册缺陷的 3 枚同串同母图重抽）的接线自证。

    与 R7 同一套写法：只读真源、不建夹具、不写盘；成员面与缺陷文本都从 R7 目视行现算，
    付费面（投次／复投／零产物那一次）从读数与证据台账现算，任何一处手抄都会与盘上分叉。
    """

    @classmethod
    def setUpClass(cls):
        cls.led = json.loads((CAMPAIGN / 'send_bodies_r8.json').read_text(encoding='utf-8'))
        cls.ev = json.loads((CAMPAIGN / 'send_bodies_r8_evidence.json').read_text(encoding='utf-8'))
        cls.r7 = json.loads((CAMPAIGN / 'send_bodies_r7.json').read_text(encoding='utf-8'))
        cls.r4 = json.loads((CAMPAIGN / 'send_bodies_r4.json').read_text(encoding='utf-8'))
        cls.readings = json.loads((CAMPAIGN / 'round_readings_r8.json').read_text(encoding='utf-8'))
        cls.notes = json.loads((ROOT / '数据' / '开图验收备注.json').read_text(encoding='utf-8'))['备注']

    def test_a_group_config_wires_the_evidence_channel(self):
        cfg = vr.GROUPS['R8']
        self.assertEqual(cfg['suffix'], 'C154取景补重投-v01')
        self.assertEqual(cfg['bodies'], 'send_bodies_r8.json')
        self.assertEqual(cfg['bodies_extra'], ['send_bodies_r8_evidence.json'],
                         'L069 那次 terminated 发起只住在并集补充台账里，漏配就等于把一次付费调用从调用面上抹掉')
        for f in (cfg['bodies'], cfg['readings'], cfg['ledger'],
                  'send_bodies_r8_note.json') + tuple(cfg['bodies_extra']):
            self.assertTrue((CAMPAIGN / f).exists(), f)

    def test_b_member_face_and_defect_text_are_derived_from_r7_notes(self):
        self.assertEqual(sorted(self.led), _r7_framing_defect_face(self.notes),
                         'R8 台账成员面与备注里 R7 取景与量级栏现算结果分叉＝名单被手抄过或目视行改了写法')
        flipped = copy.deepcopy(self.notes)
        flipped['D18'] = [(s.split('取景与量级栏另记')[0] + '取景与量级栏另记（按 C154(1) 分栏）：本条取景与量级合规。'
                           if s.startswith(R7_VISUAL_HEAD) else s) for s in flipped['D18']]
        self.assertNotIn('D18', _r7_framing_defect_face(flipped),
                         '把 D18 的取景栏改写成合规句后仍被数到＝上一条断言在空转')
        for eid, rec in sorted(self.led.items()):
            with self.subTest(eid=eid):
                r7row = [s for s in self.notes[eid] if s.startswith(R7_VISUAL_HEAD)]
                self.assertEqual(len(r7row), 1, eid)
                self.assertIn(rec['取景缺陷栏'][:24], r7row[0],
                              '台账里的取景缺陷文本不在 R7 目视行里＝缺陷面是抄来的，不是从上一轮结论派生的')

    def test_c_single_variable_same_body_and_matrix_as_r4_and_r7(self):
        for eid, rec in sorted(self.led.items()):
            with self.subTest(eid=eid):
                for other, tag in ((self.r4[eid], 'R4'), (self.r7[eid], 'R7')):
                    self.assertEqual(rec['body'], other['body'], '%s 正文不等＝这笔钱买的不是「同串重抽」' % tag)
                    self.assertEqual(rec['send_sha256'], other['send_sha256'], '%s 串摘要不等' % tag)
                    self.assertEqual(rec['ref_image'], other['ref_image'], '%s 母图不等＝一次投放动了两个变量' % tag)
                self.assertIn('C154取景补重投-v01', rec['send_name'], eid)

    def test_d_paid_face_reconciles_four_calls_three_products(self):
        st = self.readings['统计面']
        self.assertEqual(st['本轮发图串条数'], 3)
        self.assertEqual(st['投次合计'], 4, '放行面是 4 次调用（含 11-21 那次 terminated），不是 3 条')
        self.assertEqual(st['复投条目数'], 1)
        self.assertEqual(st['登记作废发起合计'], 0, '两发 prompt 逐字相等，作废的是那一次发起而不是串面')
        self.assertEqual(st['作废删除枚数合计'], 0)
        self.assertEqual(st['落盘在冻结带内条数'], 3, '落盘面必须与成员面同数：中断那次零产物、不计第二枚')
        self.assertEqual(sorted(self.ev), ['L069'], 'R8 只有 L069 有第二次发起')
        self.assertEqual(int(self.ev['L069']['投次']), 2)
        row = [r for r in self.readings['rows'] if r['id'] == 'L069'][0]
        self.assertEqual((row['投次'], row['逐字发起数'], row['非逐字发起数']), (2, 2, 0),
                         '读数面的 L069 发起面与证据台账不等＝并集通道没接上')

    def test_e_visual_rows_cover_the_face_and_split_the_two_columns(self):
        heads = {eid: [s for s in rows if s.startswith(R8_VISUAL_HEAD)]
                 for eid, rows in self.notes.items()}
        judged = sorted([e for e, h in heads.items() if h])
        self.assertEqual(judged, sorted(self.led), 'R8 目视行的覆盖面与本轮成员面不一致')
        for eid in judged:
            with self.subTest(eid=eid):
                self.assertEqual(len(heads[eid]), 1, '同一条 R8 目视结论写了两遍＝追加面出现第二条真源')
                tail = heads[eid][0]
                self.assertIn('非脚本代签', tail, eid)
                self.assertIn('画风栏 达标', tail, eid)
                self.assertIn('取景与量级栏另记', tail, eid)
                self.assertIn('CLIP 旁证 p_photo=', tail, '目视行没带 CLIP 旁证＝C134 的只作读数口径没落进这一轮')
        style_ok = sum(1 for e in judged if '画风栏 达标' in heads[e][0])
        framing_bad = sum(1 for e in judged if '不达标' in heads[e][0].split('取景与量级栏另记')[1])
        self.assertEqual((style_ok, framing_bad), (3, 3),
                         '两栏计数与目视现读不一致（画风达标面／取景不达标面要分别对得上本轮三枚）')

    def test_f_registered_cells_point_at_r8_and_old_cells_survive(self):
        _cc = importlib.util.spec_from_file_location('cc_r8', str(CAMPAIGN / 'current_cells.py'))
        cc = importlib.util.module_from_spec(_cc)
        _cc.loader.exec_module(cc)
        _q, rows, excluded = cc.current_cells(str(ROOT))
        cells = {r['id']: r for r in rows}
        self.assertEqual([e['id'] for e in excluded if e['id'] in self.led], [], 'R8 条目被剔出在册面')
        for eid in sorted(self.led):
            with self.subTest(eid=eid):
                sfx = cells[eid]['档串']
                # 同 test_e 的教训：写死「在册格必须是 R8 那枚」等于把「R8 是最新一轮」当成永恒事实，
                # R10 换掉同一格后判红判的不是回填断链，而是「后面又投了一轮」。改成「在册格是 R8 那枚，
                # 或被更晚一轮接管」，并另核 R8 交付枚仍在盘、仍被自己的机械行点名——重投只许替换不许抹旧。
                self.assertTrue('C154取景补重投' in sfx
                                or any(t in sfx for t in vr.LATER_ROUND_SUFFIXES),
                                'R8 交付后在册格既不是 R8 那枚、也不被更晚一轮接管＝档串断链：%s' % sfx)
                r8_file = {r['id']: r['file'] for r in self.readings['rows']}[eid]
                self.assertTrue((ROOT / '数据' / '图集' / eid / r8_file).is_file(),
                                'R8 交付枚不在盘＝后续轮次把它删了，重投只许替换不许抹旧')
                self.assertTrue((ROOT / self.led[eid]['replaced_cell']).exists(),
                                '被 R8 替换掉的 R7 旧格删掉了＝「生成物永不手改／只追加」这条破了')


class ToolHandlesAreClosed(unittest.TestCase):
    """工具/ 下每个文件句柄 open 调用都必须是 with 的上下文表达式。

    走 AST 而不是跑一遍数 ResourceWarning：警告只在被走到的路径上才发。§55.36 ⑪④ 当时只登记了
    build_send_bodies.py:79 一处，§55.37 按同一缺陷类枚举出投放面三脚本 18 处（其中 11 处当轮根本
    没被跑到）；本轮覆盖面从三文件扩到 工具/ 全仓，文件清单由 rglob 现派生、不钉件数也不钉处数
    ——钉个数就是写死计数，删一处读文件反而会让它假红。

    匹配口径只认 builtin `open` 与 `io.open` 两个无歧义的文件句柄工厂，其余 `*.open`
    （Image/wave/Path/gzip 等）划在匹配面外，由下面那条边界负测钉住。§55.37 那版按 `attr == 'open'`
    匹配，把 PIL 的 `Image.open` 也算进来（全仓 28 处 AST 命中）；逐处查后续用法后真漏只有 2 处，
    其余 26 处紧跟 convert/load/crop 或喂 BytesIO，fp 早已处置。静态 AST 看不到后续有没有
    convert/load/crop，覆盖 `Image.open` 就会造出 26 处假阳，故这一类改由
    PilLazyOpenIsAResourceLeak 走运行时 ResourceWarning 钉，不进本判据。

    语法错的件不许静默跳过：ast.parse 直接抛，正测当场红，避免「扫了 0 个文件」的恒绿空转。
    """

    CAMPAIGN_FILES = ('build_send_bodies.py', 'build_send_bodies_r4.py', 'verify_round.py')

    @staticmethod
    def tool_files():
        return sorted(p for p in (ROOT / '工具').rglob('*.py') if '__pycache__' not in p.parts)

    @staticmethod
    def is_file_open(func):
        if isinstance(func, ast.Name):
            return func.id == 'open'
        if isinstance(func, ast.Attribute) and func.attr == 'open':
            return isinstance(func.value, ast.Name) and func.value.id == 'io'
        return False

    @classmethod
    def unclosed(cls, src):
        tree = ast.parse(src)
        withed = {id(item.context_expr)
                  for n in ast.walk(tree) if isinstance(n, (ast.With, ast.AsyncWith))
                  for item in n.items}
        return sorted(n.lineno for n in ast.walk(tree)
                      if isinstance(n, ast.Call) and cls.is_file_open(n.func) and id(n) not in withed)

    def test_every_file_open_is_a_with_item(self):
        files = self.tool_files()
        self.assertTrue(files, '派生面为空＝正测恒绿空转')
        for p in files:
            with self.subTest(file=str(p.relative_to(ROOT))):
                self.assertEqual(self.unclosed(p.read_text(encoding='utf-8')), [],
                                 '%s 有文件句柄 open 没进 with：句柄靠 GC 回收，走到就发 ResourceWarning'
                                 % p.name)

    def test_coverage_reaches_the_campaign_scripts(self):
        """覆盖面负测：派生清单必须真够到投放面三脚本，否则 rglob 写错也只是「扫了个别处」的假绿。"""
        got = {p.name for p in self.tool_files()}
        for f in self.CAMPAIGN_FILES:
            self.assertIn(f, got, '%s 不在派生覆盖面里' % f)
            self.assertTrue((CAMPAIGN / f).exists(), f)

    def test_old_unclosed_forms_are_caught(self):
        """违例负测：改前那六种形态逐一注回内存，判据必须逐个点名，否则上面那条正测是空转。"""
        cases = {
            'read 临时': "src = io.open(p, encoding='utf-8').read()",
            'json.load 临时': "man = json.load(io.open(p, encoding='utf-8'))",
            'write 临时': "io.open(p, 'w', encoding='utf-8').write('x')",
            'for 迭代临时': "for line in io.open(p, encoding='utf-8'):\n    pass",
            '二进制裸 open': "got = hashlib.sha256(open(p, 'rb').read()).hexdigest()",
            '条件表达式里的临时': "led = json.load(io.open(p, encoding='utf-8')) if os.path.exists(p) else {}",
        }
        for label, src in cases.items():
            with self.subTest(form=label):
                self.assertEqual(len(self.unclosed(src)), 1, '%s 未被点名：%s' % (label, src))

    def test_pil_image_open_is_not_a_file_handle(self):
        """匹配面边界负测：`Image.open` 不许被点名——旧检查器正是把这一类误算成 28 处未闭合句柄。
        同时钉住「不是靠放开一切 .open 来消假阳」：io.open 仍须被抓。"""
        pil = "im = Image.open(p).convert('RGB')\nwith Image.open(q) as im2:\n    im2.load()\n"
        self.assertEqual(self.unclosed(pil), [], 'PIL 的 Image.open 被误判成文件句柄')
        self.assertEqual(len(self.unclosed(pil + "x = io.open(p, encoding='utf-8').read()\n")), 1,
                         '为了放过 Image.open 把 io.open 也放过了＝判据已空转')

    def test_with_form_passes(self):
        """对照正测：同一批语义写成 with 就须放行，证明判据钉的是句柄闭合、不是「不许读文件」。"""
        src = ("with io.open(p, encoding='utf-8') as fp:\n"
               "    src = fp.read()\n"
               "with open(p, 'rb') as fp:\n"
               "    got = hashlib.sha256(fp.read()).hexdigest()\n")
        self.assertEqual(self.unclosed(src), [])


class PilLazyOpenIsAResourceLeak(unittest.TestCase):
    """PIL 惰性 open 的运行时判据：裸取属性就丢引用会漏句柄，同一读数包进 with 就不漏。

    静态 AST 钉不了这一类——它看不到后续有没有 convert/load/crop 把 fp 处置掉，全仓 28 处命中里
    26 处是假阳。故这里真起子进程跑，每形态各一个（-W always::ResourceWarning，避免同进程过滤器
    注册键去重把第二条警告吃掉），且刻意不留 fp 引用：留着它就不会被 GC，警告永远不发、判据恒绿。
    读数相等这条同时钉住「修法不改语义」：ImageFile.__exit__ 只 _close_fp() 并置 fp=None，
    并不销毁图像核心（销毁核心的是 im.close()），所以 with 退出后 size／load 后的像素照常可读。
    """

    CHILD = (
        "import gc, sys\n"
        "import PIL.Image as Image\n"
        "P = sys.argv[1]\n"
        "def run():\n"
        "%s\n"
        "    return s\n"
        "s = run()\n"
        "print('READING=%%r' %% (s,))\n"
        "gc.collect()\n"
        "print('GC_DONE')\n"
    )

    LEAK_VS_WITH = {
        '只取幅面就丢引用': (
            "im = Image.open(P)\ns = '横幅' if im.width > im.height else '竖幅'",
            "with Image.open(P) as im:\n    s = '横幅' if im.width > im.height else '竖幅'",
        ),
        '临时对象只取 info': (
            "x = Image.open(P).info.get('xmp', b'')\ns = repr(x)",
            "with Image.open(P) as src:\n    x = src.info.get('xmp', b'')\ns = repr(x)",
        ),
    }

    LOAD_VS_WITH = (
        "im = Image.open(P)\nim.load()\ns = (im.size, im.getpixel((0, 0)))",
        "with Image.open(P) as im:\n    im.load()\ns = (im.size, im.getpixel((0, 0)))",
    )

    @classmethod
    def run_form(cls, png, body):
        src = cls.CHILD % '\n'.join('    ' + l for l in body.split('\n'))
        r = subprocess.run([sys.executable, '-X', 'utf8', '-W', 'always::ResourceWarning', '-c', src, str(png)],
                           capture_output=True, text=True, encoding='utf-8')
        leaks = [l for l in (r.stderr or '').split('\n') if 'ResourceWarning: unclosed file' in l]
        reading = [l for l in (r.stdout or '').split('\n') if l.startswith('READING=')]
        return r.returncode, len(leaks), reading

    def setUp(self):
        from PIL import Image
        self.tmp = tempfile.TemporaryDirectory(prefix='pil_gate_')
        self.addCleanup(self.tmp.cleanup)
        self.png = Path(self.tmp.name) / 'probe.png'
        Image.new('RGB', (8, 12), (10, 20, 30)).save(self.png)

    def test_lazy_forms_leak_and_with_forms_do_not(self):
        for label, (leak, fixed) in self.LEAK_VS_WITH.items():
            with self.subTest(form=label):
                rc_l, n_l, read_l = self.run_form(self.png, leak)
                rc_w, n_w, read_w = self.run_form(self.png, fixed)
                self.assertEqual(rc_l, 0, '违例形态自己先崩了＝负测空转')
                self.assertEqual(rc_w, 0, '修法跑不通')
                self.assertGreaterEqual(n_l, 1, '%s 没发 unclosed file 警告＝探针恒绿，判据钉不住这一类' % label)
                self.assertEqual(n_w, 0, '%s 的 with 修法仍在漏句柄' % label)
                self.assertEqual(read_l, read_w, '%s 修法改了读数' % label)
                self.assertEqual(len(read_w), 1, 'READING 行缺失＝没真跑到取值')

    def test_with_exit_keeps_loaded_pixels(self):
        """反证边界：load 过的图在 with 退出后取像素须与不包 with 完全同读数，且两者都不漏。"""
        rc_l, n_l, read_l = self.run_form(self.png, self.LOAD_VS_WITH[0])
        rc_w, n_w, read_w = self.run_form(self.png, self.LOAD_VS_WITH[1])
        self.assertEqual((rc_l, rc_w), (0, 0), 'with 退出后取像素崩了＝「包 with 会改坏语义」成立')
        self.assertEqual((n_l, n_w), (0, 0), 'load() 本应内部处置 fp')
        self.assertEqual(read_l, read_w)
        self.assertEqual(len(read_w), 1)
        self.assertIn('(10, 20, 30)', read_w[0], '像素没真取到＝正测空转')


if __name__ == '__main__':
    unittest.main(verbosity=2)
