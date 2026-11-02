"""Node-only review accounting: no browser session or clinical operation."""
import pytest

from tests.test_doctor_history_restore import run_browser_logic


@pytest.mark.parametrize("status,value", [("partial", "发热两天"), ("conflicting", "发热两天"), ("missing", None)])
def test_episode_gap_is_one_actionable_issue_not_an_accept_missing_choice(status, value):
    import json
    observed = run_browser_logic(r'''
const field = {status:STATUS, value:VALUE, missing:!VALUE, doctor_review_status:"pending",
 missing_elements:["本次病程用药待核对（原文第4段）：患者：昨天吃过一次布洛芬"]};
const fields={present_illness:field,candidate_diagnoses:[]};
approvalFieldItems=()=>[{key:"present_illness",title:"现病史",field}];
currentRevisionIsSigned=()=>false;currentRevisionInfo=()=>({revisionNumber:1});
const html=renderApprovalChecklist(fields);
console.log(JSON.stringify({pending:pendingApprovalCount(fields),
 missingChoice:html.includes('data-approval-missing-key="present_illness"'),
 itemCount:recordReviewSummary(fields,false).items.length}));
'''.replace("STATUS", json.dumps(status)).replace("VALUE", json.dumps(value, ensure_ascii=False)))
    assert observed == {"pending": 1, "missingChoice": False, "itemCount": 1}
