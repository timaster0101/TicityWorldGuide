"""开图清单 Markdown 的唯一渲染方（从 工具/build_prompts.py 抽出）。

抽出理由：数据/开图清单.md 与 数据/开图清单.json 会随时间分叉（收口轮实测 md 写
292／20、json 已 312／0），要能被独立刷新；而 build_prompts.py 一跑就会重算 312 条
prompt_sha256、把冻结基准整批挪走，不能用来「只刷新这张表」。

因此这里只读清单条目上已经落定的字段，配 工具/render_manifest_md.py（从 json 渲染）
与 工具/test_render_manifest_md.py（渲染与盘面逐字对拍）使用。
"""

import json
import io
import os
import re
import sys

__all__ = ["render_manifest_md"]


def render_manifest_md(manifest, out, batch_order, tech_carrier_words):
    """把清单条目渲染成 数据/开图清单.md 的正文（本文件的唯一渲染方）。

    只读 manifest 条目上已经落定的字段（id/name/parent_name/size/朝向/太阳侧别/
    参照价/提示词文件名/图片/状态/复验备注）与 out 的五个汇总数，**不回算
    prompt_sha256、不读不写 数据/开图提示词/**——所以 工具/render_manifest_md.py
    能拿 数据/开图清单.json 当输入直接调它，在不重钉提示词基准的前提下刷新本表。
    """
    md = ["# 钛湖城开图清单（%d条，一图对一点）\n" % out["prompt_count"]]
    md.append("每条提示词是 `数据/开图提示词/` 下的独立文件，文件名即“ID-名称”。生图后把图片路径回填到 `数据/开图清单.json` 的 `image_file` 与 `batch` 字段，不要另建对照表，避免两边漂移。\n")
    md.append("实际验收通过后再绑定图片：`image_prompt_sha256` 一律绑当前基准 `prompt_sha256`（C135）；有补充输入时把实际送入串记进 `generation_input_file`、`generation_input_sha256`，并用 `image_base_prompt_sha256` 记生成时基准版本——备案答「实际喂了什么」、绑定答「按哪版基准投的」，两者不能互相顶替，基准变化仍须复验。不得只复制摘要补绑；图片、批次与既有备注保留。无图始终待开图，有图不代表通过；修改状态后重跑本生成器同步提示词和本表。\n")
    md.append("**已验收的语义边界（C139）**：本表「已验收」与本清单 `accepted` 只表示机械判据验收通过（容器标识、逐字回绑、格数与档串、尺寸对回声明），**不表示人工逐张目视通过、也不表示画风已过关**。受委托代签的每条都在 `数据/开图验收备注.json` 留一行 `C139代签验收<ID>：`，写明执行人、委托来源原句、依据读数、「人工逐张目视未执行」与绑定摘要前12位；缺任一要素由 `工具/test_image_assets.py` 的 `check_sign_declaration` 判红。画风侧的反向读数与未收口偏差见该轮登记，不得把 `accepted` 读成目视结论。\n")
    md.append("提示词 %d｜待开图 %d｜有图 %d｜已验收 %d｜待复验 %d。有图数仅按非空 `image_file` 统计，不代替人工验收。\n" % (
        out["prompt_count"], out["pending"], out["generated"], out["accepted"], out["needs_review"]))
    md.append("## 批次与验收\n")
    md.append("- 建议批次顺序：%s。地标先跑，按各自正典核验建筑形态与水体关系，不统一套用单塔；片区最后跑，因其视野最广、最容易把不该看见的湖面塞进背景。" % "→".join(batch_order))
    md.append("- 验收以条目自身的【锁定与禁则】为准，通用否决项为：曲面扭转塔、湖中建塔、把L007的非对称直线斜削冠与细针状天线安到别的塔楼上、第二个机场、海港或大型人工岛、可读的招牌字形或凭空文字（招牌、灯箱、门牌必须存在，字形须是不可读的模糊笔画，这一项只否决「可读」）、出成照片质感（毛孔、镜头噪点、景深颗粒）或干净CG渲染（表面无过渡层次、高光呈均匀塑料感）、描边加平涂色阶的动画档、飞行汽车或全息投影一类近未来符号、第三方台标或渠道logo水印（模型侧带出的「LibTV」一类标记）、把湖面强塞进山外村镇背景、背景天际线画进本条【取景指令】未逐一点名的塔楼或超高层群。200米以上的塔楼在扩容后已成簇，成簇是正典事实而不是本条画面的授权，按名录逐栋核对高度与冠部，不再以「第二座超过200米的塔」作否决，但未被取景段点名的塔出现在背景里即属越权入画；这一项按能否读出专属形制记号分两档判读（C125）：未点名体量上出现非对称斜削冠、细针状天线、桅杆或斜拉索上段、冠部开洞、扭转塔身任一记号即判废，只读得出平头板楼、阶梯退台或雾中无冠部细节的剪影时记备注、不单独判废——剪影不带记号，人工复看既对不到名录的某一栋，也无从判定它是否本就不该出现。屋面上的细竖杆按 C126 量着判而不是看着判：发丝状直杆且无横档、无格构、无灯球、无斜削面、无开洞，杆高不超过同屏可见塔身的十二分之一，读作避雷带或旗杆类构件、记备注；带上述任一记号，或杆高超过十二分之一，即按记号档判废。杆高与可见塔身一律用源码网格切片在源图像素上量（杆顶y、女儿墙y、前景遮断处y），两个数一并写进读数，不靠目测印象。塔吊同样按 C126 分工：立于街面施工围挡层、不与任何未点名远景塔冠绑定的吊机读作生活痕迹（tail 的生活痕迹清单明列 construction hoarding with a tower crane 为允许项），记备注；立于天际线远景带、与未点名体量同带的吊机判废。画面可读层数与本条锁定的层数不符只记备注、不单独判废：层数与米数只写在中文段，English tail 没有可数的单元，模型无从计数。平台按AIGC强制标识加的「Qoder AI生成」角标与图片XMP里的TC260元数据标识不属否决项，须原样保留，不得裁剪、遮盖或修补。")
    md.append("- 人群核验以条目自身的【人群与烟火气】为准：先看本条详档人群段的具体描写，再看该类型的缺省人数档，二者冲突按详档。画面人物明显低于档位下限（空街、空场）或反过来形成盛大庆典、统一着装团体，均记为待复验；俯瞰与鸟瞰条不逐个数人，但地面必须看得出有人在走动。")
    md.append("- 画风与双层核验：本批按半写实数字厚涂开图，笔触可辨、颜料层次读得出来、表面是画出来的（C122 曾把本档降到「平滑过渡、皮肤豁免笔触」，2026-11-09 的 C153 按在册风险条款回退到本档）；出成照片质感（毛孔、镜头噪点、景深颗粒）或干净CG渲染（表面无过渡层次、高光呈均匀塑料感、边缘像布尔运算）都不合格。同一张图必须同时读得出科技层与老城层且二者有物理接触——只有玻璃幕墙、只有仿古街、或两层各占一半却被广场绿地切断，一律记待复验。科技层按2010年代前沿的具名设施核对（%s），这些词逐条由生成器核回 312 条正文的承载体；LED媒体立面、光纤到楼箱与屋顶通信设备一类属表层材质词，按画面材质核对、不要求名录承载体。飞行汽车、载人无人机、全息投影、机器人服务员、自动驾驶车队一类近未来符号出现即判废。生活痕迹实体（晾晒、盆栽、卸货筐、摊贩热气、灯箱、非机动车停放、下棋的老人、接送孩子的家长、施工围挡与吊装、垃圾收集点、遛狗、积水倒影）每条至少三项，不足三项记待复验。" % ("、".join(tech_carrier_words),))
    md.append("- 光照默认晚秋255°方位、6°高度；清晨、夜景、雨后、阴天只有在提示词里显式标注为变体时才允许，清单的“光照判定”列已按每条的拍摄朝向算好太阳侧别。\n")
    for typ in batch_order:
        rows = [m for m in manifest if m["type"] == typ]
        md.append("\n## %s（%d条）\n" % (typ, len(rows)))
        md.append("| ID | 名称 | 所属 | 尺寸 | 朝向° | 太阳相对° | 太阳侧别 | 参照价 | 提示词文件 | 图片 | 状态 | 复验原因/备注 |")
        md.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for m in rows:
            md.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
                m["id"], m["name"], m["parent_name"], m["size"],
                m["camera_facing_deg"], m["sun_relative_deg"], m["sun_side"].split("（")[0],
                m["pricing_reference"], m["prompt_file"], m["image_file"] or "待生成",
                m["status"], m["review_note"].replace("|", "\\|").replace("\n", "<br>") or "—"))
        md.append("")
    md.append("人工验收备注只在 数据/开图验收备注.json 里改，重跑后同步进 review_note_history；清单里的 review_note 是「人工末条＋派生原因」的拼接展示值，不手改。")
    return "\n".join(md)

