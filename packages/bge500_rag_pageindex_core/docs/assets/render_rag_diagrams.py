from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
FONT = Path(r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD = Path(r"C:\Windows\Fonts\msyhbd.ttc")

COLORS = {
    "bg": "#FFFFFF",
    "page": "#EEF2F7",
    "text": "#17233D",
    "muted": "#59677F",
    "blue": "#2368C4",
    "blue_fill": "#EEF6FF",
    "green": "#35964B",
    "green_fill": "#EEF9EC",
    "purple": "#6F3CC3",
    "purple_fill": "#F4EFFF",
    "yellow": "#D99B16",
    "yellow_fill": "#FFF7DF",
    "red": "#DC514A",
    "red_fill": "#FFF0EF",
    "gray": "#AAB3C2",
}


def font(size: int, bold: bool = False):
    return ImageFont.truetype(str(FONT_BOLD if bold else FONT), size)


def wrapped(draw, text, fnt, max_width):
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for char in paragraph:
            test = line + char
            if line and draw.textlength(test, font=fnt) > max_width:
                lines.append(line)
                line = char
            else:
                line = test
        lines.append(line)
    return lines


def centered_text(draw, xy, text, fnt, fill, max_width, spacing=7):
    x1, y1, x2, y2 = xy
    lines = wrapped(draw, text, fnt, max_width)
    bbox = draw.multiline_textbbox((0, 0), "\n".join(lines), font=fnt, spacing=spacing, align="center")
    height = bbox[3] - bbox[1]
    draw.multiline_text(
        ((x1 + x2) / 2, (y1 + y2 - height) / 2),
        "\n".join(lines), font=fnt, fill=fill, spacing=spacing,
        align="center", anchor="ma"
    )


def box(draw, xy, text, kind="blue", size=24, radius=16, width=3, bold=True):
    stroke = COLORS[kind]
    fill = COLORS[f"{kind}_fill"]
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=stroke, width=width)
    centered_text(draw, xy, text, font(size, bold), stroke, xy[2] - xy[0] - 28)


def dashed_round(draw, xy, radius=18, color=None, width=2, dash=10, gap=8):
    color = color or COLORS["gray"]
    x1, y1, x2, y2 = xy
    # Straight dashed edges are sufficient; rounded corner arcs keep the visual soft.
    for start in range(x1 + radius, x2 - radius, dash + gap):
        draw.line((start, y1, min(start + dash, x2 - radius), y1), fill=color, width=width)
        draw.line((start, y2, min(start + dash, x2 - radius), y2), fill=color, width=width)
    for start in range(y1 + radius, y2 - radius, dash + gap):
        draw.line((x1, start, x1, min(start + dash, y2 - radius)), fill=color, width=width)
        draw.line((x2, start, x2, min(start + dash, y2 - radius)), fill=color, width=width)
    draw.arc((x1, y1, x1 + radius * 2, y1 + radius * 2), 180, 270, fill=color, width=width)
    draw.arc((x2 - radius * 2, y1, x2, y1 + radius * 2), 270, 360, fill=color, width=width)
    draw.arc((x1, y2 - radius * 2, x1 + radius * 2, y2), 90, 180, fill=color, width=width)
    draw.arc((x2 - radius * 2, y2 - radius * 2, x2, y2), 0, 90, fill=color, width=width)


def arrow_down(draw, x, y1, y2, color="#27324A", width=4):
    draw.line((x, y1, x, y2 - 12), fill=color, width=width)
    draw.polygon([(x - 9, y2 - 13), (x + 9, y2 - 13), (x, y2)], fill=color)


def arrow_right(draw, x1, y, x2, color="#27324A", width=4):
    draw.line((x1, y, x2 - 12, y), fill=color, width=width)
    draw.polygon([(x2 - 13, y - 9), (x2 - 13, y + 9), (x2, y)], fill=color)


def title(draw, text, width):
    draw.text((width / 2, 45), text, font=font(45, True), fill="#124AA3", anchor="ma")


