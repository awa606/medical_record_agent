"""Read-only record history: saved evidence, edit isolation and stale responses."""

import pytest

from tests.test_doctor_history_restore import run_browser_logic


HISTORY_SETUP = r'''
const content = {innerHTML:'',querySelector:()=>({focus(){}})};
document.getElementById = () => content;
openDetailDrawer = (_title,html) => {detailDrawerVersion++;content.innerHTML=html};
appState.currentEncounter={id:13};
appState.currentTaskId=11;
appState.currentTask={current_record_revision_id:81};
appState.currentRecordFields={chief_complaint:{value:'尚未保存的修改'}};
appState.currentDraft='当前编辑正文';
appState.recordEditMode=true;
appState.recordEditDirty=true;
appState.recordEditBaseline={chief_complaint:{value:'已保存新版'}};
appState.currentExportReadiness={revision_id:81,revision_number:2,approved:false};
appState.approvalMissingDecisions={physical_exam:'accept_missing'};
const versions = [
 {id:80,encounter_id:13,revision_no:1,source:'generation',created_at:'2026-10-20T01:00:00Z',
  fields_json:JSON.stringify({chief_complaint:{value:'已保存旧版',status:'complete',missing:false,
    source_spans:[{text:'旧版原文',index:1}]}}),draft_text:'旧版保存全文'},
 {id:81,encounter_id:13,revision_no:2,source:'doctor_review',created_at:'2026-10-20T01:01:00Z',
  fields_json:JSON.stringify({chief_complaint:{value:'已保存新版',status:'complete',missing:false,
    source_spans:[{text:'新版原文',index:2}]}}),draft_text:'新版保存全文'},
];
const detail={id:13,current_revision_id:81,revisions:versions};
const protectedState=()=>JSON.stringify({fields:appState.currentRecordFields,draft:appState.currentDraft,
 dirty:appState.recordEditDirty,editing:appState.recordEditMode,baseline:appState.recordEditBaseline,
 readiness:appState.currentExportReadiness,decisions:appState.approvalMissingDecisions,
 task:appState.currentTask,encounter:appState.currentEncounter});
'''


def test_saved_snapshot_parser_never_substitutes_current_or_another_snapshot():
    result = run_browser_logic(r'''
appState.currentRecordFields={chief_complaint:{value:'当前病历不应借用'}};
const own={chief_complaint:{value:'旧版原文'}};
const parsed=savedRevisionFields({fields_json:JSON.stringify(own),result_json:JSON.stringify({fields:{chief_complaint:{value:'不同结果'}}})});
const fallback=savedRevisionFields({result_json:JSON.stringify({fields:own})});
const corrupt=savedRevisionFields({fields_json:'{broken',result_json:JSON.stringify({fields:own})});
const malformed=[null,'null','[]','[]broken'].map(fields_json=>savedRevisionFields({fields_json}));
console.log(JSON.stringify({parsed,fallback,corrupt,malformed,current:appState.currentRecordFields}));
''')
    own = {'chief_complaint': {'value': '旧版原文'}}
    assert result['parsed'] == result['fallback'] == own
    assert result['corrupt'] is None
    assert result['malformed'] == [None] * 4
    assert result['current']['chief_complaint']['value'] == '当前病历不应借用'


def test_history_comparison_escapes_saved_text_and_uses_that_versions_evidence():
    result = run_browser_logic(HISTORY_SETUP + r'''
const old=JSON.parse(versions[0].fields_json);
old.chief_complaint.value='<img src=x onerror=alert(1)>';
old.chief_complaint.source_spans=[{text:'<script>历史引文</script>'}];
old.candidate_diagnoses=[{name:'<b>历史候选</b>'}];
versions[0].fields_json=JSON.stringify(old);
versions[0].source='<u>来源</u>';
versions[0].draft_text='<svg onload=alert(2)>';
const html=recordHistoryMarkup({revisions:versions,currentId:81,selectedId:80,encounterId:13,editing:true});
console.log(JSON.stringify({html}));
''')
    html = result['html']
    assert '<img' not in html and '<script>' not in html and '<svg' not in html
    assert '&lt;img src=x onerror=alert(1)&gt;' in html
    assert '&lt;script&gt;历史引文&lt;/script&gt;' in html
    assert '&lt;b&gt;历史候选&lt;/b&gt;' in html
    assert '&lt;u&gt;来源&lt;/u&gt;' in html
    assert '已保存新版' in html and '新版原文' not in html
    assert '1项字段内容或采集状态不同' in html
    assert '不包含尚未保存的修改' in html
    assert '尚未保存的修改</p>' not in html
    assert '当前版本 2' in html
    assert '当前版本 81' not in html


