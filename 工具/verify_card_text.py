"""独立复核 `数据/卡面文案底稿.json` 的 bottom_text：把 OCR 当"第二双眼睛"逐条对拍。

为什么要有这一步：目视转录由代理完成、用户尚未逐张复核，而错字一旦进 `bottom_text`，
程序叠字会把同一个错字印到全部「有文案版」上。OCR 的错法是同音/形近替换，
所以它不能当结论（见 build_card_text_review.py 的教训），但能当**反查器**：
转录和 OCR 一致的地方风险低，一致度异常低的地方要么我抄错、要么 OCR 读错，都得回图再看。

判据：difflib 字符级相似度。实测阈值 0.5 以下进"回看图"名单，名单为空即对拍通过。
本脚本不写盘、不改任何字段，只给读数。

跑法：python -X utf8 工具/verify_card_text.py [--threshold 0.5]
"""
import argparse
import difflib
import io
import json
import os
import re
import subprocess
import sys
import tempfile

from PIL import Image
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..'))
sys.path.insert(0, HERE)
import build_card_text_review as B  # noqa: E402  复用同一套面板定位，保证对拍读的是同一块像素

TESS = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
CJK = re.compile(r'[一-鿿]')


def ocr_line(img, tmpdir):
    W, H = img.size
    g = img.convert('L')
    a = np.asarray(g, dtype=np.int16)
    p = B._panel_top(a, H)
    if p is None:
        band = g.crop((0, int(H * 0.70), W, H))
    else:
        t0, t1 = B._text_rows(a, p, H)
        band = g.crop((0, t0, W, t1))
    band = band.resize((band.width * 3, band.height * 3), Image.LANCZOS)
    fp = os.path.join(tmpdir, 'band.png')
    band.save(fp)
    env = dict(os.environ, TESSDATA_PREFIX=r'C:\Program Files\Tesseract-OCR\tessdata')
    out = subprocess.run([TESS, fp, 'stdout', '--psm', '7', '-l', 'chi_sim'],
                         capture_output=True, text=True, encoding='utf-8', env=env)
    return re.sub(r'\s+', '', out.stdout or '')


def main(threshold):
    with io.open(B.DRAFT, encoding='utf-8') as fh:
        draft = json.load(fh)
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for pos, it in enumerate(draft['items'], 1):
            want = it['bottom_text']
            if not want:
                continue
            img = Image.open(os.path.join(B.CARDS, it['file']))
            got = ocr_line(img, tmp)
            ratio = difflib.SequenceMatcher(None, want, got).ratio()
            rows.append((ratio, pos, it['card_type'], it['code'], want, got))
    rows.sort()
    low = [r for r in rows if r[0] < threshold]
    vals = [r[0] for r in rows]
    print('参与对拍 %d 条（空文案 10 条不参与）' % len(rows))
    print('相似度 min/median/max %.2f/%.2f/%.2f' % (min(vals), sorted(vals)[len(vals) // 2], max(vals)))
    print('低于 %.2f 需回看图 %d 条' % (threshold, len(low)))
    for ratio, pos, kind, code, want, got in low:
        print('  #%03d %.2f %s %s | 转录:%s | OCR:%s' % (pos, ratio, kind, code, want, got[:40]))
    return 1 if low else 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--threshold', type=float, default=0.5)
    sys.exit(main(ap.parse_args().threshold))
