# -*- coding: utf-8 -*-
"""生成《星衡精密 AI 数智化交付流程项目 · 计划方案（含推演模拟）》DOCX。
整合：制造业现状报告、寻访报告(35事实/6痛点)、现状泳道图、数智化To-Be图、24万试点报价单。"""
from docx import Document
from docx.shared import Pt, Cm, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import os

BASE = r"C:\Users\24230\Desktop\work"
OUT = os.path.join(BASE, "星衡精密-AI数智化交付流程项目-计划方案.docx")
IMG_CURRENT = os.path.join(BASE, "业务现状流程图2.jpg")
IMG_TOBE = os.path.join(BASE, "加入数智的后流程图.jpg")

doc = Document()

# ---------- 全局字体（宋体 / 小四 10.5pt）----------
def set_cn_font(style_or_run, name="宋体", size=None, bold=None, color=None):
    if hasattr(style_or_run, "font"):  # run
        run = style_or_run
        run.font.name = name
        rpr = run._element.get_or_add_rPr()
        rfonts = rpr.get_or_add_rFonts()
        rfonts.set(qn('w:eastAsia'), name)
        if size is not None:
            run.font.size = size
        if bold is not None:
            run.font.bold = bold
        if color is not None:
            run.font.color.rgb = color
    else:  # style
        style = style_or_run
        style.font.name = name
        style.font.size = size or Pt(10.5)
        rpr = style.element.get_or_add_rPr()
        rfonts = rpr.get_or_add_rFonts()
        rfonts.set(qn('w:eastAsia'), name)

normal = doc.styles['Normal']
normal.font.name = '宋体'
normal.font.size = Pt(10.5)
set_cn_font(normal)
# 页边距
for s in doc.sections:
    s.top_margin = Cm(2.0); s.bottom_margin = Cm(2.0)
    s.left_margin = Cm(2.4); s.right_margin = Cm(2.4)

NAVY = RGBColor(0x1F, 0x38, 0x64)
BLUE = RGBColor(0x2E, 0x5B, 0xA8)
ORANGE = RGBColor(0xC0, 0x55, 0x00)
GREY = RGBColor(0x55, 0x55, 0x55)

def add_h(text, level=1):
    h = doc.add_heading(level=level)
    run = h.add_run(text)
    run.font.name = '黑体'
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.get_or_add_rFonts()
    rfonts.set(qn('w:eastAsia'), '黑体')
    if level == 1:
        run.font.size = Pt(16); run.font.color.rgb = NAVY; run.font.bold = True
    elif level == 2:
        run.font.size = Pt(13); run.font.color.rgb = BLUE; run.font.bold = True
    else:
        run.font.size = Pt(11.5); run.font.color.rgb = BLUE; run.font.bold = True
    return h

def add_p(text="", size=10.5, bold=False, color=None, align=None, italic=False, space_after=6):
    p = doc.add_paragraph()
    if align: p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.25
    if text:
        r = p.add_run(text)
        set_cn_font(r, size=size, bold=bold, color=color)
        r.font.italic = italic
    return p

def add_bullet(text, size=10.5, color=None):
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.space_after = Pt(3)
    r = p.add_run(text)
    set_cn_font(r, size=size, color=color)
    return p

def shade_cell(cell, hexcolor):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear'); shd.set(qn('w:color'), 'auto'); shd.set(qn('w:fill'), hexcolor)
    tcPr.append(shd)

def set_cell(cell, text, bold=False, size=9.5, color=None, fill=None, align='left'):
    cell.text = ""
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(1); p.paragraph_format.space_before = Pt(1)
    p.alignment = {'left': WD_ALIGN_PARAGRAPH.LEFT, 'center': WD_ALIGN_PARAGRAPH.CENTER,
                   'right': WD_ALIGN_PARAGRAPH.RIGHT}[align]
    for i, line in enumerate(str(text).split("\n")):
        if i > 0:
            p = cell.add_paragraph(); p.paragraph_format.space_after = Pt(1)
        r = p.add_run(line)
        set_cn_font(r, size=size, bold=bold, color=color)
    if fill:
        shade_cell(cell, fill)

def _set_table_borders(tbl):
    tblPr = tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for edge in ('top','left','bottom','right','insideH','insideV'):
        e = OxmlElement(f'w:{edge}')
        e.set(qn('w:val'),'single'); e.set(qn('w:sz'),'4')
        e.set(qn('w:space'),'0'); e.set(qn('w:color'),'B0B8C4')
        borders.append(e)
    tblPr.append(borders)

