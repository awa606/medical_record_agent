"""Presentation-only Chinese labels for the pinned Datasette viewer.

Never rename SQLite columns, query parameters or JSON values. Hooks only render
HTML; clinical text and foreign-key links are left to Datasette unchanged.
"""
from datasette import hookimpl
from markupsafe import Markup, escape
import json

TABLES = {
    "patient": ("患者", "匿名患者编号与登记信息"),
    "encounter": ("就诊记录", "同一患者的每次就诊及当前病历版本"),
    "agent_task": ("处理任务", "输入方式、处理阶段与完成时间"),
    "record_revision": ("病历版本", "每次保存形成的病历与版本关联"),
    "revision_field": ("病历字段", "主诉等字段、原文证据和医生核对状态"),
    "approval": ("审核记录", "与具体病历版本绑定的批准和失效记录"),
    "export_event": ("导出记录", "导出时关联的就诊、版本与批准记录"),
    "knowledge_source": ("资料来源", "发布机构、适用范围与原始资料链接"),
    "knowledge_document": ("文档版本", "版本、启停状态与内容校验值"),
    "knowledge_chunk": ("知识片段", "用于检索的原文、章节和页码"),
    "knowledge_embedding_metadata": ("语义索引信息", "语义向量模型、维度与关联片段；不展示向量数组"),
}
COLUMNS = dict(zip(
    "id deidentified_id display_name created_at updated_at input_type status current_stage completed_at patient_id task_id check_in_status current_revision_id encounter_id revision_no source content_hash draft_text revision_id field_key value missing doctor_review_status evidence_json invalidated_at invalidation_reason approval_id source_id title publisher source_url published_at usage_scope document_type disease_scope document_id version content_sha256 retrieved_at page_count extraction_method is_current is_active effective_date content_format chunk_id section page content model_id dimensions text index segment_id start_time end_time".split(),
    "编号 匿名患者编号 显示名称 创建时间 更新时间 输入方式 状态 当前阶段 完成时间 患者编号 处理任务编号 报到状态 当前病历版本编号 就诊编号 版本序号 生成来源 内容校验值 病历正文 病历版本编号 字段名称 字段内容 是否缺失 医生核对状态 原文证据 失效时间 失效原因 批准记录编号 来源编号 资料标题 发布机构 来源链接 发布日期 使用边界 资料类型 适用范围 文档编号 版本 内容校验值 采集时间 页数 提取方式 是否当前版本 是否启用 生效日期 内容格式 片段编号 章节 页码 片段原文 模型名称 向量维度 原文 句子序号 音频片段编号 开始时间 结束时间".split(), strict=True))
