const deployedVersion = window.MRA_MANUAL_EVIDENCE?.app_git_sha;
if (deployedVersion) document.querySelector('[name="version"]').value = deployedVersion;
document.querySelector('#feedbackForm').addEventListener('submit', event => {
  event.preventDefault();
  const form = event.currentTarget;
  if (!form.reportValidity()) return;
  const values = Object.fromEntries(new FormData(form));
  const payload = {schema_version: 'mra-doctor-feedback-v1', created_at: new Date().toISOString(),
    scope: 'synthetic_and_simulated_only', ...values};
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], {type: 'application/json;charset=utf-8'}));
  const link = document.createElement('a'); link.href = url;
  link.download = 'medilisten-feedback-' + new Date().toISOString().replace(/[:.]/g, '-') + '.json';
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10000);
  document.querySelector('#notice').textContent = '已请求下载。请检查下载目录，再把文件交给试用组织者；本页面没有上传。内容仍保留，可继续修改。';
});
