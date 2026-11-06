# -*- coding: utf-8 -*-
"""纯文字版《星衡精密 AI 数智化交付流程项目 · 计划方案（含推演模拟）》DOCX。
与原表版相比：取消全部 14 张表格，改为分条/定义列表/对比式文字，保留两张流程图。
整合：制造业现状报告、寻访报告(35事实/6痛点)、现状泳道图、数智化To-Be图、24万试点报价单。"""
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
import os

BASE = r"C:\Users\24230\Desktop\work"
OUT = os.path.join(BASE, "星衡精密-AI数智化交付流程项目-计划方案-文字版.docx")
IMG_CURRENT = os.path.join(BASE, "业务现状流程图2.jpg")
IMG_TOBE = os.path.join(BASE, "加入数智的后流程图.jpg")

doc = Document()

# ---------- 全局字体（宋体 / 小四 10.5pt）----------
def set_cn_font(run, name="宋体", size=None, bold=None, color=None, italic=False):
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
    run.font.italic = italic

normal = doc.styles['Normal']
normal.font.name = '宋体'
normal.font.size = Pt(10.5)
set_cn_font(normal)
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
        set_cn_font(r, size=size, bold=bold, color=color, italic=italic)
    return p

def add_bullet(text, size=10.5, color=None, lead=None, lead_color=None):
    p = doc.add_paragraph(style='List Bullet')
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.line_spacing = 1.2
    if lead:
        rl = p.add_run(lead)
        set_cn_font(rl, size=size, bold=True, color=(lead_color or NAVY))
        r = p.add_run(text)
        set_cn_font(r, size=size, color=color)
    else:
        r = p.add_run(text)
        set_cn_font(r, size=size, color=color)
    return p

def hr():
    p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(2); p.paragraph_format.space_after = Pt(6)
    pPr = p._p.get_or_add_pPr(); pbdr = qn and __import__('docx.oxml').oxml.OxmlElement('w:pBdr')
    from docx.oxml import OxmlElement
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'),'single'); bottom.set(qn('w:sz'),'6'); bottom.set(qn('w:space'),'1'); bottom.set(qn('w:color'),'1F3864')
    pbdr.append(bottom); pPr.append(pbdr)

def add_footer():
    for section in doc.sections:
        footer = section.footer
        p = footer.paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run("星衡精密 · AI 数智化交付流程项目 · 计划方案（含推演模拟）   第 ")
        set_cn_font(run, size=8, color=GREY)
        fld1 = __import__('docx.oxml').oxml.OxmlElement('w:fldSimple'); fld1.set(qn('w:instr'), 'PAGE')
        run2 = p.add_run(); run2._element.addnext(fld1)
        run3 = p.add_run(" 页 / 共 "); set_cn_font(run3, size=8, color=GREY)
        fld2 = __import__('docx.oxml').oxml.OxmlElement('w:fldSimple'); fld2.set(qn('w:instr'), 'NUMPAGES')
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
add_p("下方按维度列出企业现状基线，每条均标注访谈事实编号：", size=10.5)
add_bullet("准时交付率：78%；目标 92%（F00）", )
add_bullet("延误主因：延误订单中约 60% 来自缺料，而非排产算法（F51）")
add_bullet("等料停机：CNC 三号线日均停机 70 分钟，其中约 40 分钟为等料（F12）")
add_bullet("换型记录：换型平均 45 分钟，计划表从未记录（F10）")
add_bullet("插单方式：每天上午出一次计划，下午插单靠微信群，执行版本常不一致（F01）")
add_bullet("首检管理：首检未通过靠群聊/个人表补录，关键原因非结构化（F14/F15）")
add_bullet("数据前置：ERP 订单号与 MES 工单号无稳定关联表，换型事件从未采集（F30/F31）")
add_bullet("试点边界：首期仅 CNC 三号线标准工单；先历史回放、再并行 4 周试点（F02/F05）")
add_bullet("预算：合成试点预算 24 万元（含税，含接口/培训/复核/维护）（F03）")

