const API_BASE = "/api/v1/evaluations";

const steps = [
  { event: "uploading", label: "提交任务", idle: "等待图片和题目" },
  { event: "ocr_completed", label: "OCR 识别", idle: "提取作文文本" },
  { event: "task_type_inferred", label: "任务判定", idle: "确认写作类型" },
  { event: "context_built", label: "读者建模", idle: "生成虚拟读者" },
  { event: "text_segmented", label: "文本切片", idle: "划分语义片段" },
  { event: "layer1_scanned", label: "底层扫描", idle: "检查表达与衔接" },
  { event: "layer2_graphed", label: "语义图谱", idle: "抽取中心论点" },
  { event: "layer3_evaluated", label: "交际评估", idle: "判断回应效果" },
  { event: "task_finished", label: "完成报告", idle: "汇总得分" },
];

const state = {
  source: null,
  previewUrl: null,
  lastChunks: [],
};

const form = document.querySelector("#evaluation-form");
const promptText = document.querySelector("#prompt-text");
const taskType = document.querySelector("#task-type");
const imageInput = document.querySelector("#essay-image");
const imagePreview = document.querySelector("#image-preview");
const emptyPreview = document.querySelector("#empty-preview");
const fileName = document.querySelector("#file-name");
const submitButton = document.querySelector("#submit-button");
const resetButton = document.querySelector("#reset-button");
const formStatus = document.querySelector("#form-status");
const progressList = document.querySelector("#progress-list");
const errorPanel = document.querySelector("#error-panel");
const scorePanel = document.querySelector("#score-panel");
const scoreValue = document.querySelector("#score-value");
const scoreSummary = document.querySelector("#score-summary");
const diagnosticReport = document.querySelector("#diagnostic-report");
const ocrOutput = document.querySelector("#ocr-output");
const readerContext = document.querySelector("#reader-context");
const semanticGraph = document.querySelector("#semantic-graph");
const layer1Output = document.querySelector("#layer1-output");
const layer3Output = document.querySelector("#layer3-output");

function initProgress() {
  progressList.innerHTML = steps
    .map(
      (step, index) => `
        <li class="progress-step" data-event="${step.event}">
          <span class="step-index">${index + 1}</span>
          <strong>${escapeHtml(step.label)}</strong>
          <span>${escapeHtml(step.idle)}</span>
        </li>
      `,
    )
    .join("");
}

function setStep(eventName, status, detail) {
  const step = progressList.querySelector(`[data-event="${eventName}"]`);
  if (!step) return;
  step.classList.remove("is-active", "is-done", "is-error");
  if (status === "active") step.classList.add("is-active");
  if (status === "done") step.classList.add("is-done");
  if (status === "error") step.classList.add("is-error");
  if (detail) {
    step.querySelector("span:last-child").textContent = detail;
  }
}

function markDoneThrough(eventName) {
  const index = steps.findIndex((step) => step.event === eventName);
  if (index < 0) return;
  steps.forEach((step, stepIndex) => {
    if (stepIndex <= index) setStep(step.event, "done");
    if (stepIndex === index + 1) setStep(step.event, "active");
  });
}

function resetUi() {
  closeStream();
  form.reset();
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.previewUrl = null;
  state.lastChunks = [];
  imagePreview.hidden = true;
  imagePreview.removeAttribute("src");
  emptyPreview.hidden = false;
  fileName.textContent = "支持 JPG、PNG、WEBP 等图片格式";
  submitButton.disabled = false;
  formStatus.textContent = "等待提交";
  errorPanel.hidden = true;
  errorPanel.textContent = "";
  scorePanel.hidden = true;
  scoreValue.textContent = "-- / 60";
  scoreSummary.textContent = "完成后会在这里显示最终判定。";
  diagnosticReport.classList.add("muted");
  diagnosticReport.textContent = "评改完成后显示完整诊断。";
  ocrOutput.textContent = "尚未开始 OCR。";
  readerContext.classList.add("muted");
  readerContext.textContent = "等待语境建模。";
  semanticGraph.classList.add("muted");
  semanticGraph.textContent = "等待图谱生成。";
  layer1Output.classList.add("muted");
  layer1Output.textContent = "等待层级 1 扫描。";
  layer3Output.classList.add("muted");
  layer3Output.textContent = "等待交际评估。";
  initProgress();
}

function closeStream() {
  if (state.source) {
    state.source.close();
    state.source = null;
  }
}

imageInput.addEventListener("change", () => {
  const file = imageInput.files?.[0];
  if (!file) return;
  if (state.previewUrl) URL.revokeObjectURL(state.previewUrl);
  state.previewUrl = URL.createObjectURL(file);
  imagePreview.src = state.previewUrl;
  imagePreview.hidden = false;
  emptyPreview.hidden = true;
  fileName.textContent = `${file.name} · ${formatFileSize(file.size)}`;
});

