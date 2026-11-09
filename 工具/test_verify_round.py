# -*- coding: utf-8 -*-
"""投后核验的分组分流与 C136 容器判据——夹具全在仓库外临时目录，跑前跑后对 REAL_FILES 逐件做 sha 对拍。

verify_round.py 本轮从「只认 R2」改成按组取送入串台账与档串，所以这里钉三件事：
1. 两组各写各的读数与轮次台账；R1 一轮不许覆写 R2 的 round_readings.json／ledger.json。
2. 读错组（台账里的发名不带本组档串）必须在写盘之前停手，不停就会把别组的落盘算成本轮「已投」。
3. C136：caBX=0／iTXt=1 的合规真图必须放行——旧判据 `cabx == 1` 会把已投的 3 枚全判红
   （ledger.json 第 1 轮三行实测就是 0／1）。
"""
import hashlib
import importlib.util
import contextlib
import copy
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
              'send_bodies_r1.json', 'send_bodies_r1_primary.json',
              'send_bodies_r2_full.json', 'transcripts_r2.json',
              'send_bodies_r1_evidence.json', 'transcripts_r1.json',
              'send_bodies_r1_catchup.json', 'transcripts_r3.json',
              'send_bodies_r4.json', 'send_bodies_r4_evidence.json',
              'round_readings_r4.json', 'ledger_r4.json', 'transcripts_r4.json')
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
                self.assertEqual(bad, [], '%s｜%s' % (eid, bad[:2]))
                self.assertTrue(rec['send_name'].endswith('-' + SUFFIX['R2']), eid)

    def test_style_only_diff_guard_is_not_inert(self):
        """违例负测：②那一支必须能被两种坏数据打红——画风行以外的行变了、以及画风三处一行都没变
        （后者防的是真源被整份复制回来、对拍退化成恒绿的空转）。全在内存里造，不写盘。"""
        eid, rec = sorted(self.led.items())[0]
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


if __name__ == '__main__':
    unittest.main(verbosity=2)
