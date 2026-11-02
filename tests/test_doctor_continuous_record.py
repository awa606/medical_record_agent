"""Display state regression: real JS, no model, DB or browser calls."""
from tests.test_doctor_history_restore import run_browser_logic


def test_signed_revision_requires_matching_task_hash_and_non_editing_state():
    result = run_browser_logic(r'''
appState.currentTaskId=1;
appState.currentTask={current_record_revision_id:2,result_json:{record_revision:{id:2,content_hash:'a'}}};
appState.currentExportReadiness={task_id:1,revision_id:2,content_hash:'a',ready:true};
const valid=currentRevisionIsSigned();
appState.currentExportReadiness.content_hash='b'; const wrongHash=currentRevisionIsSigned();
appState.currentExportReadiness.content_hash='a'; appState.currentExportReadiness.revision_id=1; const old=currentRevisionIsSigned();
appState.currentExportReadiness.revision_id=2; appState.recordEditMode=true; const editing=currentRevisionIsSigned();
console.log(JSON.stringify({valid,wrongHash,old,editing}));
''')
    assert result == dict(valid=True, wrongHash=False, old=False, editing=False)


def test_reference_does_not_fabricate_pending_or_confirmed_decision():
    result = run_browser_logic(r'''
const fields={treatment_plan:{value:'参考',missing:false,status:'complete'}};
const before=JSON.stringify(fields);
console.log(JSON.stringify({status:fieldReviewPresentation(fields,'treatment_plan',true),summary:recordReviewSummary(fields,true),unchanged:JSON.stringify(fields)===before}));
''')
    assert result['status'] == {'key': 'neutral', 'label': '参考建议 · 未记录独立确认'}
    assert result['summary']['items'] == []
    assert result['unchanged']


def test_review_decisions_and_conflicts_are_not_replaced_by_signature():
    result = run_browser_logic(r'''
const records=[
 {value:'发热',missing:false,status:'partial',confirmed_by_doctor:true,doctor_review_status:'content_confirmed'},
 {value:'',missing:true,status:'missing',doctor_review_status:'missing_accepted'},
 {value:'',missing:true,status:'missing',doctor_review_status:'not_asked_confirmed'},
 {value:'',missing:true,status:'missing'},
 {value:'矛盾',missing:true,status:'conflicting',doctor_review_status:'content_confirmed'}
];
console.log(JSON.stringify(records.map(field=>fieldReviewPresentation({chief_complaint:field},'chief_complaint',true))));
''')
    assert [item['key'] for item in result] == ['confirmed','confirmed','confirmed','neutral','conflicting']
    assert result[1]['label'] != result[2]['label']


def test_one_conflict_is_one_item_and_regular_confirmation_is_separate():
    result = run_browser_logic(r'''
const fields={chief_complaint:{value:'发热',missing:false,status:'complete'},
 present_illness:{value:'',missing:true,status:'conflicting'},
 allergy_history:{value:'',missing:true,status:'missing'}};
console.log(JSON.stringify(recordReviewSummary(fields,false)));
''')
    assert result['regularPending']
    assert [item['id'] for item in result['items']] == ['field:present_illness','field:allergy_history']


def test_render_keeps_all_fields_but_starts_with_clinical_history():
    result = run_browser_logic(r'''
const nodes=new Map(); document.getElementById=id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id)};
appState.currentTaskId=1; appState.viewMode='doctor';
appState.currentRecordFields=Object.fromEntries(FIELD_DEFS.map(([key])=>[key,{value:'合成内容',missing:false,status:'complete'}]));
appState.currentDraft='草稿';
renderFields(); const html=nodes.get('recordFields').innerHTML;
console.log(JSON.stringify({historyBeforeDemographics:html.indexOf('data-record-section="history"')<html.indexOf('data-record-section="demographics"'),
 fields: [...html.matchAll(/data-field="([^"]+)"/g)].map(m=>m[1]),
 anchors:[...html.matchAll(/data-record-anchor="([^"]+)"/g)].map(m=>m[1])}));
''')
    assert result['historyBeforeDemographics']
    assert len(result['fields']) == len(set(result['fields']))
    assert 'previous_treatment' in result['fields']
    assert 'patient_address' in result['fields']
    assert result['anchors'] == ['history','background','exam','management','demographics']


def test_incomplete_review_decision_is_pending_in_both_field_and_summary():
    result = run_browser_logic(r'''
const fields={chief_complaint:{value:'发热',missing:false,status:'complete',doctor_review_status:'content_confirmed',confirmed_by_doctor:false}};
console.log(JSON.stringify({field:fieldReviewPresentation(fields,'chief_complaint',false),summary:recordReviewSummary(fields,false)}));
''')
    assert result['field']['key'] != 'confirmed'
    assert result['summary']['regularPending']


def test_next_issue_uses_rendered_order_and_collapsed_group_location():
    result = run_browser_logic(r'''
const card=(key,top,closed=null)=>({dataset:{field:key},getBoundingClientRect:()=>({top}),closest:()=>closed});
const nodes=[card('chief_complaint',20),card('present_illness',100),card('accompanying_symptoms',180),card('previous_treatment',300),card('patient_address',0,{getBoundingClientRect:()=>({top:600})})];
const list={querySelectorAll:()=>nodes,querySelector:()=>({getBoundingClientRect:()=>({bottom:120})})};
const items=['previous_treatment','accompanying_symptoms','patient_address'].map(fieldKey=>({fieldKey}));
const nearest=nextRecordIssueKey(items,list);
const collapsed=nextRecordIssueKey([{fieldKey:'patient_address'}],list);
console.log(JSON.stringify({nearest,collapsed}));
''')
    assert result == dict(nearest='accompanying_symptoms', collapsed='patient_address')


def test_edit_mode_labels_inherited_decisions_as_original_revision():
    result = run_browser_logic(r'''
const nodes=new Map(); document.getElementById=id=>{if(!nodes.has(id))nodes.set(id,{});return nodes.get(id)};
appState.currentTaskId=1; appState.viewMode='doctor'; appState.recordEditMode=true;
appState.currentRecordFields={chief_complaint:{value:'发热',missing:false,status:'complete',doctor_review_status:'content_confirmed',confirmed_by_doctor:true}};
appState.recordEditFields=JSON.parse(JSON.stringify(appState.currentRecordFields));
appState.currentDraft='草稿';
renderFields(); renderReviewBoundaryNotice();
console.log(JSON.stringify({html:nodes.get('recordFields').innerHTML,badge:nodes.get('fieldCountBadge').textContent}));
''')
    assert '原版本：内容已确认' in result['html']
    assert result['badge'] == '编辑中 · 未保存'
