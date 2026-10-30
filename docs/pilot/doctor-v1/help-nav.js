(() => {
  if (window.top !== window.self) return;
  const style = document.createElement("style");
  style.textContent = `
    .help-nav-back {
      position: fixed; left: 16px; bottom: 16px; z-index: 50;
      min-height: 44px; padding: 10px 16px;
      border: 1px solid #9aafbf; border-radius: 6px;
      background: #ffffff; color: #0b3d66;
      font: 600 15px/1.3 "Microsoft YaHei", "Segoe UI", sans-serif;
      box-shadow: 0 2px 8px rgba(15, 45, 70, 0.16); cursor: pointer;
    }
    .help-nav-back:focus-visible { outline: 3px solid #1580bd; outline-offset: 3px; }
  `;
  document.head.appendChild(style);
  const button = document.createElement("button");
  button.type = "button";
  button.className = "help-nav-back";
  button.textContent = "← 返回上一页";
  button.addEventListener("click", () => {
    if (window.history.length > 1) window.history.back();
    else window.location.href = "index.html";
  });
  document.body.appendChild(button);
})();
