# -*- coding: utf-8 -*-
"""生成《星衡精密 AI数智化交付流程项目 报价单》docx"""
from docx import Document
from docx.shared import Pt, RGBColor, Cm, Emu
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_ALIGN_VERTICAL
from docx.enum.section import WD_SECTION
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
import os

OUT = r"C:\Users\24230\Desktop\work\星衡精密-AI数智化交付流程项目-报价单.docx"
FLOW = r"C:\Users\24230\Desktop\work\加入数智的后流程图.jpg"

# ---------- 基础样式 ----------
doc = Document()

# 页面 A4 窄边距
sec = doc.sections[0]
sec.top_margin = Cm(1.8); sec.bottom_margin = Cm(1.8)
sec.left_margin = Cm(2.0); sec.right_margin = Cm(2.0)

# 正文字体（中英文字体分别设置，避免出现方块）
def set_font(run, name="宋体", size=10.5, bold=False, color=None):
    run.font.name = name
    run.font.size = Pt(size)
    run.font.bold = bold
    if color is not None:
        run.font.color.rgb = color
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn('w:rFonts'))
    if rFonts is None:
        rFonts = OxmlElement('w:rFonts'); rPr.append(rFonts)
    rFonts.set(qn('w:eastAsia'), name)
    rFonts.set(qn('w:ascii'), name)
    rFonts.set(qn('w:hAnsi'), name)

# 默认正文样式
normal = doc.styles['Normal']
normal.font.name = '宋体'
normal.font.size = Pt(10.5)
normal._element.get_or_add_rPr().get_or_add_rFonts().set(qn('w:eastAsia'), '宋体')

C_BRAND = RGBColor(0x1F, 0x4E, 0x79)   # 深蓝
C_ACCENT = RGBColor(0xC0, 0x50, 0x1B)  # 橙红（痛点/强调）
C_GREY = RGBColor(0x59, 0x59, 0x59)

# 颜色填充辅助
def shade_cell(cell, hexcolor):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear'); shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hexcolor)
    tcPr.append(shd)

def set_cell_text(cell, text, bold=False, size=10, color=None, align='left', name='宋体'):
    cell.text = ''
    p = cell.paragraphs[0]
    p.alignment = {'left':WD_ALIGN_PARAGRAPH.LEFT,'center':WD_ALIGN_PARAGRAPH.CENTER,'right':WD_ALIGN_PARAGRAPH.RIGHT}[align]
    p.paragraph_format.space_after = Pt(1); p.paragraph_format.space_before = Pt(1)
    lines = text.split('\n')
    for i, ln in enumerate(lines):
        if i>0:
            run = p.add_run(); run.add_break()
        run = p.add_run(ln)
        set_font(run, name=name, size=size, bold=bold, color=color)
    cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER

def set_borders(table, color="1F4E79", sz=6):
    tbl = table._tbl
    tblPr = tbl.tblPr
    borders = OxmlElement('w:tblBorders')
    for edge in ('top','left','bottom','right','insideH','insideV'):
        e = OxmlElement(f'w:{edge}')
        e.set(qn('w:val'),'single'); e.set(qn('w:sz'),str(sz))
        e.set(qn('w:space'),'0'); e.set(qn('w:color'),color)
        borders.append(e)
    tblPr.append(borders)

# ---------- 标题区 ----------
t = doc.add_paragraph(); t.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = t.add_run("星衡精密 · AI 数智化交付流程项目")
set_font(r, name="微软雅黑", size=19, bold=True, color=C_BRAND)
t.paragraph_format.space_after = Pt(0)

t2 = doc.add_paragraph(); t2.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = t2.add_run("报 价 单")
set_font(r, name="微软雅黑", size=15, bold=True, color=C_BRAND)
t2.paragraph_format.space_after = Pt(2)

t3 = doc.add_paragraph(); t3.alignment = WD_ALIGN_PARAGRAPH.CENTER
r = t3.add_run("（试点验证阶段 · CNC 三号线标准工单 · 4 周）")
set_font(r, name="宋体", size=10, color=C_GREY)
t3.paragraph_format.space_after = Pt(6)