def render_end_to_end():
    w, h = 1500, 2220
    img = Image.new("RGB", (w, h), COLORS["bg"])
    d = ImageDraw.Draw(img)
    title(d, "当前 BGE RAG 系统端到端架构", w)

    left = (28, 145, 265, 2050)
    right = (1235, 145, 1472, 2050)
    dashed_round(d, left)
    dashed_round(d, right)
    d.text((146, 165), "数据与缓存", font=font(23, True), fill=COLORS["muted"], anchor="ma")
    d.text((1354, 165), "模型与服务", font=font(23, True), fill=COLORS["muted"], anchor="ma")

    for y, text in [
        (245, "原始语料\ncorpus/all_\ndocuments"),
        (650, "路径映射\nmanifest.sqlite3"),
        (1055, "只读索引\nElasticsearch\nBM25 +\nBGE-small"),
        (1510, "文档树缓存\nPageIndex\ncache"),
    ]:
        box(d, (48, y, 245, y + 180), text, "blue", 20)

    for y, text in [
        (260, "LLM API\n路由 / 规划 / 审计 / 生成"),
        (690, "BGE-small\n本地查询编码"),
        (1100, "Rerank API\ncross-encoder 精排"),
        (1540, "Elasticsearch\n在线检索服务"),
    ]:
        box(d, (1255, y, 1452, y + 165), text, "blue", 19)

    cx1, cx2, cx = 300, 1200, 750
    box(d, (440, 130, 1060, 220), "问题输入（question-only）\nquestion_id + question", "green", 25)
    arrow_down(d, cx, 220, 265)
    box(d, (440, 265, 1060, 350), "LLM 题型路由", "purple", 28)
    box(d, (465, 365, 1035, 420), "只根据问题文本推断内部检索模式，不读取 benchmark 题型标签", "purple", 17, 10, 1)
    arrow_down(d, cx, 420, 460)

    retrieval = (cx1, 460, cx2, 1000)
    dashed_round(d, retrieval)
    d.text((330, 485), "按题型启用多路检索视图", font=font(28, True), fill="#174FA8")
    route_boxes = [
        ((330, 535, 590, 625), "默认题型\nkeyword + dense"),
        ((620, 535, 910, 625), "semantic / project_related\nkeyword + dense\n+ rewrite + intent"),
        ((940, 535, 1170, 625), "completeness\nkeyword + dense\n+ intent"),
    ]
    for xy, text in route_boxes:
        box(d, xy, text, "yellow", 16, 11, 2)
    views = [
        ((325, 665, 525, 790), "Original keyword\nElasticsearch BM25"),
        ((545, 665, 745, 790), "Original dense\nBGE-small-en-v1.5"),
        ((765, 665, 965, 790), "Query rewrite\n最多 2 路"),
        ((985, 665, 1175, 790), "Answer intent\n最多 2 路"),
    ]
    for xy, text in views:
        box(d, xy, text, "blue", 17, 12, 2)
        arrow_down(d, (xy[0] + xy[2]) // 2, xy[3], 825, width=2)
    box(d, (475, 825, 1025, 895), "带权 RRF 融合", "blue", 23)
    box(d, (450, 910, 1050, 965), "keyword 1.2 / dense 1.0 / rewrite 0.9 / intent 0.4", "blue", 16, 9, 1)

    arrow_down(d, cx, 1000, 1040)
    box(d, (430, 1040, 1070, 1130), "Remote reranker：120 个候选 → top 30", "blue", 24)
    arrow_down(d, cx, 1130, 1170)
    box(d, (415, 1170, 1085, 1265), "Semantic consensus rescue\n双视图共识，最多补 1 个文档", "blue", 23)
    arrow_down(d, cx, 1265, 1305)

    pi = (cx1, 1305, cx2, 1575)
    dashed_round(d, pi)
    d.text((330, 1330), "PageIndex：文档级证据控制", font=font(28, True), fill="#174FA8")
    pi_steps = [
        ((325, 1390, 520, 1505), "题型判断\n是否进入"),
        ((545, 1390, 740, 1505), "文档树\n节点选择"),
        ((765, 1390, 960, 1505), "缺失分面\n最多 2 跳"),
        ((985, 1390, 1175, 1505), "权威性与\n节点审计"),
    ]
    for i, (xy, text) in enumerate(pi_steps):
        box(d, xy, text, "yellow", 17, 11, 2)
        if i < 3:
            arrow_right(d, xy[2] + 4, 1447, pi_steps[i + 1][0][0] - 4, width=2)
    d.text((750, 1542), "简单题跳过；结构化题型按题型预算进入", font=font(16), fill=COLORS["muted"], anchor="mm")

    arrow_down(d, cx, 1575, 1615)
    evidence = (cx1, 1615, cx2, 1845)
    dashed_round(d, evidence)
    d.text((330, 1640), "Evidence selection / answer preparation", font=font(27, True), fill="#174FA8")
    ev = [
        ((340, 1700, 580, 1795), "precision_v3\n24 → 最多 10 个证据"),
        ((630, 1700, 870, 1795), "事实核验"),
        ((920, 1700, 1160, 1795), "最终答案与\n来源审计"),
    ]
    for i, (xy, text) in enumerate(ev):
        box(d, xy, text, "yellow", 18, 11, 2)
        if i < 2:
            arrow_right(d, xy[2] + 5, 1747, ev[i + 1][0][0] - 5, width=2)
    d.text((750, 1820), "每文档最多 4 个证据 · fail-closed", font=font(15), fill=COLORS["muted"], anchor="mm")

    arrow_down(d, cx, 1845, 1885)
    box(d, (445, 1885, 1055, 1970), "Lark 答案生成", "purple", 27)
    arrow_down(d, cx, 1970, 2010)
    box(d, (430, 2010, 1070, 2100), "answers.jsonl\nanswer + document_ids（最多 10 个）", "green", 23)

    # Legend
    y = 2160
    legend = [("green", "输入 / 输出"), ("blue", "数据 / 检索 / 服务"), ("purple", "LLM / 推理"), ("yellow", "工具调用 / Action"), ("red", "判断 / 控制流")]
    x = 170
    for kind, label in legend:
        d.rounded_rectangle((x, y - 13, x + 30, y + 5), radius=4, fill=COLORS[f"{kind}_fill"], outline=COLORS[kind], width=1)
        d.text((x + 40, y - 4), label, font=font(15), fill=COLORS["muted"], anchor="lm")
        x += 240

    img.save(ROOT / "bge-rag-end-to-end.png", optimize=True)


def render_pageindex():
    w, h = 1450, 1850
    img = Image.new("RGB", (w, h), COLORS["bg"])
    d = ImageDraw.Draw(img)
    title(d, "PageIndex：三关两跳证据路由", w)
    d.text((w / 2, 110), "Elasticsearch 找候选；PageIndex 决定读哪份原文、哪些章节，以及证据是否完整", font=font(19), fill=COLORS["muted"], anchor="ma")
    cx = w // 2

    box(d, (390, 155, 1060, 235), "输入：reranker top 30 chunks", "blue", 24)
    arrow_down(d, cx, 235, 275)
    box(d, (475, 275, 975, 365), "题型是否需要结构化证据？", "red", 24)
    box(d, (1000, 280, 1390, 360), "否 → basic / miscellaneous / info_not_found\n跳过 PageIndex，直接进入 precision_v3", "yellow", 15, 10, 2)
    arrow_right(d, 975, 320, 1000, width=2)
    arrow_down(d, cx, 365, 405)
    box(d, (365, 405, 1085, 500), "第 0 步：证据计划\n拆分 facets，提取实体、日期、版本、状态等硬约束", "purple", 22)
    arrow_down(d, cx, 500, 540)
    box(d, (350, 540, 1100, 635), "第 1 跳：原始结果 + 最多 4 条分面查询\n交错合并，避免单一查询或文档独占候选窗口", "yellow", 21)
    arrow_down(d, cx, 635, 675)

    stage = (90, 675, 1360, 930)
    dashed_round(d, stage)
    d.text((120, 700), "三道证据关", font=font(28, True), fill="#174FA8")
    gates = [
        ((120, 760, 470, 880), "第 1 关：候选文档\ndoc_id 去重 → manifest 回读原文 → 文档树"),
        ((550, 760, 900, 880), "第 2 关：节点选择\n定位直接证据，排除错实体、错日期、错版本"),
        ((980, 760, 1330, 880), "第 3 关：节点审计\n检查分面覆盖、权威性、冲突和重复对象"),
    ]
    for i, (xy, text) in enumerate(gates):
        box(d, xy, text, "blue", 18, 12, 2)
        if i < 2:
            arrow_right(d, xy[2] + 8, 820, gates[i + 1][0][0] - 8, width=2)

    arrow_down(d, cx, 930, 970)
    box(d, (475, 970, 975, 1060), "全部分面是否完整？", "red", 24)
    arrow_down(d, cx, 1060, 1110)
    d.text((245, 1120), "完整", font=font(18, True), fill=COLORS["green"], anchor="ma")
    d.text((725, 1120), "缺失且仍有 hop 预算", font=font(18, True), fill=COLORS["yellow"], anchor="ma")
    d.text((1205, 1120), "最终仍不完整", font=font(18, True), fill=COLORS["red"], anchor="ma")
    branches = [
        ((70, 1160, 430, 1325), "形成证据闭集\n只输出通过审计的节点，不再混入其他 ES chunk", "green"),
        ((545, 1160, 905, 1325), "第 2 跳：只补缺失分面\n冲突题同时找 previous/latest；保留第 1 跳已审计文档", "yellow"),
        ((1020, 1160, 1380, 1325), "按题型决定最终退路\n部分证据只在准入文档内补全文；完全失败才 ES fallback 或拒答", "red"),
    ]
    for xy, text, kind in branches:
        box(d, xy, text, kind, 18, 13, 2)
    d.text((725, 1360), "第 2 跳完成后重新执行三关审计；第 1 跳已确认的证据不会被淘汰", font=font(18, True), fill=COLORS["purple"], anchor="ma")
    arrow_down(d, cx, 1385, 1430)
    box(d, (315, 1430, 1135, 1530), "统一进入 precision_v3 → 事实核验 → 最终答案与来源审计", "green", 23)

    box(d, (160, 1595, 1290, 1745), "审计时重点查看\nplan：采用的题型预算    hops：实际跳数\nmissing_facets：仍缺什么    route_action：完整闭集 / 限定补充 / ES 回退", "blue", 19, 14, 2)
    d.text((w / 2, 1800), "核心原则：完整结果形成闭集；部分结果只在已准入文档内扩展；完全失败才按题型决定回退。", font=font(18), fill=COLORS["muted"], anchor="ma")

    img.save(ROOT / "pageindex-three-gates-two-hops.png", optimize=True)


if __name__ == "__main__":
    render_end_to_end()
    render_pageindex()
