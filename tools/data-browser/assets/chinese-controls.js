/* Translate only Datasette's generated menu controls, never record text. */
document.addEventListener("DOMContentLoaded", () => {
  const labels = {
    ".dropdown-sort-asc": "升序排列", ".dropdown-sort-desc": "降序排列",
    ".dropdown-facet": "按此字段分组", ".dropdown-hide-column": "隐藏此列",
    ".dropdown-show-all-columns": "显示全部列", ".dropdown-not-blank": "仅显示非空记录"
  };
  const translateMenu = () => {
    document.querySelectorAll('a[aria-label="Remove this filter"], a[title="Remove this filter"]').forEach(el => {
      el.title = "移除这一筛选"; el.setAttribute("aria-label", "移除这一筛选");
    });
    for (const [selector, label] of Object.entries(labels)) {
      document.querySelectorAll(selector).forEach(el => { if (el.textContent !== label) el.textContent = label; });
    }
  };
  translateMenu();
  new MutationObserver(translateMenu).observe(document.body, { childList: true, subtree: true });
});