# 编号信息条
info = doc.add_table(rows=2, cols=4)
info.alignment = WD_TABLE_ALIGNMENT.CENTER
set_borders(info, sz=4)
info_data = [
    ("报价单编号", "XH-AI-2026-001"),
    ("报价日期", "2026-10-23"),
    ("版本", "V1.0"),
    ("有效期", "自发出之日起 30 天"),
]
for i,(k,v) in enumerate(info_data):
    set_cell_text(info.rows[0].cells[i], k, bold=True, size=9, color=RGBColor(0xFF,0xFF,0xFF), align='center')
    shade_cell(info.rows[0].cells[i], "1F4E79")
    set_cell_text(info.rows[1].cells[i], v, size=10, align='center')
info.columns[0].width = Cm(3.2); info.columns[1].width = Cm(4.0)
info.columns[2].width = Cm(2.2); info.columns[3].width = Cm(5.0)
doc.add_paragraph()

# 双方信息
def h1(text):
    p = doc.add_paragraph()
    set_font(p.add_run(text), name="微软雅黑", size=12.5, bold=True, color=C_BRAND)
    # 下边框
    pPr = p._p.get_or_add_pPr(); pbdr = OxmlElement('w:pBdr')
    bottom = OxmlElement('w:bottom')
    bottom.set(qn('w:val'),'single'); bottom.set(qn('w:sz'),'6')
    bottom.set(qn('w:space'),'4'); bottom.set(qn('w:color'),'1F4E79')
    pbdr.append(bottom); pPr.append(pbdr)
    p.paragraph_format.space_before = Pt(8); p.paragraph_format.space_after = Pt(4)

def body(text, size=10.5, color=None, bold=False, space=3, align='left'):
    p = doc.add_paragraph()
    p.alignment = {'left':WD_ALIGN_PARAGRAPH.LEFT,'center':WD_ALIGN_PARAGRAPH.CENTER,'right':WD_ALIGN_PARAGRAPH.RIGHT}[align]
    set_font(p.add_run(text), size=size, color=color, bold=bold)
    p.paragraph_format.space_after = Pt(space); p.paragraph_format.line_spacing = 1.18
    return p

def bullet(text, size=10.5):
    p = doc.add_paragraph(style='List Bullet')
    set_font(p.add_run(text), size=size)
    p.paragraph_format.space_after = Pt(2); p.paragraph_format.line_spacing = 1.15
    return p

# 一、项目背景与痛点
h1("一、项目背景与痛点")
body("行业背景：据 2026 年制造业公开数据，中国已建成卓越级智能工厂 500 家、累计 5.6 万基础级智能工厂，"
     "工业互联网覆盖 41 个工业大类；AI 重点场景普及率达 34.2%，10.6% 的规上企业已普及大模型，"
     "灯塔工厂全球 238 家中中国占 103 家。在“智改数转网联”主线下，交付可视化、排产可解释、质量可签核已成为离散制造数智化的共性刚需。", size=10)

body("星衡精密现状（来源：车间寻访与六角色访谈，编号 F** 为访谈事实编号）：", bold=True, space=2)
bullet("F00／F01 准交率仅 78%（目标 92%）；计划每天上午出一次、下午插单靠微信群，最终执行版本经常不一致，调度会拿不出唯一版本对客解释交期。")
bullet("F51／F12 延误订单 60% 来自缺料；CNC 三号线日均停机 70 分钟，其中 40 分钟为等料，原常被误计为设备故障。")
bullet("F10／F11 换型平均 45 分钟且计划表从未记录；缺料订单仍被排入当日计划；设备报警恢复时间不确定却继续向后压单。")
bullet("F30／F31／F33 订单号（ERP）与工单号（MES）无稳定关联表；故障记录漏填、换型事件从未采集，数据基线缺失。")
bullet("F15／F44 插单／缺料／换型／首检未通过，常在群聊或个人表补录，关键原因未做成结构化字段随交接流转；质量主管要求上线须签核、首检合格率≥98%。")
bullet("F50／F53 客户盯承诺日期、厂长盯利用率，冲突须评审会定；准交率 92%、首检 98% 的口径尚待业务负责人书面固定。")