add_h("2.3 立项依据：四来源收敛摘要", 2)
add_p("寻访报告采用 Buyer / Brief / Operator / Industry 四来源收敛法，结论指向同一瓶颈：")
add_bullet("Buyer（厂长 顾明岚）：目标是把准交率从 78% 提到 92%、优先保关键客户交期；AI 只提可解释建议，不得直接下发；立项厂长牵头，质量有否决权，销售参与验收（F00/F02/F04）。")
add_bullet("Operator（班组长 林亦舟）：最耗时的不是设备，是换型与等料；缺料订单仍被排入当日计划，关键原因未结构化交接（F10/F11/F12/F14）。")
add_bullet("Brief（书面诉求）：订单越来越多、交期仍常延误，希望上 AI 自动排产提利用率——但四来源收敛显示，真实瓶颈在物料/换型信号缺失与版本不一致，直接追“满负荷”会与保交期冲突。")
add_bullet("Industry（行业可行性）：需先补订单-工单映射、物料就绪与换型信号，建立唯一日计划版本与人工复核关卡，再谈 AI 排产建议（与湘钢、上海电气、TCL 等标杆路径一致）。")

# ================= 3 现状诊断 =================
add_h("3  现状诊断（基于一线寻访）", 1)
add_h("3.1 六大痛点清单（REQ-1~6）", 2)
add_bullet("REQ-1［P0］交付瓶颈首先是物料与换型信号缺失，而非排产算法（关键依据 F51/F12/F10）")
add_bullet("REQ-2［P0］需要唯一日计划版本与插单留痕，替代微信群补丁（关键依据 F01/F20/F21）")
add_bullet("REQ-3［P0］订单与工单映射缺失，无法归因交期（数据前置）（关键依据 F30/F31/F33）")
add_bullet("REQ-4［P0］AI 只提建议、人工复核，不得覆盖原记录（关键依据 F22/F15/F42）")
add_bullet("REQ-5［P1］兜底转人工需明确接手人、时限与记录位置（关键依据 F44/F35/F25）")
add_bullet("REQ-6［P1］交期变更影响清单与准交率/首检口径需先固定（关键依据 F50/F52/F53）")
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
add_p("各项指标的目标设定均标明口径责任与事实来源：", size=10.5)
add_bullet("准时交付率：现状基线 78% → 试点目标 ≥92%（口径责任：业务负责人书面固定；来源 F00/F53）")
add_bullet("首检合格率：暂无基线（待实测）→ 试点目标 ≥98%（口径责任：质量主管签核门槛；来源 F42）")
add_bullet("返工率：基线值 → 试点目标 不上升（底线）（口径责任：验收硬指标；来源 F02）")
add_bullet("等料停机：现状 40 分钟/天 → 试点目标 ≤15 分钟/天（口径责任：班组/计划联动；来源 F12）")
add_bullet("换型透明：现状 0 记录 → 试点目标 100% 自动采集入表（口径责任：MES/PLC 接口；来源 F10/F31）")
add_bullet("计划版本：现状 微信群多版本 → 试点目标 唯一版本+留痕（口径责任：计划员维护；来源 F01/F20）")

