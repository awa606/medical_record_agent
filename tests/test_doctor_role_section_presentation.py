"""Exercise presentation logic only; no real browser, ASR, model or API calls."""
import json
from html import unescape
from pathlib import Path

import pytest

from tests.test_doctor_history_restore import run_browser_logic

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("row, expected", [
    ({"speaker": "doctor", "roleTrusted": True}, {"role": "doctor", "state": "confirmed", "warning": ""}),
    ({"speaker": "patient", "roleTrusted": True}, {"role": "patient", "state": "confirmed", "warning": ""}),
    ({"speaker": "other", "label": "家属", "roleTrusted": True}, {"role": "other", "state": "confirmed", "warning": ""}),
    ({"speaker": "doctor"}, {"role": "doctor", "state": "pending", "warning": "角色待核对"}),
    ({"speaker": "patient", "roleSource": "rules"}, {"role": "patient", "state": "pending", "warning": "角色待核对"}),
    ({"speaker": "doctor", "roleWarning": True}, {"role": "doctor", "state": "inferred", "warning": "系统推定，待核对"}),
    ({"speaker": "patient", "needsReview": True}, {"role": "patient", "state": "pending", "warning": "角色待核对"}),
    ({"speaker": "doctor", "provisional": True}, {"role": "doctor", "state": "provisional", "warning": "临时转写"}),
    ({"speaker": "speaker", "label": "说话人 A"}, {"role": "unknown", "state": "unknown", "warning": ""}),
    ({"speaker": "unknown"}, {"role": "unknown", "state": "unknown", "warning": ""}),
    ({"speaker": "speaker", "needsReview": True}, {"role": "unknown", "state": "pending", "warning": "角色待核对"}),
    ({"speaker": "doctor\" onclick=bad"}, {"role": "unknown", "state": "unknown", "warning": ""}),
])
def test_transcript_presentation_whitelists_roles_without_changing_rows(row, expected):
    result = run_browser_logic("const row=" + json.dumps(row, ensure_ascii=False) + r""";
const before=JSON.stringify(row); const display=transcriptRowPresentation(row);
console.log(JSON.stringify({display, unchanged:JSON.stringify(row)===before}));
""")
    assert result == {"display": expected, "unchanged": True}


def test_actual_text_rows_only_trust_explicit_line_prefixes():
    result = run_browser_logic(r"""
const rows=transcriptRowsFromText('医生：哪里不舒服？\n患者：发热两天。\n他说医生让我看看。');
console.log(JSON.stringify(rows.map(row=>({text:row.text,presentation:transcriptRowPresentation(row)}))));
""")
    assert [item["presentation"]["state"] for item in result] == ["confirmed", "confirmed", "unknown"]
    assert result[2]["text"] == "他说医生让我看看。"


@pytest.mark.parametrize("segment, expected_role, expected_state", [
    ({"text": "哪里不舒服？", "speaker_id": "spk0", "role": "医生", "role_confidence": 0.99, "needs_review": False}, "doctor", "confirmed"),
    ({"text": "发热两天。", "speaker_id": "spk0", "role": "患者", "role_confidence": 0.1, "needs_review": True}, "unknown", "pending"),
    ({"text": "发热两天。", "speaker_id": "spk0", "role": "患者", "role_source": "manual_review", "reviewed_by_doctor": True, "needs_review": False}, "patient", "confirmed"),
])
def test_actual_asr_rows_reuse_existing_role_trust_without_mutating_source(segment, expected_role, expected_state):
    result = run_browser_logic("const segment=" + json.dumps(segment, ensure_ascii=False) + r""";
appState.currentAsrResult={segments:[segment]}; appState.liveTranscriptSegments=[];
const before=JSON.stringify(segment); const row=transcriptRows()[0];
console.log(JSON.stringify({presentation:transcriptRowPresentation(row), unchanged:JSON.stringify(segment)===before}));
""")
    assert result["unchanged"]
    assert result["presentation"]["role"] == expected_role
    assert result["presentation"]["state"] == expected_state


