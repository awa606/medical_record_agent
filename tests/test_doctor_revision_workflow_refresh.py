"""A saved revision must invalidate the previously exported UI state."""
import json
import subprocess
from pathlib import Path


def test_refresh_task_reloads_persisted_encounter_after_review():
    source = Path("static/doctor.js").read_text(encoding="utf-8")
    state_functions = source[source.index("const WORKFLOW_STATE_BY_BACKEND_TOKEN"):source.index("function currentWorkflowState()")]
    refresh = source[source.index("async function refreshTask("):source.index("function listenForEvents(")]
    script = state_functions + refresh + """
const appState = {
  currentEncounter: {id: 13, task_id: 9, status: 'exported'},
  currentTaskId: 9, approvalRevisionId: 19,
  currentExportReadiness: {revision_id: 19},
};
const requested = [];
const api = async path => {
  requested.push(path);
  if (path === '/api/tasks/9/steps') return [];
  if (path === '/api/encounters/13') return {id: 13, task_id: 9, status: 'pending_review', current_revision_id: 20};
  throw Error('unexpected request: ' + path);
};
const selectedEncounterId = () => appState.currentEncounter?.id;
const syncApprovalReviewStateWithRevision = () => {};
const refreshKnowledgeEvidence = async () => {};
const refreshAgentTrace = async () => {};
let renderedState;
const renderAll = () => { renderedState = derivePersistedWorkflowState({
  encounterStatus: appState.currentEncounter.status,
  taskStatus: appState.currentTask.status,
  currentStage: appState.currentTask.current_stage,
  hasTask: true, hasFields: true,
}); };
(async () => {
  await refreshTask(9, {id: 9, status: 'WAITING_DOCTOR_REVIEW', current_stage: 'reviewed', current_record_revision_id: 20, result_json: {fields: {}, draft: 'synthetic'}});
  console.log(JSON.stringify({renderedState, encounter: appState.currentEncounter, requested}));
})().catch(e => {console.error(e); process.exitCode=1;});
"""
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    observed = json.loads(result.stdout)
    assert observed["renderedState"] == "pending_review"
    assert observed["encounter"]["current_revision_id"] == 20
    assert "/api/encounters/13" in observed["requested"]
