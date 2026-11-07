# -*- coding: utf-8 -*-
"""提示词基准冻结器：把 312 条提示词的 prompt_sha256 固化成一份快照，作为重投期的唯一比对基准。

为什么要这份文件：重投 1056 格（画风判废）与 60 格（绑定关口）要逐轮放量，一轮放几十格。
只要基准在这期间动过一枚摘要，之前投出去的格就整体失去可主张绑定的资格——
`工具/build_prompts.py` 的 `declaration` 写明「基准变化仍须复验，不得只复制摘要补绑」，
2026-11-06 的关口B 正是据此把 60 枚定档后格判成 0/60 可绑。所以放量之前必须先把基准钉死，
并且把「钉死」做成机器可判的关口（见 工具/verify_prompt_baseline.py），而不是写在散文里靠自觉。

摘要口径（本轮实测订正，勿再按旧说法实现）：
    prompt_sha256 = sha256(整份 txt 去掉四行元数据后的文本 + 结尾换行)
四行元数据是 `- 状态：` / `- prompt_sha256：` / `- image_prompt_sha256：` / `- 复验原因/备注：`，
它们在算完摘要之后才插进 `- 正典出处：` 与空行之间（`build_prompts.py` 的 `metadata_at`），
所以备注镜像行变化不动摘要。**不是**只对「## 提示词正文」段算摘要——那个口径实测 312 条全不中。

用法：
    python 工具/freeze_prompt_baseline.py            # 生成/更新快照；基准已冻结且未漂移时只刷新 frozen_at 之前的字段并拒绝覆盖
    python 工具/freeze_prompt_baseline.py --force    # 明确换档：重写快照（须同时追加裁定，闸门会报漂移）
"""
import argparse
import datetime
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REL_MANIFEST = '数据/开图清单.json'
REL_PROMPT_DIR = '数据/开图提示词'
REL_BASELINE = '数据/提示词基准冻结.json'

META_LINE = re.compile(r'^- (?:状态|prompt_sha256|image_prompt_sha256|复验原因/备注)：')
MS_TS = re.compile(r'_(1\d{12})_')


def sha12(b):
    return hashlib.sha256(b).hexdigest()[:12]


def base_sha(text):
    """按 build_prompts.py 的口径重算：整份文本去掉四行元数据后逐字相接再加结尾换行。"""
    keep = [l for l in text.split('\n')[:-1] if not META_LINE.match(l)]
    return hashlib.sha256(('\n'.join(keep) + '\n').encode('utf-8')).hexdigest()