@pytest.mark.parametrize("overrides, expected", [
    ({}, "confirmed"),
    ({"role_source": "manual_speaker_map", "role_warning": "系统自动推定"}, "confirmed"),
    ({"reviewed_by_doctor": False}, "inferred"),
    ({"reviewed_by_doctor": "false"}, "inferred"),
    ({"needs_review": True}, "inferred"),
    ({"role_source": "automatic"}, "inferred"),
    ({"role_warning": "需重新核实音段来源"}, "inferred"),
])
def test_saved_asr_role_uses_explicit_review_with_historical_warning(overrides, expected):
    segment = {
        "text": "昨天没有这个感觉。", "speaker_id": "spk0", "role": "患者",
        "role_source": "manual", "reviewed_by_doctor": True, "needs_review": False,
        "role_warning": "系统自动推定说话人角色，最终病历字段仍需医生审核。", **overrides,
    }
    result = run_browser_logic("const segment=" + json.dumps(segment, ensure_ascii=False) + r""";
appState.currentAsrResult={segments:[segment]}; appState.liveTranscriptSegments=[];
const before=JSON.stringify(segment); const display=transcriptRowPresentation(transcriptRows()[0]);
console.log(JSON.stringify({state:display.state, unchanged:JSON.stringify(segment)===before}));
""")
    assert result == {"state": expected, "unchanged": True}


@pytest.mark.parametrize("approved, review, expected", [
    (True, "not_asked_confirmed", "本次未询问（医生已确认）"),
    (True, "missing_accepted", "本次资料缺失（医生已接受）"),
    (True, "", "该字段无记录；历史病历已审核，未记录分项处理原因"),
    (False, "not_asked_confirmed", "建议补问：发热多久？"),
    (False, "", "建议补问：发热多久？"),
])
def test_approved_missing_presentation_uses_recorded_review_and_preserves_original(approved, review, expected):
    field = {"value": "", "hint": "建议补问：发热多久？", "missing": True,
             "status": "missing", "doctor_review_status": review, "source_spans": []}
    result = run_browser_logic("const field=" + json.dumps(field, ensure_ascii=False) + "; const approved=" + json.dumps(approved) + r""";
const before=JSON.stringify(field);
const text=recordFieldDisplayValue({chief_complaint:field}, 'chief_complaint', approved);
console.log(JSON.stringify({text,raw:fieldValue({chief_complaint:field}, 'chief_complaint'),unchanged:JSON.stringify(field)===before}));
""")
    assert result["text"] == expected
    assert result["raw"] == "建议补问：发热多久？"
    assert result["unchanged"]


@pytest.mark.parametrize("field, expected", [
    ({"value": "否认胸痛", "missing": False, "status": "complete"}, "否认胸痛"),
    ({"value": "否认胸痛", "missing": True, "status": "partial"}, "否认胸痛"),
    ({"value": "未采纳错误", "missing": True, "status": "conflicting"}, "待核对（模型内容未采纳）"),
])
def test_approved_display_does_not_hide_existing_content_or_conflicts(field, expected):
    result=run_browser_logic("const field=" + json.dumps(field, ensure_ascii=False) + r""";
console.log(JSON.stringify(recordFieldDisplayValue({chief_complaint:field}, 'chief_complaint', true)));
""")
    assert result == expected


def test_record_sections_have_semantic_titles_and_transcript_role_attributes():
    script=(ROOT/'static/doctor.js').read_text(encoding='utf-8')
    assert '<h3 class="field-title"' in script
    assert 'aria-labelledby="record-field-heading-${escapeHtml(key)}"' in script
    assert 'data-role="${presentation.role}"' in script
    assert 'data-role-state="${presentation.state}"' in script
    assert '生成时提示（历史记录）' in script


