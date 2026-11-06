/* 纯前端样稿：无 API、无麦克风、无持久化。确认版式后再接现有业务适配器。 */
"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const fields = [
    {
      key: "chief_complaint",
      title: "主诉",
      text: "发热伴咳嗽、咽痛 1 天。",
      source: "00:08—00:15",
    },
    {
      key: "present_illness",
      title: "现病史",
      text: "患者诉今日开始发热，自测体温 38.2℃，伴咳嗽和咽痛。否认胸痛。其余伴随症状及已用药情况尚待问诊补充。",
      source: "00:08—00:32",
    },
    {
      key: "past_history",
      title: "既往史",
      text: "未提及，待医生补充。",
      missing: true,
    },
    {
      key: "allergy_history",
      title: "过敏史",
      text: "患者否认花生过敏及药物过敏史。",
      source: "00:35—00:43",
    },
    {
      key: "physical_exam",
      title: "查体",
      text: "未查体，待医生补充。",
      missing: true,
    },
    {
      key: "preliminary_diagnosis",
      title: "初步诊断",
      text: "待医生结合问诊、查体及检查结果判断。",
      missing: true,
    },
    { key: "plan", title: "处理意见", text: "待医生填写。", missing: true },
  ];
  const transcripts = [
    ["医生", "00:02", "今天主要有什么不舒服？"],
    ["患者", "00:08", "今天发热，体温三十八点二度，有咳嗽和咽痛。"],
    ["医生", "00:23", "有没有胸痛？"],
    ["患者", "00:27", "没有胸痛。"],
    ["医生", "00:35", "有花生或者药物过敏史吗？"],
    ["患者", "00:39", "我没有花生过敏，也没有药物过敏史。"],
  ];
  const state = {
    mode: "draft",
    revision: 1,
    dirty: false,
    panel: null,
    trigger: null,
    values: {},
    saved: {},
    recording: false,
    paused: false,
    seconds: 13,
  };
  let recordingTimer = null;
  let processingTimer = null;
  let toastTimer = null;
  let confirmAction = null;
  const escape = (value) =>
    String(value).replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const icon = (name) =>
    `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const notify = (message) => {
    clearTimeout(toastTimer);
    $("toast").textContent = message;
    $("toast").hidden = false;
    toastTimer = setTimeout(() => {
      $("toast").hidden = true;
    }, 3500);
  };
  const isEditing = () => ["editing", "conflict"].includes(state.mode);
  function stopTimers() {
    clearInterval(recordingTimer);
    clearTimeout(processingTimer);
    recordingTimer = null;
    processingTimer = null;
  }
  function resetValues() {
    state.values = Object.fromEntries(fields.map((f) => [f.key, f.text]));
    state.saved = { ...state.values };
  }
  function renderFields() {
    $("record-fields").innerHTML = fields
      .map(
        (f) =>
          `<section class="ml-field" data-field="${f.key}"><div class="ml-field-head"><h3>${f.title}</h3>${f.source ? `<button class="ml-source-link" data-source="${f.key}">${icon("link")}原文 ${f.source}</button>` : ""}</div>${isEditing() ? `<textarea aria-label="${f.title}" data-edit="${f.key}" rows="${f.key === "present_illness" ? 4 : 2}">${escape(state.values[f.key])}</textarea>` : `<p class="${f.missing ? "ml-missing" : ""}">${escape(state.values[f.key])}</p>`}</section>`,
      )
      .join("");
  }
  const modes = {
    empty: {
      step: 1,
      badge: "待采集",
      primary: "开始录音",
      secondary: "输入文本",
      hint: "选择输入方式，开始本次就诊记录",
    },
    recording: {
      step: 1,
      badge: "正在录音 · 示意",
      primary: "查看录音",
      secondary: "取消录音",
      hint: "样稿模拟录音状态，不访问物理麦克风",
    },
    processing: {
      step: 2,
      badge: "病历生成中 · 示意",
      primary: "等待生成",
      secondary: "取消",
      hint: "正在整理转写内容与字段证据（状态示意）",
    },
    draft: {
      step: 3,
      badge: "草稿待处理",
      primary: "编辑病历",
      secondary: "开始新录音",
      hint: "核对病历内容后，进入医生审核",
    },
    editing: {
      step: 3,
      badge: "正在编辑",
      primary: "保存修改",
      secondary: "取消修改",
      hint: "修改只存在于样稿；保存后需重新审核",
    },
    review: {
      step: 3,
      badge: "等待医生审核",
      primary: "审核病历",
      secondary: "继续修改",
      hint: "已保存 · 请核对正文和原文证据",
    },
    approved: {
      step: 4,
      badge: "审核完成 · 示意",
      primary: "模拟导出",
      secondary: "修改病历",
      hint: "当前样稿版本已确认；修改后需要重新审核",
    },
    role: {
      step: 2,
      badge: "说话人待确认",
      primary: "确认说话人",
      secondary: "查看转写",
      hint: "先确认说话人身份，才能继续生成",
    },
    conflict: {
      step: 3,
      badge: "版本冲突",
      primary: "查看版本冲突",
      secondary: "保留本地修改",
      hint: "保存已阻止 · 本地修改仍保留",
    },
    failed: {
      step: 2,
      badge: "生成失败",
      primary: "重试当前阶段",
      secondary: "查看转写",
      hint: "已保留转写；只重试失败的病历生成阶段",
    },
    long: {
      step: 3,
      badge: "草稿待处理",
      primary: "编辑病历",
      secondary: "查看转写",
      hint: "长病历完整展示，正文单独纵向滚动",
    },
  };
  function render() {
    const current = modes[state.mode];
    $("scenario").value = state.mode;
    $("phase-badge").textContent = current.badge;
    $("primary-action").querySelector("span").textContent = current.primary;
    $("primary-action").disabled = state.mode === "processing";
    $("secondary-action").textContent = current.secondary;
    $("action-hint").textContent = current.hint;
    $("revision-label").textContent = `Revision ${state.revision}`;
    $("paper-stamp").textContent =
      state.mode === "approved"
        ? "已审核 · 仅为交互示意"
        : "AI 草稿 · 待医生审核";
    document.querySelectorAll("[data-step]").forEach((el, i) => {
      el.classList.toggle("complete", i < current.step);
      el.classList.toggle("current", i === current.step);
    });
    const empty = [
      "empty",
      "recording",
      "processing",
      "role",
      "failed",
    ].includes(state.mode);
    $("paper").hidden = empty;
    $("empty-state").hidden = !empty;
    $("input-options").hidden = state.mode !== "empty";
    const titles = {
      empty: "从这次问诊开始",
      recording: "专注问诊，记录交给工作台",
      processing: "正在整理病历草稿",
      role: "先确认是谁在说话",
      failed: "病历生成暂未完成",
    };
    const descriptions = {
      empty: "录音、上传音频或输入文本，形成可核对的病历草稿。",
      recording: "录音控件在右侧；停止后可以试听、取消或提交。",
      processing: "转写已经保留。您可以打开右侧面板核对内容。",
      role: "说话人身份尚未确认，当前不能生成或导出病历。",
      failed: "样稿展示失败恢复。不会用固定输出冒充真实模型成功。",
    };
    $("empty-title").textContent = titles[state.mode] || "";
    $("empty-description").textContent = descriptions[state.mode] || "";
    $("notice").hidden = !["conflict", "role", "failed"].includes(state.mode);
    $("notice").classList.toggle("error", state.mode === "failed");
    $("notice").textContent =
      {
        conflict:
          "当前病历存在较新版本。本地修改已保留；先查看差异，再重新编辑保存。",
        role: "身份未确认：生成操作已阻止。请核对转写后确认医生和患者。",
        failed:
          "示例失败原因：本地模型响应超时。尚未生成病历；可重试当前阶段。",
      }[state.mode] || "";
    renderFields();
  }
  function setMode(mode, keepValues = true) {
    stopTimers();
    state.recording = false;
    if (!keepValues) {
      resetValues();
      state.revision = 1;
      state.dirty = false;
    }
    state.mode = mode;
    if (mode === "long")
      state.values.present_illness = Array(10)
        .fill(
          fields[1].text + "\n本段为排版压力测试重复内容，不构成新增患者事实。",
        )
        .join("\n\n");
    if (mode === "conflict") {
      state.values.present_illness += "\n本地新增内容示例：请医生进一步核对。";
      state.dirty = true;
    }
    render();
    $("paper-scroll").scrollTop = 0;
    if (mode === "recording") {
      state.recording = true;
      openPanel("record");
    }
  }
  function panelSemantics() {
    const overlay = state.panel !== null && window.innerWidth < 1200;
    $("reference-panel").setAttribute(
      "role",
      overlay ? "dialog" : "complementary",
    );
    if (overlay) $("reference-panel").setAttribute("aria-modal", "true");
    else $("reference-panel").removeAttribute("aria-modal");
    document.querySelector(".ml-document-area").inert = overlay;
  }
  function openPanel(kind, fieldKey = "allergy_history") {
    if (!state.panel) state.trigger = document.activeElement;
    state.panel = kind;
    $("reference-panel").hidden = false;
    $("workspace-grid").classList.add("has-panel");
    document
      .querySelectorAll("[data-panel]")
      .forEach((b) =>
        b.setAttribute("aria-pressed", String(b.dataset.panel === kind)),
      );
    const titles = {
      transcript: "对话转写",
      evidence: "原文证据",
      knowledge: "查询参考依据",
      record: "浏览器录音",
      role: "确认说话人身份",
      text: "输入转写文本",
      upload: "上传问诊音频",
    };
    $("panel-title").textContent = titles[kind];
    $("panel-kicker").textContent = ["record", "text", "upload"].includes(kind)
      ? "CAPTURE · PREVIEW"
      : "REFERENCE";
    const content = $("panel-content");
    if (kind === "transcript")
      content.innerHTML = `<p class="ml-panel-caption">匿名合成对话 · 仅用于版式预览</p>${transcripts.map(([speaker, time, text]) => `<section class="ml-speech"><header><span class="ml-speaker ${speaker === "患者" ? "patient" : ""}">${speaker}</span><time>${time}</time></header><p>${escape(text)}</p></section>`).join("")}<div class="ml-safe-note">保留医生提问与患者回答的区别；问题不能直接成为患者事实。</div>`;
    if (kind === "evidence") {
      const f = fields.find((item) => item.key === fieldKey) || fields[3];
      const quote =
        f.key === "allergy_history"
          ? transcripts[5][2]
          : f.key === "chief_complaint"
            ? transcripts[1][2]
            : `${transcripts[1][2]} ${transcripts[3][2]}`;
      content.innerHTML = `<p class="ml-panel-caption">对应字段 · ${f.title}</p><span class="ml-tag">患者原话 · 只读</span><blockquote class="ml-quote">“${escape(quote)}”</blockquote><div class="ml-fact"><span>说话人</span><strong>患者 · 人工确认示意</strong></div><div class="ml-fact"><span>音频位置</span><strong>${f.source || "00:39—00:43"}</strong></div><div class="ml-fact"><span>断言</span><strong>${f.key === "allergy_history" ? "absent · 否认" : "按原文逐项核对"}</strong></div><div class="ml-fact"><span>证据编号</span><strong>DEMO-SPAN-${f.key}</strong></div><div class="ml-safe-note">原文不可在这里修改。病历中的医生补充另行留痕，不改变音频证据。</div>`;
    }
    if (kind === "knowledge")
      content.innerHTML = `<p class="ml-panel-caption">来源卡片示意 · 未执行真实检索</p><div class="ml-search"><input aria-label="知识检索词" value="病历书写 现病史"><button id="search-preview">查询</button></div><section class="ml-knowledge-card"><span class="ml-tag">病历书写规范 · 来源展示示意</span><h3>病历书写基本规范</h3><p>发布机构：原卫生部<br>版本：卫医政发〔2010〕11号<br>章节：门（急）诊病历书写内容及要求<br>逻辑页：1（网页来源）</p><div class="ml-quote">此处展示检索摘要。样稿不提供临床建议，也不把知识内容写入患者事实。</div><p>chunk：DEMO-CHUNK-001</p><p class="ml-hash">内容 SHA256：待真实接口返回，样稿不生成虚假哈希</p><a href="https://www.nhc.gov.cn/wjw/gfxwj/201002/79d42b9c8b3f47ee91000d31de116784.shtml" target="_blank" rel="noopener noreferrer">查看官方来源 ↗</a></section><div class="ml-safe-note">参考依据用于医生核对，不自动诊断、处方或批准病历。</div>`;
    if (kind === "record") renderRecorder();
    if (kind === "role")
      content.innerHTML = `<p class="ml-panel-caption">异常恢复入口 · 不增加常驻流程步骤</p><h3>说话人 A</h3><p>“今天主要有什么不舒服？”</p><label>身份 <select id="role-a"><option value="">请选择</option><option value="doctor">医生</option><option value="patient">患者</option></select></label><h3>说话人 B</h3><p>“今天发热，体温三十八点二度……”</p><label>身份 <select id="role-b"><option value="">请选择</option><option value="doctor">医生</option><option value="patient">患者</option></select></label><div class="ml-panel-actions"><button class="ml-primary" id="confirm-roles">确认映射并继续</button></div><div class="ml-safe-note">实际业务中提交现有PATCH接口并复验角色门禁。此处仅演示交互。</div>`;
    if (kind === "text")
      content.innerHTML = `<p class="ml-panel-caption">输入方式示意 · 不提交至服务器</p><label for="input-text">脱敏问诊文本</label><textarea id="input-text">${transcripts.map((t) => `${t[0]}：${t[2]}`).join("\n")}</textarea><div class="ml-panel-actions"><button class="ml-primary" id="generate-preview">模拟生成草稿</button></div>`;
    if (kind === "upload")
      content.innerHTML = `<p class="ml-panel-caption">上传入口示意 · 不读取或发送您的文件</p><div class="ml-rec-card"><h3>选择问诊音频</h3><p>真实业务将使用现有音频上传接口。样稿只展示操作顺序。</p><button id="choose-audio-preview">选择示例音频</button><p id="file-preview" hidden>匿名问诊.wav · 样稿占位</p></div><div class="ml-panel-actions"><button class="ml-primary" id="generate-preview" disabled>模拟转写与生成</button></div>`;
    panelSemantics();
    $("close-panel").focus();
  }
  function closePanel() {
    state.panel = null;
    $("reference-panel").hidden = true;
    $("workspace-grid").classList.remove("has-panel");
    document
      .querySelectorAll("[data-panel]")
      .forEach((b) => b.setAttribute("aria-pressed", "false"));
    panelSemantics();
    if (state.trigger?.isConnected && !state.trigger.disabled)
      state.trigger.focus();
  }
  function renderRecorder() {
    $("panel-content").innerHTML =
      `<p class="ml-panel-caption">录音交互示意 · 不访问麦克风，不产生音频</p><div class="ml-rec-card"><div class="ml-rec-time"><span id="record-label">${state.recording ? "正在录音" : "录音已就绪"}</span><strong id="record-time">00:${String(state.seconds).padStart(2, "0")}</strong></div><div class="ml-waveform" aria-hidden="true">${"<span></span>".repeat(36)}</div><div class="ml-rec-controls"><button id="record-toggle">${state.recording ? "暂停" : "重新录制"}</button><button id="record-stop" ${!state.recording ? "disabled" : ""}>停止</button><button id="record-cancel">取消</button></div><progress value="${state.recording ? 40 : 100}" max="100" aria-label="录音进度示意"></progress></div><div class="ml-panel-actions"><button id="record-listen" ${state.recording ? "disabled" : ""}>试听示意</button><button id="generate-preview" class="ml-primary" ${state.recording ? "disabled" : ""}>模拟提交</button></div><div class="ml-safe-note">真实链路将在版式确认后接入。物理麦克风验收与此样稿分开记录。</div>`;
  }
  function generatePreview() {
    closePanel();
    setMode("processing");
    processingTimer = setTimeout(() => {
      setMode("draft");
      notify("样稿草稿已展示，未调用模型");
    }, 1300);
  }
  function showDialog(title, html, label, action, requireCheck = false) {
    $("dialog-title").textContent = title;
    $("dialog-content").innerHTML = html;
    $("dialog-confirm").textContent = label;
    $("dialog-confirm").disabled = requireCheck;
    confirmAction = action;
    $("dialog").returnValue = "";
    $("dialog").showModal();
  }
  $("dialog").addEventListener("close", () => {
    if ($("dialog").returnValue === "confirm") confirmAction?.();
    confirmAction = null;
  });
  $("dialog-content").addEventListener("change", () => {
    const check = $("review-check");
    if (check) $("dialog-confirm").disabled = !check.checked;
  });
  $("scenario").addEventListener("change", (event) => {
    closePanel();
    setMode(event.target.value, false);
  });
  $("primary-action").addEventListener("click", () => {
    if (["draft", "long"].includes(state.mode)) {
      state.saved = { ...state.values };
      setMode("editing");
      return;
    }
    if (state.mode === "editing") {
      state.saved = { ...state.values };
      state.dirty = false;
      state.revision++;
      setMode("review");
      notify("已保存到样稿状态；需要重新审核");
      return;
    }
    if (state.mode === "review") {
      showDialog(
        "审核当前病历",
        "<p>核对正文、原文证据及医生修改。本次只演示审核交互。</p><label><input id='review-check' type='checkbox'>我已核对本页匿名示例内容</label>",
        "确认审核（示意）",
        () => {
          setMode("approved");
          notify("样稿审核完成，未产生真实批准记录");
        },
        true,
      );
      return;
    }
    if (state.mode === "approved") {
      showDialog(
        "导出预览",
        "<p>实际业务只允许导出最新已批准Revision。此样稿不会调用导出接口或生成正式病历。</p>",
        "完成演示",
        () => notify("导出交互已确认；真实文件核对留待5.1"),
      );
      return;
    }
    if (state.mode === "empty") {
      state.seconds = 0;
      setMode("recording");
      return;
    }
    if (state.mode === "recording") {
      openPanel("record");
      return;
    }
    if (state.mode === "role") {
      openPanel("role");
      return;
    }
    if (state.mode === "failed") {
      generatePreview();
      return;
    }
    if (state.mode === "conflict")
      showDialog(
        "保存冲突 · 本地修改已保留",
        "<p>服务器已有较新版本，不能直接覆盖。本地修改保留供对照。</p><p>样稿选择继续编辑；真实接入后将读取最新Revision并显示差异，未经核对不自动合并。</p>",
        "返回编辑",
        () => setMode("editing"),
      );
  });
  $("secondary-action").addEventListener("click", () => {
    if (state.mode === "editing") {
      state.values = { ...state.saved };
      state.dirty = false;
      setMode("draft");
    } else if (["review", "approved"].includes(state.mode)) {
      state.saved = { ...state.values };
      setMode("editing");
    } else if (["recording", "processing"].includes(state.mode)) {
      closePanel();
      setMode("empty");
    } else if (state.mode === "empty") openPanel("text");
    else if (state.mode === "conflict")
      notify("本地修改已保留，尚未覆盖服务器版本");
    else if (["role", "failed", "long"].includes(state.mode))
      openPanel("transcript");
    else {
      state.seconds = 0;
      setMode("recording");
    }
  });
  document.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.dataset.panel) openPanel(button.dataset.panel);
    if (button.dataset.source) openPanel("evidence", button.dataset.source);
    if (button.dataset.input === "record") {
      state.seconds = 0;
      setMode("recording");
    } else if (button.dataset.input) openPanel(button.dataset.input);
    if (button.id === "search-preview")
      notify("这是来源卡片版式示意，尚未发出检索请求");
    if (button.id === "choose-audio-preview") {
      $("file-preview").hidden = false;
      $("generate-preview").disabled = false;
    }
    if (button.id === "generate-preview") generatePreview();
    if (button.id === "record-stop") {
      clearInterval(recordingTimer);
      state.recording = false;
      state.paused = false;
      renderRecorder();
    }
    if (button.id === "record-toggle") {
      state.recording = true;
      state.paused = !state.paused;
      $("record-label").textContent = state.paused
        ? "已暂停（示意）"
        : "正在录音（示意）";
      button.textContent = state.paused ? "恢复" : "暂停";
      $("record-stop").disabled = false;
      $("generate-preview").disabled = true;
      $("record-listen").disabled = true;
    }
    if (button.id === "record-cancel") {
      closePanel();
      setMode("empty");
      notify("样稿录音已取消，无音频或业务记录");
    }
    if (button.id === "record-listen")
      notify("试听控件示意：样稿没有音频，不播放替代录音");
    if (button.id === "confirm-roles") {
      if ($("role-a").value !== "doctor" || $("role-b").value !== "patient")
        notify("请根据示例原文核对：A为医生，B为患者");
      else generatePreview();
    }
  });
  $("record-fields").addEventListener("input", (event) => {
    if (!event.target.dataset.edit) return;
    state.values[event.target.dataset.edit] = event.target.value;
    state.dirty = true;
    event.target.closest(".ml-field").classList.add("edited");
    $("action-hint").textContent = "存在未保存修改 · 保存后原批准失效";
  });
  $("close-panel").addEventListener("click", closePanel);
  $("encounter-nav").addEventListener("click", () => {
    closePanel();
    $("paper-scroll").focus();
  });
  $("worklist-button").addEventListener("click", () =>
    showDialog(
      "就诊列表 · 示意",
      "<p><strong>模拟患者 · SIM-001</strong><br>当前就诊 DEMO-0923</p><p>此轮只确认就诊工作区布局。真实工作列表、登记与登录复用原系统。</p>",
      "返回当前就诊",
      () => {},
    ),
  );
  document.addEventListener("keydown", (event) => {
    if ($("dialog").open || !state.panel) return;
    if (event.key === "Escape") {
      event.preventDefault();
      closePanel();
    }
    if (event.key === "Tab" && window.innerWidth < 1200) {
      const focusable = [
        ...$("reference-panel").querySelectorAll(
          "button:not(:disabled),input,select,textarea,a[href]",
        ),
      ].filter((el) => el.getClientRects().length);
      const first = focusable[0],
        last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  });
  window.addEventListener("resize", panelSemantics);
  resetValues();
  render();
})();
