"""Full-generator regressions for guardian patient references; no model calls."""
import json
import os
from unittest.mock import patch

import pytest

from app.services.llm.base import LLMProviderResponse, LLMProviderUnavailableError
from app.services.llm.llm_record_generator import FIELD_KEYS, LLMRecordGenerator


def generate(tmp_path, source, quote, value, *, key='present_illness', index=0, trusted=None):
    payload = {name: {'value': None, 'missing': True, 'hint': None,
                     'confidence': None, 'source_spans': []} for name in FIELD_KEYS}
    payload[key] = {'value': value, 'missing': False, 'hint': None, 'confidence': 0.9,
                    'source_spans': [{'text': quote, 'index': index}]}
    payload['candidate_diagnoses'] = []

    class Replay:
        name, model = 'online', 'fixed-response-no-inference'

        def generate_fields_json(self, text, *, timeout_seconds):
            return LLMProviderResponse(self.name, self.model, json.dumps(payload, ensure_ascii=False), 0)

    with patch.dict(os.environ, {'MRA_ANONYMIZE': '1', 'MEDICAL_RECORD_AGENT_DB': str(tmp_path / 'isolated.sqlite3')}):
        generator = LLMRecordGenerator(provider=Replay(), mode='live', allow_mock_fallback=False)
        generator.max_retries = 0
        generator.diagnostics_enabled = True
        generator.source_segments = trusted
        try:
            generator.extract_fields(source)
        except LLMProviderUnavailableError:
            pass
        assert generator.attempt_count == 1
        return generator.diagnostic_attempts[0]['grounded'][key]


def test_child_reference_in_quote_can_ground_patient_field_without_repeating_child(tmp_path):
    field = generate(tmp_path, '家长：孩子咳嗽两天，咽痛。', '孩子咳嗽两天，咽痛', '咳嗽两天，咽痛')
    assert field['status'] == 'complete'


def test_child_quote_shorthand_stays_patient_with_parent_own_history_elsewhere(tmp_path):
    field = generate(tmp_path, '家长：孩子咳嗽两天。我自己有高血压。', '孩子咳嗽两天', '咳嗽两天')
    assert field['status'] == 'complete'


def test_full_child_subject_is_already_accepted(tmp_path):
    field = generate(tmp_path, '家长：孩子咳嗽两天，咽痛。', '孩子咳嗽两天，咽痛', '孩子咳嗽两天，咽痛')
    assert field['status'] == 'complete'


@pytest.mark.parametrize('source,quote,value,key,index', [
    ('家长：我自己咳嗽两天。', '我自己咳嗽两天', '咳嗽两天', 'present_illness', 0),
    ('家长：孩子咳嗽两天。我自己有高血压。', '我自己有高血压', '有高血压', 'past_history', 1),
    ('患者：孩子咳嗽两天。', '孩子咳嗽两天', '咳嗽两天', 'present_illness', 0),
    ('家长：咳嗽两天。', '咳嗽两天', '咳嗽两天', 'present_illness', 0),
    ('家长：孩子昨天咳嗽。', '孩子昨天咳嗽', '孩子咳嗽', 'present_illness', 0),
    ('家长：孩子可能咳嗽两天。', '孩子可能咳嗽两天', '孩子咳嗽两天', 'present_illness', 0),
    ('家长：孩子没有胸痛。', '孩子没有胸痛', '孩子胸痛', 'present_illness', 0),
])
def test_shorthand_must_not_accept_parent_facts_ambiguity_or_qualifier_loss(tmp_path, source, quote, value, key, index):
    assert generate(tmp_path, source, quote, value, key=key, index=index)['status'] == 'conflicting'


def test_child_quote_does_not_bypass_unconfirmed_audio_role(tmp_path):
    quote = '孩子咳嗽两天'
    field = generate(tmp_path, '家长：孩子咳嗽两天。', quote, quote,
                     trusted=[{'segment_id': 's1', 'text': quote, 'role': '待确认'}])
    assert field['status'] == 'conflicting'


def test_guardian_question_cannot_be_promoted_to_patient_fact(tmp_path):
    field = generate(tmp_path, '家长：孩子咳嗽两天吗？', '孩子咳嗽两天吗', '孩子咳嗽两天')
    assert field['status'] == 'conflicting'


@pytest.mark.parametrize('source,quote,value,index', [
    ('家属：孩子咳嗽两天。', '孩子咳嗽两天', '咳嗽两天', 0),
    ('家长：儿子咳嗽两天。', '儿子咳嗽两天', '咳嗽两天', 0),
    ('家长：女儿咳嗽两天。', '女儿咳嗽两天', '咳嗽两天', 0),
])
def test_explicit_guardian_child_reference_is_bound_to_quoted_context(tmp_path, source, quote, value, index):
    assert generate(tmp_path, source, quote, value, index=index)['status'] == 'complete'


@pytest.mark.parametrize('source,quote,value,index', [
    ('家长：孩子咳嗽两天。患者：孩子胸痛。', '孩子胸痛', '胸痛', 1),
    ('家长：孩子咳嗽两天。家长：我自己胸痛。', '我自己胸痛', '胸痛', 1),
    ('家长：孩子的父亲咳嗽两天。', '孩子的父亲咳嗽两天', '咳嗽两天', 0),
    ('家属：孩子是否咳嗽两天？', '孩子是否咳嗽两天', '咳嗽两天', 0),
    ('家长：孩子发热。孩子有没有胸痛？', '孩子有没有胸痛', '孩子胸痛', 1),
    ('家长：孩子可能咳嗽两天。', '孩子可能咳嗽两天', '咳嗽两天', 0),
    ('家长：我自己咳嗽，但是孩子咽痛。', '我自己咳嗽，但是孩子咽痛', '咳嗽，但是孩子咽痛', 0),
    ('家长：孩子咽痛，但是我自己咳嗽。', '孩子咽痛，但是我自己咳嗽', '咽痛，但是咳嗽', 0),
])
def test_guardian_shorthand_cannot_borrow_other_subject_or_question_context(tmp_path, source, quote, value, index):
    assert generate(tmp_path, source, quote, value, index=index)['status'] == 'conflicting'
