(() => {
  if (window.top !== window.self) return;
  const style = document.createElement("style");
  style.textContent = `
    .help-back-bar {
      padding: 10px 16px; background: #ffffff; border-bottom: 1px solid #d8e0e7;
    }
    .help-nav-back {
      min-height: 44px; padding: 8px 16px;
      border: 1px solid #9aafbf; border-radius: 6px;
      background: #ffffff; color: #0b3d66;
      font: 600 15px/1.3 "Microsoft YaHei", "Segoe UI", sans-serif;
      cursor: pointer;
    }
    .help-nav-back:focus-visible { outline: 3px solid #1580bd; outline-offset: 3px; }
  `;
  document.head.appendChild(style);
  const bar = document.createElement("div");
  bar.className = "help-back-bar";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "help-nav-back";
  button.textContent = "← 返回上一页";
  button.addEventListener("click", () => {
    if (window.history.length > 1) window.history.back();
    else window.location.href = "index.html";
  });
  bar.appendChild(button);
  const header = document.querySelector("header");
  if (header && header.parentElement === document.body) header.insertAdjacentElement("afterend", bar);
  else document.body.prepend(bar);
})();