def add_table(headers, rows, widths=None, header_fill="1F3864", header_color=RGBColor(0xFF,0xFF,0xFF),
              zebra="EEF2F8", size=9.5, aligns=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    # 不依赖命名样式（腾讯文档/WPS 对 Table Grid 兼容差）；手动加边框 + 固定布局 + 明确列宽，确保单元格文字正常显示
    _set_table_borders(t._tbl)
    aligns = aligns or ['left'] * len(headers)
    for i, h in enumerate(headers):
        set_cell(t.rows[0].cells[i], h, bold=True, size=size, color=header_color, fill=header_fill, align='center')
    for ri, row in enumerate(rows):
        cells = t.add_row().cells
        for ci, val in enumerate(row):
            set_cell(cells[ci], val, size=size, fill=(zebra if ri % 2 else None), align=aligns[ci])
    if not widths:
        widths = [15.0/len(headers)] * len(headers)
    for row in t.rows:
        for ci, w in enumerate(widths):
            row.cells[ci].width = Cm(w)
    # 固定布局 + 明确表格宽度(dxa)，避免预览按 0 宽塌缩列
    tblPr = t._tbl.tblPr
    layout = tblPr.find(qn('w:tblLayout'))
    if layout is None:
        layout = OxmlElement('w:tblLayout'); tblPr.append(layout)
    layout.set(qn('w:type'), 'fixed')
    tblW = tblPr.find(qn('w:tblW'))
    if tblW is None:
        tblW = OxmlElement('w:tblW'); tblPr.append(tblW)
    tblW.set(qn('w:type'), 'dxa'); tblW.set(qn('w:w'), str(int(sum(widths)*567)))
    return t

def hr():
    p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(2); p.paragraph_format.space_after = Pt(6)
    pPr = p._p.get_or_add_pPr(); pbdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'),'single'); bottom.set(qn('w:sz'),'6'); bottom.set(qn('w:space'),'1'); bottom.set(qn('w:color'),'1F3864')
    pbdr.append(bottom); pPr.append(pbdr)

def add_footer():
    for section in doc.sections:
        footer = section.footer
        p = footer.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("星衡精密 · AI 数智化交付流程项目 · 计划方案（含推演模拟）   第 ")
        set_cn_font(run, size=8, color=GREY)
        # PAGE field
        fld1 = OxmlElement('w:fldSimple'); fld1.set(qn('w:instr'), 'PAGE')
        run2 = p.add_run(); run2._element.addnext(fld1)
        run3 = p.add_run(" 页 / 共 "); set_cn_font(run3, size=8, color=GREY)
        fld2 = OxmlElement('w:fldSimple'); fld2.set(qn('w:instr'), 'NUMPAGES')
        run4 = p.add_run(); run4._element.addnext(fld2)
        run5 = p.add_run(" 页"); set_cn_font(run5, size=8, color=GREY)

# ================= 封面 =================
for _ in range(2): doc.add_paragraph()
p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = p.add_run("星衡精密"); set_cn_font(r, size=26, bold=True, color=NAVY); r.font.name='黑体'
p2 = doc.add_paragraph(); p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
r2 = p2.add_run("AI 数智化交付流程项目\n计划方案（含推演模拟）"); set_cn_font(r2, size=20, bold=True, color=BLUE); r2.font.name='黑体'
p2.paragraph_format.space_after = Pt(4)
for _ in range(1): doc.add_paragraph()
sub = doc.add_paragraph(); sub.alignment = WD_ALIGN_PARAGRAPH.CENTER
rs = sub.add_run("——从“排产表之外的交付危机”到 AI 数智化目标态的落地路径与场景推演")
set_cn_font(rs, size=12, color=GREY)
for _ in range(3): doc.add_paragraph()
meta = doc.add_paragraph(); meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
for line in ["文档编号：XH-AI-PLAN-2026-001", "编制单位：星衡精密 · 数字化项目组 / 合作实施方",
             "版本：V1.0（拟稿）", "编制日期：2026-10-24", "保密等级：公司内部"]:
    rr = meta.add_run(line + "\n"); set_cn_font(rr, size=11, color=GREY)
# 封底分隔
doc.add_page_break()

# ================= 目录（手动） =================
add_h("目  录", 1)
toc = [
 "1  文档说明与编制依据",
 "2  项目背景",
 "   2.1 行业背景：制造业数智化已成必答题",
 "   2.2 企业现状与核心诉求",
 "   2.3 立项依据：四来源收敛摘要",
 "3  现状诊断（基于一线寻访）",
 "   3.1 六大痛点清单（REQ-1~6）",
 "   3.2 现状交付流程瓶颈",
 "4  目标蓝图与方案架构",
 "   4.1 目标指标",
 "   4.2 九大 AI 数智能力模块与痛点映射",
 "   4.3 人机协同原则（不可逾越的三条线）",
 "5  实施计划",
 "   5.1 总体实施策略",
 "   5.2 五阶段实施路线图",
 "   5.3 试点方案：CNC 三号线 4 周并行",
 "   5.4 组织与角色分工（RACI）",
 "   5.5 关键里程碑与时间表",
 "6  推演模拟（核心）",
 "   6.1 推演假设与基线",
 "   6.2 场景一：缺料 + 插单日的流程推演",
 "   6.3 场景二：换型与等料停机的流程推演",
 "   6.4 试点前后关键指标预测",
 "   6.5 投资回报（ROI）模拟",
 "7  预算与资源保障（摘要）",
 "8  风险管控与兜底设计",
 "9  验收标准与口径",
 "附录 A  术语表与依据编号",
]
for t in toc:
    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(2)
    indent = 0 if (not t.startswith(" ") ) else (1 if t.startswith("   ") else 0.6)
    p.paragraph_format.left_indent = Cm(indent*1.0)
    r = p.add_run(t); set_cn_font(r, size=10.5, color=(NAVY if not t.startswith(" ") else GREY), bold=(not t.startswith(" ")))
doc.add_page_break()

# ================= 1 文档说明 =================
add_h("1  文档说明与编制依据", 1)
add_p("本文档是星衡精密“AI 数智化交付流程项目”的计划方案与推演模拟，用于内部立项评审与试点启动。它是在此前已完成的三项工作的基础上整合而成：")
add_bullet("《2026 年制造行业现状与优秀案例、成果及经验总结报告》——提供行业背景与可行性对标；")
add_bullet("《星衡精密 · 业务需求发现报告（discovery-report）》——35 条一线访谈事实、6 大痛点（REQ-1~6）与验收约束；")
add_bullet("《业务现状流程图》与《AI 数智化交付流程 To-Be 图》——现状与目标态两张泳道流程图；")
add_bullet("《AI 数智化交付流程项目 · 报价单》——24 万元试点含税报价与付款/里程碑约定。")
add_p("说明：本报告中的“推演模拟”章节为基于现状基线与行业经验的情景推演，用于辅助决策，不构成对试点结果的承诺；所有量化目标与节省额均标注为“模拟口径，待试点实测确认”，与寻访报告“待验证假设”的口径一致。", color=ORANGE, size=9.5)

# ================= 2 项目背景 =================
add_h("2  项目背景", 1)
add_h("2.1 行业背景：制造业数智化已成必答题", 2)
add_p("根据 2026 年制造业现状研究：中国制造业增加值约 34.7 万亿元（占 GDP 约 25%），两化融合水平达 67.1，AI 重点场景普及率 34.2%（同比 +5.5pp），10.6% 规上企业已普及大模型；工业互联网覆盖 41 个工业大类，5G 工厂超 8000 家。全球“灯塔工厂”达 238 家，中国 103 家（43.3%）。行业共识已从“要不要数字化”转向“如何以数据+AI 把交付与质量真正打通”。")
add_p("对星衡精密这类以多品种、小批量、关键客户交期为生命线的精密制造企业而言，瓶颈往往不在单机效率，而在订单—工单—物料—换型—首检—交接之间的数据链断裂与版本不一致。这正是本项目要解决的“排产表之外的交付危机”。")

add_h("2.2 企业现状与核心诉求", 2)
add_table(
 ["维度", "现状（基线）", "来源"],
 [
  ["准时交付率", "78%；目标 92%", "F00"],
  ["延误主因", "延误订单中约 60% 来自缺料，而非排产算法", "F51"],
  ["等料停机", "CNC 三号线日均停机 70 分钟，其中约 40 分钟为等料", "F12"],
  ["换型记录", "换型平均 45 分钟，计划表从未记录", "F10"],
  ["插单方式", "每天上午出一次计划，下午插单靠微信群，执行版本常不一致", "F01"],
  ["首检管理", "首检未通过靠群聊/个人表补录，关键原因非结构化", "F14/F15"],
  ["数据前置", "ERP 订单号与 MES 工单号无稳定关联表，换型事件从未采集", "F30/F31"],
  ["试点边界", "首期仅 CNC 三号线标准工单；先历史回放、再并行 4 周试点", "F02/F05"],
  ["预算", "合成试点预算 24 万元（含税，含接口/培训/复核/维护）", "F03"],
 ],
 widths=[3.0, 9.5, 2.0], aligns=['left','left','center']
)

add_h("2.3 立项依据：四来源收敛摘要", 2)
add_p("寻访报告采用 Buyer / Brief / Operator / Industry 四来源收敛法，结论指向同一瓶颈：")
add_bullet("Buyer（厂长 顾明岚）：目标是把准交率从 78% 提到 92%、优先保关键客户交期；AI 只提可解释建议，不得直接下发；立项厂长牵头，质量有否决权，销售参与验收（F00/F02/F04）。")
add_bullet("Operator（班组长 林亦舟）：最耗时的不是设备，是换型与等料；缺料订单仍被排入当日计划，关键原因未结构化交接（F10/F11/F12/F14）。")
add_bullet("Brief（书面诉求）：订单越来越多、交期仍常延误，希望上 AI 自动排产提利用率——但四来源收敛显示，真实瓶颈在物料/换型信号缺失与版本不一致，直接追“满负荷”会与保交期冲突。")
add_bullet("Industry（行业可行性）：需先补订单-工单映射、物料就绪与换型信号，建立唯一日计划版本与人工复核关卡，再谈 AI 排产建议（与湘钢、上海电气、TCL 等标杆路径一致）。")

# ================= 3 现状诊断 =================
add_h("3  现状诊断（基于一线寻访）", 1)
add_h("3.1 六大痛点清单（REQ-1~6）", 2)
add_table(
 ["编号", "痛点", "关键依据", "优先级"],
 [
  ["REQ-1", "交付瓶颈首先是物料与换型信号缺失，而非排产算法", "F51/F12/F10", "P0"],
  ["REQ-2", "需要唯一日计划版本与插单留痕，替代微信群补丁", "F01/F20/F21", "P0"],
  ["REQ-3", "订单与工单映射缺失，无法归因交期（数据前置）", "F30/F31/F33", "P0"],
  ["REQ-4", "AI 只提建议、人工复核，不得覆盖原记录", "F22/F15/F42", "P0"],
  ["REQ-5", "兜底转人工需明确接手人、时限与记录位置", "F44/F35/F25", "P1"],
  ["REQ-6", "交期变更影响清单与准交率/首检口径需先固定", "F50/F52/F53", "P1"],
 ],
 widths=[1.6, 8.4, 3.0, 1.5], aligns=['center','left','center','center']
)
add_p("说明：P0/P1 为优先级标记，取自寻访报告，不等于已完成价值-风险评分；具体占比仍需历史订单回放量化。", size=9.5, color=GREY)

add_h("3.2 现状交付流程瓶颈", 2)
add_p("下方泳道图还原了现状链路：厂办→计划→班组→质量数据→销售复盘五条泳道，15 个步骤节点、5 个判断菱形，以及右侧 6 处“橙色虚线”标注的现状痛点（缺料仍排产、微信群插单、群聊补录、人工修复队列、接口失败只读快照、指标口径未固定）。")
if os.path.exists(IMG_CURRENT):
    doc.add_paragraph()
    doc.add_picture(IMG_CURRENT, width=Cm(15.5))
    cap = doc.add_paragraph(); cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rc = cap.add_run("图 1  星衡精密交付流程现状图（五泳道）"); set_cn_font(rc, size=9, color=GREY)
doc.add_page_break()

# ================= 4 目标蓝图 =================
add_h("4  目标蓝图与方案架构", 1)
add_h("4.1 目标指标", 2)
add_table(
 ["指标", "现状基线", "试点目标", "口径责任", "来源"],
 [
  ["准时交付率", "78%", "≥92%", "业务负责人书面固定", "F00/F53"],
  ["首检合格率", "暂无基线（待实测）", "≥98%", "质量主管签核门槛", "F42"],
  ["返工率", "基线值", "不上升（底线）", "验收硬指标", "F02"],
  ["等料停机", "40 分钟/天", "≤15 分钟/天", "班组/计划联动", "F12"],
  ["换型透明", "0 记录", "100% 自动采集入表", "MES/PLC 接口", "F10/F31"],
  ["计划版本", "微信群多版本", "唯一版本+留痕", "计划员维护", "F01/F20"],
 ],
 widths=[2.6, 2.6, 3.2, 3.4, 2.0], aligns=['left','center','center','left','center']
)

add_h("4.2 九大 AI 数智能力模块与痛点映射", 2)
add_table(
 ["#", "AI 能力模块", "承载泳道", "消除的痛点", "关键约束"],
 [
  ["1", "订单 ↔ 工单自动映射与关联表", "质量数据", "REQ-3 无法归因交期", "主编号/事件时间/来源/版本校验；缺字段进人工队列不猜值(F33)"],
  ["2", "物料就绪预测（库存+在途融合）", "计划", "REQ-1 缺料仍排产", "缺料自动标红不排入(F11)"],
  ["3", "智能排产引擎 + 插单统一入口", "计划", "REQ-2 微信群插单", "AI 只出建议+唯一版本留痕；改交期需销售批准(F22)"],
  ["4", "IoT 换型信号自动采集", "班组", "REQ-1 换型 45min 未记录", "PLC/工位终端读状态，禁自动下发(F32)"],
  ["5", "等料预警 · 动态重排", "班组", "REQ-1 等料停机 40min", "异常先由计划员核对(F15)"],
  ["6", "机器视觉首检（AI-VI）", "班组/质量", "REQ-4 群聊补录首检", "未通过自动停线；不覆盖原记录(F15)"],
  ["7", "数据治理（15 分钟刷新+只读快照）", "质量数据", "REQ-3/REQ-5 数据缺口", "过期标“待刷新”；失败保留只读快照(F34/F35)"],
  ["8", "经营驾驶舱（准交/利用率看板）", "厂办", "厂办看不见过程数据", "客户交期 vs 利用率冲突交评审会(F50)"],
  ["9", "AI 复盘助手 + 指标口径固化", "销售复盘", "REQ-6 口径未固定", "周复盘复测达标才更新规则(F55)"],
 ],
 widths=[0.7, 4.2, 1.8, 3.0, 5.0], aligns=['center','left','center','left','left'], size=9.0
)

add_h("4.3 人机协同原则（不可逾越的三条线）", 2)
add_bullet("建议线：AI 仅输出“可解释建议版”日计划，每条建议须说明卡在哪条约束、哪张订单让了步（F00/F22）。", color=NAVY)
add_bullet("复核线：日计划生效、质量签核两处保留人工确认；未确认结果不得覆盖原记录，原记录始终可点回（F15/F22/F42）。", color=NAVY)
add_bullet("红线：工艺参数仅授权班组可见、客户图纸不进外部模型；质量签核一票否决；首检低于 98% 项目叫停（F41/F42/F44）。", color=ORANGE)
add_p("下方 To-Be 泳道图为上述模块与原则的可视化落地：绿色实线为 AI 能力节点，紫色胶囊为人工复核关卡，判断菱形保留为流程卡点。")
if os.path.exists(IMG_TOBE):
    doc.add_paragraph()
    doc.add_picture(IMG_TOBE, width=Cm(15.5))
    cap = doc.add_paragraph(); cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    rc = cap.add_run("图 2  星衡精密 AI 数智化交付流程 To-Be 方案图"); set_cn_font(rc, size=9, color=GREY)
doc.add_page_break()

# ================= 5 实施计划 =================
add_h("5  实施计划", 1)
add_h("5.1 总体实施策略", 2)
add_p("遵循“数据先行 → 小场景切入 → 试点验证 → 推广复制”的迭代路线（与明珞四阶段、金叶七步闭环等标杆实践一致）：")
add_bullet("数据先行：前 2 周补订单-工单映射与数据基线，不跑通不谈排产（REQ-3）。")
add_bullet("小场景切入：首期只覆盖 CNC 三号线标准工单，先历史回放、再并行试点，不直接关掉现有人工流程（F05）。")
add_bullet("试点验证：4 周并行，AI 建议与人工计划逐单比对，硬指标验收。")
add_bullet("推广复制：试点达标后，按单厂→多基地扩展（见报价单第八章推广估算）。")

add_h("5.2 五阶段实施路线图", 2)
add_table(
 ["阶段", "周期", "主要工作", "交付物", "对应 REQ"],
 [
  ["P0 数据基线", "W1–W2", "订单-工单映射原型、字段校验、人工修复队列、换型/缺料信号采集方案", "数据基线报告、映射表原型", "REQ-3"],
  ["P1 平台部署", "W3–W4", "MES/ERP只读接口、经营驾驶舱、数据治理(15min刷新)、统一日计划版本", "集成环境、唯一版本日计划", "REQ-2/3"],
  ["P2 智能模块", "W5–W6", "物料就绪预测、智能排产+插单入口、IoT换型采集、等料预警、AI-VI首检", "9 模块 MVP、人工复核关卡", "REQ-1/4"],
  ["P3 并行试点", "W7–W10", "CNC 三号线 4 周并行，AI建议 vs 人工计划逐单比对，周复盘", "试点周报、差异清单、复盘记录", "REQ-4/5/6"],
  ["P4 验收推广", "W11+", "硬指标验收、规则固化、推广路线图与预算", "验收报告、推广方案", "全部"],
 ],
 widths=[2.2, 1.6, 6.3, 3.6, 1.8], aligns=['center','center','left','left','center'], size=9.0
)

add_h("5.3 试点方案：CNC 三号线 4 周并行", 2)
add_table(
 ["周次", "并行试点动作", "验收观察点"],
 [
  ["W7", "历史回放阶段结论固化；AI 建议版与人工计划双轨运行", "每条建议可解释（约束/让步可视化）"],
  ["W8", "接入物料就绪预测与插单统一入口，替换微信群补丁", "插单 100% 留痕、版本唯一"],
  ["W9", "IoT 换型采集 + 等料预警上线；AI-VI 首检试运行", "换型 100% 入表；首检不覆盖原记录"],
  ["W10", "全模块并行 + 周复盘；准交率/首检率统计", "准交率≥92%、首检≥98%、返工率不升"],
 ],
 widths=[1.6, 8.0, 6.0], aligns=['center','left','left'], size=9.0
)

add_h("5.4 组织与角色分工（RACI）", 2)
add_p("R=负责执行  A=最终担责  C=被咨询  I=被知会")
add_table(
 ["工作流", "顾明岚(厂长)", "唐映秋(计划)", "林亦舟(班组)", "傅景(质量)", "秦芮(MES)", "叶书(销售)"],
 [
  ["立项与范围", "A/R", "C", "C", "C", "C", "I"],
  ["日计划/插单", "I", "A/R", "C", "C", "C", "I"],
  ["现场执行/换型", "I", "C", "A/R", "I", "C", "I"],
  ["数据/映射", "I", "C", "C", "C", "A/R", "I"],
  ["质量签核", "I", "C", "I", "A/R", "C", "I"],
  ["交期验收/复盘", "A", "C", "I", "C", "C", "R"],
 ],
 widths=[3.0, 2.2, 2.2, 2.2, 2.0, 2.0, 2.0], aligns=['left']+['center']*6, size=9.0
)

add_h("5.5 关键里程碑与时间表", 2)
add_bullet("M1（W2 末）：数据基线报告与映射表原型通过——准入门槛。")
add_bullet("M2（W4 末）：唯一版本日计划 + 经营驾驶舱可用。")
add_bullet("M3（W6 末）：9 模块 MVP 完成，人工复核关卡到位。")
add_bullet("M4（W10 末）：CNC 三号线 4 周并行结束，硬指标验收。")
add_bullet("M5（W11+）：验收报告签字，推广路线图与预算确认。")
doc.add_page_break()

# ================= 6 推演模拟 =================
add_h("6  推演模拟（核心）", 1)
add_p("以下为基于现状基线与行业经验的情景推演，用于辅助立项决策。标注“模拟口径，待试点实测确认”，与寻访报告“待验证假设”一致。", color=ORANGE, size=9.5)

add_h("6.1 推演假设与基线", 2)
add_table(
 ["参数", "基线值(现状)", "推演设定(To-Be 试点)", "假设说明"],
 [
  ["CNC 三号线日有效工时", "约 7.5h(450min)", "约 7.8h(470min)", "等料回收 25min/天"],
  ["等料停机", "40 min/天", "≤15 min/天", "等料预警+动态重排(模拟)"],
  ["换型记录完整度", "0%", "100%", "IoT 自动采集"],
  ["日计划版本数", "≥2(群聊多版)", "1(唯一版本)", "插单统一入口"],
  ["准交率", "78%", "92%", "目标值，需实测"],
  ["首检合格率", "—", "≥98%", "验收门槛"],
 ],
 widths=[3.6, 3.4, 3.6, 4.0], aligns=['left','center','center','left'], size=9.0
)

add_h("6.2 场景一：缺料 + 插单日的流程推演", 2)
add_p("【现状】周二下午 14:00 收到关键客户插单；计划员在微信群发“红色=已催两次”；物料系统显示某单料未齐，但该单已被排入当日计划。班组长开工后发现料未到，跳过做别的产品，顺序打乱；首检未通过靠群聊补录。结果：当日 2 单延误，准交率受损，责任版本说不清。")
add_p("【To-Be】下午插单进入统一入口并自动留痕；物料就绪预测在排产前标红缺料单、不排入当日计划；唯一版本日计划同步至班组终端；首检由 AI-VI 自动判定，未通过即时停线并关联原记录；经营驾驶舱实时显示该插单对关键客户交期的影响。结果：插单 0 版本冲突，缺料单自动顺延，准交可解释。", color=BLUE)
add_table(
 ["环节", "现状处理", "To-Be 处理", "差异"],
 [
  ["插单", "微信群口头，版本漂移", "统一入口+留痕", "版本唯一"],
  ["缺料单", "仍排入当日计划", "预测标红、自动顺延", "避免无效开工"],
  ["首检", "群聊补录、非结构化", "AI-VI 自动判定+原记录关联", "可追溯、不覆盖"],
  ["责任", "说不清哪一版", "版本号+签核人可重建", "审计闭环"],
 ],
 widths=[2.2, 4.6, 4.6, 3.0], aligns=['left','left','left','center'], size=9.0
)

add_h("6.3 场景二：换型与等料停机的流程推演", 2)
add_p("【现状】三号线日均停机 70 分钟，其中 40 分钟等料；换型 45 分钟从未进计划表，排出来的计划“看着满、实际一换型就压”。计划员反复手工核对物料与换型窗口。")
add_p("【To-Be】IoT 采集换型信号并自动入表；物料就绪预测驱动等料预警，触发动态重排把等料窗口让给可开工订单；经营驾驶舱显示换型/等料占用比。模拟结果：等料停机 40→15min（回收 25min/天≈2.1h/周有效产能），换型冲突下降约 30%。", color=BLUE)

add_h("6.4 试点前后关键指标预测", 2)
add_table(
 ["指标", "现状基线", "4 周试点预期", "提升", "可信度"],
 [
  ["准时交付率", "78%", "88%~92%", "+10~14pp", "中（需实测）"],
  ["等料停机", "40 min/天", "≤15 min/天", "-62%", "中"],
  ["换型入表", "0%", "100%", "—", "高"],
  ["首检合格率", "暂无基线（待实测）", "≥98%", "验收门槛", "高(硬约束)"],
  ["返工率", "基线", "不上升", "底线", "高(硬约束)"],
  ["计划版本冲突", "频繁", "0", "消除", "高"],
 ],
 widths=[3.0, 2.6, 3.2, 2.4, 3.0], aligns=['left','center','center','center','center'], size=9.0
)

add_h("6.5 投资回报（ROI）模拟", 2)
add_p("试点投入已锁定为 24 万元（含税，见报价单）；以下节省额为“模拟口径，待试点实测确认”，且按寻访报告要求“既有系统采购不纳入节省额、节省额只算可验证部分”。")
add_table(
 ["节省项", "计算口径（模拟）", "试点 4 周估算", "单厂年化估算"],
 [
  ["等料产能回收", "25min/天×5天×约 4 周 × 工时价值", "1.5~3 万", "20~40 万"],
  ["延误罚/加急费减少", "准交 +10~14pp 对应关键客户加急费下降", "2~4 万", "25~50 万"],
  ["首检/返工质量损失下降", "首检≥98% 带来的返工下降", "1~2 万", "10~25 万"],
  ["计划员工时释放", "版本统一+插单留痕减少手工核对", "1~1.5 万", "10~20 万"],
  ["合计（可验证部分）", "—", "5.5~10.5 万", "65~135 万"],
 ],
 widths=[3.4, 5.6, 3.0, 3.0], aligns=['left','left','center','center'], size=9.0
)
add_p("模拟结论：单厂推广总投入约 120–180 万元（见报价单第八章），按上述年化可验证节省测算，投资回收期约 12–18 个月；试点期 24 万投入本身以“打通数据链、验证指标”为主，不追求试点期即回本。", color=NAVY)
doc.add_page_break()

# ================= 7 预算 =================
add_h("7  预算与资源保障（摘要）", 1)
add_p("详细报价见《AI 数智化交付流程项目 · 报价单》。试点含税包干 24 万元，结构如下：")
add_table(
 ["类别", "内容", "占比(示意)", "备注"],
 [
  ["软件/平台", "排产引擎、驾驶舱、数据治理、AI-VI 授权", "约 45%", "试点期授权"],
  ["基础设施", "接口开发(ERP/MES只读)、边缘采集、服务器", "约 20%", "不含既有系统采购"],
  ["实施集成", "部署、映射、建模、培训、复核", "约 25%", "含接口/培训/复核/维护(F03)"],
  ["运维质保", "试点期运维与质保", "约 10%", "质保金 5% 单列"],
 ],
 widths=[2.6, 6.4, 2.4, 3.6], aligns=['left','left','center','left'], size=9.0
)
add_p("付款：30% 预付款 / 40% 中期 / 25% 验收 / 5% 质保。后续单厂推广 120–180 万、多基地 300–600 万（参考估算，非签约范围）。")

# ================= 8 风险 =================
add_h("8  风险管控与兜底设计", 1)
add_table(
 ["风险", "来源", "兜底/应对"],
 [
  ["插单/缺料/换型/首检未通过自动建议失控", "F44", "停止自动建议，标明原因+接手人+确认时间；保留人工流程"],
  ["接口失败", "F35", "继续原人工流程，保留只读快照与时间戳，恢复后按业务编号去重补齐"],
  ["质量红线被突破", "F41/F42", "质量签核一票否决；首检<98% 即叫停；客户图纸不进外部模型"],
  ["原记录被覆盖", "F15", "未确认结果不得覆盖原记录；复核可点回原记录"],
  ["指标口径不一致", "F53", "业务负责人书面固定准交率/首检分母、周期、排除规则后再验收"],
  ["责任边界模糊", "F23/F25", "交接带版本号与未解决事项；接手人确认才算责任转移"],
 ],
 widths=[4.4, 2.2, 8.4], aligns=['left','center','left'], size=9.0
)

# ================= 9 验收 =================
add_h("9  验收标准与口径", 1)
add_bullet("硬指标①：CNC 三号线试运行 4 周，准时交付率 ≥ 92%（基线口径需业务负责人书面固定，F53）。", color=NAVY)
add_bullet("硬指标②：首检合格率 ≥ 98%，且试点期间返工率不得上升（F02/F42）。", color=NAVY)
add_bullet("过程项：订单-工单映射完整、换型 100% 入表、插单 100% 留痕、AI 建议可解释、原记录不被覆盖。", color=NAVY)
add_bullet("口径前置：准交率/首检率的分母、统计周期、排除规则须由业务负责人在验收前书面固定，不能用消息量代替完成量（F53）。", color=ORANGE)
add_bullet("验收组织：厂长牵头，质量主管有否决权，销售交付经理参与交接结果验收（F04）。", color=NAVY)

# ================= 附录 =================
add_h("附录 A  术语表与依据编号", 1)
add_table(
 ["术语/编号", "含义"],
 [
  ["F00~F55", "寻访报告一线访谈事实编号（见 discovery-report.md）"],
  ["REQ-1~6", "六大候选需求（痛点），P0/P1 为优先级"],
  ["To-Be", "目标态（Target State），即数智化后的流程"],
  ["AI-VI", "机器视觉首检（AI Visual Inspection）"],
  ["唯一版本日计划", "替代微信群多版本，系统唯一且留痕的日计划"],
  ["人工复核关卡", "AI 只出建议、人工确认才生效的卡点（日计划生效、质量签核）"],
  ["读写接口边界", "MES 可读工单/状态，PLC 不在接口范围、禁自动下发动作(F32)"],
 ],
 widths=[3.6, 11.4], aligns=['left','left'], size=9.5
)
hr()
add_p("编制说明：本方案整合自《2026 制造行业现状报告》《星衡精密业务需求发现报告》《业务现状/数智化流程图》《AI 数智化报价单》。推演模拟章节用于辅助决策，所有量化目标与节省额均标注为模拟口径，最终以试点实测与业务负责人书面固定口径为准。", size=9.5, color=GREY)

add_footer()
doc.save(OUT)
print("SAVED:", OUT, os.path.getsize(OUT), "bytes")