def collect(root=ROOT):
    """统计面：清单 items 逐条 + 数据/开图提示词/*.txt 全量（312 枚，无子目录、无其他扩展名）。

    返回 (entries, readings)。entries 的 prompt_sha256 一律取清单真源，
    txt 现算值另存 txt_sha256 供闸门做断链对拍，两者不等时本函数直接把条目剔出并计红。
    """
    data = json.loads((root / REL_MANIFEST).read_text(encoding='utf-8'))
    items = data['items']
    txts = sorted((root / REL_PROMPT_DIR).glob('*.txt'))
    by_file = {p.name.split('-', 1)[0]: p for p in txts}
    entries = []
    txt_only = sorted(set(by_file) - {it['id'] for it in items})
    mismatch = []
    for it in items:
        p = by_file.get(it['id'])
        if p is None:
            mismatch.append('%s 无提示词文件' % it['id'])
            continue
        t = base_sha(p.read_text(encoding='utf-8'))
        if t != it['prompt_sha256']:
            mismatch.append(it['id'])
            continue
        cells = list(it.get('image_file') or [])
        entries.append({
            'id': it['id'],
            'name': it['name'],
            'type': it['type'],
            'prompt_file': '数据/开图提示词/' + p.name,
            'prompt_sha256': it['prompt_sha256'],
            'cell_count': len(cells),
            'cell_ts_ms': sorted(int(m.group(1)) for c in cells for m in [MS_TS.search(Path(c).name)] if m),
        })
    readings = {
        '清单条数': len(items),
        '清单声明条数': data.get('prompt_count'),
        '提示词txt枚数': len(txts),
        '参与冻结条数': len(entries),
        '摘要断链条目': len(mismatch),
        '摘要断链清单': mismatch[:20],
        '清单外txt条目': txt_only,
        '格总数': sum(len(list(it.get('image_file') or [])) for it in items),
        '带毫秒时间戳的格数': sum(len(e['cell_ts_ms']) for e in entries),
    }
    return entries, readings


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--force', action='store_true', help='明确换档并重写已存在的快照')
    args = ap.parse_args()

    entries, readings = collect()
    out_path = ROOT / REL_BASELINE
    now_ms = int(datetime.datetime.now().timestamp() * 1000)
    now_text = datetime.datetime.fromtimestamp(now_ms / 1000).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]

    if readings['摘要断链条目']:
        print('❌ 冻结失败：清单 prompt_sha256 与提示词 txt 现算摘要不等 %d 条（前 20 条见下）。'
              '先重跑 build_prompts.py 再冻结，不要冻结一份自相矛盾的基准。' % readings['摘要断链条目'])
        print('   %s' % readings['摘要断链清单'])
        return 1
    if readings['清单外txt条目']:
        print('❌ 冻结失败：提示词目录里有清单外的条目 %s' % readings['清单外txt条目'])
        return 1
    if len(entries) != readings['清单声明条数'] or readings['清单条数'] != readings['清单声明条数']:
        print('❌ 冻结失败：条数三方不符 清单items=%s 清单声明=%s 参与冻结=%s'
              % (readings['清单条数'], readings['清单声明条数'], len(entries)))
        return 1

    old = None
    if out_path.exists():
        old = json.loads(out_path.read_text(encoding='utf-8'))
        prev = {e['id']: e['prompt_sha256'] for e in old['entries']}
        cur = {e['id']: e['prompt_sha256'] for e in entries}
        drift = sorted(k for k in set(prev) | set(cur) if prev.get(k) != cur.get(k))
        if drift and not args.force:
            print('❌ 拒绝静默换档：自上次冻结（%s）以来基准漂移 %d 条：%s' % (old['frozen_at'], len(drift), drift[:20]))
            print('   重投期改基准 = 之前投出的格全部失去绑定资格。确要换档请追加裁定后用 --force。')
            return 1
        if not drift:
            # 幂等：基准没动就不写盘，避免「每次跑闸门都把 frozen_at 推后」把冻结时刻洗成最新的。
            print('✅ 基准未漂移，快照保持原样（不刷新 frozen_at）：frozen_at=%s 条数=%d 快照=%s'
                  % (old['frozen_at'], len(entries), sha12(out_path.read_bytes())))
            return 0

    payload = {
        'version': '1.0',
        'declaration': '本文件是重投期的提示词基准唯一快照。frozen_at 之后任何一条 prompt_sha256 变化都算换档，'
                       '须先追加裁定再 --force 重写，且该条目已投出的格全部降回待复验、不得复制摘要补绑'
                       '（口径见 数据/开图清单.json 的 declaration 与 工具/build_prompts.py 的 declaration；'
                       'C139 起受用户明确委托的代签另走 工具/sign_acceptance.py，须逐条留代签申报行，'
                       '那不等于允许在基准换档后补绑——换档后的格只能重投）。'
                       '摘要口径为整份提示词 txt 去掉「状态/prompt_sha256/image_prompt_sha256/复验原因备注」四行元数据后的文本，'
                       '不是只对「## 提示词正文」段算摘要；重跑生成器只会新增备注镜像行时摘要不变，属正常。'
                       'cell_ts_ms 取图片文件名里的毫秒时间戳，无时间戳的格不参与本字段（统计面见 readings）。',
        'frozen_at': now_text,
        'frozen_at_ms': now_ms,
        'frozen_by': 'freeze_prompt_baseline.py（会话代理执行，非人工签收）',
        'prompt_count': len(entries),
        'baseline_sha256_12': sha12(('\n'.join('%s %s' % (e['id'], e['prompt_sha256']) for e in sorted(entries, key=lambda x: x['id'])) + '\n').encode('utf-8')),
        'readings': readings,
        'entries': entries,
    }
    body = json.dumps(payload, ensure_ascii=False, indent=2) + '\n'
    out_path.write_bytes(body.encode('utf-8'))
    print('✅ 已冻结：%s｜条数 %d｜基准总摘要 %s｜快照 %d 字节/%s'
          % (now_text, len(entries), payload['baseline_sha256_12'], len(body.encode('utf-8')), sha12(body.encode('utf-8'))))
    print('   readings=%s' % json.dumps(readings, ensure_ascii=False))
    if old is not None:
        print('   上一版快照 %s 已被 --force 换档覆盖（原 frozen_at=%s）' % (sha12(out_path.read_bytes()), old['frozen_at']))
    return 0


if __name__ == '__main__':
    sys.exit(main())
