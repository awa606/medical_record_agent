"""Protect individual speaker reviews when an ordinary doctor saves a whole-group choice."""
from tests.test_doctor_history_restore import run_browser_logic


SETUP = r"""
const segments = [
  {speaker_id:'A',role:'陪同人员',role_source:'manual',reviewed_by_doctor:true,text:'甲'},
  {speaker_id:'A',role:'医生',reviewed_by_doctor:true,text:'乙'},
];
appState.currentAsrResult = {segments, role_quality:{status:'passed'},speaker_assignments:[
  {speaker_id:'A',role:'陪同人员',source:'manual_speaker_map',confidence:0.99},
]};
showToast=()=>{}; renderAll=()=>{}; resetRecordPreview=()=>{};
"""


def test_saved_mixed_group_is_reviewable_and_untouched_until_individual_roles_agree():
    result = run_browser_logic(SETUP + r"""
const before = JSON.stringify(segments);
updateSpeakerRole('A','陪同人员');
console.log(JSON.stringify({
  complete:roleQualityPassed(), needsReview:roleReviewRequired(),
  unchanged:before===JSON.stringify(segments), maps:speakerRolesForReviewSave(),
}));
""")
    assert result == {'complete': False, 'needsReview': True, 'unchanged': True, 'maps': []}


def test_only_a_chosen_compatible_group_is_sent_and_implicit_suggestions_are_omitted():
    result = run_browser_logic(SETUP + r"""
segments[1].reviewed_by_doctor=false;
const original = JSON.stringify(segments);
const before=speakerRolesForReviewSave();
updateSpeakerRole('A','医生');
const rejected=speakerRolesForReviewSave();
updateSpeakerRole('A','陪同人员');
console.log(JSON.stringify({before,rejected,accepted:speakerRolesForReviewSave(),unchanged:original===JSON.stringify(segments)}));
""")
    assert result == {'before': [], 'rejected': [], 'accepted': [
        {'speaker_id': 'A', 'role': '陪同人员', 'reviewed_by_doctor': True},
    ], 'unchanged': True}


def test_text_edit_alone_retains_an_unreviewed_role():
    result = run_browser_logic(SETUP + r"""
segments[1].reviewed_by_doctor=false; segments[1].role_source='rules';
renderFields=()=>{}; renderRunContext=()=>{}; syncAsrTextFromSegments=()=>{};
updateReviewSegment(1,{text:'订正后的文字'});
console.log(JSON.stringify({change:appState.segmentReviewCorrections,reviewed:segments[1].reviewed_by_doctor,
  role:segments[1].role,maps:speakerRolesForReviewSave()}));
""")
    assert result == {'change': {'1': {'text': '订正后的文字'}}, 'reviewed': False, 'role': '医生', 'maps': []}


def test_conflicting_review_help_and_listening_are_visible_in_the_mobile_doctor_drawer():
    import base64
    import io
    import wave

    from playwright.sync_api import expect, sync_playwright
    from tests.test_doctor_itemized_approval_playwright import RunningServer, _login
    from tests.test_doctor_role_review_recovery_playwright import _inject_role_result

    audio = io.BytesIO()
    with wave.open(audio, 'wb') as recording:
        recording.setparams((1, 1, 8000, 0, 'NONE', 'not compressed'))
        recording.writeframes(b'\x80' * 8000 * 12)
    audio_url = 'data:audio/wav;base64,' + base64.b64encode(audio.getvalue()).decode()
    server = RunningServer()
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={'width': 390, 'height': 844})
            _login(page, server.base_url)
            _inject_role_result(page, status='needs_review')
            page.evaluate("""
                audioUrl => {
                  const asr = appState.currentAsrResult;
                  asr.segments = [
                    {segment_id:'a',speaker_id:'spk1',role:'陪同人员',role_source:'manual',reviewed_by_doctor:true,text:'甲',start_time:1,end_time:3},
                    {segment_id:'b',speaker_id:'spk1',role:'医生',role_source:'manual',reviewed_by_doctor:true,text:'乙',start_time:6,end_time:8},
                  ];
                  appState.liveTranscriptSegments = asr.segments;
                  appState.audioDurationSeconds = 12;
                  document.getElementById('consultationAudio').src = audioUrl;
                  renderAll();
                }
            """, audio_url)
            page.locator('#showTranscriptButton').click()
            page.locator('[data-workflow-action="open-role-review"]').click()
            note = page.locator('[data-speaker-review-evidence]')
            expect(note.get_by_text('同一组有不同的已核身份', exact=False)).to_be_visible()
            expect(page.locator('[data-speaker-role-select][data-speaker-id="spk1"]')).to_be_disabled()
            listen = note.get_by_role('button', name='回听第2段 00:06 · 医生')
            expect(listen).to_be_visible()
            page.wait_for_function("document.getElementById('consultationAudio').readyState >= 1")
            listen.click()
            page.wait_for_function("document.getElementById('consultationAudio').currentTime >= 6")
            assert page.locator('#detailDrawerContent').evaluate('el => el.scrollWidth <= el.clientWidth')
            browser.close()
    finally:
        server.close()
