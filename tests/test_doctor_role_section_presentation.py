"""Exercise presentation logic only; no real browser, ASR, model or API calls."""
import json
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