add_h("4.2 九大 AI 数智能力模块与痛点映射", 2)
add_p("以下模块按承载泳道与消除痛点逐项列出，并标明关键约束与事实来源：", size=10.5)
add_bullet("① 订单 ↔ 工单自动映射与关联表［承载泳道：质量数据］——消除 REQ-3（无法归因交期）；关键约束：主编号/事件时间/来源/版本校验，缺字段进人工队列不猜值（F33）")
add_bullet("② 物料就绪预测（库存+在途融合）［承载泳道：计划］——消除 REQ-1（缺料仍排产）；关键约束：缺料自动标红不排入（F11）")
add_bullet("③ 智能排产引擎 + 插单统一入口［承载泳道：计划］——消除 REQ-2（微信群插单）；关键约束：AI 只出建议+唯一版本留痕，改交期需销售批准（F22）")
add_bullet("④ IoT 换型信号自动采集［承载泳道：班组］——消除 REQ-1（换型 45min 未记录）；关键约束：PLC/工位终端读状态，禁自动下发（F32）")
add_bullet("⑤ 等料预警 · 动态重排［承载泳道：班组］——消除 REQ-1（等料停机 40min）；关键约束：异常先由计划员核对（F15）")
add_bullet("⑥ 机器视觉首检（AI-VI）［承载泳道：班组/质量］——消除 REQ-4（群聊补录首检）；关键约束：未通过自动停线，不覆盖原记录（F15）")
add_bullet("⑦ 数据治理（15 分钟刷新+只读快照）［承载泳道：质量数据］——消除 REQ-3/REQ-5（数据缺口）；关键约束：过期标“待刷新”，失败保留只读快照（F34/F35）")
add_bullet("⑧ 经营驾驶舱（准交/利用率看板）［承载泳道：厂办］——消除 厂办看不见过程数据；关键约束：客户交期 vs 利用率冲突交评审会（F50）")
add_bullet("⑨ AI 复盘助手 + 指标口径固化［承载泳道：销售复盘］——消除 REQ-6（口径未固定）；关键约束：周复盘复测达标才更新规则（F55）")

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
add_bullet("P0 数据基线（W1–W2）：主要工作为订单-工单映射原型、字段校验、人工修复队列、换型/缺料信号采集方案；交付物为数据基线报告与映射表原型；对应 REQ-3。")
add_bullet("P1 平台部署（W3–W4）：主要工作为 MES/ERP 只读接口、经营驾驶舱、数据治理(15min 刷新)、统一日计划版本；交付物为集成环境与唯一版本日计划；对应 REQ-2/3。")
add_bullet("P2 智能模块（W5–W6）：主要工作为物料就绪预测、智能排产+插单入口、IoT 换型采集、等料预警、AI-VI 首检；交付物为 9 模块 MVP 与人工复核关卡；对应 REQ-1/4。")
add_bullet("P3 并行试点（W7–W10）：主要工作为 CNC 三号线 4 周并行、AI 建议 vs 人工计划逐单比对、周复盘；交付物为试点周报、差异清单、复盘记录；对应 REQ-4/5/6。")
add_bullet("P4 验收推广（W11+）：主要工作为硬指标验收、规则固化、推广路线图与预算；交付物为验收报告与推广方案；对应全部。")

add_h("5.3 试点方案：CNC 三号线 4 周并行", 2)
add_bullet("W7：并行试点动作为历史回放阶段结论固化、AI 建议版与人工计划双轨运行；验收观察点为每条建议可解释（约束/让步可视化）。")
add_bullet("W8：并行试点动作为接入物料就绪预测与插单统一入口、替换微信群补丁；验收观察点为插单 100% 留痕、版本唯一。")
add_bullet("W9：并行试点动作为 IoT 换型采集 + 等料预警上线、AI-VI 首检试运行；验收观察点为换型 100% 入表、首检不覆盖原记录。")
add_bullet("W10：并行试点动作为全模块并行 + 周复盘、准交率/首检率统计；验收观察点为准交率≥92%、首检≥98%、返工率不升。")

add_h("5.4 组织与角色分工（RACI）", 2)
add_p("图例：R = 负责执行；A = 最终担责；C = 被咨询；I = 被知会。", size=10)
add_bullet("立项与范围：顾明岚(厂长) A/R；唐映秋(计划) C；林亦舟(班组) C；傅景(质量) C；秦芮(MES) C；叶书(销售) I", size=9.5)
add_bullet("日计划/插单：顾明岚(厂长) I；唐映秋(计划) A/R；林亦舟(班组) C；傅景(质量) C；秦芮(MES) C；叶书(销售) I", size=9.5)
add_bullet("现场执行/换型：顾明岚(厂长) I；唐映秋(计划) C；林亦舟(班组) A/R；傅景(质量) I；秦芮(MES) C；叶书(销售) I", size=9.5)
add_bullet("数据/映射：顾明岚(厂长) I；唐映秋(计划) C；林亦舟(班组) C；傅景(质量) C；秦芮(MES) A/R；叶书(销售) I", size=9.5)
add_bullet("质量签核：顾明岚(厂长) I；唐映秋(计划) C；林亦舟(班组) I；傅景(质量) A/R；秦芮(MES) C；叶书(销售) I", size=9.5)
add_bullet("交期验收/复盘：顾明岚(厂长) A；唐映秋(计划) C；林亦舟(班组) I；傅景(质量) C；秦芮(MES) C；叶书(销售) R", size=9.5)

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
add_bullet("CNC 三号线日有效工时：基线约 7.5h(450min) → To-Be 约 7.8h(470min)（假设：等料回收 25min/天）。")
add_bullet("等料停机：基线 40 min/天 → To-Be ≤15 min/天（假设：等料预警+动态重排，模拟）。")
add_bullet("换型记录完整度：基线 0% → To-Be 100%（假设：IoT 自动采集）。")
add_bullet("日计划版本数：基线 ≥2(群聊多版) → To-Be 1(唯一版本)（假设：插单统一入口）。")
add_bullet("准交率：基线 78% → To-Be 92%（假设：目标值，需实测）。")
add_bullet("首检合格率：基线 —— → To-Be ≥98%（假设：验收门槛）。")