resetButton.addEventListener("click", resetUi);

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  closeStream();
  errorPanel.hidden = true;
  submitButton.disabled = true;
  formStatus.textContent = "正在提交任务";
  initProgress();
  setStep("uploading", "active", "上传中");

  const file = imageInput.files?.[0];
  if (!file) {
    showError("请先选择作文图片。");
    return;
  }

  const promptValue = promptText.value.trim();
  if (!promptValue) {
    showError("请填写作文题目或写作要求。");
    return;
  }

  const formData = new FormData();
  formData.append("image", file);
  formData.append("task_type", taskType.value);
  formData.append("prompt_text", promptValue);

  try {
    const response = await fetch(`${API_BASE}/upload`, {
      method: "POST",
      body: formData,
    });

    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || payload.msg || "任务提交失败。");
    }

    setStep("uploading", "done", `任务号 ${payload.task_id}`);
    setStep("ocr_completed", "active", "等待服务推送");
    formStatus.textContent = `任务已创建：${payload.task_id}`;
    openStream(payload.task_id);
  } catch (error) {
    showError(error.message || "任务提交失败。");
  }
});

function openStream(taskId) {
  const source = new EventSource(`${API_BASE}/stream/${encodeURIComponent(taskId)}`);
  state.source = source;

  source.addEventListener("ocr_completed", (event) => {
    const data = parseEventData(event);
    markDoneThrough("ocr_completed");
    ocrOutput.textContent = data.markdown || "OCR 未返回可展示文本。";
  });

  source.addEventListener("task_type_inferred", (event) => {
    const data = parseEventData(event);
    markDoneThrough("task_type_inferred");
    setStep("task_type_inferred", "done", data.inferred_type || "已判定");
    formStatus.textContent = `任务类型：${data.inferred_type || "已判定"}`;
  });

  source.addEventListener("context_built", (event) => {
    const data = parseEventData(event);
    markDoneThrough("context_built");
    readerContext.classList.remove("muted");
    readerContext.innerHTML = renderReaderContext(data);
  });

  source.addEventListener("text_segmented", (event) => {
    const data = parseEventData(event);
    state.lastChunks = Array.isArray(data.chunks) ? data.chunks : [];
    markDoneThrough("text_segmented");
    setStep("text_segmented", "done", `${state.lastChunks.length} 个片段`);
  });

  source.addEventListener("layer1_scanned", (event) => {
    const data = parseEventData(event);
    markDoneThrough("layer1_scanned");
    layer1Output.classList.remove("muted");
    layer1Output.innerHTML = renderLayer1(data.evaluations || []);
  });

  source.addEventListener("layer2_graphed", (event) => {
    const data = parseEventData(event);
    markDoneThrough("layer2_graphed");
    semanticGraph.classList.remove("muted");
    semanticGraph.innerHTML = renderSemanticGraph(data);
  });

  source.addEventListener("layer3_evaluated", (event) => {
    const data = parseEventData(event);
    markDoneThrough("layer3_evaluated");
    layer3Output.classList.remove("muted");
    layer3Output.innerHTML = renderLayer3(data);
  });

  source.addEventListener("task_finished", (event) => {
    const data = parseEventData(event);
    markDoneThrough("task_finished");
    setStep("task_finished", "done", "评改完成");
    renderFinalResult(data);
    formStatus.textContent = "评改完成";
    submitButton.disabled = false;
    closeStream();
  });

  source.addEventListener("error", (event) => {
    if (event.data) {
      const data = parseEventData(event);
      showError(data.msg || "评改过程中发生错误。");
    } else if (state.source) {
      showError("流式连接已中断，请检查后端服务日志。");
    }
  });
}

function renderFinalResult(data) {
  scorePanel.hidden = false;
  scoreValue.textContent = `${Number(data.total_score ?? 0).toFixed(1)} / 60`;
  scoreSummary.textContent = summarizeScore(data);
  diagnosticReport.classList.remove("muted");
  diagnosticReport.innerHTML = renderMarkdownLite(data.diagnostic_report || "暂无诊断评语。");

  if (data.layer1_recognizability) {
    layer1Output.classList.remove("muted");
    layer1Output.innerHTML = renderLayer1(data.layer1_recognizability);
  }
  if (data.layer2_focus) {
    semanticGraph.classList.remove("muted");
    semanticGraph.innerHTML = renderSemanticGraph(data.layer2_focus);
  }
  if (data.layer3_cooperation) {
    layer3Output.classList.remove("muted");
    layer3Output.innerHTML = renderLayer3(data.layer3_cooperation);
  }
}