body("建设目标：以“先补齐信号与数据、再谈 AI 排产建议”为序，将准交率从 78% 提升至 92%、首检合格率保持 ≥98%、"
     "返工率不上升；AI 仅出可解释建议、人工复核关卡强制卡点，不覆盖原记录。", bold=True, color=C_ACCENT, space=4)

# 二、解决方案范围
h1("二、解决方案范围（对应痛点与角色）")
body("在既有 ERP／MES 之上叠加“数智化交付中台”，按五条泳道职责嵌入 AI 能力，保留人工复核关卡，逐项消除上述痛点。", space=4)

sol = [
    ("1","订单-工单映射与数据治理","构建订单↔工单稳定关联表，补齐换型/故障数据基线，主编号/时间/来源/版本四要素校验，缺字段进人工修复队列（不猜值）","REQ-3 数据前置","秦芮"),
    ("2","物料就绪预测","库存+在途融合，缺料订单自动标红、不排入当日计划，从源头消除“缺料仍排产”","REQ-1 缺料","唐映秋／林亦舟"),
    ("3","智能排产引擎 + 插单统一入口","约束求解生成“建议版”日计划，唯一版本留痕、插单线上化、优先级规则可视化","REQ-2 版本统一","唐映秋"),
    ("4","IoT 换型信号自动采集","工业网关+工位终端读取 PLC 信号，换型时长自动入表，消除“45 分钟不记录”","REQ-1 换型","林亦舟"),
    ("5","等料预警·动态重排","停机超阈自动预警并触发动态重排，减少三号线等料 40 分钟/天","REQ-1 等料","林亦舟"),
    ("6","机器视觉首检（AI-VI）","工业相机采集首件，异常自动停线，结果仅展示、不覆盖原记录","质量风险","傅景"),
    ("7","经营驾驶舱 / BI 看板","准交率、利用率、等料/换型热力实时看板，厂长与销售可见可解释","管理可视","顾明岚"),
    ("8","AI 复盘助手","周复盘自动归因误判与未解决项，指标口径自动固化（准交 92%／首检 98%）","REQ-6 口径","叶书"),
    ("9","质量签核关卡（人工复核）","日计划生效、质量签核两处强制人工确认；插单/缺料/换型/首检未过/接口失败自动转人工兜底","REQ-4/5 兜底","傅景"),
]
tbl = doc.add_table(rows=1, cols=5)
tbl.alignment = WD_TABLE_ALIGNMENT.CENTER
set_borders(tbl)
hdr = ["#","能力模块","核心功能","对应痛点","主责角色"]
for i,h in enumerate(hdr):
    set_cell_text(tbl.rows[0].cells[i], h, bold=True, size=9.5, color=RGBColor(0xFF,0xFF,0xFF), align='center')
    shade_cell(tbl.rows[0].cells[i], "1F4E79")
for row in sol:
    cells = tbl.add_row().cells
    for i,val in enumerate(row):
        set_cell_text(cells[i], val, size=9, align='center' if i in (0,3,4) else 'left')
widths = [0.8, 3.0, 7.4, 2.0, 2.0]
for i,w in enumerate(widths):
    for r_ in tbl.rows:
        r_.cells[i].width = Cm(w)
doc.add_paragraph()

# 三、报价明细
h1("三、报价明细（试点阶段 · 含税）")
body("计费口径参考工业互联网私有化部署“四层模型”：软件授权 / 基础设施 / 实施集成 / 运维培训；既有 ERP、MES 采购不纳入本报价。"
     "以下为 CNC 三号线标准工单 4 周试点全部费用，合计 ¥240,000（含硬件、软件、实施与试点期服务）。", size=9.5, space=4)