add_h("6.2 场景一：缺料 + 插单日的流程推演", 2)
add_p("【现状】周二下午 14:00 收到关键客户插单；计划员在微信群发“红色=已催两次”；物料系统显示某单料未齐，但该单已被排入当日计划。班组长开工后发现料未到，跳过做别的产品，顺序打乱；首检未通过靠群聊补录。结果：当日 2 单延误，准交率受损，责任版本说不清。")
add_p("【To-Be】下午插单进入统一入口并自动留痕；物料就绪预测在排产前标红缺料单、不排入当日计划；唯一版本日计划同步至班组终端；首检由 AI-VI 自动判定，未通过即时停线并关联原记录；经营驾驶舱实时显示该插单对关键客户交期的影响。结果：插单 0 版本冲突，缺料单自动顺延，准交可解释。", color=BLUE)
add_p("环节对比：", size=10.5, bold=True)
add_bullet("插单：现状——微信群口头，版本漂移｜ To-Be——统一入口+留痕（差异：版本唯一）。")
add_bullet("缺料单：现状——仍排入当日计划｜ To-Be——预测标红、自动顺延（差异：避免无效开工）。")
add_bullet("首检：现状——群聊补录、非结构化｜ To-Be——AI-VI 自动判定+原记录关联（差异：可追溯、不覆盖）。")
add_bullet("责任：现状——说不清哪一版｜ To-Be——版本号+签核人可重建（差异：审计闭环）。")

add_h("6.3 场景二：换型与等料停机的流程推演", 2)
add_p("【现状】三号线日均停机 70 分钟，其中 40 分钟等料；换型 45 分钟从未进计划表，排出来的计划“看着满、实际一换型就压”。计划员反复手工核对物料与换型窗口。")
add_p("【To-Be】IoT 采集换型信号并自动入表；物料就绪预测驱动等料预警，触发动态重排把等料窗口让给可开工订单；经营驾驶舱显示换型/等料占用比。模拟结果：等料停机 40→15min（回收 25min/天≈2.1h/周有效产能），换型冲突下降约 30%。", color=BLUE)

add_h("6.4 试点前后关键指标预测", 2)
add_bullet("准时交付率：现状 78% → 4 周预期 88%~92%（提升 +10~14pp；可信度：中，需实测）。")
add_bullet("等料停机：现状 40 min/天 → 4 周预期 ≤15 min/天（提升 -62%；可信度：中）。")
add_bullet("换型入表：现状 0% → 4 周预期 100%（提升 ——；可信度：高）。")
add_bullet("首检合格率：现状 暂无基线（待实测）→ 4 周预期 ≥98%（提升：验收门槛；可信度：高，硬约束）。")
add_bullet("返工率：现状 基线 → 4 周预期 不上升（提升：底线；可信度：高，硬约束）。")
add_bullet("计划版本冲突：现状 频繁 → 4 周预期 0（提升：消除；可信度：高）。")

add_h("6.5 投资回报（ROI）模拟", 2)
add_p("试点投入已锁定为 24 万元（含税，见报价单）；以下节省额为“模拟口径，待试点实测确认”，且按寻访报告要求“既有系统采购不纳入节省额、节省额只算可验证部分”。")
add_bullet("等料产能回收：计算口径（25min/天×5天×约 4 周 × 工时价值）→ 试点 4 周估算 1.5~3 万；单厂年化 20~40 万。")
add_bullet("延误罚/加急费减少：计算口径（准交 +10~14pp 对应关键客户加急费下降）→ 试点 4 周估算 2~4 万；单厂年化 25~50 万。")
add_bullet("首检/返工质量损失下降：计算口径（首检≥98% 带来的返工下降）→ 试点 4 周估算 1~2 万；单厂年化 10~25 万。")
add_bullet("计划员工时释放：计算口径（版本统一+插单留痕减少手工核对）→ 试点 4 周估算 1~1.5 万；单厂年化 10~20 万。")
add_bullet("合计（可验证部分）：试点 4 周估算 5.5~10.5 万；单厂年化 65~135 万。")
add_p("模拟结论：单厂推广总投入约 120–180 万元（见报价单第八章），按上述年化可验证节省测算，投资回收期约 12–18 个月；试点期 24 万投入本身以“打通数据链、验证指标”为主，不追求试点期即回本。", color=NAVY)
doc.add_page_break()

