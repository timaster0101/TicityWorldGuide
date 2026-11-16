# -*- coding: utf-8 -*-
"""卡面 R4 回绑闸门的违例负测：夹具全在仓库外临时目录，跑前跑后对仓内三件真源逐件 sha 对拍。

本轮小样本（已投 14／395）暴露的缺陷是「逐字命中被当成已投出来」：D04／D20 两枚撞 403 code 112，
串确实发进去了、产物为零，而它们的 landing 路径上压着上一轮判废旧图（mtime 04:09／04:13）。
旧版只看串面与 images，两枚都算进「台账条目被逐字命中数 8」，续投差集就会漏掉它们。
所以这里逐条钉住三档落盘判（落盘相符／零产物／落盘漂移）与三档发名（放量／探针／异名），
并对闸门本身做变异：把判据改成恒绿之后，对应的负测必须不再判红——否则那条负测根本没在测它。
"""
import hashlib
import importlib.util
import io
import json
import os
import re
import glob
import shutil
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REAL_FILES = (ROOT / '数据' / '卡面主图提示词3x4' / '投放台账R4.json',
              ROOT / '数据' / '卡面主图提示词3x4' / '派单登记R4.json',
              ROOT / '数据' / '卡面主图提示词3x4' / '回绑源登记R4.json')
PREFIX = 'bind_card_r4_neg_'

_spec = importlib.util.spec_from_file_location('bind_card_r4_under_test', str(HERE / 'bind_check_card_r4.py'))
bc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bc)


def _real_shas():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in REAL_FILES if p.exists()}


def _sha(b):
    return hashlib.sha256(b).hexdigest()


class Fixture:
    """一份最小卡面 R4 投放面：台账 1 条＋paste＋分片 transcript＋主会话 jsonl＋逐片证据行＋落地 PNG。"""

    def __init__(self, cid='D01', body='图1 只作本条的画风母图。\n正文逐字。', ref='D06.png'):
        self.tmp = tempfile.mkdtemp(prefix=PREFIX)
        self.root = os.path.join(self.tmp, 'repo')
        self.evid = os.path.join(self.tmp, 'evid')
        self.paste = os.path.join(self.evid, 'paste')
        self.session = os.path.join(self.tmp, 'session')
        for d in (self.root, self.evid, self.paste, os.path.join(self.tmp, 'tr'),
                  os.path.join(self.root, '数据', '视觉控制资产', '卡牌', '主图3x4')):
            os.makedirs(d, exist_ok=True)
        self.cid, self.body, self.ref = cid, body, ref
        self.land_rel = '数据/视觉控制资产/卡牌/主图3x4/%s.png' % cid
        self.ref_rel = '数据/视觉控制资产/卡牌/主图3x4/%s' % ref
        self.land = os.path.join(self.root, self.land_rel)
        self.old_bytes = b'OLD-REJECTED-PRE-R4'
        self.new_bytes = b'NEW-R4-PRODUCT'
        Path(self.land).write_bytes(self.old_bytes)
        Path(os.path.join(self.root, self.ref_rel)).write_bytes(b'MOTHER')
        Path(os.path.join(self.paste, '%s.txt' % cid)).write_bytes(body.encode('utf-8'))
        self.led = {'条数': 1, 'items': [{'id': cid, 'send_sha256': _sha(body.encode('utf-8')),
                                        'ref_image': self.ref_rel, 'landing': self.land_rel}]}
        self.tr = os.path.join(self.tmp, 'tr', 'shard1.jsonl')
        Path(self.tr).write_text('', encoding='utf-8')
        Path(self.session + '.jsonl').write_text('', encoding='utf-8')
        # 第二份主会话：2026-11-16 起回绑源是清单不是单份钉死路径（分片通道禁用那几轮的直投在别的会话里）。
        self.session2 = os.path.join(self.tmp, 'session2')
        Path(self.session2 + '.jsonl').write_text('', encoding='utf-8')
        self.reg = {'登记时刻': '2026-11-09', '卡面分片': [
            {'分片': 1, '命中': [{'在盘': True, 'transcript': self.tr}]}]}

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def send(self, name=None, images=None, prompt=None, to='shard', size='768x1024'):
        inp = {'name': name if name is not None else 'card3x4r4-%s' % self.cid,
               'size': size, 'prompt': self.body if prompt is None else prompt}
        if images is not None:
            inp['images'] = images
        rec = {'type': 'assistant', 'message': {'content': [
            {'type': 'tool_use', 'name': 'ImageGen', 'input': inp}]}}
        p = {'shard': self.tr, 'main': self.session + '.jsonl',
             'main2': self.session2 + '.jsonl'}[to]
        with io.open(p, 'a', encoding='utf-8', newline='\n') as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + '\n')

    def evidence(self, status='ok', land_bytes=None, sha=None, landing=None, error='',
                 prompt_sha256=None, send_sha256=None):
        b = self.new_bytes if land_bytes is None else land_bytes
        Path(self.land).write_bytes(b)
        row = {'id': self.cid, 'arm': 'ref', 'status': status, 'error': error,
               'landing': landing if landing is not None else os.path.abspath(self.land).replace('\\', '/'),
               'landing_sha256': sha if sha is not None else _sha(b),
               'landing_bytes': len(b), 'width': 768, 'height': 1024,
               'timestamp_ms': 1794185722017}
        # 串面两列只在登记了作废发起的行上写：真实代理行里 403 那类失败行不带这两列，
        # 夹具也不该凭空替它们造出来，否则「error 写了串面不符、两列缺席」那一档永远测不到。
        if prompt_sha256 is not None:
            row['prompt_sha256'] = prompt_sha256
        if send_sha256 is not None:
            row['send_sha256'] = send_sha256
        with io.open(os.path.join(self.evid, 'sent_shard01.jsonl'), 'a', encoding='utf-8', newline='\n') as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')

    def run(self):
        return bc.scan(self.led, self.reg, self.root, self.paste, self.evid, self.session)