items = [
    ("1","数据治理与订单-工单映射","数据基线补齐、关联表原型、四要素校验、人工修复队列机制","项","1","40,000.00","40,000.00","秦芮接口对接"),
    ("2","物料就绪预测模块","库存/在途融合、缺料标红不排入、等料预警与动态重排","项","1","50,000.00","50,000.00","含 ERP/MES 接口"),
    ("3","智能排产引擎 + 插单统一入口","约束求解建议版、唯一日计划、插单留痕","项","1","60,000.00","60,000.00","仅建议·人工复核"),
    ("4","IoT 换型信号自动采集","工业网关+工位终端+PLC 采集，换型时长入表","套","1","30,000.00","30,000.00","含硬件网关"),
    ("5","机器视觉首检 AI-VI","工业相机 1 通道+光源+模型+异常停线","套","1","35,000.00","35,000.00","不覆盖原记录"),
    ("6","经营驾驶舱 / BI 看板","准交率/利用率实时看板（基础版）","项","1","10,000.00","10,000.00","厂长/销售可见"),
    ("7","培训与质量签核关卡配置","人工复核流程配置、操作与签核培训","项","1","10,000.00","10,000.00","傅景签核"),
    ("8","试点期维护与复核支持","4 周现场+远程支持、接口失败兜底与只读快照","项","1","5,000.00","5,000.00","含 90 天评价留存"),
]
dt = doc.add_table(rows=1, cols=8)
dt.alignment = WD_TABLE_ALIGNMENT.CENTER
set_borders(dt)
dh = ["序号","产品/服务名称","规格/服务内容","单位","数量","单价(元)","金额(元)","备注"]
for i,h in enumerate(dh):
    set_cell_text(dt.rows[0].cells[i], h, bold=True, size=9, color=RGBColor(0xFF,0xFF,0xFF), align='center')
    shade_cell(dt.rows[0].cells[i], "1F4E79")
total = 0.0
for it in items:
    cells = dt.add_row().cells
    amt = float(it[6].replace(',',''))
    total += amt
    for i,val in enumerate(it):
        align = 'center' if i in (0,3,4,5,6) else 'left'
        set_cell_text(cells[i], val, size=9, align=align)
dwidths = [1.0, 3.2, 4.6, 1.0, 1.0, 1.8, 1.8, 2.4]
for i,w in enumerate(dwidths):
    for r_ in dt.rows:
        r_.cells[i].width = Cm(w)
doc.add_paragraph()

# 四、费用汇总
h1("四、费用汇总")
tax_ex = total/1.06
tax = total - tax_ex
summ = doc.add_table(rows=5, cols=4)
set_borders(summ)
summ_data = [
    ("费用项目","金额(元)","说明","|"),
    ("报价明细合计（含税）", f"{total:,.2f}", "以上 8 项之和", ""),
    ("其中：不含税金额", f"{tax_ex:,.2f}", "税率 6%（现代服务业，以实际开票为准）", ""),
    ("增值税额", f"{tax:,.2f}", "试点预算 24 万元为含税包干", ""),
    ("优惠金额", "0.00", "批量/战略客户另行申请", ""),
]
# 重新构建汇总表（含合计行）
summ._tbl.remove(summ.rows[0]._tr)
rows_def = [
    ("报价明细合计（含税）", f"{total:,.2f}", "以上 8 项之和"),
    ("其中：不含税金额", f"{tax_ex:,.2f}", "税率 6%（现代服务业，以实际开票为准）"),
    ("增值税额", f"{tax:,.2f}", "试点预算 24 万元为含税包干"),
    ("优惠金额", "0.00", "战略客户另行申请"),
]
for i,(k,v,note) in enumerate(rows_def):
    cells = summ.add_row().cells if i>0 else summ.rows[0].cells
    set_cell_text(cells[0], k, bold=(i==0), size=10)
    set_cell_text(cells[1], v, bold=(i==0), size=10, align='right', color=C_ACCENT if i==0 else None)
    set_cell_text(cells[2], note, size=9, color=C_GREY)