function renderReaderContext(data) {
  return `
    <dl>
      <dt>任务类型</dt>
      <dd>${escapeHtml(data.task_type || "未返回")}</dd>
      <dt>读者身份</dt>
      <dd>${escapeHtml(data.reader_identity || "未返回")}</dd>
      <dt>既有认知</dt>
      <dd>${renderPillList(data.prior_knowledge)}</dd>
      <dt>核心期望</dt>
      <dd>${renderPillList(data.reader_expectation)}</dd>
    </dl>
  `;
}

function renderLayer1(evaluations) {
  if (!evaluations.length) return "未返回层级 1 扫描结果。";
  return `
    <ul class="chunk-list">
      ${evaluations
        .map((item) => {
          const chunk = state.lastChunks.find((entry) => entry.chunk_index === item.chunk_index);
          return `
            <li>
              <strong>片段 ${escapeHtml(item.chunk_index)}</strong>
              <span class="badge ${item.is_recognizable ? "good" : "bad"}">可识别 ${item.is_recognizable ? "达成" : "未达成"}</span>
              <span class="badge ${item.has_coherence ? "good" : "bad"}">衔接 ${item.has_coherence ? "达成" : "未达成"}</span>
              <p>${escapeHtml(item.deduction_reason || "无")}</p>
              ${chunk ? `<p class="muted">${escapeHtml(chunk.original_text)}</p>` : ""}
            </li>
          `;
        })
        .join("")}
    </ul>
  `;
}

function renderSemanticGraph(data) {
  const nodes = Array.isArray(data.node_chains) ? data.node_chains : [];
  return `
    <div class="graph-core">中心论点：${escapeHtml(data.core_claim || "未返回")}</div>
    <ul class="node-list">
      ${nodes
        .map(
          (node) => `
            <li class="node-item">
              <strong>${escapeHtml(node.edge_node || "未命名节点")}</strong>
              <div class="node-meta">
                <span class="badge ${node.is_isolated ? "bad" : "good"}">${node.is_isolated ? "孤岛节点" : "指向中心"}</span>
                <span class="badge">中介层级 ${escapeHtml(node.intermediary_count ?? "-")}</span>
                <span class="badge">逻辑 ${escapeHtml(node.logic_strength || "-")}</span>
              </div>
            </li>
          `,
        )
        .join("")}
    </ul>
  `;
}

function renderLayer3(data) {
  return `
    <dl>
      <dt>信息意义</dt>
      <dd><span class="badge ${data.has_information_meaning ? "good" : "bad"}">${data.has_information_meaning ? "达成" : "未达成"}</span>${escapeHtml(data.information_analysis || "")}</dd>
      <dt>行动意义</dt>
      <dd><span class="badge ${data.has_action_meaning ? "good" : "bad"}">${data.has_action_meaning ? "达成" : "未达成"}</span>${escapeHtml(data.action_analysis || "")}</dd>
    </dl>
  `;
}

function renderPillList(items) {
  if (!Array.isArray(items) || !items.length) return "未返回";
  return `<ul class="pill-list">${items.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
}

function renderMarkdownLite(markdown) {
  const blocks = escapeHtml(markdown)
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(Boolean);

  return blocks
    .map((block) => {
      const withBold = block.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");
      if (withBold.startsWith("### ")) return `<h3>${withBold.slice(4)}</h3>`;
      if (withBold.startsWith("- ")) return `<p>${withBold.replace(/^- /gm, "• ").replace(/\n/g, "<br>")}</p>`;
      return `<p>${withBold.replace(/\n/g, "<br>")}</p>`;
    })
    .join("");
}

function summarizeScore(data) {
  const score = Number(data.total_score ?? 0);
  if (score >= 54) return "表达、聚焦和交际回应整体稳定，可以继续打磨语言力度。";
  if (score >= 42) return "文章基本完成交际任务，仍有部分表达或逻辑节点需要加强。";
  if (score >= 36) return "文章达到基础要求，但关键层级存在明显阻碍。";
  return "文章交际目标达成不足，需要优先修正核心论点与回应对象。";
}

function showError(message) {
  errorPanel.hidden = false;
  errorPanel.textContent = message;
  formStatus.textContent = "任务中断";
  submitButton.disabled = false;
  steps.forEach((step) => {
    const node = progressList.querySelector(`[data-event="${step.event}"]`);
    if (node?.classList.contains("is-active")) setStep(step.event, "error", "已中断");
  });
  closeStream();
}

function parseEventData(event) {
  try {
    return JSON.parse(event.data || "{}");
  } catch {
    return {};
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatFileSize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

resetUi();
