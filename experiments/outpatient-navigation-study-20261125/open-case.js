// Bring both rounds to the same starting point after the normal encounter restore completes.
(() => {
  const expected = new URL(location.href).searchParams.get('encounter_id');
  const deadline = Date.now() + 30000;
  function openField() {
    const button = document.querySelector('#recordFields [data-knowledge-field="past_history"]');
    if (button && !appState.busy && String(selectedEncounterId()) === expected &&
        appState.currentTask?.current_record_revision_id && document.body.dataset.productView === 'encounter') {
      button.focus();
      button.click();
      return;
    }
    if (Date.now() < deadline) {
      setTimeout(openField, 80);
    } else {
      const message = document.createElement('p');
      message.setAttribute('role','alert');
      message.textContent = '本轮资料未能自动打开。请关闭本页，从任务页重新进入本轮。';
      document.body.prepend(message);
    }
  }
  openField();
})();