class BindCardR4Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before = _real_shas()

    @classmethod
    def tearDownClass(cls):
        assert _real_shas() == cls.before, '负测夹具污染了仓内真源'
        left = [d for d in os.listdir(tempfile.gettempdir()) if d.startswith(PREFIX)]
        assert not left, ('临时夹具残留 %d 个：%s' % (len(left), left[:5]))

    def setUp(self):
        self.fx = Fixture()
        self.addCleanup(self.fx.close)

    # ---------- 正例 ----------
    def test_a_landed_ok_is_green_and_counted(self):
        self.fx.send(images=[self.fx.ref_rel])
        self.fx.evidence()
        out, rc = self.fx.run()
        self.assertEqual(rc, 0)
        self.assertEqual(out['放量已落盘条目数'], 1)
        self.assertEqual(out['放量已落盘条目'], [self.fx.cid])
        self.assertEqual(out['放量落盘判分布'], {'落盘相符': [self.fx.cid]})
        self.assertEqual(out['命中发名档合计']['放量'], 1)
        self.assertEqual(out['逐条明细'][0]['母图相符'], True)

    def test_j_trailing_newline_form_is_counted_separately(self):
        self.fx.send(images=[self.fx.ref_rel], prompt=self.fx.body + '\n')
        self.fx.evidence()
        out, rc = self.fx.run()
        self.assertEqual(rc, 0)
        self.assertEqual(out['命中形态合计'], {'去结尾换行': 0, '含结尾换行': 1})

    def test_k_unmatched_sends_are_attributed_by_name(self):
        self.fx.send(images=[self.fx.ref_rel])
        self.fx.evidence()
        self.fx.send(name='D03-东湖金融片区-C133冻结重投-v01', prompt='往轮的串', to='main')
        out, rc = self.fx.run()
        self.assertEqual(rc, 0, '往轮／别组送入不命中本轮台账是预期，不是违例')
        self.assertEqual(out['未命中合计'], 1)
        self.assertEqual(out['未命中发名分布'], {'D03-东湖金融片区-C133冻结重投-v01': 1})

    # ---------- 负测：403 零产物不许洗成已投 ----------
    def test_b_403_zero_product_is_not_landed(self):
        # 串发进去了、额度墙挡下、零产物；landing 上还是上一轮判废旧图（在盘！）。
        self.fx.send(images=[self.fx.ref_rel])
        out, rc = self.fx.run()
        self.assertEqual(out['台账条目被逐字命中数'], 1, '串面确实命中，这一列不该改')
        self.assertEqual(out['放量落盘判分布'], {'零产物': [self.fx.cid]})
        self.assertEqual(out['放量已落盘条目数'], 0, '零产物被算成已投＝续投差集会漏掉它')
        self.assertEqual(out['放量已落盘条目'], [])
        self.assertEqual(rc, 0, '额度停手是纪律要求的动作，不该判成违例')
        self.assertTrue(os.path.isfile(self.fx.land), '夹具前提：旧图确实在盘，否则这条负测测不到东西')

    def test_b2_failed_status_evidence_is_not_landed(self):
        self.fx.send(images=[self.fx.ref_rel])
        self.fx.evidence(status='failed')
        out, rc = self.fx.run()
        self.assertEqual(rc, 1)
        self.assertEqual(out['放量落盘判分布'], {'证据非ok': [self.fx.cid]})
        self.assertEqual(out['放量已落盘条目数'], 0)

    # ---------- 负测：落盘漂移必须判红 ----------
    def test_c_landing_drift_is_red(self):
        self.fx.send(images=[self.fx.ref_rel])
        self.fx.evidence()
        Path(self.fx.land).write_bytes(b'SOMEONE-OVERWROTE-IT-LATER')
        out, rc = self.fx.run()
        self.assertEqual(rc, 1, '落地字节与证据行 sha 不符必须判红')
        self.assertEqual(out['放量落盘判分布'], {'落盘漂移': [self.fx.cid]})
        self.assertEqual(out['放量落盘异常条目'], [self.fx.cid])
        self.assertEqual(out['放量已落盘条目数'], 0)

    def test_d_landing_missing_is_red(self):
        self.fx.send(images=[self.fx.ref_rel])
        self.fx.evidence()
        os.remove(self.fx.land)
        out, rc = self.fx.run()
        self.assertEqual(rc, 1)
        self.assertEqual(out['放量落盘判分布'], {'落盘缺失': [self.fx.cid]})

    def test_d2_landing_path_mismatch_is_red(self):
        self.fx.send(images=[self.fx.ref_rel])
        self.fx.evidence(landing=os.path.join(self.fx.root, '数据', '别处', '%s.png' % self.fx.cid))
        out, rc = self.fx.run()
        self.assertEqual(rc, 1)
        self.assertEqual(out['放量落盘判分布'], {'落点不符': [self.fx.cid]})

    def test_k2_round_named_send_with_corrupted_string_is_red(self):
        # 本轮发名却串面不符＝发送侧字符损坏（主链 F007 被插 442 字英文声明正是这一类）。
        # 只把它计进「未命中分布」不判红，等于把改坏的串当成没投过。
        self.fx.send(images=[self.fx.ref_rel], prompt=self.fx.body + '插入的一段声明')
        out, rc = self.fx.run()
        self.assertEqual(rc, 1)
        self.assertEqual(out['台账条目被逐字命中数'], 0)
        self.assertEqual(len(out['本轮发名却未命中']), 1)
        self.assertEqual(out['本轮发名却未命中'][0]['发名'], 'card3x4r4-%s' % self.fx.cid)
        self.assertEqual(out['未命中合计'], 1)

    def test_k3_probe_named_send_with_corrupted_string_is_also_red(self):
        self.fx.send(name='card3x4r4ref-%s' % self.fx.cid, images=[self.fx.ref_rel],
                     prompt=self.fx.body + '改坏', to='main')
        out, rc = self.fx.run()
        self.assertEqual(rc, 1, '探针档的串损坏同样是损坏，不因档别豁免')
        self.assertEqual(len(out['本轮发名却未命中']), 1)

    # ---------- 新判据：已登记作废发起的豁免（2026-11-16 起于 idx094），四条违例负测 ----------
    def test_n_registered_void_send_is_exempted_with_provenance(self):
        # idx094 实测形态：首发代理自造串（本轮发名却未命中台账串），代理当场把那一发记成
        # status≠ok＋error 写明串面不符，随后按 paste 逐字重投并留盘。
        # 这一类对闸门只该披露，判红会把「已处置的作废发起」报成「未登记的字符损坏」。
        self.fx.send(images=[self.fx.ref_rel], prompt=self.fx.body + '自造的一段无关场景')
        self.fx.evidence(status='failed', land_bytes=b'SELF-MADE-BAD-FRAME',
                         error='串面不符：该次发起未逐字复述 paste 全文，判作废发起、不计绿，已另行重投',
                         prompt_sha256='', send_sha256=_sha(self.fx.body.encode('utf-8')))
        self.fx.send(images=[self.fx.ref_rel])
        self.fx.evidence()
        out, rc = self.fx.run()
        self.assertEqual(rc, 0, '已登记作废的那发仍判红＝把处置完的形态报成欠账')
        self.assertEqual(out['本轮发名却未命中'], [])
        self.assertEqual(out['未命中合计'], 1)
        self.assertEqual(out['命中发名档合计']['放量'], 1, '逐字重投那一发照旧进放量档')
        self.assertEqual(out['放量落盘判分布'], {'落盘相符': [self.fx.cid]})
        self.assertEqual(out['作废发起登记数'], {self.fx.cid: 1})
        rec = out['本轮发名却未命中（已登记作废豁免）']
        self.assertEqual(len(rec), 1)
        self.assertEqual(rec[0]['发名'], 'card3x4r4-%s' % self.fx.cid)
        self.assertTrue(rec[0]['豁免依据'], '豁免必须带得出依据，不许静默吞掉')

    def test_n2_exemption_cannot_outnumber_registration(self):
        # 登记 1 次作废只豁免 1 发；第二次改串仍判红——否则一次登记就能洗掉后续任意多次损坏。
        self.fx.send(images=[self.fx.ref_rel], prompt=self.fx.body + '第一次自造')
        self.fx.send(images=[self.fx.ref_rel], prompt=self.fx.body + '第二次自造')
        self.fx.evidence(status='failed', land_bytes=b'SELF-MADE-BAD-FRAME',
                         error='串面不符：代理自造串，已另行重投',
                         prompt_sha256='', send_sha256=_sha(self.fx.body.encode('utf-8')))
        self.fx.send(images=[self.fx.ref_rel])
        self.fx.evidence()
        out, rc = self.fx.run()
        self.assertEqual(rc, 1, '超出登记次数的未命中必须留下判红')
        self.assertEqual(len(out['本轮发名却未命中（已登记作废豁免）']), 1)
        self.assertEqual(len(out['本轮发名却未命中']), 1)
        self.assertEqual(out['本轮发名却未命中'][0]['送入sha12'],
                         _sha((self.fx.body + '第二次自造').encode('utf-8'))[:12],
                         '豁免要先扣登记那一次；剩下的必须是后发那一串')

    def test_n3_zero_product_failure_does_not_exempt(self):
        # 403／参数校验那种失败行没有「串面不符」字样，它的串本来就逐字相等：不是串面作废，不豁免。
        self.fx.send(images=[self.fx.ref_rel], prompt=self.fx.body + '改坏')
        self.fx.evidence(status='failed', error='HTTP 403 code 112 额度拒绝，零产物')
        out, rc = self.fx.run()
        self.assertEqual(rc, 1)
        self.assertEqual(out['作废发起登记数'], {}, '零产物失败行不该被当成串面作废登记')
        self.assertEqual(len(out['本轮发名却未命中']), 1)
        self.assertEqual(out['本轮发名却未命中（已登记作废豁免）'], [])

    def test_n4_self_contradictory_registration_does_not_exempt(self):
        # error 写了串面不符、prompt_sha256 却等于台账 send_sha256＝登记自相矛盾，不认这种豁免。
        self.fx.send(images=[self.fx.ref_rel], prompt=self.fx.body + '改坏')
        self.fx.evidence(status='failed', error='串面不符（但两列相等，属误登）',
                         prompt_sha256=_sha(self.fx.body.encode('utf-8')),
                         send_sha256=_sha(self.fx.body.encode('utf-8')))
        out, rc = self.fx.run()
        self.assertEqual(rc, 1)
        self.assertEqual(out['作废发起登记数'], {})
        self.assertEqual(len(out['本轮发名却未命中']), 1)

    # ---------- 负测：母图与发名 ----------
    def test_e_wrong_mother_image_on_production_arm_is_red(self):
        self.fx.send(images=['数据/视觉控制资产/卡牌/主图3x4/D99.png'])
        self.fx.evidence()
        out, rc = self.fx.run()
        self.assertEqual(rc, 1, '放量臂挂错母图＝投的不是本轮那条路线')
        self.assertEqual(out['母图未对上的条目'], {'放量': [self.fx.cid]})

    def test_e2_no_images_on_production_arm_is_red(self):
        self.fx.send(images=[])
        self.fx.evidence()
        out, rc = self.fx.run()
        self.assertEqual(rc, 1, '漏挂母图＝裸串，探针实测出照片质感')
        self.assertEqual(out['母图未对上的条目'], {'放量': [self.fx.cid]})

    def test_f_probe_mother_deviation_is_reported_not_red(self):
        # 探针可以合法地借别的放行枚（本轮 L001 探针挂 L016 而台账派 L010）：单列，不算放量违例。
        self.fx.send(name='card3x4r4ref-%s' % self.fx.cid, images=['数据/别处/L016.png'], to='main')
        out, rc = self.fx.run()
        self.assertEqual(rc, 0)
        self.assertEqual(out['命中发名档合计'], {'放量': 0, '探针': 1, '异名': 0})
        self.assertEqual(out['母图未对上的条目'], {'探针': [self.fx.cid]})
        self.assertEqual(out['放量已落盘条目数'], 0)

    def test_g_wrong_send_name_is_red(self):
        self.fx.send(name='card3x4r4-D01-fix')
        self.fx.evidence()
        out, rc = self.fx.run()
        self.assertEqual(rc, 1, '串对了发名不对：按名回绑的主链闸门会数不到这一发')
        self.assertEqual(out['命中发名档合计']['异名'], 1)
        self.assertEqual(out['发名不符的命中'][0]['发名'], 'card3x4r4-D01-fix')
        self.assertEqual(out['放量已落盘条目数'], 0, '异名档不许进放量落盘计数')

    # ---------- 负测：回绑源与 paste 契约 ----------
    def test_h_missing_transcript_is_red(self):
        self.fx.send(images=[self.fx.ref_rel])
        self.fx.evidence()
        os.remove(self.fx.tr)
        self.fx.reg['卡面分片'][0]['命中'][0]['在盘'] = False
        out, rc = self.fx.run()
        self.assertEqual(rc, 1, '缺失回绑源不等于通过')
        self.assertEqual(out['缺失份数'], 1)
        self.assertEqual(out['放量已落盘条目数'], 0)

    def test_h2_stale_registration_flag_is_rechecked_on_disk(self):
        # 登记件说在盘、之后被会话区清掉：必须按扫的这一刻实测判缺失，不许信登记时的快照。
        self.fx.send(images=[self.fx.ref_rel])
        self.fx.evidence()
        os.remove(self.fx.tr)
        self.assertEqual(self.fx.reg['卡面分片'][0]['命中'][0]['在盘'], True, '夹具前提：登记快照仍说在盘')
        out, rc = self.fx.run()
        self.assertEqual(rc, 1)
        self.assertEqual(out['缺失份数'], 1)
        self.assertEqual(out['回绑源在盘份数'], 1, '只剩主会话一份')
        self.assertEqual(out['放量已落盘条目数'], 0)

    def test_i_paste_byte_contract_asserts(self):
        Path(os.path.join(self.fx.paste, '%s.txt' % self.fx.cid)).write_bytes(
            (self.fx.body + '\n').encode('utf-8'))
        with self.assertRaises(AssertionError):
            self.fx.run()

    def test_l_probe_evidence_without_landing_is_not_landing_proof(self):
        # 探针证据行没有 landing／landing_sha256 字段：它是「产物留在 vibe_images」的凭据，不是落盘凭据。
        self.fx.send(name='card3x4r4ref-%s' % self.fx.cid, images=[self.fx.ref_rel], to='main')
        with io.open(os.path.join(self.fx.evid, 'sent_shard_probe_ref.jsonl'), 'w',
                     encoding='utf-8', newline='\n') as fh:
            fh.write(json.dumps({'id': self.fx.cid, 'arm': 'ref', 'status': 'ok',
                                 'imagegen_path': 'vibe_images/x.png', 'image_sha256': _sha(b'x')},
                                ensure_ascii=False) + '\n')
        ev, files = bc.load_evidence(self.fx.evid)
        self.assertEqual(len(files), 1)
        self.assertEqual(ev, {}, '无落点字段的证据行被当成落盘凭据＝探针产物洗成已回填')

    def test_o_main_session_list_pulls_in_a_second_session(self):
        # 2026-11-16 起回绑源是清单：分片通道禁用那几轮的直投只长在别的主会话 jsonl 里。
        self.fx.send(images=[self.fx.ref_rel], to='main2')
        self.fx.evidence()
        self.fx.reg['主会话jsonl清单'] = [self.fx.session, self.fx.session2]
        out, rc = self.fx.run()
        self.assertEqual(rc, 0)
        self.assertEqual(out['回绑源在盘份数'], 3, '分片 1 份＋清单 2 份（重复的那份要折叠）')
        self.assertEqual(out['逐字命中合计'], 1)
        self.assertEqual(out['放量已落盘条目数'], 1)

    def test_o2_without_the_list_a_second_session_send_is_orphan_landed(self):
        # 同一条用例去掉清单键：发起扫不到、证据行却写着已落盘——只判「未命中」不放红就是拿缺失当通过。
        self.fx.send(images=[self.fx.ref_rel], to='main2')
        self.fx.evidence()
        out, rc = self.fx.run()
        self.assertEqual(rc, 1, '登记漏一份主会话＝已落盘没有发起面撑着，必须响')
        self.assertEqual(out['回绑源在盘份数'], 2, '退回显式传入的那一份主会话')
        self.assertEqual(out['逐字命中合计'], 0)
        self.assertEqual([x['id'] for x in out['已落盘证据却无回绑发起']], [self.fx.cid])
        self.assertEqual(out['已落盘证据却无回绑发起'][0]['落盘判'], '落盘相符')

    def test_p_landing_claim_without_any_launch_is_red(self):
        # 一份发起都没扫到（补投没登记、jsonl 被清）但证据行声称落盘相符＝孤悬落盘。
        self.fx.evidence()
        out, rc = self.fx.run()
        self.assertEqual(rc, 1)
        self.assertEqual([x['id'] for x in out['已落盘证据却无回绑发起']], [self.fx.cid])
        self.assertEqual(out['放量已落盘条目数'], 0, '孤悬落盘不许进续投差集的已落盘面')

    def test_p2_no_evidence_row_is_not_an_orphan_claim(self):
        # 没投过 ≠ 违例：零产物（无证据行）与证据非ok（代理写明这发没成）都不算落盘主张，续投差集照样补得上。
        out, rc = self.fx.run()
        self.assertEqual(rc, 0, '台账里还没投的条目判红＝放量第一轮永远过不去，续投差集也就没意义')
        self.assertEqual(out['已落盘证据却无回绑发起'], [])
        self.fx.evidence(status='failed', error='403 code 112 额度不足')
        out, rc = self.fx.run()
        self.assertEqual(rc, 0, '失败行是「没投出来」的凭据，不是落盘主张')
        self.assertEqual(out['已落盘证据却无回绑发起'], [])

    # ---------- 对闸门本身做变异：证明上面每条负测真的在测它 ----------
    def test_m_evidence_file_named_by_dispatch_batch_is_picked_up(self):
        # 2026-11-13 放量批次的证据文件叫 sent_r4-todo-cardNN.jsonl，11-09 那批才叫 sent_shardNN。
        # 收件的 glob 若写死成某一代前缀，那一批发度逐字命中却查无证据行，会被整批判成「零产物」——
        # 本轮真仓实测过这个形态：24 枚已落盘的卡面被读成零产物。
        self.fx.send(images=[self.fx.ref_rel])
        b = self.fx.new_bytes
        Path(self.fx.land).write_bytes(b)
        row = {'id': self.fx.cid, 'arm': 'ref', 'status': 'ok', 'error': '',
               'landing': os.path.abspath(self.fx.land).replace('\\', '/'),
               'landing_sha256': _sha(b), 'landing_bytes': len(b),
               'width': 768, 'height': 1024, 'timestamp_ms': 1794185722017}
        with io.open(os.path.join(self.fx.evid, 'sent_r4-todo-card03.jsonl'), 'w',
                     encoding='utf-8', newline='\n') as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + '\n')
        ev, files = bc.load_evidence(self.fx.evid)
        self.assertEqual([os.path.basename(f) for f in files], ['sent_r4-todo-card03.jsonl'],
                         '收件面没收到放量批次的证据文件')
        self.assertEqual([r[0] for r in ev[self.fx.cid]],
                         [os.path.abspath(self.fx.evid).replace('\\', '/') + '/sent_r4-todo-card03.jsonl'])
        out, rc = self.fx.run()
        self.assertEqual(out['放量落盘判分布'], {'落盘相符': [self.fx.cid]},
                         '证据行在别的命名代里就判零产物＝把已投洗成待投，下一轮会重投烧额')
        self.assertEqual(out['放量已落盘条目数'], 1)

    def test_mutation_prefix_only_evidence_glob_makes_m_toothless(self):
        # 把我改掉的那一版 glob 装回去：同一条用例必须退成零产物，否则 test_m 验的不是收件面。
        orig = bc.load_evidence

        def buggy(evid_dir):
            ev, files = {}, sorted(glob.glob(os.path.join(evid_dir, 'sent_shard*.jsonl')))
            files = [os.path.abspath(p).replace('\\', '/') for p in files]
            for p in files:
                with io.open(p, encoding='utf-8') as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        r = json.loads(line)
                        if not r.get('landing') or not r.get('landing_sha256'):
                            continue
                        ev.setdefault(r['id'], []).append((p, r))
            return ev, files

        bc.load_evidence = buggy
        try:
            self.fx.send(images=[self.fx.ref_rel])
            b = self.fx.new_bytes
            Path(self.fx.land).write_bytes(b)
            row = {'id': self.fx.cid, 'arm': 'ref', 'status': 'ok', 'error': '',
                   'landing': os.path.abspath(self.fx.land).replace('\\', '/'),
                   'landing_sha256': _sha(b), 'landing_bytes': len(b),
                   'width': 768, 'height': 1024, 'timestamp_ms': 1794185722017}
            with io.open(os.path.join(self.fx.evid, 'sent_r4-todo-card03.jsonl'), 'w',
                         encoding='utf-8', newline='\n') as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + '\n')
            out, rc = self.fx.run()
            self.assertEqual(out['放量落盘判分布'], {'零产物': [self.fx.cid]},
                             '变异后仍判落盘相符＝test_m 测的就不是 glob 收件面')
            self.assertEqual(out['放量已落盘条目数'], 0)
        finally:
            bc.load_evidence = orig

    def test_mutation_landing_state_always_ok_makes_drift_negative_toothless(self):
        orig = bc.landing_state
        bc.landing_state = lambda item, ev, root: ('落盘相符', 'ab' * 6, 'ab' * 6)
        try:
            self.fx.send(images=[self.fx.ref_rel])
            self.fx.evidence()
            Path(self.fx.land).write_bytes(b'SOMEONE-OVERWROTE-IT-LATER')
            out, rc = self.fx.run()
            self.assertEqual(rc, 0, '变异后落盘漂移负测不再判红＝test_c 测的就是 landing_state 这一条')
            self.assertEqual(out['放量已落盘条目数'], 1)
        finally:
            bc.landing_state = orig

    def test_mutation_landed_claim_always_false_makes_p_toothless(self):
        # 把「是否主张已落盘」判成恒否：孤悬落盘支退成不响，且 test_p2 的豁免面也失去意义——
        # 证明 test_p/o2 守的正是 landed_claim 这一层，而不是恰好被别的判红顺带打掉。
        orig = bc.landed_claim
        bc.landed_claim = lambda state: False
        try:
            self.fx.evidence()
            out, rc = self.fx.run()
            self.assertEqual(rc, 0, '变异后孤悬落盘不再判红＝test_p 测的就是 landed_claim')
            self.assertEqual(out['已落盘证据却无回绑发起'], [])
        finally:
            bc.landed_claim = orig

    def test_mutation_send_form_always_production_makes_probe_negative_toothless(self):
        orig = bc.send_form
        bc.send_form = lambda name, cid: '放量'
        try:
            self.fx.send(name='card3x4r4ref-%s' % self.fx.cid, images=['数据/别处/L016.png'], to='main')
            out, rc = self.fx.run()
            self.assertEqual(rc, 1, '变异后探针档不再豁免＝test_f 测的就是 send_form 分档')
            self.assertEqual(out['母图未对上的条目'], {'放量': [self.fx.cid]})
        finally:
            bc.send_form = orig

    def test_mutation_basename_only_landing_check_makes_d2_toothless(self):
        # 我第一版就是只比 basename，被 test_d2 当场判红。这条变异证明 test_d2 守的正是那一处。
        orig = bc.landing_state

        def buggy(item, ev, root):
            rows = ev.get(item['id']) or []
            if not rows:
                return '零产物', '', ''
            path, r = rows[-1]
            land = os.path.join(root, item['landing'])
            if os.path.basename(r['landing']) != os.path.basename(land):
                return '落点不符', '', r['landing_sha256'][:12]
            if not os.path.isfile(land):
                return '落盘缺失', '', r['landing_sha256'][:12]
            with open(land, 'rb') as fh:
                got = hashlib.sha256(fh.read()).hexdigest()
            return ('落盘相符' if got == r['landing_sha256'] else '落盘漂移'), got[:12], r['landing_sha256'][:12]

        bc.landing_state = buggy
        try:
            self.fx.send(images=[self.fx.ref_rel])
            self.fx.evidence(landing=os.path.join(self.fx.root, '数据', '别处', '%s.png' % self.fx.cid))
            out, rc = self.fx.run()
            self.assertEqual(rc, 0, '只比 basename 时异目录落点混过＝test_d2 测的就是绝对路径归一那一处')
            self.assertEqual(out['放量落盘判分布'], {'落盘相符': [self.fx.cid]})
        finally:
            bc.landing_state = orig

    def test_mutation_empty_round_prefixes_makes_k2_toothless(self):
        orig = bc.ROUND_NAME_PREFIXES
        bc.ROUND_NAME_PREFIXES = ()
        try:
            self.fx.send(images=[self.fx.ref_rel], prompt=self.fx.body + '插入的一段声明')
            out, rc = self.fx.run()
            self.assertEqual(rc, 0, '前缀表置空后串损坏不再判红＝test_k2 测的就是这一支')
            self.assertEqual(out['本轮发名却未命中'], [])
            self.assertEqual(out['未命中合计'], 1, '它仍被计进未命中，只是不再判红——正是旧版的假绿形态')
        finally:
            bc.ROUND_NAME_PREFIXES = orig

    def test_mutation_zero_product_counted_as_landed_reproduces_the_original_bug(self):
        # 旧版缺陷的等价变异：没有证据行也报落盘相符。test_b 必须当场失效，否则它没守住那个缺陷。
        orig = bc.landing_state

        def buggy(item, ev, root):
            state, got, want = orig(item, ev, root)
            return ('落盘相符' if state == '零产物' else state), got, want

        bc.landing_state = buggy
        try:
            self.fx.send(images=[self.fx.ref_rel])
            out, rc = self.fx.run()
            self.assertEqual(out['放量已落盘条目数'], 1,
                             '变异后 403 零产物被算成已投＝test_b 正是守住这一条的负测')
        finally:
            bc.landing_state = orig


    def test_mutation_void_registrations_always_empty_makes_n_toothless(self):
        # 豁免来源置空：test_n 必须退成判红，否则它验的不是 void_registrations 这一支。
        orig = bc.void_registrations
        bc.void_registrations = lambda ev: {}
        try:
            self.fx.send(images=[self.fx.ref_rel], prompt=self.fx.body + '自造的一段')
            self.fx.evidence(status='failed', land_bytes=b'BAD', error='串面不符：代理自造串',
                             prompt_sha256='', send_sha256=_sha(self.fx.body.encode('utf-8')))
            self.fx.send(images=[self.fx.ref_rel])
            self.fx.evidence()
            out, rc = self.fx.run()
            self.assertEqual(rc, 1, '变异后仍判红＝test_n 测的是别的支')
            self.assertEqual(out['本轮发名却未命中（已登记作废豁免）'], [])
            self.assertEqual(len(out['本轮发名却未命中']), 1)
        finally:
            bc.void_registrations = orig

    def test_mutation_exempt_without_counting_makes_n2_toothless(self):
        # 登记面改成无限次：超发那一发被洗白＝test_n2 的计数闸才是载荷。
        orig = bc.void_registrations
        bc.void_registrations = lambda ev: {k: 10 ** 6 for k in ev}
        try:
            self.fx.send(images=[self.fx.ref_rel], prompt=self.fx.body + '第一次自造')
            self.fx.send(images=[self.fx.ref_rel], prompt=self.fx.body + '第二次自造')
            self.fx.evidence(status='failed', land_bytes=b'BAD', error='串面不符：代理自造串',
                             prompt_sha256='', send_sha256=_sha(self.fx.body.encode('utf-8')))
            self.fx.send(images=[self.fx.ref_rel])
            self.fx.evidence()
            out, rc = self.fx.run()
            self.assertEqual(rc, 0, '变异后仍判红＝test_n2 靠的是别的支')
            self.assertEqual(out['本轮发名却未命中'], [])
            self.assertEqual(len(out['本轮发名却未命中（已登记作废豁免）']), 2)
        finally:
            bc.void_registrations = orig


    def _q_fixture(self):
        """R5 跨轮重投形态的最小现场：旧轮行在 `sent_shard01.jsonl`（字典序靠后）、
        新轮行在 `sent_r5-card01.jsonl`（字典序靠前），落点上是新轮的字节。"""
        self.fx.send(images=[self.fx.ref_rel])
        old_row = {'id': self.fx.cid, 'arm': 'ref', 'status': 'ok', 'error': '',
                   'landing': os.path.abspath(self.fx.land).replace('\\', '/'),
                   'landing_sha256': _sha(self.fx.old_bytes), 'landing_bytes': len(self.fx.old_bytes),
                   'width': 768, 'height': 1024, 'timestamp_ms': 1794185700000,
                   '投放时刻_ms': 1794185714034}
        with io.open(os.path.join(self.fx.evid, 'sent_shard01.jsonl'), 'w',
                     encoding='utf-8', newline='\n') as fh:
            fh.write(json.dumps(old_row, ensure_ascii=False) + '\n')
        Path(self.fx.land).write_bytes(self.fx.new_bytes)
        new_row = dict(old_row, landing_sha256=_sha(self.fx.new_bytes),
                       landing_bytes=len(self.fx.new_bytes), timestamp_ms=1794826760000,
                       投放时刻_ms=1794826757992)
        with io.open(os.path.join(self.fx.evid, 'sent_r5-card01.jsonl'), 'w',
                     encoding='utf-8', newline='\n') as fh:
            fh.write(json.dumps(new_row, ensure_ascii=False) + '\n')
        self.assertEqual([os.path.basename(f) for f in sorted(glob.glob(
            os.path.join(self.fx.evid, 'sent_*.jsonl')))],
            ['sent_r5-card01.jsonl', 'sent_shard01.jsonl'],
            '夹具的字典序前提没成立，本例就测不到跨文件排序')

    def test_q_cross_wave_resend_in_an_earlier_named_file_wins(self):
        # 2026-11-16 R5 重投轮的形态：消费方取的是「末行＝最近那一发」。只按文件名字典序收行，
        # 末行仍是旧轮那行，于是新图对上旧 landing_sha256＝假漂移，落盘面会判红一整批。
        self._q_fixture()
        ev, _files = bc.load_evidence(self.fx.evid)
        self.assertEqual([pair[1].get('投放时刻_ms') for pair in ev[self.fx.cid]],
                         [1794185714034, 1794826757992], '末行不是最近那一发＝按投放时刻排序未生效')
        out, rc = self.fx.run()
        self.assertEqual(rc, 0, '跨轮重投对上本轮证据行却判红＝把已投洗成漂移')
        self.assertEqual(out['放量落盘判分布'], {'落盘相符': [self.fx.cid]})

    def test_mutation_filename_order_instead_of_send_time_makes_q_toothless(self):
        # 把排序退回旧口径（send_ms 恒 0 → 稳定排序保留文件名字典序）：test_q 必须当场判成漂移，
        # 否则它验的就不是「末行＝最近那一发」而是别的支。
        orig = bc.send_ms
        bc.send_ms = lambda row: 0
        try:
            self._q_fixture()
            ev, _files = bc.load_evidence(self.fx.evid)
            self.assertEqual([pair[1].get('投放时刻_ms') for pair in ev[self.fx.cid]],
                             [1794826757992, 1794185714034], '变异没接回字典序形态＝负测打的是别的支')
            out, rc = self.fx.run()
            self.assertEqual(rc, 1, '变异后仍全绿＝test_q 守的不是跨文件投放时刻排序这一支')
            self.assertEqual(out['放量落盘判分布'], {'落盘漂移': [self.fx.cid]})
            self.assertEqual(out['放量已落盘条目数'], 0)
        finally:
            bc.send_ms = orig