VALUES = {
    "chief_complaint": "主诉", "present_illness": "现病史", "previous_treatment": "既往处理",
    "accompanying_symptoms": "伴随症状", "past_history": "既往史", "allergy_history": "过敏史", "physical_exam": "查体",
    "text": "文本输入", "audio": "音频输入", "browser_recording": "浏览器录音",
    "draft": "草稿", "created": "已创建", "registered": "已登记", "checked_in": "已报到",
    "in_progress": "处理中", "in_consultation": "问诊中", "cancelled": "已取消", "canceled": "已取消",
    "transcribing": "转写中", "extracting_fields": "提取病历字段", "generating_draft": "生成草稿",
    "safety_checking": "安全校验中", "degraded": "降级处理中", "doctor_review": "医生核对",
    "waiting_doctor_review": "等待医生审核", "waiting_review": "等待审核", "pending_review": "待审核",
    "reviewed": "已核对", "approved": "已批准", "exported": "已导出", "completed": "已完成", "done": "已完成",
    "failed": "失败", "invalidated": "已失效", "pending": "待处理", "confirmed": "已确认",
    "supported": "有原文支持", "conflicting": "证据冲突", "insufficient": "依据不足", "missing": "未采集",
    "not_mentioned": "未提及", "partial": "部分采集", "unreviewed": "待核对", "accepted": "已接受",
    "accepted_missing": "已接受缺失", "accepted_partial": "已接受部分采集", "not_asked": "尚未询问",
    "doctor_edited": "医生已修改", "doctor_edit": "医生修改", "doctor_review_save": "医生保存",
    "generated": "系统生成", "ai_generated": "系统生成", "generation": "系统生成", "regeneration": "重新生成",
    "clinical-reference": "临床参考", "record-standard": "病历规范", "markdown": "Markdown文本", "plain_text": "纯文本",
    "utf-8": "UTF-8文本编码", "pdf_text": "PDF文字提取", "ocr": "图像文字识别", "manual": "人工整理",
    "pypdf": "PDF文字提取", "rapidocr": "图像文字识别", "browser_utf8_markdown_v1": "网页文字提取",
    "pdf": "PDF文档", "date": "日期分组", "array": "列表分组",
}
LOOKUPS = {
    "exact": "等于", "not": "不等于", "contains": "包含", "notcontains": "不包含", "startswith": "开头是",
    "endswith": "结尾是", "gt": "大于", "gte": "大于或等于", "lt": "小于", "lte": "小于或等于",
    "like": "模式匹配", "notlike": "不匹配", "glob": "通配符匹配", "isnull": "为空值", "notnull": "非空值",
    "isblank": "为空", "notblank": "非空", "in": "属于列表", "notin": "不属于列表", "arraycontains": "数组包含",
    "arraynotcontains": "数组不包含", "date": "日期等于",
}
ENUM_COLUMNS = {"field_key", "status", "current_stage", "check_in_status", "input_type", "doctor_review_status", "source", "document_type", "extraction_method", "content_format"}


def label(key):
    return TABLES[key][0] if key in TABLES else COLUMNS.get(key, {"mra_snapshot": "数据目录", "Datasette": "查看器首页", "home": "查看器首页"}.get(key, key))


def value_label(value):
    raw = str(value)
    return VALUES.get(raw, VALUES.get(raw.lower(), "未配置中文释义"))


def badge(value):
    return Markup('{} <small class="technical">({})</small>').format(value_label(value), escape(value))


@hookimpl
def prepare_jinja2_environment(env, datasette):
    env.globals.update(mra_label=label, mra_tables=TABLES, mra_lookup=lambda key: LOOKUPS.get(key, "未配置中文释义（" + key + "）"),
                       mra_value=value_label, mra_enum_columns=ENUM_COLUMNS,
                       mra_context=datasette.metadata().get("mra_context", {}))


@hookimpl
def render_cell(row, value, column, table, database, datasette):
    if database != "mra_snapshot" or table not in TABLES or value is None:
        return None
    if column in ENUM_COLUMNS:
        return badge(value)
    if column in {"is_active", "is_current", "missing"}:
        names = {"is_active": ("停用", "启用"), "is_current": ("历史版本", "当前版本"), "missing": ("否", "是")}
        if value in (0, 1):
            return Markup('{} <small class="technical">({})</small>').format(names[column][int(value)], value)
    if column == "evidence_json":
        try:
            spans = json.loads(value)
            if not isinstance(spans, list) or any(not isinstance(s, dict) for s in spans):
                return None
            rows = []
            for i, span in enumerate(spans, 1):
                items = Markup('').join(Markup('<dt>{} <small>({})</small></dt><dd>{}</dd>').format(label(k), escape(k), escape(v)) for k, v in span.items())
                rows.append(Markup('<section><h4>片段 {}</h4><dl>{}</dl></section>').format(i, items))
            return Markup('<details><summary>查看 {} 项原文证据</summary>{}<details><summary>原始 JSON（结构化记录）</summary><pre>{}</pre></details></details>').format(len(spans), Markup('').join(rows), escape(value))
        except (ValueError, TypeError):
            return None
    return None