def test_role_palette_is_limited_to_confirmed_rows_and_preserves_timing():
    css=(ROOT/'static/doctor-workspace.css').read_text(encoding='utf-8')
    for role in ('doctor','patient'):
        assert f'[data-role="{role}"][data-role-state="confirmed"]' in css
    script=(ROOT/'static/doctor.js').read_text(encoding='utf-8')
    assert '${transcriptTimeMarkup(item)}' in script
    assert '${hasAudioSource && item.startTime != null ? `data-segment-start="${item.startTime}"` : ""}' in script


@pytest.mark.parametrize("approved", [False, True])
def test_field_detail_shows_current_review_and_keeps_generation_hint_as_history(approved):
    result=run_browser_logic("const approved=" + json.dumps(approved) + r""";
const fields={chief_complaint:{value:'',hint:'建议补问：发热多久？',missing:true,status:'missing',doctor_review_status:'missing_accepted'}};
activeRecordFields=()=>fields; doctorDisplayState=()=>({key:approved?'approved':'review'});
fieldQualityItem=()=>null; renderFieldEvidenceDetails=()=>'<p>没有患者原句</p>';
const before=JSON.stringify(fields); const html=renderFieldDetailContent('chief_complaint');
console.log(JSON.stringify({html,unchanged:JSON.stringify(fields)===before}));
""")
    assert result['unchanged']
    assert '建议补问：发热多久？' in result['html']
    if approved:
        assert '生成时提示（历史记录）' in result['html']
        assert '本次资料缺失（医生已接受）' in result['html']
        assert '医生接受本次信息缺失' in result['html']
        assert '>待补充<' not in result['html']
    else:
        assert '生成时提示（历史记录）' not in result['html']
        assert '>待补充<' in result['html']


@pytest.mark.parametrize("signed,review,status,confidence,expected", [
    (True, "content_confirmed", "complete", None, "内容已确认"),
    (True, "pending", "complete", None, "未记录分项决定"),
    (False, "pending", "complete", 0.81, "待医生审核"),
    (False, "content_confirmed", "complete", None, "待医生审核"),
    (True, "content_confirmed", "conflicting", None, "证据冲突 · 需修正"),
    (False, "pending", "conflicting", None, "证据冲突"),
])
def test_field_detail_distinguishes_review_from_draft_quality(signed, review, status, confidence, expected):
    field = {"value": "合成主诉", "missing": False, "status": status, "confidence": confidence,
             "confirmed_by_doctor": review == "content_confirmed", "doctor_review_status": review}
    setup = "const signed=" + json.dumps(signed) + ",field=" + json.dumps(field, ensure_ascii=False) + ";"
    html = run_browser_logic(setup + r"""
const quality={key:"chief_complaint",status:"needs_doctor_review",reason:"主诉来自系统抽取，尚未医生确认。"};
activeRecordFields=()=>({chief_complaint:field}); currentRevisionIsSigned=()=>signed;
doctorDisplayState=()=>({key:signed?"approved":"review"});
activeQualityReport=()=>({field_quality:[quality]});
console.log(JSON.stringify(renderFieldDetailContent('chief_complaint')));
""")
    assert "本版字段状态" in html and f">{expected}<" in html
    assert "模型置信度" in html and (">未提供<" if confidence is None else ">81%<") in html
    assert "草稿生成时的自动检查" in html
    assert ("尚未医生确认" in html) is (not signed)