# 合计行
tcells = summ.add_row().cells
set_cell_text(tcells[0], "最终应付金额（含税）", bold=True, size=10.5, color=RGBColor(0xFF,0xFF,0xFF))
shade_cell(tcells[0], "C0501B")
set_cell_text(tcells[1], f"{total:,.2f}", bold=True, size=11, align='right', color=RGBColor(0xFF,0xFF,0xFF))
shade_cell(tcells[1], "C0501B")
set_cell_text(tcells[2], "大写：人民币贰拾肆万圆整", bold=True, size=9.5, color=RGBColor(0xFF,0xFF,0xFF))
shade_cell(tcells[2], "C0501B")
summ.columns[0].width = Cm(5.5); summ.columns[1].width = Cm(3.5); summ.columns[2].width = Cm(6.5)
doc.add_paragraph()
body("说明：本报价为 CNC 三号线试点阶段含税包干价，已包含接口、培训、复核与维护四项；不含既有 ERP/MES 采购、"
     "新增网络改造及试点范围外的产线复制费用。最终金额以需求调研确认后的正式合同为准。", size=9, color=C_GREY, space=4)

# 五、付款方式
h1("五、付款方式")
pay = doc.add_table(rows=1, cols=4)
set_borders(pay)
for i,h in enumerate(["阶段","比例","金额(元)","触发条件"]):
    set_cell_text(pay.rows[0].cells[i], h, bold=True, size=9.5, color=RGBColor(0xFF,0xFF,0xFF), align='center')
    shade_cell(pay.rows[0].cells[i], "1F4E79")
pay_rows = [
    ("1 预付款","30%","72,000.00","合同签订后 3 个工作日内"),
    ("2 中期款","40%","96,000.00","数据基线完成、系统上线试运行"),
    ("3 验收款","25%","60,000.00","4 周试点验收合格（准交↑、返工不↑）"),
    ("4 质保款","5%","12,000.00","质保期满无质量问题"),
]
for r_ in pay_rows:
    cells = pay.add_row().cells
    for i,v in enumerate(r_):
        set_cell_text(cells[i], v, size=9.5, align='center' if i<3 else 'left')
pay.columns[0].width = Cm(3.2); pay.columns[1].width = Cm(2.0); pay.columns[2].width = Cm(3.3); pay.columns[3].width = Cm(6.5)
doc.add_paragraph()

# 六、实施周期与里程碑
h1("六、实施周期与里程碑（约 8–10 周）")
ms = doc.add_table(rows=1, cols=3)
set_borders(ms)
for i,h in enumerate(["阶段","周期","交付物/验收点"]):
    set_cell_text(ms.rows[0].cells[i], h, bold=True, size=9.5, color=RGBColor(0xFF,0xFF,0xFF), align='center')
    shade_cell(ms.rows[0].cells[i], "1F4E79")
ms_rows = [
    ("需求确认与数据基线","第 1–2 周","映射表原型、换型/故障数据基线报告（秦芮）"),
    ("模块部署与系统集成","第 3–4 周","排产引擎、物料就绪、IoT 采集、AI-VI 上线联调"),
    ("CNC 三号线并行试点","第 5–8 周","与现有人工流程并行 4 周，逐单比对差异"),
    ("验收与复盘","第 9–10 周","准交率↑且返工率不↑、首检≥98%；规则复测后更新"),
]
for r_ in ms_rows:
    cells = ms.add_row().cells
    for i,v in enumerate(r_):
        set_cell_text(cells[i], v, size=9.5, align='center' if i==1 else 'left')
ms.columns[0].width = Cm(4.0); ms.columns[1].width = Cm(2.6); ms.columns[2].width = Cm(8.4)
doc.add_paragraph()

# 七、服务条款
h1("七、服务条款")
bullet("质量标准：交付系统须支撑“准交率 92%、首检合格率 ≥98%、返工率不上升”的验收硬指标；AI 仅出可解释建议，不自动下发动作至 PLC。")
bullet("售后服务：试点期含 4 周现场+远程支持；质保期 1 年免费维保，7×24 小时响应，关键故障 48 小时到场。")
bullet("知识产权：报价方自有软件/模型知识产权归报价方，客户在合同范围内享有使用权；客户业务数据归客户所有，模型训练仅使用脱敏数据。")
bullet("保密与合规：客户图纸、工艺参数仅向授权班组开放，不进入外部模型；审核日志保留映射/物料/换型/首检的版本、建议、人工修正与签核人，可重建当次处理。")
bullet("违约责任：逾期交付按日万分之五支付违约金；客户逾期付款按日万分之三支付滞纳金。")
bullet("其他：本报价单自发出日起 30 天内有效；解释权归报价方，未尽事宜双方友好协商。")