def _first_diff(a, b):
    la, lb = a.split("\n"), b.split("\n")
    for i in range(min(len(la), len(lb))):
        if la[i] != lb[i]:
            return i + 1, la[i], lb[i]
    if len(la) != len(lb):
        return min(len(la), len(lb)) + 1, "<无此行>", "<无此行>"
    return None


def tech_carrier_words_from_source(path):
    """从 build_prompts.py 源码里读出 TECH_CARRIER_WORDS，不执行该脚本。

    该脚本一 import 就会重算提示词并落盘，只能读源码；读不到就抛错，让闸门红。
    """
    with io.open(path, encoding="utf-8") as fp:
        text = fp.read()
    m = re.search(r"^TECH_CARRIER_WORDS = \((.*?)\)\n", text, re.S | re.M)
    if not m:
        raise SystemExit("读不到 TECH_CARRIER_WORDS：build_prompts.py 结构变了？")
    return tuple(re.findall(r'"([^"]+)"', m.group(1)))


def check(doc, md_text, batch_order, tech_carrier_words, limit=5):
    """返回问题清单；空表＝盘面 md 与按 json 现渲染逐字相同。

    逐行对拍而不是只报首处差异：收口轮这张表有 20 条状态与多处备注同时变了，
    只报第一行会让人以为只有一行过期。最多列 limit 行，末尾报总数。
    """
    want = render_manifest_md(doc["items"], doc, batch_order, tech_carrier_words)
    if want == md_text:
        return []
    la, lb = md_text.split("\n"), want.split("\n")
    diffs = []
    for i in range(max(len(la), len(lb))):
        got = la[i] if i < len(la) else "<无此行>"
        exp = lb[i] if i < len(lb) else "<无此行>"
        if got != exp:
            diffs.append((i + 1, got, exp))
    out = ["第 %d 行与清单不符：盘面 %r／应为 %r" % (n, got[:110], exp[:110])
           for n, got, exp in diffs[:limit]]
    if len(diffs) > limit:
        out.append("……共 %d 行不符（只列前 %d 行）" % (len(diffs), limit))
    return out
