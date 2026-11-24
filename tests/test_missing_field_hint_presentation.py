"""Verify separation of field values, historical hints, and question prompts."""
import json
from html.parser import HTMLParser

import pytest

from tests.test_doctor_history_restore import run_browser_logic


class HintDisclosure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.details = []

    def handle_starttag(self, tag, attrs):
        if tag == "details":
            self.details.append(dict(attrs))


@pytest.mark.parametrize("hint, question", [
    ("医生未进行查体", False),
    ("患者提及左腕曾有疼痛，但未明确既往史", False),
    ("血压测了，数值仍未传回来", False),
    ("建议补问：发热多久？", True),
    ("最近有没有量体温？", True),
    ("建议补问：病人左腕骨折。什么时候确诊？", False),
])
def test_missing_hint_stays_separate_from_value_and_source(hint, question):
    field = {"value": None, "status": "missing", "missing": True, "hint": hint,
             "source_spans": [{"text": "现在还没有听诊", "index": 0}]}
    result = run_browser_logic("const field=" + json.dumps(field, ensure_ascii=False) + """;
const before=JSON.stringify(field);
console.log(JSON.stringify({value: fieldValue({physical_exam:field}, "physical_exam"),
    draftHint:originalFieldHint(field),signedHint:originalFieldHint(field,true),
    unchanged:before===JSON.stringify(field)}));
""")
    assert result["unchanged"]
    assert result["value"] == "此栏尚无已记录的内容，请核对原文或补录。"
    for key, open_by_default in (("draftHint", question), ("signedHint", False)):
        disclosure = HintDisclosure()
        disclosure.feed(result[key])
        assert len(disclosure.details) == 1
        assert ("open" in disclosure.details[0]) == open_by_default
        assert hint in result[key]


@pytest.mark.parametrize("value", ["本次未进行查体", "我按过右下腹，没发现压痛"])
def test_clinician_value_and_observed_negative_are_preserved(value):
    result = run_browser_logic("const value="+json.dumps(value, ensure_ascii=False)+""";
const field={value,missing:false,hint:'需要复核',status:'complete',source_spans:[]};
console.log(JSON.stringify([fieldValue({physical_exam:field},'physical_exam'),originalFieldHint(field)]));
""")
    assert result == [value, ""]


def test_treatment_reference_and_assistant_keep_hints_out_of_the_plan():
    result = run_browser_logic("""
const field={value:null,missing:true,hint:'合成未核实处理内容',source_spans:[]};
activeRecordFields=()=>({treatment_plan:field,candidate_diagnoses:[]});
previewTreatmentText=()=>'';
renderReferenceTabs=({patient})=>patient;
renderClinicalReferenceContext=()=>'';
allEvidence=()=>[]; missingItems=()=>[]; riskSummary=()=>({warnings:[],errors:[]});
console.log(JSON.stringify([renderTreatmentReferenceDetail(),renderAssistDetailContent('treatment')]));
""")
    for html in result:
        assert html.count("合成未核实处理内容") == 1
        trace = html.split("data-original-field-hint", 1)[1].split("</details>", 1)[0]
        assert "合成未核实处理内容" in trace
        assert "暂无明确处理建议，需医生补充。" in html
