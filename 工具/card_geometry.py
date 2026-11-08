#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡面几何/印章口径单一真源（路线 B：满幅主图 + HTML 叠字）。

2026-11-08 卡面交付从「Pillow 烤 PNG」改为满幅主图后（裁定 C147/C148），烤图时代的
窗带、内缩、本体矩形随交付形态一起失效，本文件只留在 HTML 路线里真有读取点的口径：

  - SEAL_VIS        供 verify_seal_asset.py 逐边对回 720 素材的可见章面占比；
  - SEAL_LANDING_B  供 build_card_html.py 生成 `.card .seal` 的 CSS，渲染器不另抄数字；
  - CANVAS/SEAL_BADGE_BAND 供落点判据换算（章面须让开右下台标带）。

数值来历：SEAL_VIS 为 720 素材去四周透明留白后的外接框占比（实测 x0.058..0.946 y0.049..0.939）；
SEAL_BADGE_BAND 为满幅口径下 manifest status=OK 全 114 张逐张全量扫描（非抽样）可检出台标上沿距实景下沿最大值 ceil(52.6)=53（真源
`数据/台标带实测.json`，由 `test_build_card_html.py` 的 `test_badge_band_is_the_minimal_cover_of_the_full_bleed_measurement`
双向钉住：调小判压台标、调大判白丢净空）；SEAL_LANDING_B 的右内缩 4%、下内缩 19% 为 2026-11-08
在 Chrome 里把 .card 强制成 768×1024 实测的包围盒反推，章径档位同日按用户「都做」推翻 24% 那一版、
回到烤图时代裁定的视觉尺寸「章径＝本体宽 1/3」＝卡宽 27.6%（768×0.276＝211.97≈212 px），
实测章框 (525,618)-(737,829)、边长 212.0（换算框 (525,617)-(737,829)，差 1 px 是浏览器对 211.968 的取整）。
锚点从烤图时代的「实景窗下沿」改成路线 B 的「满幅整卡下沿」，因此必须靠 19% 的下内缩把章面抬到
台标带与底部浮层之上（可见章面下沿 816 < 浮层上沿 973.5 < 台标带上沿 1024−53=971）。
"""
CANVAS = (768, 1024)

SEAL_VIS = (0.058, 0.049, 0.946, 0.939)
SEAL_BADGE_BAND = 53

# 路线 B 印章落点：相对整张卡的宽高占比，渲染器据此生成 CSS
SEAL_LANDING_B = {"size_r": 0.276, "right_r": 0.04, "bottom_r": 0.19}


def seal_box_canvas(landing=None, canvas=CANVAS):
    """把落点比例换算成 768×1024 上的印章框像素包围盒 (x0, y0, x1, y1)。"""
    l = landing or SEAL_LANDING_B
    w, h = canvas
    side = w * l["size_r"]
    x1 = w - w * l["right_r"]
    y1 = h - h * l["bottom_r"]
    return round(x1 - side), round(y1 - side), round(x1), round(y1)


def seal_visible_box_canvas(landing=None, canvas=CANVAS):
    """印章框按 SEAL_VIS 折算出的可见章面像素包围盒。"""
    x0, y0, x1, y1 = seal_box_canvas(landing, canvas)
    w, h = x1 - x0, y1 - y0
    return (round(x0 + SEAL_VIS[0] * w), round(y0 + SEAL_VIS[1] * h),
            round(x0 + SEAL_VIS[2] * w), round(y0 + SEAL_VIS[3] * h))
