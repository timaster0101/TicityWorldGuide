# -*- coding: utf-8 -*-
"""提示词基准冻结件的单测：口径、幂等、闸门对拍与违例注入必须逐条有读数。

跑法：python -m unittest discover -s 工具 -p "test_*.py"（本文件会被递归收集）
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_prompt_baseline as V  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def run(script, *args):
    proc = subprocess.run([sys.executable, str(ROOT / '工具' / script)] + list(args),
                          capture_output=True, cwd=str(ROOT))
    return proc.returncode, proc.stdout.decode('utf-8', 'replace')


class FreezeFile(unittest.TestCase):
    def test_baseline_snapshot_is_on_disk_and_covers_every_entry(self):
        """统计面：数据/提示词基准冻结.json entries、数据/开图清单.json items、数据/开图提示词/*.txt 三方。"""
        snap = json.loads((ROOT / V.REL_BASELINE).read_text(encoding='utf-8'))
        data = json.loads((ROOT / V.REL_MANIFEST).read_text(encoding='utf-8'))
        txts = list((ROOT / V.REL_PROMPT_DIR).glob('*.txt'))
        self.assertEqual(len(snap['entries']), len(data['items']))
        self.assertEqual(len(snap['entries']), len(txts))
        self.assertEqual(len(snap['entries']), data['prompt_count'])

    def test_digest_scope_is_whole_file_minus_four_meta_lines(self):
        """口径钉：prompt_sha256 = 整份 txt 去掉四行元数据；只取「## 提示词正文」段的旧说法必须判不符。

        Why: 2026-11-06 的关口B 曾按「只对正文段算摘要」实现，本轮对拍实测 312 条全不中，
        照那个口径写闸门会把每一枚 txt 都报成断链（假红），或反过来让真断链躲过（假绿）。
        """
        data = json.loads((ROOT / V.REL_MANIFEST).read_text(encoding='utf-8'))
        by_id = {it['id']: it for it in data['items']}
        body_only = []
        for p in sorted((ROOT / V.REL_PROMPT_DIR).glob('*.txt'))[:40]:
            t = p.read_text(encoding='utf-8')
            self.assertEqual(V.base_sha(t), by_id[p.name.split('-', 1)[0]]['prompt_sha256'],
                             '%s 的去元数据摘要 ≠ 清单 prompt_sha256' % p.name)
            i = t.index('## 提示词正文')
            body_only.append(hashlib.sha256(t[i - 1:].encode('utf-8')).hexdigest() ==
                             by_id[p.name.split('-', 1)[0]]['prompt_sha256'])
        self.assertEqual(body_only, [False] * len(body_only), '「只对正文段算摘要」竟然对上了，口径已再次变更，须同步闸门')

    def test_freeze_is_idempotent_and_refuses_silent_rebase(self):
        """重跑冻结器不得移动 frozen_at；改过基准后无 --force 必须拒写。"""
        snap = json.loads((ROOT / V.REL_BASELINE).read_text(encoding='utf-8'))
        before = snap['frozen_at_ms']
        rc, out = run('freeze_prompt_baseline.py')
        self.assertEqual(rc, 0, out)
        after = json.loads((ROOT / V.REL_BASELINE).read_text(encoding='utf-8'))['frozen_at_ms']
        self.assertEqual(before, after, '幂等复跑把冻结时刻推后了，等于把「冻结后落盘」的分界线洗成最新')
        # 真换档注入在临时目录里做，不碰被守护仓库
        tmp = Path(tempfile.mkdtemp(prefix='test_pbase_'))
        try:
            tree = tmp / 'repo'
            shutil.copytree(ROOT / '数据/开图提示词', str(tree / V.REL_PROMPT_DIR))
            shutil.copy(ROOT / V.REL_MANIFEST, str(tree / V.REL_MANIFEST))
            shutil.copy(ROOT / V.REL_BASELINE, str(tree / V.REL_BASELINE))
            snap = json.loads((tree / V.REL_BASELINE).read_text(encoding='utf-8'))
            first = snap['entries'][0]
            (tree / first['prompt_file']).write_text(
                (tree / first['prompt_file']).read_text(encoding='utf-8') + '【注入换档】\n', encoding='utf-8')
            data = json.loads((tree / V.REL_MANIFEST).read_text(encoding='utf-8'))
            for it in data['items']:
                if it['id'] == first['id']:
                    it['prompt_sha256'] = V.base_sha(
                        (tree / first['prompt_file']).read_text(encoding='utf-8'))
            (tree / V.REL_MANIFEST).write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            viol, readings = V.check(tree)
            names = [v.split('：')[0] for v in viol]
            self.assertIn(V.K_DRIFT, names, viol)
            self.assertIn(V.K_TXT_DRIFT, names, '改了 txt 却没同步快照，断链判据也必须同时亮：%s' % viol)
            self.assertEqual(readings['基准漂移条数'], 1, readings)
            # 冻结器面对漂移必须拒写并留证据
            src = (ROOT / '工具/freeze_prompt_baseline.py').read_text(encoding='utf-8')
            (tree / '工具').mkdir(parents=True, exist_ok=True)
            (tree / '工具/freeze_prompt_baseline.py').write_text(
                src.replace("ROOT = Path(__file__).resolve().parents[1]",
                            "ROOT = Path(r'%s')" % str(tree).replace('\\', '\\\\')), encoding='utf-8')
            proc = subprocess.run([sys.executable, str(tree / '工具/freeze_prompt_baseline.py')],
                                  capture_output=True, cwd=str(tree))
            self.assertEqual(proc.returncode, 1, proc.stdout.decode('utf-8', 'replace'))
            self.assertIn('拒绝静默换档', proc.stdout.decode('utf-8', 'replace'))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_positive_gate_and_full_negtest_are_both_green(self):
        rc, out = run('verify_prompt_baseline.py')
        self.assertEqual(rc, 0, out)
        self.assertIn('提示词基准冻结闸门通过', out)
        rc2, out2 = run('verify_prompt_baseline.py', '--negtest')
        self.assertEqual(rc2, 0, out2)
        self.assertIn('命中 %d/%d' % (len(V.ALL_KINDS), len(V.ALL_KINDS)), out2)
        self.assertIn('残留 0', out2)
        self.assertNotIn('✗', out2)

    def test_zero_hit_must_not_print_pass(self):
        """闸门自身惰性判据：entries 读空时不得打印通过——用夹具把快照掏空复现假绿形态。"""
        tmp = Path(tempfile.mkdtemp(prefix='test_pbase_'))
        try:
            V.build_fixture(tmp)
            bp = tmp / V.REL_BASELINE
            snap = json.loads(bp.read_text(encoding='utf-8'))
            snap['entries'] = []
            bp.write_text(json.dumps(snap, ensure_ascii=False), encoding='utf-8')
            viol, _ = V.check(tmp)
            self.assertEqual([v.split('：')[0] for v in viol], [V.K_INERT], viol)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_post_freeze_cell_losing_qualification_is_red(self):
        """重投放量的核心约束：时间戳 ≥ frozen_at 的格，其条目基准必须仍等于快照。

        未绑定本身不判红——回填通道刻意留空由人工签收时填（backfill_batch9g 口径3「脚本不代签」），
        判红的是「投出去之后基准又变了」，即 §54 关口B 把 60 枚打成 0/60 的那个失效形态。
        """
        tmp = Path(tempfile.mkdtemp(prefix='test_pbase_'))
        try:
            V.build_fixture(tmp)
            mp = tmp / V.REL_MANIFEST
            data = json.loads(mp.read_text(encoding='utf-8'))
            snap = json.loads((tmp / V.REL_BASELINE).read_text(encoding='utf-8'))
            snap['entries'][0]['prompt_sha256'] = 'a' * 64
            (tmp / V.REL_BASELINE).write_text(json.dumps(snap, ensure_ascii=False), encoding='utf-8')
            viol, readings = V.check(tmp)
            self.assertIn(V.K_AFTER_UNQUALIFIED, [v.split('：')[0] for v in viol], viol)
            # 夹具自 C135 起有两枚冻结后落盘的格：X01 文本生图一枚＋X03 图生图一枚
            self.assertEqual(readings['冻结后落盘的格数'], 2, readings)
            self.assertEqual(readings['冻结后具备绑定资格格数'], 1, readings)
            # 反向闸：只是「尚未人工签收填绑定」而基准仍冻结时，不得判红（否则每轮放量都红，闸门会被当噪音绕开）
            V.build_fixture(tmp)
            mp2 = tmp / V.REL_MANIFEST
            md2 = json.loads(mp2.read_text(encoding='utf-8'))
            md2['items'][0]['image_prompt_sha256'] = None
            mp2.write_text(json.dumps(md2, ensure_ascii=False), encoding='utf-8')
            viol0, readings0 = V.check(tmp)
            self.assertNotIn(V.K_AFTER_UNQUALIFIED, [v.split('：')[0] for v in viol0], viol0)
            self.assertEqual(readings0['冻结后未绑定待人工签收格数'], 1, readings0)
            # 反向：把同一枚格的时间戳挪到冻结前，本判据必须转绿（证明分界线真的按 frozen_at 切）
            name = Path(data['items'][0]['image_file'][0]).name
            old_ms = json.loads((tmp / V.REL_BASELINE).read_text(encoding='utf-8'))['frozen_at_ms']
            data['items'][0]['image_file'] = ['X01-甲-E1重出-v09_%d_deadbeef.png' % (old_ms - 60000)]
            mp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
            viol2, readings2 = V.check(tmp)
            self.assertNotIn(V.K_AFTER_UNQUALIFIED, [v.split('：')[0] for v in viol2], viol2)
            # X01 那枚挪到冻结前之后，剩下的 1 枚是 X03 的图生图格，不随本用例移动
            self.assertEqual(readings2['冻结后落盘的格数'], 1, readings2)
            self.assertEqual(readings2['冻结前落盘的带时间戳格数'], 1, readings2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_i2i_cell_binds_to_frozen_baseline_not_to_sent_string(self):
        """C135 口径钉：图生图格「按冻结串绑，实际送入串只作第二字段」。

        夹具的 X03 是图生图格：image_prompt_sha256 记冻结串摘要 sha3，送入串摘要 sha3b 只出现在
        image_cell_provenance 里。把它改成绑 sha3b（即「按实际送入串绑」）必须判红，
        且红的是新那一类 K_I2I_BIND_MODE 而不是「图生图格备案不完整」——两类各管一件事：
        备案管可回查（送入串原文／其摘要／母图都在盘且对得上），绑定管基准口径。
        """
        tmp = Path(tempfile.mkdtemp(prefix='test_pbase_'))
        try:
            base = V.build_fixture(tmp)
            viol, readings = V.check(tmp)
            self.assertEqual(viol, [], viol)
            self.assertEqual(readings['图生图备案合规格数'], 1, readings)
            self.assertEqual(readings['图生图格绑到送入串违例数'], 0, readings)

            mp = tmp / V.REL_MANIFEST
            md = json.loads(mp.read_text(encoding='utf-8'))
            md['items'][2]['image_prompt_sha256'] = base['sha3b']
            mp.write_text(json.dumps(md, ensure_ascii=False), encoding='utf-8')
            viol, readings = V.check(tmp)
            names = [v.split('：')[0] for v in viol]
            self.assertIn(V.K_I2I_BIND_MODE, names, viol)
            self.assertNotIn(V.K_IMG2IMG_PROVENANCE, names, viol)
            self.assertEqual(readings['图生图格绑到送入串违例数'], 1, readings)
            self.assertEqual(readings['图生图备案合规格数'], 1, readings)

            # 反向：送入串原文从盘上抽掉，备案类必须红，且不得被绑定类顶掉
            V.build_fixture(tmp)
            (tmp / V.REL_I2I_DIR / 'X03-丙-送入串.txt').unlink()
            viol, readings = V.check(tmp)
            names = [v.split('：')[0] for v in viol]
            self.assertIn(V.K_IMG2IMG_PROVENANCE, names, viol)
            self.assertEqual(readings['图生图备案合规格数'], 0, readings)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_repo_has_no_test_residue(self):
        """临时夹具不得在被守护仓库里留下任何目录或文件。"""
        hits = [p.name for p in ROOT.rglob('*') if 'test_pbase_' in p.name or V.RESIDUE_PREFIX in p.name]
        self.assertEqual(hits, [], hits)


if __name__ == '__main__':
    unittest.main()
