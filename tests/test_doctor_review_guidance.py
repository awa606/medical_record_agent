"""Targeted display and review navigation checks; no browser or model calls."""
import pytest
from tests.test_doctor_history_restore import run_browser_logic


@pytest.mark.parametrize("state,editing,visible", [
    ("pending_review", False, False), ("approved", False, False),
    ("exported", False, False), ("incomplete", False, True),
    ("pending_review", True, False),
])
def test_routine_banner_does_not_duplicate_review_or_edit_notices(state, editing, visible):
    import json
    result = run_browser_logic("""
const notice={}; document.getElementById=()=>notice;
appState.currentRecordFields={chief_complaint:{value:'合成内容'}};
appState.recordEditMode=EDITING; doctorDisplayState=()=>({key:STATE});
renderReviewBoundaryNotice();
console.log(JSON.stringify({visible:!notice.hidden,text:notice.textContent}));
""".replace("EDITING", json.dumps(editing)).replace("STATE", json.dumps(state)))
    assert result["visible"] is visible
    assert ("历史病历内容不完整" in result["text"]) is visible


def test_pending_review_opens_checklist_without_submission_or_error():
    result = run_browser_logic(r"""
const calls=[];let focus=false;const list={scrollTop:300};
document.querySelector=()=>({focus(){focus=true}});
document.getElementById=()=>list;
appState.currentTaskId=1;
appState.currentRecordFields={chief_complaint:{value:'发热',status:'complete',missing:false}};
approvalFieldItems=()=>[{key:'chief_complaint',title:'主诉',field:appState.currentRecordFields.chief_complaint}];
renderFields=()=>{};renderFooter=()=>{};
api=async p=>{calls.push(p);return {}};
refreshExportReadiness=async()=>{calls.push('readiness');return {}};
await confirmFields();
console.log(JSON.stringify({calls,open:appState.approvalDisclosureOpen,focus,
 scroll:list.scrollTop,busy:!!appState.busy,error:appState.lastActionError||'',
 autoConfirmed:!!appState.approvalRegularFieldsConfirmed}));
""")
    assert result == dict(calls=[], open=True, focus=True, scroll=0,
                          busy=False, error="", autoConfirmed=False)


def test_no_pending_items_still_requires_explicit_submit_and_original_payload():
    result = run_browser_logic(r"""
appState.currentTaskId=8;pendingApprovalCount=()=>0;
const expected={revision_id:9,content_hash:'approved-revision-hash',field_decisions:[{field:'chief_complaint',action:'confirm_content'}]};
let calls=[];buildTaskApprovalPayload=async()=>expected;
api=async (path,request)=>{calls.push({path,method:request.method,body:JSON.parse(request.body)});return {id:8}};
refreshTask=async()=>{};refreshExportReadiness=async()=>({});
await confirmFields();console.log(JSON.stringify({calls,error:appState.lastActionError||''}));
""")
    assert result["error"] == ""
    assert result["calls"] == [{
        "path": "/api/tasks/8/approve", "method": "POST",
        "body": {"revision_id": 9, "content_hash": "approved-revision-hash",
                 "field_decisions": [{"field": "chief_complaint", "action": "confirm_content"}]},
    }]


def test_pending_navigation_cannot_bypass_unsaved_edit_guard():
    result = run_browser_logic(r"""
appState.currentTaskId=1;appState.recordEditDirty=true;
pendingApprovalCount=()=>1;let calls=0;api=async()=>{calls++;};
await confirmFields();
console.log(JSON.stringify({calls,error:appState.lastActionError}));
""")
    assert result["calls"] == 0
    assert "请先保存或取消" in result["error"]


def test_checklist_stays_collapsed_and_does_not_hide_real_field_problems():
    result = run_browser_logic(r"""
appState.currentTaskId=1;appState.approvalDisclosureOpen=false;
currentRevisionIsSigned=()=>false;currentRevisionInfo=()=>({revisionNumber:2});
const fields={present_illness:{value:'发热两天',missing:false,status:'partial',
 missing_elements:['本次病程用药待核对（原文第4段）：患者：昨天吃过一次布洛芬']},
 family_history:{value:'错误内容',status:'conflicting',missing:false}};
approvalFieldItems=()=>Object.entries(fields).map(([key,field])=>({key,title:key,field}));
const html=renderApprovalChecklist(fields);
console.log(JSON.stringify({html,summary:recordReviewSummary(fields,false)}));
""")
    assert len(result["summary"]["items"]) == 2
    html = result["html"]
    assert '<details class="approval-disclosure" >' in html
    assert '<details class="review-instructions">' in html
    assert "2项异常 · 展开处理" in html
    assert "用药漏记" in html
    assert 'data-record-edit-field="family_history"' in html
    assert 'data-approval-missing-key="present_illness"' not in html


def test_footer_label_tracks_pending_state_without_creating_decisions():
    result = run_browser_logic(r"""
const nodes=new Map();
document.getElementById=id=>{if(!nodes.has(id))nodes.set(id,{classList:{toggle(){},add(){},remove(){}},dataset:{},setAttribute(){}});return nodes.get(id)};
document.querySelector=()=>null;
doctorDisplayState=()=>({key:'pending_review'});
appState.currentTaskId=1;appState.currentRecordFields={};
let pending=1;pendingApprovalCount=()=>pending;
renderFooter();const before=nodes.get('confirmFieldsButton').textContent;
pending=0;renderFooter();
console.log(JSON.stringify({before,after:nodes.get('confirmFieldsButton').textContent}));
""")
    assert result == {"before": "核对病历", "after": "完成病历审核"}