class PinnedMutationCountIsNotDocumented(unittest.TestCase):
    """§55.50 的文档面：变异条数不再写死在手册与报告里，判据要能自己响。

    这三支用例是成对写的：第一支证盘上真源没有钉死条数，第二支把旧串注回内存证明同一支正则不是空转；
    第三支把派生措辞删掉，证明判据读的是措辞面而不是恒真的空命中。
    """

    PINNED = re.compile(u'（\\d+ 条对闸门本身的变异）')
    DERIVED = u'本轮输出为准，本句不抄第二份）'
    OLD_TAIL = u'）'

    def _carriers(self):
        out = []
        for rel in (u'../AI创作使用手册.md', u'../工具/compile_book.py'):
            p = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), rel))
            with io.open(p, encoding='utf-8') as fh:
                out.append((rel, fh.read()))
        return out

    def test_no_pinned_mutation_count_in_the_two_sources(self):
        for rel, text in self._carriers():
            self.assertIsNone(self.PINNED.search(text),
                              '%s 里仍有「N 条对闸门本身的变异」这种写死条数' % rel)
            self.assertEqual(text.count(self.DERIVED), 1,
                             '%s 的派生措辞命中数应为恰 1（现读 %d）' % (rel, text.count(self.DERIVED)))

    def test_injected_old_string_is_caught_by_the_same_regex(self):
        # 违例注入：旧串注回内存，判据必须当场命中；不命中说明正测那支是恒绿空转。
        for rel, text in self._carriers():
            bad = text.replace(self.DERIVED, u'（5 条对闸门本身的变异' + self.OLD_TAIL, 1)
            self.assertNotEqual(bad, text, '%s 注不进旧串，锚点错了' % rel)
            self.assertIsNotNone(self.PINNED.search(bad),
                                 '%s 注回旧写死串后判据没响＝这支判据空转' % rel)

    def test_removing_derived_phrase_is_caught(self):
        # 违例注入：派生措辞被删（比如哪天又把条数钉回去），命中数必须掉到 0。
        for rel, text in self._carriers():
            bare = text.replace(self.DERIVED, u'）', 1)
            self.assertNotEqual(bare, text, '%s 删不掉派生措辞，锚点错了' % rel)
            self.assertEqual(bare.count(self.DERIVED), 0, rel)



if __name__ == '__main__':
    unittest.main(verbosity=2)