# ================= 7 预算 =================
add_h("7  预算与资源保障（摘要）", 1)
add_p("详细报价见《AI 数智化交付流程项目 · 报价单》。试点含税包干 24 万元，结构如下：")
add_bullet("软件/平台（约 45%）：排产引擎、驾驶舱、数据治理、AI-VI 授权（备注：试点期授权）。")
add_bullet("基础设施（约 20%）：接口开发(ERP/MES 只读)、边缘采集、服务器（备注：不含既有系统采购）。")
add_bullet("实施集成（约 25%）：部署、映射、建模、培训、复核（备注：含接口/培训/复核/维护 F03）。")
add_bullet("运维质保（约 10%）：试点期运维与质保（备注：质保金 5% 单列）。")
add_p("付款：30% 预付款 / 40% 中期 / 25% 验收 / 5% 质保。后续单厂推广 120–180 万、多基地 300–600 万（参考估算，非签约范围）。")

# ================= 8 风险 =================
add_h("8  风险管控与兜底设计", 1)
add_bullet("风险：插单/缺料/换型/首检未通过自动建议失控（来源 F44）——兜底/应对：停止自动建议，标明原因+接手人+确认时间；保留人工流程。")
add_bullet("风险：接口失败（来源 F35）——兜底/应对：继续原人工流程，保留只读快照与时间戳，恢复后按业务编号去重补齐。")
add_bullet("风险：质量红线被突破（来源 F41/F42）——兜底/应对：质量签核一票否决；首检<98% 即叫停；客户图纸不进外部模型。")
add_bullet("风险：原记录被覆盖（来源 F15）——兜底/应对：未确认结果不得覆盖原记录；复核可点回原记录。")
add_bullet("风险：指标口径不一致（来源 F53）——兜底/应对：业务负责人书面固定准交率/首检分母、周期、排除规则后再验收。")
add_bullet("风险：责任边界模糊（来源 F23/F25）——兜底/应对：交接带版本号与未解决事项；接手人确认才算责任转移。")

# ================= 9 验收 =================
add_h("9  验收标准与口径", 1)
add_bullet("硬指标①：CNC 三号线试运行 4 周，准时交付率 ≥ 92%（基线口径需业务负责人书面固定，F53）。", color=NAVY)
add_bullet("硬指标②：首检合格率 ≥ 98%，且试点期间返工率不得上升（F02/F42）。", color=NAVY)
add_bullet("过程项：订单-工单映射完整、换型 100% 入表、插单 100% 留痕、AI 建议可解释、原记录不被覆盖。", color=NAVY)
add_bullet("口径前置：准交率/首检率的分母、统计周期、排除规则须由业务负责人在验收前书面固定，不能用消息量代替完成量（F53）。", color=ORANGE)
add_bullet("验收组织：厂长牵头，质量主管有否决权，销售交付经理参与交接结果验收（F04）。", color=NAVY)

# ================= 附录 =================
add_h("附录 A  术语表与依据编号", 1)
add_bullet("F00~F55：寻访报告一线访谈事实编号（见 discovery-report.md）。")
add_bullet("REQ-1~6：六大候选需求（痛点），P0/P1 为优先级。")
add_bullet("To-Be：目标态（Target State），即数智化后的流程。")
add_bullet("AI-VI：机器视觉首检（AI Visual Inspection）。")
add_bullet("唯一版本日计划：替代微信群多版本，系统唯一且留痕的日计划。")
add_bullet("人工复核关卡：AI 只出建议、人工确认才生效的卡点（日计划生效、质量签核）。")
add_bullet("读写接口边界：MES 可读工单/状态，PLC 不在接口范围、禁自动下发动作（F32）。")
hr()
add_p("编制说明：本方案整合自《2026 制造行业现状报告》《星衡精密业务需求发现报告》《业务现状/数智化流程图》《AI 数智化报价单》。推演模拟章节用于辅助决策，所有量化目标与节省额均标注为模拟口径，最终以试点实测与业务负责人书面固定口径为准。", size=9.5, color=GREY)

add_footer()
doc.save(OUT)
print("SAVED:", OUT, os.path.getsize(OUT), "bytes")