@pytest.mark.parametrize("note,origin", [
    ("manual_doctor_edit_v1: 医生手工修改；原始转写证据仅供对照，不作为该修改的自动证据。", "医生已修改"),
    ("manual_doctor_edit_v1: 医生补录；新内容为人工来源，原模型内容和错误引用保留在旧版本。", "医生补录"),
    ("doctor_source_correction_v1: 医生根据原文修正，已重新校验证据；需审核当前版本。", "医生根据原文修正"),
])
def test_revision_note_keeps_physician_words_and_original_for_debug(note, origin):
    comment = " 医生补录是患者转述。\n  原句 <来源> & 标点；审核说明：保留。  "
    result = run_browser_logic("const note=" + json.dumps(note) + ",comment=" + json.dumps(comment) + r""";
const signed = [false,true].map(flag=>{
  currentRevisionIsSigned=()=>flag; appState.viewMode="doctor";
  return renderFieldRevisionNote(note+"；审核说明："+comment);
});
const paper=renderFieldRevisionNote(note); const origin=knownFieldRevisionNote(note+"；审核说明："+comment).origin;
appState.viewMode="debug";
console.log(JSON.stringify({signed,paper,origin,raw:renderFieldRevisionNote(note+"；审核说明："+comment)}));
""")
    assert result["origin"] == origin
    assert "修订时的操作记录" in result["paper"] and "医生审核说明" not in result["paper"]
    assert result["signed"][0] == result["signed"][1]
    shown = result["signed"][0]
    assert "医生审核说明" in shown and comment in unescape(shown) and "<来源>" not in shown
    assert "_v1:" not in shown and "需审核当前版本" not in shown
    assert note + "；审核说明：" + comment in unescape(result["raw"])


@pytest.mark.parametrize("note", [
    "医生根据原文修正，所选证据存在冲突，需重新核对。",
    "manual_doctor_edit_v1: 医生自行输入的备注，提及医生补录。",
    "doctor_source_correction_v1: 自由文本；审核说明：附注<保留>。",
    "doctor_source_correction_v1: 医生根据原文修正，已重新校验证据；需审核当前版本。手写补述",
    "doctor_source_correction_v1: 医生根据原文修正，已重新校验证据；需审核当前版本。；审核说明：",
    " 原始备注\n  第二行 & 末尾空格  ",
])
def test_unrecognized_revision_note_is_preserved_without_inferred_origin(note):
    result = run_browser_logic("const note=" + json.dumps(note) + r""";
appState.viewMode="doctor";
console.log(JSON.stringify({origin:knownFieldRevisionNote(note),html:renderFieldRevisionNote(note)}));
""")
    assert result["origin"] is None and "修订时的操作记录" not in result["html"]
    assert note in unescape(result["html"])


@pytest.mark.parametrize("audio", [True, False])
def test_real_transcript_renderer_preserves_text_timing_and_neutral_warning(audio):
    result=run_browser_logic("const audio=" + json.dumps(audio) + r""";
const nodes=new Map();document.getElementById=id=>{if(!nodes.has(id))nodes.set(id,{innerHTML:'',textContent:'',hidden:false});return nodes.get(id)};
appState.currentAudioId=audio?'saved-audio':'';
appState.currentAsrResult=audio?{segments:[]}:null;
const rows=[
 {index:0,segmentId:'saved-0',startTime:4,endTime:7,time:'00:04',speaker:'doctor',label:'医生',text:'最近有什么不舒服？'},
 {index:1,segmentId:'saved-1',startTime:7,endTime:10,time:'00:07',speaker:'patient',label:'患者',text:'发热两天。'},
 {index:2,segmentId:'saved-2',startTime:null,time:'--:--',speaker:'patient',label:'患者',needsReview:true,text:'角色仍待核对。'}
];
transcriptRows=()=>rows; visibleTranscriptRows=value=>value; renderAudioPlayer=()=>{};
const before=JSON.stringify(rows); renderTranscript();
console.log(JSON.stringify({html:nodes.get('transcriptList').innerHTML,unchanged:JSON.stringify(rows)===before}));
""")
    assert result['unchanged']
    assert 'data-role="doctor"' in result['html']
    assert 'data-role="patient"' in result['html']
    assert 'data-role-state="pending"' in result['html']
    assert '角色待核对' in result['html']
    assert '最近有什么不舒服？' in result['html'] and '发热两天。' in result['html']
    if audio:
        assert '00:04' in result['html'] and '00:07' in result['html']
        assert '时间未记录' in result['html']
        assert 'data-segment-start="4"' in result['html']
    else:
        assert 'transcript-row-time' not in result['html']
        assert 'data-segment-start' not in result['html']