# 八、后续推广投资估算
h1("八、后续推广投资估算（参考 · 非本次签约范围）")
body("以下为单厂全产线推广与多基地复制的参考区间，供立项决策，不在本报价约束内。", size=9.5, space=3)
est = doc.add_table(rows=1, cols=4)
set_borders(est)
for i,h in enumerate(["推广阶段","范围","投资区间(万元)","说明"]):
    set_cell_text(est.rows[0].cells[i], h, bold=True, size=9.5, color=RGBColor(0xFF,0xFF,0xFF), align='center')
    shade_cell(est.rows[0].cells[i], "1F4E79")
est_rows = [
    ("阶段二 · 单厂推广","全产线/全车间复制","120 – 180","平台 License 扩容+多线采集+模型复用，约试点 5–7 倍"),
    ("阶段三 · 多基地复制","2–5 个基地","300 – 600","标准化平台跨基地部署，单点成本下降 20–30%"),
    ("年度运维(推广后)","平台+模型+支持","15 – 40 /年","含维保、版本升级与模型迭代"),
]
for r_ in est_rows:
    cells = est.add_row().cells
    for i,v in enumerate(r_):
        set_cell_text(cells[i], v, size=9.5, align='center' if i==2 else 'left')
est.columns[0].width = Cm(3.6); est.columns[1].width = Cm(3.4); est.columns[2].width = Cm(3.0); est.columns[3].width = Cm(5.0)
doc.add_paragraph()

# 附录：方案流程图
doc.add_page_break()
h1("附录 · AI 数智化交付流程方案图（To-Be）")
body("下图为本项目目标态流程，标注 AI 能力节点、人工复核关卡与痛点消除关系，与正文第二、三节一一对应。", size=9.5, space=4)
if os.path.exists(FLOW):
    doc.add_picture(FLOW, width=Cm(16.5))
    last = doc.paragraphs[-1]; last.alignment = WD_ALIGN_PARAGRAPH.CENTER

# 签署区
doc.add_paragraph()
h1("九、签署确认")
sign = doc.add_table(rows=2, cols=2)
set_borders(sign, sz=4)
set_cell_text(sign.rows[0].cells[0], "报价方（供应商）", bold=True, size=10, align='center')
shade_cell(sign.rows[0].cells[0], "EAF1F8")
set_cell_text(sign.rows[0].cells[1], "客户方（星衡精密）", bold=True, size=10, align='center')
shade_cell(sign.rows[0].cells[1], "EAF1F8")
set_cell_text(sign.rows[1].cells[0], "名称：____________________\n授权代表：____________  日期：________\n（盖章）", size=9.5, align='left')
set_cell_text(sign.rows[1].cells[1], "名称：____________________\n授权代表：____________  日期：________\n（盖章）", size=9.5, align='left')
sign.columns[0].width = Cm(8.0); sign.columns[1].width = Cm(8.0)

# 页脚页眉
footer = sec.footer
fp = footer.paragraphs[0]; fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
set_font(fp.add_run("星衡精密 AI 数智化交付流程项目 · 报价单（机密） · 第 "), size=8, color=C_GREY)
# 页码域
fld1 = OxmlElement('w:fldSimple'); fld1.set(qn('w:instr'), 'PAGE')
fp._p.append(fld1)
set_font(fp.add_run(" 页 / 共 "), size=8, color=C_GREY)
fld2 = OxmlElement('w:fldSimple'); fld2.set(qn('w:instr'), 'NUMPAGES')
fp._p.append(fld2)
set_font(fp.add_run(" 页"), size=8, color=C_GREY)

doc.save(OUT)
print("SAVED:", OUT)
print("Total amount CNY:", total)
print("Tax-ex:", round(tax_ex,2), "Tax:", round(tax,2))
