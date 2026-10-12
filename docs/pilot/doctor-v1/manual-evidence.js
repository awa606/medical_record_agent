// Replaced only in a local generated handbook, with screenshots of its exact deployment.
window.MRA_MANUAL_EVIDENCE = {version: "候选版通用步骤；本地截图版与PDF由维护人员按实际部署生成。", screenshots: []};
if (new URLSearchParams(window.location.search).get("offline") === "1") {
  const notice = document.createElement("p");
  notice.className = "notice";
  notice.textContent = "离线操作手册：服务当前不可用。此文件随本地版本保存，页面与最新运行版可能不同；不能在手册内生成或修改病历。";
  document.body.prepend(notice);
}