def test_open_and_select_history_only_reads_and_preserves_current_edit_and_review():
    result = run_browser_logic(HISTORY_SETUP + r'''
const before=protectedState();const calls=[];
api=async (path,options={})=>{calls.push({path,method:options.method||'GET'});return detail};
await openRecordHistory();
const first=content.innerHTML;const selected=recordHistoryView.selectedId;
selectRecordHistoryVersion('81');const current=content.innerHTML;
selectRecordHistoryVersion('999');
console.log(JSON.stringify({calls,selected,first,current,unchanged:protectedState()===before,
 selectedAfter:recordHistoryView.selectedId,htmlAfter:content.innerHTML}));
''')
    assert result['calls'] == [{'path': '/api/encounters/13', 'method': 'GET'}]
    assert result['selected'] == 80
    assert result['selectedAfter'] == 81
    assert result['unchanged']
    assert '旧版原文' in result['first']
    assert '新版原文' in result['current']
    assert '旧版原文' not in result['current']
    assert '当前已保存版本' in result['current']
    assert result['htmlAfter'] == result['current']


@pytest.mark.parametrize('invalidate', [
    'appState.encounterRestoreVersion++;appState.currentEncounter={id:14};appState.currentTaskId=12;',
    'detailDrawerVersion++;content.innerHTML="已关闭";',
    'appState.currentTask={current_record_revision_id:82};',
    'appState.authUser=null;',
])
def test_late_history_response_cannot_reopen_closed_or_replaced_context(invalidate):
    result = run_browser_logic(HISTORY_SETUP + r'''
let release;api=()=>new Promise(resolve=>release=resolve);
const pending=openRecordHistory();
''' + invalidate + r'''
const before=content.innerHTML;
release(detail);await pending;
console.log(JSON.stringify({unchanged:content.innerHTML===before,view:recordHistoryView,html:content.innerHTML}));
''')
    assert result['unchanged']
    assert result['view'] is None
    assert '旧版原文' not in result['html']


@pytest.mark.parametrize('wrong_data', [
    'detail.id=14;',
    'detail.revisions[0].encounter_id=14;',
])
def test_history_rejects_mismatched_encounter_without_leaking_content(wrong_data):
    result = run_browser_logic(HISTORY_SETUP + wrong_data + r'''
const before=protectedState();api=async()=>detail;
await openRecordHistory();
console.log(JSON.stringify({html:content.innerHTML,view:recordHistoryView,unchanged:protectedState()===before}));
''')
    assert '历史版本读取失败' in result['html']
    assert '旧版原文' not in result['html']
    assert result['view'] is None
    assert result['unchanged']


def test_read_failure_keeps_edits_and_offers_explicit_retry_without_automatic_calls():
    result = run_browser_logic(HISTORY_SETUP + r'''
const before=protectedState();let calls=0;
api=async()=>{calls++;throw Error('403 denied')};
await openRecordHistory();
console.log(JSON.stringify({calls,html:content.innerHTML,unchanged:protectedState()===before}));
''')
    assert result['calls'] == 1
    assert '重新加载历史版本' in result['html']
    assert result['unchanged']


def test_missing_login_or_encounter_cannot_read_history():
    result = run_browser_logic(HISTORY_SETUP + r'''
let calls=0;api=async()=>{calls++;return detail};
appState.authUser=null;await openRecordHistory();
appState.authUser={id:1};appState.currentEncounter=null;await openRecordHistory();
console.log(JSON.stringify({calls}));
''')
    assert result['calls'] == 0


def test_version_label_uses_matching_local_number_never_global_primary_key():
    result = run_browser_logic(HISTORY_SETUP + r'''
appState.currentEncounter={id:13,current_revision:{id:81,revision_no:2,content_hash:'saved'}};
appState.currentExportReadiness={revision_id:80,revision_number:1,content_hash:'stale'};
const matching=currentRevisionInfo();
appState.currentTask={current_record_revision_id:82,result_json:{record_revision:{id:81,revision_no:2,content_hash:'old'}}};
const absent=currentRevisionInfo();
appState.currentTask={current_record_revision_id:81};
appState.currentEncounter={id:13,revisions:[{id:81,revision_no:2,content_hash:'list'}]};
const fromList=currentRevisionInfo();
console.log(JSON.stringify({matching,absent,fromList}));
''')
    assert result['matching'] == {'revisionId': 81, 'revisionNumber': 2, 'contentHash': 'saved'}
    assert result['absent'] == {'revisionId': 82, 'revisionNumber': None, 'contentHash': ''}
    assert result['fromList'] == {'revisionId': 81, 'revisionNumber': 2, 'contentHash': 'list'}
