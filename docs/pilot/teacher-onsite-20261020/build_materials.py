"""生成教师现场试用资料。仅写入指定输出目录，不访问产品或保存凭据。"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

VERSION = "4b041cf4"
DATE = "2026-10-24"
BASE_CASE = """医生：今天哪里不舒服？
患者：我发热、咳嗽、咽痛两天了，最高体温38.2摄氏度。
医生：有没有胸痛？有没有药物过敏？
患者：没有胸痛，没有药物过敏史。
医生：这两天用过什么药？以前有没有慢性疾病？
患者：这两天没有服用药物。以前没有慢性疾病。
医生：这次做过检查吗？
患者：这次还没有做检查。"""
OPTIONAL_CASE = """医生：请问孩子哪里不舒服？
家属：我是孩子的妈妈。孩子六岁，从昨天开始发热、咳嗽，最高体温38.5摄氏度。
医生：孩子有没有药物过敏？
家属：孩子的药物过敏情况我不清楚。我自己有哮喘，孩子没有诊断过哮喘。
医生：孩子这次用过什么药，做过检查吗？
家属：用药和检查的情况我现在记不清楚，需要回去核实。"""
SINGLE_SCRIPT = "我发热、咳嗽、咽痛两天了，最高体温三十八点二摄氏度。没有胸痛，没有药物过敏史。这两天没有服用药物。以前没有慢性疾病。这次还没有做检查。"


def p(text): return {"kind": "p", "text": text}
def h(text): return {"kind": "h", "text": text}
def step(text): return {"kind": "step", "text": text}
def blank(text, lines=2): return {"kind": "blank", "text": text, "lines": lines}
def script(text, ident): return {"kind": "script", "text": text, "id": ident}


DOCS = {
 "guide": {"title": "MediListen 教师现场操作指南", "subtitle": "先走通一个新病例，再评价使用体验", "pages": [
 [h("第一步 进入工作台并建立新就诊"),
  p("本指南用于在演示电脑上独立操作。请使用组织者提供的医生账号和本包合成病例；无需安装程序、操作数据库或输入命令。第一次建议先做文本任务，再选做录音。"),
  step("1. 双击桌面教师试用入口，选择进入系统，并将窗口最大化。若出现登录页，使用组织者现场提供的医生账号；账号和密码不写在本资料中。"),
  step("2. 进入工作台，展开“新建匿名就诊”，选择“新建匿名患者”，点击“登记并报到”。记下系统生成的患者标识和就诊号，避免打开其他人的测试记录。"),
  step("3. 在新记录上点击“开始接诊”。成功后，页面顶部应显示本次患者与就诊号，下面显示问诊转写、门诊病历和诊疗参考三栏。"),
  h("第二步 输入主线病例"),
  step("4. 打开本包“测试病例”，复制 T01 的全部对话。回到系统点击“文本输入”；左栏收起时先点“转写与录音”。在输入框按 Ctrl+A 全选，再粘贴替换默认示例，不要追加在示例后面。"),
  step("5. 检查没有遗漏角色前缀，再点击一次“确认生成”。等待结果；不要因等待重复提交。生成需要联网，失败时保留页面提示并记录就诊号。"),
  p("成功后应同时看到输入原文与病历草稿。草稿是待核对内容，出现文字不代表内容已经正确，也不代表已保存为批准版。"),
  h("本轮完成标记"),
  p("患者标识：____________________　就诊号：____________________\n初次生成结果：□ 有草稿　□ 被阻断　□ 失败　□ 尚未执行")],
 [h("第三步 核对原文与指南"),
  step("6. 从主诉开始逐项阅读。点击字段旁“查看原文证据”，对照症状、时间、体温、否认和用药信息；不要把医生的问题当成患者已经回答的事实。"),
  step("7. 点击“查依据”，查看指南标题、版本、章节或页码及适用人群。指南用于参考，不能作为患者已经发生某种症状的证明。无关联或无结果也应如实记录。"),
  h("第四步 修改保存与历史对照"),
  step("8. 点击字段旁“修改”，或底部“编辑整页病历”。在编辑框按 Ctrl+A 替换全文，核对没有重复追加。可把主诉改为“发热伴咳嗽、咽痛2天”。不要新增检查、诊断或药物。"),
  step("9. 若显示“证据冲突”，先查看原文和原因，再使用“根据原文修正”或“医生补录”。只有实际核对并输入了可承担责任的内容时，才选择相应方式；不能靠勾选确认解除冲突。"),
  step("10. 点击“保存修改”。看到保存成功和新的病历版本后再继续。保存失败时先保留编辑内容，记录提示；出现版本冲突时不要刷新覆盖本地修改。"),
  p("保存后，点击当前版本旁的“历史版本”，选择旧版本查看修改前内容和差异。关闭后回到当前工作区继续编辑；只读查看不会还原或覆盖当前病历。"),
  p("模型和规则仍可能出现内容遗漏或误拦。若原文与字段看起来一致仍冲突，保留原句及提示并向组织者求助；不要反复点击生成来隐藏失败。"),
  h("第五步 完成分项审核"),
  step("11. 展开“医生分项审核”，阅读已列出的范围后点击“确认当前全部普通字段”。缺失项单独处理：没有问过选“确认未询问”；已问但暂时没有答案可选“接受本次缺失”。这两种选择都不等于“正常”或“没有”。"),
  step("12. AI 候选诊断需逐项保留或删除；本轮不要求作出诊断。没有依据时可“删除AI候选”，仅表示移除系统候选。若仍有高风险提示，阅读并完成核对后才点“已单独确认”，不为通过而盲点。全部处理后，点击底部“完成病历审核”。")],
 [h("第六步 导出并重新打开"),
  step("13. 页面显示已审核后，点击“导出已审核病历”。在浏览器下载列表找到文件并打开，检查患者标识、刚才修改的内容和中文分页。只有实际找到并打开文件才记为导出成功。"),
  step("14. 记下当前病历版本，返回“工作台”，按患者标识搜索刚才的就诊。点击“继续处理”（当前就诊可能显示“返回工作区”），检查原文、修改内容和审核状态是否保留。"),
  step("15. 打开本包“反馈表”，按实际结果填写。请分别记录 AI 首次结果、系统阻断和手工修改；没有做的项目选“未测试”。填写后点击“导出反馈”，将文件交给组织者。"),
  h("选做 录音或上传音频"),
  p("另建一次就诊，避免覆盖已完成的文本任务。左栏点击“开始录音”，按“录音朗读稿”完成短对话；可暂停后恢复，结束后停止并试听。声音异常或内容为空时不要提交。"),
  p("上传已录好的文件时点击“上传音频”，选择组织者准备的授权音频，保持“实时识别”后按页面提交。此名称表示及时显示返回的转写，不等于已实现边录边转写。"),
  p("如出现“确认说话人身份”，先试听并核对相关片段，再选择医生、患者或陪同人员，点击“保存身份确认”。不要为继续操作把所有人一律设为患者。随后按页面继续生成，并重复步骤 6—15。"),
  h("遇到问题时"),
  p("帮助：点击系统“帮助”，在窗口内查看；关闭帮助后继续操作。\n生成失败：保留输入和错误，不连续重试。\n保存冲突：保留本地修改，请组织者协助。\n导出未找到：查看浏览器下载列表；仍没有文件则记录失败。\n无法继续：记下按钮、页面提示与就诊号，联系现场组织者。"),
  p("完成后先保存或取消编辑，停止录音，再退出账号。不要停止服务、修改知识资料或删除其他测试记录。")]
 ]},
 "cases": {"title": "MediListen 现场测试病例", "subtitle": "合成教学材料  不使用真实患者身份信息", "pages": [
 [h("T01 发热咳嗽主线病例"),
  p("用途：完成文本输入、原文核对、指南查询、修改保存、审核导出和历史重开。请完整复制下方对话，保留角色前缀。"),
  script(BASE_CASE, "caseT01"),
  h("核对时重点看什么"),
  p("症状是发热、咳嗽、咽痛；时间为两天；最高体温38.2摄氏度。胸痛和药物过敏被明确否认；两天内没有服药；既往没有慢性疾病。"),
  p("“还没有做检查”不等于查体正常。对话没有给出查体结果、诊断、治疗方案或药物剂量，系统不应补出这些内容。"),
  h("建议完成的一次修改"),
  p("在核对原文后，可将主诉规范为“发热伴咳嗽、咽痛2天”，保存为新版本。若系统已经这样写，可以调整措辞但不增减事实。请记录这一步是人工修订，不计为 AI 首次正确。"),
  p("本卡是输入事实对照，不是临床诊断答案，也不保证当前模型每次都通过。")],
 [h("T02 家属代述与信息不全  选做"),
  p("主线完成后另建一次就诊。此例观察人物归属和未知信息，不要求生成完整治疗方案。"),
  script(OPTIONAL_CASE, "caseT02"),
  h("观察重点"),
  p("发热和咳嗽属于六岁患儿；哮喘属于母亲，不能写成患儿哮喘。孩子没有诊断过哮喘，不能扩大为孩子从未有喘息症状。"),
  p("孩子药物过敏情况不清楚，不等于没有过敏。当前用药和检查情况待核实，不等于未用药、未检查或结果正常。儿童资料需标明适用人群。"),
  h("怎样记录结果"),
  p("先保存首次输出或错误提示，再观察是否被系统隔离。不要为了完成表格把未知信息补成否认。如需要人工修订，记录修改前内容、依据和修改后内容。"),
  p("如果当前模型或规则不能正确处理，记录任务未完成和具体字段即可。此例不设置“必须导出”目标，也不作临床判断。"),
  blank("就诊号与问题记录", 3)]
 ]},
 "recording": {"title": "MediListen 录音转写朗读稿", "subtitle": "双人主稿与单人备用稿  合成教学对话", "pages": [
 [h("双人主稿"),
  p("两人分别扮演医生和患者。请只读台词，不读“医生”“患者”、序号和括号提示。自然语速、轮流讲话，不故意强调关键词；时长约60—90秒，以实际录音为准。"),
  p("开始前确认麦克风已开启，录3秒试听环境音；正式朗读另建新录音。可在第4轮结束后暂停2秒，恢复后继续；暂停期间不要讲话。"),
  script("医生：今天哪里不舒服？大概有多长时间了？\n患者：我发热、咳嗽、咽痛两天了。最高体温量到三十八点二摄氏度。\n医生：有没有胸痛？有没有药物过敏史？\n患者：没有胸痛，也没有药物过敏史。\n医生：这两天有没有自己吃过药？\n患者：这两天没有服用药物。\n医生：以前有没有慢性疾病？\n患者：以前没有慢性疾病。\n医生：这次已经做过什么检查吗？\n患者：这次还没有做检查。", "dualScript"),
  h("停止后先试听"),
  p("确认声音速度正常、两人都能听清，录音计时和播放器时长大致一致，再按页面提交。角色不确定时按实际声音更正；本稿不预先假定角色识别通过。"),
  p("核对转写重点：两天、三十八点二摄氏度、没有胸痛、没有药物过敏、没有服用药物、没有慢性疾病、没有做检查。口语数词可以规范成数字，但数值、单位、否定不能改变。")],
 [h("单人备用稿"),
  p("只有一人时使用本稿，以患者身份连续陈述。它用于检查录音、转写和字段核对，不能代替双人角色识别测试。正常语速约25—40秒，以实际录音为准。"),
  script(SINGLE_SCRIPT, "singleScript"),
  h("提交与核对"),
  p("停止后先试听。如果页面要求确认说话人身份，按实际录音将该人的片段确认为患者，保存后再继续生成。不要把一个人的声音人为拆成两种身份来模拟通过。"),
  p("检查病历与原文一致。未提供诊断、查体、治疗方案或药物剂量；未提供的信息可以保持缺失。遇到内容错误，先记录首次结果，再修改保存并审核。"),
  h("录音记录"),
  blank("试用编号／就诊号／日期", 1),
  blank("实际录音时长／播放器时长／是否使用暂停恢复", 1),
  blank("试听发现的问题或转写错误原句", 3),
  p("请勿朗读真实患者身份信息。本次只检查录音、转写与操作流程，不评价临床诊疗能力。")]
 ]},
 "feedback": {"title": "MediListen 教师现场试用反馈表", "subtitle": "请按实际操作填写  未操作的项目保留为未测试", "pages": [
 [p("本表记录操作体验与内容问题。填写不要求医学诊断；可随时停止。页面不会自动上传反馈，完成后请显式导出并交给现场组织者。"),
  {"kind":"identity"},
  h("一 任务完成情况"),
  {"kind":"tasks"},
  h("二 您在哪里需要帮助"),
  blank("最先找不到或不确定用途的按钮是什么？当时想完成什么？", 2),
  blank("是否有提示让您不知道下一步该做什么？请写出页面提示或就诊号。", 2)],
 [h("三 内容核对记录"),
  p("如发现问题，尽量保留对应原句。请区分转写错误、AI 首次结果、规则阻断和人工修订，不把修订后的结果记为首次正确。"),
  blank("输入原句或音频片段", 2),
  blank("系统首次显示了什么或怎样阻断", 2),
  {"kind":"category"},
  blank("您是否修改过？修改了什么，依据是什么？", 2),
  h("四 使用感受与改进"),
  blank("哪一步最顺畅？哪一步最费力？", 2),
  blank("如果只改一件事，您希望先改什么？", 2),
  blank("下次不由开发者陪同，您愿意再试一次吗？还需要哪些帮助？", 2)]
 ]},
}

TASKS = ["新建匿名就诊并开始接诊", "输入文本并生成一次", "核对原文与查询指南", "修改内容并保存新版本", "分项审核并提交审核", "导出文件并实际打开", "历史重开并核对内容", "录音或上传音频（选做）"]
RESULTS = ["独立完成", "帮助后完成", "未完成", "未测试"]

CSS = """*{box-sizing:border-box}body{margin:0;background:#f2f3f4;color:#111;font:17px/1.75 'Microsoft YaHei','SimSun',sans-serif}main{max-width:920px;margin:auto;padding:20px}header{text-align:center;margin:15px 0 24px}h1{font-size:28px;line-height:1.35;margin:0 0 10px;font-weight:700}h2{font-size:21px;line-height:1.5;margin:26px 0 10px}p{margin:10px 0}.meta{font-size:14px}.topnav{display:flex;gap:12px;flex-wrap:wrap;padding:12px 0}a{color:inherit}button{font:inherit;background:white;border:1px solid #777;border-radius:5px;padding:8px 16px;cursor:pointer}button:focus-visible,a:focus-visible,input:focus-visible,textarea:focus-visible{outline:3px solid #222;outline-offset:3px}.page{background:white;padding:32px 42px;margin:18px 0}.step{margin:12px 0}.script{white-space:pre-wrap;font:17px/1.9 'Microsoft YaHei',sans-serif;width:100%;resize:vertical;background:#fff;border:1px solid #b7b7b7;padding:15px;min-height:240px;color:#111}.copy{margin:8px 0}.question{margin:15px 0}.question label{display:block;font-weight:600}textarea.answer{display:block;width:100%;min-height:90px;font:inherit;border:1px solid #aaa;padding:9px;background:#fff;color:#111}input[type=text],input[type=date]{font:inherit;padding:6px;border:1px solid #aaa;max-width:100%}.task{padding:14px 0;border-bottom:1px solid #ddd}.task strong{display:block}.choices{display:flex;flex-wrap:wrap;gap:8px 20px}.choices label{font-size:16px;white-space:nowrap}input[type=radio],input[type=checkbox]{width:18px;height:18px;vertical-align:middle}.identity{display:grid;gap:12px;grid-template-columns:1fr 1fr}.status{min-height:1.6em}.actions{display:flex;flex-wrap:wrap;gap:12px;margin:24px 0}.pdfonly{display:none}.pagefoot{text-align:center;font-size:13px;margin-top:24px}footer{text-align:center;font-size:14px;padding:20px}.printonly{display:none}@media(max-width:640px){main{padding:10px}.page{padding:20px}.identity{grid-template-columns:1fr}h1{font-size:25px}}@media print{@page{size:A4;margin:18mm}body{background:white;font:11pt/1.5 'SimSun',serif}main{padding:0;max-width:none}.topnav,.copy,.actions,.status,.screenonly{display:none}.page{padding:0;margin:0;break-after:page;box-shadow:none}.page:last-child{break-after:auto}h1{font-size:20pt}h2{font-size:14pt;margin:14pt 0 6pt}p{margin:6pt 0}.script{font:11pt/1.55 'SimSun',serif;border:0;padding:0;resize:none;overflow:visible;min-height:0;height:auto}.scriptprint{display:block;white-space:pre-wrap}.script{display:none}textarea.answer{min-height:60px;border:0;border-bottom:1px solid #ccc}header{margin:0 0 16pt}.pagefoot{font-size:9pt}.identity{font-size:10pt}.task{padding:8px 0}.choices label{font-size:10pt}footer{display:none}.printonly{display:block}}"""

JS = """document.querySelectorAll('[data-copy]').forEach(b=>b.addEventListener('click',async()=>{const t=document.getElementById(b.dataset.copy);try{await navigator.clipboard.writeText(t.value);b.textContent='已复制';}catch(e){t.focus();t.select();b.textContent='已选中，请按 Ctrl+C';}}));
const form=document.querySelector('form');if(form){form.addEventListener('submit',e=>e.preventDefault());document.getElementById('exportFeedback').addEventListener('click',()=>{const fields=Object.fromEntries(new FormData(form).entries());fields.feedback_schema='medilisten-teacher-v1';fields.material_version='4b041cf4';fields.exported_at=new Date().toISOString();const blob=new Blob([JSON.stringify(fields,null,2)],{type:'application/json;charset=utf-8'});const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='MediListen_教师反馈_'+new Date().toISOString().replace(/[:.]/g,'-')+'.json';document.body.appendChild(a);a.click();setTimeout(()=>{URL.revokeObjectURL(a.href);a.remove();},1000);document.getElementById('feedbackStatus').textContent='已请求下载反馈文件。请在下载列表确认文件存在，再交给组织者；本页未上传任何内容。';});document.getElementById('resetFeedback').addEventListener('click',()=>{if(confirm('清空当前填写内容？请先导出需要保留的反馈。')){form.reset();document.getElementById('feedbackStatus').textContent='已清空本页填写内容。';}});}
"""


def html_block(b, n):
    kind=b["kind"]; text=html.escape(b.get("text", "")).replace("\n", "<br>")
    if kind=="h": return f"<h2>{text}</h2>"
    if kind in {"p","step"}: return f'<p class="{kind}">{text}</p>'
    if kind=="script":
        return f'<textarea class="script" id="{b["id"]}" readonly rows="{len(b["text"].splitlines())+1}" aria-label="可复制朗读或输入文本">{html.escape(b["text"])}</textarea><p class="printonly scriptprint">{text}</p><button type="button" class="copy" data-copy="{b["id"]}">复制全文</button>'
    if kind=="blank": return f'<div class="question"><label for="answer{n}">{text}</label><textarea class="answer" id="answer{n}" name="answer{n}" aria-label="{html.escape(b["text"])}" rows="{max(2,b["lines"])}"></textarea></div>'
    if kind=="identity": return '<div class="identity"><label>试用编号 <input type="text" name="trial_id"></label><label>日期 <input type="date" name="date"></label><label>就诊号 <input type="text" name="encounter"></label><label>实际运行版本 <input type="text" name="runtime_version" placeholder="请按现场标识填写"></label></div>'
    if kind=="tasks": return ''.join(f'<div class="task"><strong>{i+1}. {html.escape(t)}</strong><div class="choices">'+''.join(f'<label><input type="radio" name="task_{i+1}" value="{r}"> {r}</label>' for r in RESULTS)+'</div></div>' for i,t in enumerate(TASKS))
    if kind=="category": return '<div class="question"><p>您认为问题在哪一步（可多选，不确定可留空）</p><div class="choices">'+''.join(f'<label><input type="checkbox" name="problem_{i}" value="{v}"> {v}</label>' for i,v in enumerate(['录音或转写','人物身份','AI首次内容','规则或审核阻断','保存或导出','操作提示','尚不能确定']))+'</div></div>'
    raise ValueError(kind)


def make_html(key, d, out):
    pieces=['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">',f'<title>{d["title"]}</title><link rel="stylesheet" href="trial.css"></head><body><main>',f'<nav class="topnav"><a href="index.html">返回试用首页</a><a href="{key}.pdf">打开打印版 PDF</a><button type="button" onclick="window.print()">打印本页</button></nav>']
    if key=='feedback': pieces.append('<form autocomplete="off">')
    n=0
    for i,page in enumerate(d['pages']):
        pieces.append('<section class="page">')
        if i==0: pieces.append(f'<header><h1>{d["title"]}</h1><p>{d["subtitle"]}</p><p class="meta">资料日期 {DATE}　材料基线版本 {VERSION}　现场电脑 8798；实际前端和后端以试用首页为准。</p></header>')
        for b in page:
            n+=1;pieces.append(html_block(b,n))
        pieces.append(f'<p class="pagefoot">{d["title"]}　{i+1} / {len(d["pages"])}</p></section>')
    if key=='feedback':
        pieces.append('<div class="actions"><button type="button" id="exportFeedback">导出反馈 JSON</button><button type="button" onclick="window.print()">打印或另存 PDF</button><button type="button" id="resetFeedback">清空本页</button></div><p id="feedbackStatus" class="status" role="status">填写仅在当前页面中保留；关闭或刷新前请先导出。本页不自动保存、不自动上传。</p></form>')
    pieces.append('<footer>教师现场使用资料 · 不包含账号、密码或 API 密钥</footer></main><script src="trial.js"></script></body></html>')
    (out/f'{key}.html').write_text('\n'.join(pieces),encoding='utf-8')


def prepare_fonts():
    pdfmetrics.registerFont(TTFont('BodyCN', 'C:/Windows/Fonts/simsun.ttc', subfontIndex=0))
    pdfmetrics.registerFont(TTFont('HeadCN', 'C:/Windows/Fonts/msyhbd.ttc', subfontIndex=0))
    pdfmetrics.registerFontFamily('BodyCN',normal='BodyCN',bold='HeadCN',italic='BodyCN',boldItalic='HeadCN')


def make_pdf(key,d,out):
    dest=out/f'{key}.pdf'; c=canvas.Canvas(str(dest),pagesize=A4)
    c.setTitle(d['title']);c.setAuthor('MediListen 项目组')
    W,H=A4; left=21*mm; width=W-42*mm
    styles={
      'p':ParagraphStyle('p',fontName='BodyCN',fontSize=11.3,leading=17.3,textColor=colors.black,spaceAfter=7),
      'h':ParagraphStyle('h',fontName='HeadCN',fontSize=14.5,leading=21,textColor=colors.black,spaceAfter=7),
      'title':ParagraphStyle('title',fontName='HeadCN',fontSize=20,leading=28,alignment=TA_CENTER,textColor=colors.black),
      'sub':ParagraphStyle('sub',fontName='BodyCN',fontSize=10,leading=15,alignment=TA_CENTER,textColor=colors.black),
      'tiny':ParagraphStyle('tiny',fontName='BodyCN',fontSize=9.5,leading=14,textColor=colors.black),
    }
    audit=[]
    for idx,page in enumerate(d['pages']):
        y=H-19*mm
        def draw(text,style='p',gap=7):
            nonlocal y
            q=Paragraph(html.escape(text).replace('\n','<br/>'),styles[style]);qw,qh=q.wrap(width,1000)
            q.drawOn(c,left,y-qh);y-=qh+gap
        if idx==0:
            draw(d['title'],'title',7);draw(d['subtitle'],'sub',5);draw(f'资料日期 {DATE}  |  材料基线版本 {VERSION}  |  现场电脑 8798','sub',15)
        else:
            draw(d['title'],'sub',15)
        for b in page:
            k=b['kind']
            if k=='h': y-=5;draw(b['text'],'h',7)
            elif k in {'p','step'}:draw(b['text'])
            elif k=='script':draw(b['text'],'p',12)
            elif k=='blank':
                draw(b['text'],'p',2)
                for _ in range(b['lines']):
                    y-=17;c.setStrokeColor(colors.HexColor('#bdbdbd'));c.setLineWidth(.4);c.line(left,y,left+width,y)
                y-=12
            elif k=='identity':
                draw('试用编号：________________　日期：________________','p',9)
                draw('就诊号：__________________　实际运行版本：________','p',10)
            elif k=='tasks':
                for j,t in enumerate(TASKS):
                    draw(f'{j+1}. {t}','p',2)
                    draw('□ 独立完成   □ 帮助后完成   □ 未完成   □ 未测试','tiny',9)
            elif k=='category':
                draw('问题位置（可多选）：□ 录音或转写  □ 人物身份  □ AI 首次内容\n□ 规则或审核阻断  □ 保存或导出  □ 操作提示  □ 尚不能确定','tiny',10)
        audit.append({'page':idx+1,'bottom_y_points':round(y,2)})
        if y<45: raise ValueError(f'{key} page {idx+1} overflow: {y}')
        c.setFillColor(colors.black);c.setFont('BodyCN',9);c.drawCentredString(W/2,12*mm,f'{idx+1} / {len(d["pages"])}')
        c.showPage()
    c.save();return audit


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);args=ap.parse_args()
    out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=True)
    prepare_fonts();audit={}
    (out/'trial.css').write_text(CSS,encoding='utf-8');(out/'trial.js').write_text(JS,encoding='utf-8')
    (out/'case-T01.txt').write_text(BASE_CASE+'\n',encoding='utf-8');(out/'case-T02.txt').write_text(OPTIONAL_CASE+'\n',encoding='utf-8')
    for key,doc in DOCS.items():make_html(key,doc,out);audit[key]=make_pdf(key,doc,out)
    manifest={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(out.iterdir()) if p.is_file() and p.name not in {'materials-build.json'}}
    (out/'materials-build.json').write_text(json.dumps({'date':DATE,'runtime_version':VERSION,'pdf_layout':audit,'files':manifest,'visual_qa':'pending'},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(out),'pdf_layout':audit},ensure_ascii=False))


if __name__=='__main__':main()
