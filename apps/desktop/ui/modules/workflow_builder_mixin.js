(function (global) {
  const ns = (global.VideoEditorModules = global.VideoEditorModules || {});

  ns.createWorkflowBuilderMixin = function createWorkflowBuilderMixin() {
    return {
    _normalizeWorkflowStepId(value, fallback = "") {
      const text = `${value || fallback || ""}`.trim().toLowerCase();
      if (!text) return "";
      return text
        .replace(/[^a-z0-9_ -/]/g, "")
        .replace(/[\s/-]+/g, "_")
        .replace(/_+/g, "_")
        .replace(/^_+|_+$/g, "")
        .slice(0, 64);
    },

    _workflowCatalogEntry(capabilityId) {
      const cid = `${capabilityId || ""}`.trim().toLowerCase();
      const items = Array.isArray(this.workflowCatalog) ? this.workflowCatalog : [];
      return items.find(x => `${x && x.capability_id ? x.capability_id : ""}`.trim().toLowerCase() === cid) || null;
    },

    workflowActionsForCapability(capabilityId) {
      const entry = this._workflowCatalogEntry(capabilityId);
      const actions = Array.isArray(entry && entry.actions) ? entry.actions : [];
      const names = actions
        .map(x => `${x && x.action ? x.action : ""}`.trim().toLowerCase())
        .filter(Boolean);
      const uniq = [];
      const seen = new Set();
      names.forEach((n) => {
        if (seen.has(n)) return;
        seen.add(n);
        uniq.push(n);
      });
      if (!uniq.includes("auto")) uniq.unshift("auto");
      return uniq;
    },

    _workflowDeepCopy(value, fallback = null) {
      try {
        return JSON.parse(JSON.stringify(value));
      } catch {
        return fallback;
      }
    },

    _workflowCurrentSnapshot() {
      return {
        steps: this._workflowDeepCopy(Array.isArray(this.workflowSteps) ? this.workflowSteps : [], []),
        activeIndex: Math.max(0, Number(this.workflowActiveStepIndex || 0)),
        view: {
          zoom: Number(this.workflowCanvasZoom || 1),
          panX: Number(this.workflowCanvasPanX || 20),
          panY: Number(this.workflowCanvasPanY || 20),
        },
      };
    },

    _workflowSnapshotsEqual(a, b) {
      if (!a || !b) return false;
      try {
        return JSON.stringify(a) === JSON.stringify(b);
      } catch {
        return false;
      }
    },

    _workflowHistoryReset() {
      this.workflowUndoStack = [];
      this.workflowRedoStack = [];
      const snapshot = this._workflowCurrentSnapshot();
      this.workflowUndoStack.push(snapshot);
    },

    _workflowHistoryRecord() {
      if (this.workflowHistoryMuted) return;
      const snapshot = this._workflowCurrentSnapshot();
      const stack = Array.isArray(this.workflowUndoStack) ? this.workflowUndoStack : [];
      const last = stack.length ? stack[stack.length - 1] : null;
      if (last && this._workflowSnapshotsEqual(last, snapshot)) return;
      stack.push(snapshot);
      const maxSize = Math.max(20, Number(this.workflowHistoryMax || 120));
      while (stack.length > maxSize) stack.shift();
      this.workflowUndoStack = stack;
      this.workflowRedoStack = [];
    },

    _workflowApplySnapshot(snapshot) {
      if (!snapshot || !Array.isArray(snapshot.steps)) return;
      this.workflowHistoryMuted = true;
      this.workflowSteps = snapshot.steps.map((step, idx) => this._workflowStepFromRaw(step, idx + 1));
      if (this.workflowSteps.length === 0) {
        this.workflowSteps = [this._defaultWorkflowStep("", 1)];
      }
      const idx = Number(snapshot.activeIndex || 0);
      this.workflowActiveStepIndex = Math.max(0, Math.min(idx, this.workflowSteps.length - 1));
      const view = snapshot.view && typeof snapshot.view === "object" ? snapshot.view : {};
      this.workflowCanvasZoom = this._workflowClampZoom(Number(view.zoom || this.workflowCanvasZoom || 1));
      this.workflowCanvasPanX = Math.round(Number(view.panX || this.workflowCanvasPanX || 20));
      this.workflowCanvasPanY = Math.round(Number(view.panY || this.workflowCanvasPanY || 20));
      this._serializeWorkflowSteps();
      this._ensureWorkflowNodePositions();
      this.workflowHistoryMuted = false;
    },

    workflowCanUndo() {
      return Array.isArray(this.workflowUndoStack) && this.workflowUndoStack.length > 1;
    },

    workflowCanRedo() {
      return Array.isArray(this.workflowRedoStack) && this.workflowRedoStack.length > 0;
    },

    workflowUndo() {
      if (!this.workflowCanUndo()) return;
      const undo = this.workflowUndoStack;
      const current = undo.pop();
      if (current) this.workflowRedoStack.push(current);
      const prev = undo[undo.length - 1];
      if (!prev) return;
      this._workflowApplySnapshot(this._workflowDeepCopy(prev, prev));
    },

    workflowRedo() {
      if (!this.workflowCanRedo()) return;
      const snap = this.workflowRedoStack.pop();
      if (!snap) return;
      this._workflowApplySnapshot(this._workflowDeepCopy(snap, snap));
      this.workflowUndoStack.push(this._workflowDeepCopy(snap, snap));
    },

    _workflowCommitWithHistory() {
      const ret = this._serializeWorkflowSteps();
      if (ret.error) {
        this.workflowStepJsonError = ret.error;
        return ret;
      }
      this._workflowHistoryRecord();
      return ret;
    },

    _workflowEnsureUniqueStepId(rawStepId, fallback = "step") {
      let candidate = this._normalizeWorkflowStepId(rawStepId, fallback);
      if (!candidate) candidate = this._normalizeWorkflowStepId(fallback, "step") || "step";
      const taken = new Set(
        (Array.isArray(this.workflowSteps) ? this.workflowSteps : [])
          .map((step, idx) => this._normalizeWorkflowStepId(step && step.step_id, `step_${idx + 1}`))
          .filter(Boolean),
      );
      if (!taken.has(candidate)) return candidate;
      const base = candidate.replace(/_\d+$/, "");
      let n = 2;
      while (n < 9999) {
        const next = this._normalizeWorkflowStepId(`${base}_${n}`, `${base}_${n}`);
        if (next && !taken.has(next)) return next;
        n += 1;
      }
      return `${base}_${Date.now()}`;
    },

    workflowCopyActiveNode() {
      const idx = Number(this.workflowActiveStepIndex || 0);
      if (!Number.isFinite(idx) || idx < 0 || idx >= this.workflowSteps.length) {
        this.capabilityMessage = "没有可复制的节点";
        return;
      }
      const step = this.workflowSteps[idx];
      this.workflowClipboardNode = this._workflowDeepCopy(step, null);
      this.capabilityMessage = `已复制节点：${step && step.step_id ? step.step_id : `step_${idx + 1}`}`;
    },

    workflowPasteNode() {
      const raw = this.workflowClipboardNode;
      if (!raw || typeof raw !== "object") {
        this.capabilityMessage = "剪贴板里没有节点";
        return;
      }
      const at = Math.max(0, Math.min(Number(this.workflowActiveStepIndex || 0), this.workflowSteps.length - 1));
      const insertAt = this.workflowSteps.length ? at + 1 : 0;
      const cloned = this._workflowStepFromRaw(this._workflowDeepCopy(raw, {}), insertAt + 1);
      const srcId = this._normalizeWorkflowStepId(cloned.step_id, `step_${insertAt + 1}`) || `step_${insertAt + 1}`;
      cloned.step_id = this._workflowEnsureUniqueStepId(`${srcId}_copy`, `${srcId}_copy`);
      const anchor = this.workflowSteps[at];
      const anchorPos = anchor ? this._workflowStepPosition(anchor, at) : this._workflowAutoPosition(insertAt);
      const posX = Math.max(16, Number(anchorPos.x || 0) + 42);
      const posY = Math.max(16, Number(anchorPos.y || 0) + 26);
      cloned.ui_x = posX;
      cloned.ui_y = posY;
      cloned.ui_position = { x: posX, y: posY };
      this.workflowSteps.splice(insertAt, 0, cloned);
      this.workflowActiveStepIndex = insertAt;
      const ret = this._workflowCommitWithHistory();
      if (!ret.error) this.capabilityMessage = `已粘贴节点：${cloned.step_id}`;
    },

    _workflowIsShortcutContextAllowed(ev) {
      if (!ev || !ev.target || typeof ev.target.closest !== "function") return true;
      if (this.capabilityTab !== "workflow_builder") return false;
      if (this.topModule !== "production") return false;
      if (ev.target.closest("input,textarea,select,[contenteditable='true']")) return false;
      return true;
    },

    _bindWorkflowShortcuts() {
      if (this.workflowShortcutBound) return;
      this.workflowShortcutKeydownHandler = (ev) => {
        if (!this._workflowIsShortcutContextAllowed(ev)) return;
        const key = `${ev.key || ""}`.trim().toLowerCase();
        const mod = !!(ev.ctrlKey || ev.metaKey);
        if (!mod) return;
        if (key === "z" && !ev.shiftKey) {
          this.workflowUndo();
          ev.preventDefault();
          return;
        }
        if ((key === "z" && ev.shiftKey) || key === "y") {
          this.workflowRedo();
          ev.preventDefault();
          return;
        }
        if (key === "c") {
          this.workflowCopyActiveNode();
          ev.preventDefault();
          return;
        }
        if (key === "v") {
          this.workflowPasteNode();
          ev.preventDefault();
        }
      };
      window.addEventListener("keydown", this.workflowShortcutKeydownHandler);
      this.workflowShortcutBound = true;
    },

    _workflowCoord(value, fallback = 0) {
      const n = Number(value);
      if (!Number.isFinite(n)) {
        const fb = Number(fallback);
        return Number.isFinite(fb) ? Math.round(fb) : 0;
      }
      return Math.round(n);
    },

    _workflowAutoPosition(index = 0) {
      const idx = Math.max(0, this._workflowCoord(index, 0));
      const col = idx % 4;
      const row = Math.floor(idx / 4);
      return {
        x: 36 + col * 320,
        y: 28 + row * 210,
      };
    },

    _workflowNodeOutputsByType(nodeType = "action") {
      if (`${nodeType || "action"}`.trim().toLowerCase() === "condition") {
        return [
          { key: "true", label: "true" },
          { key: "false", label: "false" },
        ];
      }
      return [
        { key: "success", label: "success" },
        { key: "error", label: "error" },
        { key: "skip", label: "skip" },
        { key: "default", label: "default" },
      ];
    },

    workflowNodeOutputs(step) {
      const nodeType = `${step && step.node_type ? step.node_type : "action"}`.trim().toLowerCase();
      return this._workflowNodeOutputsByType(nodeType);
    },

    _workflowRouteFieldForOutput(step, outputKey) {
      const nodeType = `${step && step.node_type ? step.node_type : "action"}`.trim().toLowerCase();
      const key = `${outputKey || ""}`.trim().toLowerCase();
      if (nodeType === "condition") {
        if (key === "true") return "next_on_success";
        if (key === "false") return "next_on_error";
        return "next_step_id";
      }
      if (key === "success") return "next_on_success";
      if (key === "error") return "next_on_error";
      if (key === "skip") return "next_on_skip";
      return "next_step_id";
    },

    workflowNodeRouteTarget(step, outputKey) {
      const field = this._workflowRouteFieldForOutput(step, outputKey);
      if (!field) return "";
      return this._normalizeWorkflowStepId(step && step[field], "");
    },

    workflowNodeRouteBadge(outputKey) {
      const key = `${outputKey || ""}`.trim().toLowerCase();
      if (key === "true") return "true";
      if (key === "false") return "false";
      if (key === "success") return "success";
      if (key === "error") return "error";
      if (key === "skip") return "skip";
      return "default";
    },

    workflowNodeMetrics(step) {
      const nodeType = `${step && step.node_type ? step.node_type : "action"}`.trim().toLowerCase();
      const outputs = this._workflowNodeOutputsByType(nodeType);
      const width = 272;
      const headerH = 70;
      const rowH = 22;
      const height = headerH + outputs.length * rowH + 12;
      return {
        width,
        height,
        inputY: Math.round(height / 2),
        outputStartY: headerH + Math.round(rowH / 2) - 3,
        outputRowH: rowH,
      };
    },

    _workflowStepPosition(step, index = 0) {
      const fallback = this._workflowAutoPosition(index);
      const uiPos = (step && typeof step.ui_position === "object" && !Array.isArray(step.ui_position))
        ? step.ui_position
        : {};
      const rawX = uiPos.x !== undefined ? uiPos.x : (step ? step.ui_x : undefined);
      const rawY = uiPos.y !== undefined ? uiPos.y : (step ? step.ui_y : undefined);
      const x = Math.max(16, this._workflowCoord(rawX, fallback.x));
      const y = Math.max(16, this._workflowCoord(rawY, fallback.y));
      return { x, y };
    },

    _ensureWorkflowNodePositions() {
      const rows = Array.isArray(this.workflowSteps) ? this.workflowSteps : [];
      rows.forEach((step, idx) => {
        const pos = this._workflowStepPosition(step, idx);
        step.ui_x = pos.x;
        step.ui_y = pos.y;
        step.ui_position = { x: pos.x, y: pos.y };
      });
      this._refreshWorkflowCanvasMetrics();
    },

    _workflowCanvasWrapEl() {
      return document.getElementById("workflow-node-canvas-wrap");
    },

    _workflowCanvasPointFromEvent(ev) {
      const wrap = this._workflowCanvasWrapEl();
      if (!wrap || !ev) return null;
      const rect = wrap.getBoundingClientRect();
      const localX = ev.clientX - rect.left + wrap.scrollLeft;
      const localY = ev.clientY - rect.top + wrap.scrollTop;
      if (!Number.isFinite(localX) || !Number.isFinite(localY)) return null;
      const zoom = Math.max(0.1, Number(this.workflowCanvasZoom) || 1);
      const panX = Number(this.workflowCanvasPanX) || 0;
      const panY = Number(this.workflowCanvasPanY) || 0;
      const x = (localX - panX) / zoom;
      const y = (localY - panY) / zoom;
      return { x, y };
    },

    _refreshWorkflowCanvasMetrics() {
      const rows = Array.isArray(this.workflowSteps) ? this.workflowSteps : [];
      let maxW = 960;
      let maxH = 460;
      rows.forEach((step, idx) => {
        const pos = this._workflowStepPosition(step, idx);
        const m = this.workflowNodeMetrics(step);
        maxW = Math.max(maxW, pos.x + m.width + 140);
        maxH = Math.max(maxH, pos.y + m.height + 120);
      });
      this.workflowCanvasSize = {
        width: Math.max(960, Math.round(maxW)),
        height: Math.max(460, Math.round(maxH)),
      };
    },

    _workflowWorldBounds(padding = 0) {
      const rows = Array.isArray(this.workflowSteps) ? this.workflowSteps : [];
      if (!rows.length) {
        return { minX: 0, minY: 0, maxX: 960, maxY: 560, width: 960, height: 560 };
      }
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      rows.forEach((step, idx) => {
        const pos = this._workflowStepPosition(step, idx);
        const m = this.workflowNodeMetrics(step);
        minX = Math.min(minX, pos.x);
        minY = Math.min(minY, pos.y);
        maxX = Math.max(maxX, pos.x + m.width);
        maxY = Math.max(maxY, pos.y + m.height);
      });
      if (!Number.isFinite(minX) || !Number.isFinite(minY) || !Number.isFinite(maxX) || !Number.isFinite(maxY)) {
        return { minX: 0, minY: 0, maxX: 960, maxY: 560, width: 960, height: 560 };
      }
      const pad = Math.max(0, Number(padding || 0));
      const out = {
        minX: minX - pad,
        minY: minY - pad,
        maxX: maxX + pad,
        maxY: maxY + pad,
      };
      out.width = Math.max(120, out.maxX - out.minX);
      out.height = Math.max(120, out.maxY - out.minY);
      return out;
    },

    workflowCanvasBoardStyle() {
      const size = this.workflowCanvasSize || { width: 1200, height: 560 };
      return `width:${Math.max(960, Number(size.width) || 1200)}px;height:${Math.max(460, Number(size.height) || 560)}px;`;
    },

    workflowCanvasSceneStyle() {
      const zoom = Math.max(0.45, Math.min(1.8, Number(this.workflowCanvasZoom) || 1));
      const panX = Number(this.workflowCanvasPanX) || 0;
      const panY = Number(this.workflowCanvasPanY) || 0;
      return `transform:translate(${panX}px, ${panY}px) scale(${zoom});transform-origin:0 0;`;
    },

    workflowCanvasZoomLabel() {
      return `${Math.round((Number(this.workflowCanvasZoom) || 1) * 100)}%`;
    },

    _workflowClampZoom(value) {
      const n = Number(value);
      if (!Number.isFinite(n)) return 1;
      return Math.max(0.45, Math.min(1.8, n));
    },

    _setWorkflowZoom(targetZoom, anchorEvent = null) {
      const wrap = this._workflowCanvasWrapEl();
      if (!wrap) {
        this.workflowCanvasZoom = this._workflowClampZoom(targetZoom);
        return;
      }
      const nextZoom = this._workflowClampZoom(targetZoom);
      const rect = wrap.getBoundingClientRect();
      const currentZoom = Math.max(0.1, Number(this.workflowCanvasZoom) || 1);
      const currentPanX = Number(this.workflowCanvasPanX) || 0;
      const currentPanY = Number(this.workflowCanvasPanY) || 0;
      let localX = rect.width * 0.5 + wrap.scrollLeft;
      let localY = rect.height * 0.5 + wrap.scrollTop;
      if (anchorEvent && Number.isFinite(anchorEvent.clientX) && Number.isFinite(anchorEvent.clientY)) {
        localX = anchorEvent.clientX - rect.left + wrap.scrollLeft;
        localY = anchorEvent.clientY - rect.top + wrap.scrollTop;
      }
      const worldX = (localX - currentPanX) / currentZoom;
      const worldY = (localY - currentPanY) / currentZoom;
      this.workflowCanvasZoom = nextZoom;
      this.workflowCanvasPanX = Math.round(localX - worldX * nextZoom);
      this.workflowCanvasPanY = Math.round(localY - worldY * nextZoom);
    },

    zoomWorkflowCanvas(delta = 0, anchorEvent = null) {
      const d = Number(delta);
      if (!Number.isFinite(d) || d === 0) return;
      const next = (Number(this.workflowCanvasZoom) || 1) + d;
      this._setWorkflowZoom(next, anchorEvent);
    },

    resetWorkflowCanvasView() {
      this.workflowCanvasZoom = 1;
      this.workflowCanvasPanX = 20;
      this.workflowCanvasPanY = 20;
    },

    fitWorkflowCanvasView() {
      const wrap = this._workflowCanvasWrapEl();
      if (!wrap) {
        this.resetWorkflowCanvasView();
        return;
      }
      const bounds = this._workflowWorldBounds(56);
      const viewW = Math.max(180, Number(wrap.clientWidth || 0));
      const viewH = Math.max(160, Number(wrap.clientHeight || 0));
      const zoom = this._workflowClampZoom(Math.min(viewW / bounds.width, viewH / bounds.height));
      this.workflowCanvasZoom = zoom;
      this.workflowCanvasPanX = Math.round((viewW - bounds.width * zoom) / 2 - bounds.minX * zoom);
      this.workflowCanvasPanY = Math.round((viewH - bounds.height * zoom) / 2 - bounds.minY * zoom);
    },

    onWorkflowCanvasWheel(ev) {
      if (!ev) return;
      if (!ev.ctrlKey && !ev.metaKey) return;
      const delta = Number(ev.deltaY || 0);
      if (!Number.isFinite(delta) || delta === 0) return;
      this.zoomWorkflowCanvas(delta > 0 ? -0.08 : 0.08, ev);
      if (typeof ev.preventDefault === "function") ev.preventDefault();
    },

    workflowMinimapModel() {
      const bounds = this._workflowWorldBounds(24);
      const miniWidth = 230;
      const miniHeight = 140;
      const scale = Math.min(miniWidth / bounds.width, miniHeight / bounds.height);
      const contentW = bounds.width * scale;
      const contentH = bounds.height * scale;
      const offsetX = (miniWidth - contentW) * 0.5;
      const offsetY = (miniHeight - contentH) * 0.5;
      const rows = Array.isArray(this.workflowSteps) ? this.workflowSteps : [];
      const nodes = rows.map((step, idx) => {
        const pos = this._workflowStepPosition(step, idx);
        const m = this.workflowNodeMetrics(step);
        return {
          step_id: this._normalizeWorkflowStepId(step && step.step_id, `step_${idx + 1}`),
          x: offsetX + (pos.x - bounds.minX) * scale,
          y: offsetY + (pos.y - bounds.minY) * scale,
          w: Math.max(10, m.width * scale),
          h: Math.max(8, m.height * scale),
          status: this.workflowNodeRuntimeStatus(step),
          active: idx === this.workflowActiveStepIndex,
        };
      });
      const wrap = this._workflowCanvasWrapEl();
      const zoom = Math.max(0.1, Number(this.workflowCanvasZoom) || 1);
      const panX = Number(this.workflowCanvasPanX) || 0;
      const panY = Number(this.workflowCanvasPanY) || 0;
      const viewWWorld = wrap ? Math.max(10, Number(wrap.clientWidth || 0) / zoom) : 280;
      const viewHWorld = wrap ? Math.max(10, Number(wrap.clientHeight || 0) / zoom) : 160;
      const viewLeftWorld = (-panX) / zoom;
      const viewTopWorld = (-panY) / zoom;
      const viewport = {
        x: offsetX + (viewLeftWorld - bounds.minX) * scale,
        y: offsetY + (viewTopWorld - bounds.minY) * scale,
        w: Math.max(12, viewWWorld * scale),
        h: Math.max(10, viewHWorld * scale),
      };
      return {
        miniWidth,
        miniHeight,
        scale,
        offsetX,
        offsetY,
        bounds,
        nodes,
        viewport,
      };
    },

    onWorkflowMinimapPointer(ev) {
      const wrap = this._workflowCanvasWrapEl();
      if (!ev || !wrap) return;
      const model = this.workflowMinimapModel();
      const target = ev.currentTarget;
      if (!target || typeof target.getBoundingClientRect !== "function") return;
      const rect = target.getBoundingClientRect();
      const localX = Number(ev.clientX || 0) - rect.left;
      const localY = Number(ev.clientY || 0) - rect.top;
      const worldX = model.bounds.minX + (localX - model.offsetX) / model.scale;
      const worldY = model.bounds.minY + (localY - model.offsetY) / model.scale;
      if (!Number.isFinite(worldX) || !Number.isFinite(worldY)) return;
      const zoom = Math.max(0.1, Number(this.workflowCanvasZoom) || 1);
      const viewW = Number(wrap.clientWidth || 0);
      const viewH = Number(wrap.clientHeight || 0);
      this.workflowCanvasPanX = Math.round(viewW * 0.5 - worldX * zoom);
      this.workflowCanvasPanY = Math.round(viewH * 0.5 - worldY * zoom);
      if (typeof ev.preventDefault === "function") ev.preventDefault();
    },

    onWorkflowCanvasMouseDown(ev) {
      if (!ev || ev.button !== 0) return;
      if (ev.target && typeof ev.target.closest === "function") {
        if (ev.target.closest(".workflow-canvas-node")) return;
        if (ev.target.closest(".workflow-port-output-btn")) return;
        if (ev.target.closest(".workflow-port-input")) return;
      }
      this.workflowCanvasPanning = true;
      this.workflowCanvasPanStartClientX = Number(ev.clientX || 0);
      this.workflowCanvasPanStartClientY = Number(ev.clientY || 0);
      this.workflowCanvasPanStartX = Number(this.workflowCanvasPanX || 0);
      this.workflowCanvasPanStartY = Number(this.workflowCanvasPanY || 0);
      if (typeof ev.preventDefault === "function") ev.preventDefault();
    },

    workflowNodeStyle(step, index) {
      const pos = this._workflowStepPosition(step, index);
      const m = this.workflowNodeMetrics(step);
      return `left:${pos.x}px;top:${pos.y}px;width:${m.width}px;height:${m.height}px;`;
    },

    _workflowOutputKeyFromWhen(when) {
      const key = `${when || ""}`.trim().toLowerCase();
      if (key === "condition_true") return "true";
      if (key === "condition_false") return "false";
      if (key === "success" || key === "error" || key === "skip") return key;
      return "default";
    },

    workflowEdgeLabel(edge) {
      return this._workflowOutputKeyFromWhen(edge && edge.when ? edge.when : "");
    },

    _workflowNodeInputAnchor(index) {
      const idx = Number(index);
      if (!Number.isFinite(idx) || idx < 0 || idx >= this.workflowSteps.length) return null;
      const step = this.workflowSteps[idx];
      const pos = this._workflowStepPosition(step, idx);
      const m = this.workflowNodeMetrics(step);
      return { x: pos.x, y: pos.y + m.inputY };
    },

    _workflowNodeOutputAnchor(index, outputKey) {
      const idx = Number(index);
      if (!Number.isFinite(idx) || idx < 0 || idx >= this.workflowSteps.length) return null;
      const step = this.workflowSteps[idx];
      const outputs = this.workflowNodeOutputs(step);
      const key = `${outputKey || ""}`.trim().toLowerCase();
      const found = outputs.findIndex(x => `${x.key || ""}`.trim().toLowerCase() === key);
      const outputIdx = found >= 0 ? found : 0;
      const pos = this._workflowStepPosition(step, idx);
      const m = this.workflowNodeMetrics(step);
      return {
        x: pos.x + m.width,
        y: pos.y + m.outputStartY + outputIdx * m.outputRowH,
      };
    },

    _workflowBezierPath(fromPt, toPt) {
      if (!fromPt || !toPt) return "";
      const dx = Math.max(72, Math.abs(toPt.x - fromPt.x) * 0.45);
      const c1x = fromPt.x + dx;
      const c1y = fromPt.y;
      const c2x = toPt.x - dx;
      const c2y = toPt.y;
      return `M ${fromPt.x} ${fromPt.y} C ${c1x} ${c1y}, ${c2x} ${c2y}, ${toPt.x} ${toPt.y}`;
    },

    workflowCanvasEdges() {
      const rows = Array.isArray(this.workflowSteps) ? this.workflowSteps : [];
      const idToIndex = new Map();
      rows.forEach((step, idx) => {
        const sid = this._normalizeWorkflowStepId(step && step.step_id, `step_${idx + 1}`);
        if (sid) idToIndex.set(sid, idx);
      });
      const edgesRaw = this.workflowGraphEdgesPreview();
      return edgesRaw
        .map((edge) => {
          const fromId = this._normalizeWorkflowStepId(edge && edge.from, "");
          const toId = this._normalizeWorkflowStepId(edge && edge.to, "");
          const fromIdx = idToIndex.has(fromId) ? idToIndex.get(fromId) : -1;
          const toIdx = idToIndex.has(toId) ? idToIndex.get(toId) : -1;
          const outputKey = this._workflowOutputKeyFromWhen(edge && edge.when ? edge.when : "");
          const fromPt = fromIdx >= 0 ? this._workflowNodeOutputAnchor(fromIdx, outputKey) : null;
          const toPt = toIdx >= 0 ? this._workflowNodeInputAnchor(toIdx) : null;
          const fallbackFrom = fromPt || { x: 24, y: 24 };
          const fallbackTo = toPt || { x: fallbackFrom.x + 180, y: fallbackFrom.y + 40 };
          return {
            ...edge,
            output_key: outputKey,
            invalid: toIdx < 0 || !toPt,
            path: this._workflowBezierPath(fallbackFrom, fallbackTo),
          };
        })
        .filter(x => x.path);
    },

    workflowCanvasDraftPath() {
      if (!this.workflowCanvasLinkActive) return "";
      const fromPt = this._workflowNodeOutputAnchor(this.workflowCanvasLinkFromIndex, this.workflowCanvasLinkOutputKey);
      if (!fromPt) return "";
      const toPt = {
        x: this._workflowCoord(this.workflowCanvasLinkPointerX, fromPt.x),
        y: this._workflowCoord(this.workflowCanvasLinkPointerY, fromPt.y),
      };
      return this._workflowBezierPath(fromPt, toPt);
    },

    _workflowPointerInputIndexFromEvent(ev) {
      if (!ev || !ev.target || typeof ev.target.closest !== "function") return -1;
      const el = ev.target.closest("[data-wf-input-index]");
      if (!el) return -1;
      const idx = Number(el.getAttribute("data-wf-input-index"));
      if (!Number.isFinite(idx)) return -1;
      return idx;
    },

    _bindWorkflowCanvasPointerEvents() {
      if (this.workflowCanvasPointerBound) return;
      this.workflowCanvasPointerMoveHandler = (ev) => this.onWorkflowCanvasPointerMove(ev);
      this.workflowCanvasPointerUpHandler = (ev) => this.onWorkflowCanvasPointerUp(ev);
      window.addEventListener("mousemove", this.workflowCanvasPointerMoveHandler);
      window.addEventListener("mouseup", this.workflowCanvasPointerUpHandler);
      this.workflowCanvasPointerBound = true;
    },

    onWorkflowCanvasPointerMove(ev) {
      if (this.workflowCanvasPanning) {
        const dx = Number(ev && ev.clientX) - Number(this.workflowCanvasPanStartClientX || 0);
        const dy = Number(ev && ev.clientY) - Number(this.workflowCanvasPanStartClientY || 0);
        if (Number.isFinite(dx)) this.workflowCanvasPanX = Math.round(Number(this.workflowCanvasPanStartX || 0) + dx);
        if (Number.isFinite(dy)) this.workflowCanvasPanY = Math.round(Number(this.workflowCanvasPanStartY || 0) + dy);
        return;
      }
      if (this.workflowCanvasDragIndex >= 0) {
        const idx = this.workflowCanvasDragIndex;
        const step = this.workflowSteps[idx];
        if (!step) return;
        const pt = this._workflowCanvasPointFromEvent(ev);
        if (!pt) return;
        const nextX = Math.max(16, Math.round(pt.x - this.workflowCanvasNodeDragOffsetX));
        const nextY = Math.max(16, Math.round(pt.y - this.workflowCanvasNodeDragOffsetY));
        step.ui_x = nextX;
        step.ui_y = nextY;
        step.ui_position = { x: nextX, y: nextY };
        this._refreshWorkflowCanvasMetrics();
        return;
      }
      if (this.workflowCanvasLinkActive) {
        const pt = this._workflowCanvasPointFromEvent(ev);
        if (!pt) return;
        this.workflowCanvasLinkPointerX = pt.x;
        this.workflowCanvasLinkPointerY = pt.y;
      }
    },

    onWorkflowCanvasPointerUp(ev) {
      if (this.workflowCanvasPanning) {
        this.workflowCanvasPanning = false;
      }
      if (this.workflowCanvasDragIndex >= 0) {
        this.onWorkflowNodeDragEnd();
      }
      if (this.workflowCanvasLinkActive) {
        const targetIdx = this._workflowPointerInputIndexFromEvent(ev);
        if (targetIdx >= 0) {
          this.finishWorkflowConnect(targetIdx);
        } else {
          this.cancelWorkflowConnect();
        }
      }
    },

    onWorkflowNodePointerDown(index, ev) {
      const idx = Number(index);
      if (!Number.isFinite(idx) || idx < 0 || idx >= this.workflowSteps.length) return;
      if (ev && Number.isFinite(ev.button) && ev.button !== 0) return;
      this.workflowCanvasPanning = false;
      if (ev && ev.target && typeof ev.target.closest === "function") {
        if (ev.target.closest(".workflow-port-output-btn")) return;
        if (ev.target.closest(".workflow-port-input")) return;
        if (ev.target.closest("input,textarea,select,button,label")) return;
      }
      const step = this.workflowSteps[idx];
      const pt = this._workflowCanvasPointFromEvent(ev);
      if (!pt || !step) return;
      const pos = this._workflowStepPosition(step, idx);
      this.workflowCanvasDragIndex = idx;
      this.workflowCanvasDropIndex = -1;
      this.workflowCanvasNodeDragOffsetX = Math.max(0, pt.x - pos.x);
      this.workflowCanvasNodeDragOffsetY = Math.max(0, pt.y - pos.y);
      this.setActiveWorkflowStep(idx);
      if (ev && typeof ev.preventDefault === "function") ev.preventDefault();
    },

    startWorkflowConnect(index, outputKey, ev) {
      const idx = Number(index);
      if (!Number.isFinite(idx) || idx < 0 || idx >= this.workflowSteps.length) return;
      const step = this.workflowSteps[idx];
      const field = this._workflowRouteFieldForOutput(step, outputKey);
      if (!field) return;
      const fromPt = this._workflowNodeOutputAnchor(idx, outputKey);
      this.workflowCanvasLinkActive = true;
      this.workflowCanvasLinkFromIndex = idx;
      this.workflowCanvasLinkOutputKey = `${outputKey || "default"}`.trim().toLowerCase() || "default";
      this.workflowCanvasLinkPointerX = fromPt ? fromPt.x : 0;
      this.workflowCanvasLinkPointerY = fromPt ? fromPt.y : 0;
      this.setActiveWorkflowStep(idx);
      if (ev && typeof ev.preventDefault === "function") ev.preventDefault();
    },

    finishWorkflowConnect(targetIndex) {
      const toIdx = Number(targetIndex);
      if (!this.workflowCanvasLinkActive) return;
      if (!Number.isFinite(toIdx) || toIdx < 0 || toIdx >= this.workflowSteps.length) {
        this.cancelWorkflowConnect();
        return;
      }
      const fromIdx = Number(this.workflowCanvasLinkFromIndex);
      if (!Number.isFinite(fromIdx) || fromIdx < 0 || fromIdx >= this.workflowSteps.length) {
        this.cancelWorkflowConnect();
        return;
      }
      const fromStep = this.workflowSteps[fromIdx];
      const toStep = this.workflowSteps[toIdx];
      const field = this._workflowRouteFieldForOutput(fromStep, this.workflowCanvasLinkOutputKey);
      if (!field) {
        this.cancelWorkflowConnect();
        return;
      }
      fromStep[field] = this._normalizeWorkflowStepId(toStep && toStep.step_id, "");
      this.cancelWorkflowConnect();
      this.onWorkflowStepChanged();
    },

    clearWorkflowRoute(index, outputKey) {
      const idx = Number(index);
      if (!Number.isFinite(idx) || idx < 0 || idx >= this.workflowSteps.length) return;
      const step = this.workflowSteps[idx];
      const field = this._workflowRouteFieldForOutput(step, outputKey);
      if (!field) return;
      step[field] = "";
      this.onWorkflowStepChanged();
    },

    cancelWorkflowConnect() {
      this.workflowCanvasLinkActive = false;
      this.workflowCanvasLinkFromIndex = -1;
      this.workflowCanvasLinkOutputKey = "";
      this.workflowCanvasLinkPointerX = 0;
      this.workflowCanvasLinkPointerY = 0;
    },

    autoLayoutWorkflowNodes() {
      const rows = Array.isArray(this.workflowSteps) ? this.workflowSteps : [];
      rows.forEach((step, idx) => {
        const pos = this._workflowAutoPosition(idx);
        step.ui_x = pos.x;
        step.ui_y = pos.y;
        step.ui_position = { x: pos.x, y: pos.y };
      });
      this._refreshWorkflowCanvasMetrics();
      this._workflowCommitWithHistory();
    },

    _defaultWorkflowStep(capabilityId = "", index = 1, nodeType = "action") {
      const normalizedNodeType = ["action", "condition"].includes(`${nodeType || ""}`.trim().toLowerCase())
        ? `${nodeType}`.trim().toLowerCase()
        : "action";
      const catalog = Array.isArray(this.workflowCatalog) ? this.workflowCatalog : [];
      const pickedId = normalizedNodeType === "action"
        ? `${capabilityId || this.workflowQuickAddCapability || (catalog[0] && catalog[0].capability_id) || "subtitle_calibration"}`.trim().toLowerCase()
        : "";
      const entry = this._workflowCatalogEntry(pickedId);
      const actions = this.workflowActionsForCapability(pickedId);
      const action = actions.includes("run") ? "run" : (actions[0] || "auto");
      const stepIdRaw = normalizedNodeType === "condition" ? `cond_${index}` : `step_${index}_${pickedId}`;
      const stepId = this._normalizeWorkflowStepId(stepIdRaw) || `step_${index}`;
      const inputObj = normalizedNodeType === "condition" ? {} : { input_mode: "auto" };
      const pos = this._workflowAutoPosition(Math.max(0, Number(index) - 1));
      if (normalizedNodeType === "action" && entry && entry.supports_input_mode === false) delete inputObj.input_mode;
      return {
        step_id: stepId,
        node_type: normalizedNodeType,
        capability_id: pickedId,
        action: normalizedNodeType === "action" ? action : "auto",
        input_mode: "auto",
        continue_on_error: false,
        enabled: true,
        save_as: "",
        next_step_id: "",
        next_on_success: "",
        next_on_error: "",
        next_on_skip: "",
        run_if_expr: "",
        condition_expr: "",
        input: inputObj,
        input_json: this.jsonPretty(inputObj),
        ui_x: pos.x,
        ui_y: pos.y,
        ui_position: { x: pos.x, y: pos.y },
      };
    },

    _workflowStepFromRaw(stepRaw, idx = 1) {
      const step = (stepRaw && typeof stepRaw === "object" && !Array.isArray(stepRaw)) ? stepRaw : {};
      const fallback = this._defaultWorkflowStep("", idx);
      const nodeType = ["action", "condition"].includes(`${step.node_type || ""}`.trim().toLowerCase())
        ? `${step.node_type}`.trim().toLowerCase()
        : "action";
      const rawCapabilityId = `${step.capability_id || ""}`.trim().toLowerCase();
      const capabilityId = nodeType === "action"
        ? (rawCapabilityId || `${fallback.capability_id || ""}`.trim().toLowerCase())
        : rawCapabilityId;
      const actions = nodeType === "action" ? this.workflowActionsForCapability(capabilityId) : ["auto"];
      let action = `${step.action || "auto"}`.trim().toLowerCase() || "auto";
      if (nodeType !== "action") action = "auto";
      if (nodeType === "action" && !actions.includes(action)) action = actions[0] || "auto";
      const inputObj = (step.input && typeof step.input === "object" && !Array.isArray(step.input))
        ? step.input
        : {};
      const inputModeRaw = `${step.input_mode || inputObj.input_mode || "auto"}`.trim().toLowerCase();
      const inputMode = ["auto", "project", "inline"].includes(inputModeRaw) ? inputModeRaw : "auto";
      const rawPos = this._workflowStepPosition(step, idx - 1);
      return {
        step_id: this._normalizeWorkflowStepId(step.step_id, `step_${idx}`) || `step_${idx}`,
        node_type: nodeType,
        capability_id: capabilityId,
        action,
        input_mode: inputMode,
        continue_on_error: !!step.continue_on_error,
        enabled: step.enabled === undefined ? true : !!step.enabled,
        save_as: this._normalizeWorkflowStepId(step.save_as, ""),
        next_step_id: this._normalizeWorkflowStepId(step.next_step_id, ""),
        next_on_success: this._normalizeWorkflowStepId(step.next_on_success, ""),
        next_on_error: this._normalizeWorkflowStepId(step.next_on_error, ""),
        next_on_skip: this._normalizeWorkflowStepId(step.next_on_skip, ""),
        run_if_expr: step.run_if === undefined ? "" : (typeof step.run_if === "string" ? step.run_if : this.jsonPretty(step.run_if)),
        condition_expr: step.condition === undefined ? "" : (typeof step.condition === "string" ? step.condition : this.jsonPretty(step.condition)),
        input: inputObj,
        input_json: this.jsonPretty(inputObj),
        ui_x: rawPos.x,
        ui_y: rawPos.y,
        ui_position: { x: rawPos.x, y: rawPos.y },
      };
    },

    syncWorkflowStepsFromJson() {
      const parsed = this.parseJsonSafe(this.workflowBuilder.steps_json, null);
      if (!Array.isArray(parsed)) {
        this.workflowStepJsonError = "步骤 JSON 解析失败，请检查格式";
        if (!Array.isArray(this.workflowSteps) || this.workflowSteps.length === 0) {
          this.workflowSteps = [this._defaultWorkflowStep("", 1)];
        }
        this.workflowActiveStepIndex = Math.max(0, Math.min(this.workflowActiveStepIndex, this.workflowSteps.length - 1));
        return false;
      }
      this.workflowSteps = parsed.map((step, idx) => this._workflowStepFromRaw(step, idx + 1));
      if (this.workflowSteps.length === 0) {
        this.workflowSteps = [this._defaultWorkflowStep("", 1)];
      }
      this.workflowActiveStepIndex = Math.max(0, Math.min(this.workflowActiveStepIndex, this.workflowSteps.length - 1));
      this.workflowCanvasDragIndex = -1;
      this.workflowCanvasDropIndex = -1;
      this.workflowCanvasLinkActive = false;
      this.workflowCanvasLinkFromIndex = -1;
      this.workflowCanvasLinkOutputKey = "";
      this.workflowStepJsonError = "";
      this.resetWorkflowRuntimeStatus();
      this._ensureWorkflowNodePositions();
      if (!this.workflowHistoryMuted) {
        this._workflowHistoryReset();
      }
      return true;
    },

    _serializeWorkflowSteps() {
      const rows = Array.isArray(this.workflowSteps) ? this.workflowSteps : [];
      const out = [];
      for (let i = 0; i < rows.length; i += 1) {
        const step = rows[i] || {};
        const stepId = this._normalizeWorkflowStepId(step.step_id, `step_${i + 1}`) || `step_${i + 1}`;
        const nodeType = ["action", "condition"].includes(`${step.node_type || ""}`.trim().toLowerCase())
          ? `${step.node_type}`.trim().toLowerCase()
          : "action";
        const capabilityId = `${step.capability_id || ""}`.trim().toLowerCase();
        if (nodeType === "action" && !capabilityId) return { error: `第 ${i + 1} 个 action 节点缺少 capability_id` };
        const actions = nodeType === "action"
          ? this.workflowActionsForCapability(capabilityId || this.workflowQuickAddCapability)
          : ["auto"];
        let action = `${step.action || "auto"}`.trim().toLowerCase() || "auto";
        if (nodeType !== "action") action = "auto";
        if (nodeType === "action" && !actions.includes(action)) action = actions[0] || "auto";
        const inputMode = ["auto", "project", "inline"].includes(`${step.input_mode || ""}`.trim().toLowerCase())
          ? `${step.input_mode}`.trim().toLowerCase()
          : "auto";
        const inputParsed = this.parseJsonSafe(step.input_json, null);
        if (inputParsed === null || typeof inputParsed !== "object" || Array.isArray(inputParsed)) {
          return { error: `节点 ${stepId} 的 input JSON 必须是对象` };
        }
        step.input = inputParsed;
        step.step_id = stepId;
        step.node_type = nodeType;
        step.capability_id = capabilityId;
        step.action = action;
        step.input_mode = inputMode;
        step.save_as = this._normalizeWorkflowStepId(step.save_as, "");
        step.next_step_id = this._normalizeWorkflowStepId(step.next_step_id, "");
        step.next_on_success = this._normalizeWorkflowStepId(step.next_on_success, "");
        step.next_on_error = this._normalizeWorkflowStepId(step.next_on_error, "");
        step.next_on_skip = this._normalizeWorkflowStepId(step.next_on_skip, "");
        const pos = this._workflowStepPosition(step, i);
        step.ui_x = pos.x;
        step.ui_y = pos.y;
        step.ui_position = { x: pos.x, y: pos.y };
        const runIfText = `${step.run_if_expr || ""}`.trim();
        const conditionText = `${step.condition_expr || ""}`.trim();
        let runIfValue = "";
        if (runIfText) {
          const parsedRunIf = this.parseJsonSafe(runIfText, null);
          runIfValue = parsedRunIf === null ? runIfText : parsedRunIf;
        }
        let conditionValue = "";
        if (conditionText) {
          const parsedCondition = this.parseJsonSafe(conditionText, null);
          conditionValue = parsedCondition === null ? conditionText : parsedCondition;
        }
        out.push({
          step_id: stepId,
          node_type: nodeType,
          continue_on_error: !!step.continue_on_error,
          enabled: step.enabled === undefined ? true : !!step.enabled,
          next_step_id: step.next_step_id || undefined,
          next_on_success: step.next_on_success || undefined,
          next_on_error: step.next_on_error || undefined,
          next_on_skip: step.next_on_skip || undefined,
          input: inputParsed,
          ui_position: { x: pos.x, y: pos.y },
        });
        if (nodeType === "action") {
          out[out.length - 1].capability_id = capabilityId;
          out[out.length - 1].action = action;
          out[out.length - 1].input_mode = inputMode;
          out[out.length - 1].run_if = runIfValue || undefined;
          out[out.length - 1].save_as = step.save_as || undefined;
        } else {
          if (capabilityId) out[out.length - 1].capability_id = capabilityId;
          out[out.length - 1].condition = conditionValue || undefined;
        }
      }
      if (out.length === 0) return { error: "至少保留一个节点" };
      this.workflowBuilder.steps_json = this.jsonPretty(out);
      this.workflowActiveStepIndex = Math.max(0, Math.min(this.workflowActiveStepIndex, out.length - 1));
      this.workflowStepJsonError = "";
      this._refreshWorkflowCanvasMetrics();
      return { steps: out };
    },

    addWorkflowStep(capabilityId = "") {
      const nextIndex = (Array.isArray(this.workflowSteps) ? this.workflowSteps.length : 0) + 1;
      const row = this._defaultWorkflowStep(capabilityId, nextIndex);
      this.workflowSteps.push(row);
      this.workflowActiveStepIndex = this.workflowSteps.length - 1;
      this._workflowCommitWithHistory();
    },

    addWorkflowConditionStep() {
      const nextIndex = (Array.isArray(this.workflowSteps) ? this.workflowSteps.length : 0) + 1;
      const row = this._defaultWorkflowStep("", nextIndex, "condition");
      this.workflowSteps.push(row);
      this.workflowActiveStepIndex = this.workflowSteps.length - 1;
      this._workflowCommitWithHistory();
    },

    removeWorkflowStep(index) {
      const idx = Number(index);
      if (!Number.isFinite(idx) || idx < 0 || idx >= this.workflowSteps.length) return;
      this.workflowSteps.splice(idx, 1);
      if (this.workflowSteps.length === 0) {
        this.workflowSteps.push(this._defaultWorkflowStep("", 1));
      }
      this.workflowActiveStepIndex = Math.max(0, Math.min(idx, this.workflowSteps.length - 1));
      this._workflowCommitWithHistory();
    },

    moveWorkflowStep(index, delta) {
      const idx = Number(index);
      const d = Number(delta);
      if (!Number.isFinite(idx) || !Number.isFinite(d)) return;
      const target = idx + d;
      if (idx < 0 || target < 0 || idx >= this.workflowSteps.length || target >= this.workflowSteps.length) return;
      const arr = this.workflowSteps;
      const tmp = arr[idx];
      arr[idx] = arr[target];
      arr[target] = tmp;
      this.workflowActiveStepIndex = target;
      this._workflowCommitWithHistory();
    },

    onWorkflowStepCapabilityChange(index) {
      const idx = Number(index);
      if (!Number.isFinite(idx) || idx < 0 || idx >= this.workflowSteps.length) return;
      const row = this.workflowSteps[idx];
      if (`${row.node_type || "action"}`.trim().toLowerCase() !== "action") {
        this._workflowCommitWithHistory();
        return;
      }
      const actions = this.workflowActionsForCapability(row.capability_id);
      if (!actions.includes(`${row.action || ""}`.trim().toLowerCase())) {
        row.action = actions[0] || "auto";
      }
      this._workflowCommitWithHistory();
    },

    onWorkflowStepNodeTypeChange(index) {
      const idx = Number(index);
      if (!Number.isFinite(idx) || idx < 0 || idx >= this.workflowSteps.length) return;
      const row = this.workflowSteps[idx];
      const nodeType = `${row.node_type || "action"}`.trim().toLowerCase() === "condition" ? "condition" : "action";
      row.node_type = nodeType;
      if (nodeType === "condition") {
        row.capability_id = "";
        row.action = "auto";
        row.input_mode = "auto";
        row.continue_on_error = false;
        row.save_as = "";
        row.run_if_expr = "";
      } else {
        if (!`${row.capability_id || ""}`.trim()) {
          row.capability_id = `${this.workflowQuickAddCapability || (this.workflowCatalog[0] && this.workflowCatalog[0].capability_id) || "subtitle_calibration"}`.trim().toLowerCase();
        }
        const actions = this.workflowActionsForCapability(row.capability_id);
        if (!actions.includes(`${row.action || ""}`.trim().toLowerCase())) {
          row.action = actions[0] || "auto";
        }
      }
      this._workflowCommitWithHistory();
    },

    onWorkflowStepChanged() {
      this._workflowCommitWithHistory();
    },

    _workflowRuntimeStepKey(rawStepId, fallback = "") {
      return this._normalizeWorkflowStepId(rawStepId, fallback);
    },

    resetWorkflowRuntimeStatus() {
      this.workflowRuntimeStatusMap = {};
      this.workflowRuntimeRunningStepId = "";
    },

    _workflowApplyRunResultStatus(run, runningStepId = "") {
      const map = {};
      const rows = Array.isArray(run && run.steps) ? run.steps : [];
      rows.forEach((item, idx) => {
        const sid = this._workflowRuntimeStepKey(item && item.step_id, `step_${idx + 1}`);
        if (!sid) return;
        const status = `${item && item.status ? item.status : ""}`.trim().toLowerCase();
        if (!status) return;
        map[sid] = status;
      });
      const runningSid = this._workflowRuntimeStepKey(runningStepId, "");
      if (runningSid && !["done", "error", "failed", "skipped", "cancelled"].includes(map[runningSid])) {
        map[runningSid] = "running";
      }
      this.workflowRuntimeStatusMap = map;
      this.workflowRuntimeRunningStepId = runningSid;
      const runId = run && run.run_id ? `${run.run_id}`.trim() : "";
      if (runId) this.workflowRuntimeLastRunId = runId;
    },

    _workflowRunningStepFromLog(logRows) {
      const rows = Array.isArray(logRows) ? logRows : [];
      for (let i = rows.length - 1; i >= 0; i -= 1) {
        const line = `${rows[i] || ""}`;
        const m = line.match(/\[Workflow\]\s+step_id=([a-zA-Z0-9_\-]+)/);
        if (m && m[1]) return this._workflowRuntimeStepKey(m[1], "");
      }
      return "";
    },

    onWorkflowRunJobTick(job) {
      const run = job && job.result && job.result.run ? job.result.run : null;
      const runningSid = this._workflowRunningStepFromLog(job && job.log ? job.log : []);
      if (run && typeof run === "object") {
        this._workflowApplyRunResultStatus(run, runningSid);
        return;
      }
      if (runningSid) {
        const map = this._workflowDeepCopy(this.workflowRuntimeStatusMap, {}) || {};
        if (!["done", "error", "failed", "skipped", "cancelled"].includes(map[runningSid])) {
          map[runningSid] = "running";
        }
        this.workflowRuntimeStatusMap = map;
        this.workflowRuntimeRunningStepId = runningSid;
      }
    },

    workflowNodeRuntimeStatus(step) {
      const sid = this._workflowRuntimeStepKey(step && step.step_id, "");
      if (!sid) return "";
      const map = this.workflowRuntimeStatusMap && typeof this.workflowRuntimeStatusMap === "object"
        ? this.workflowRuntimeStatusMap
        : {};
      const status = `${map[sid] || ""}`.trim().toLowerCase();
      if (status) return status;
      if (sid === this.workflowRuntimeRunningStepId) return "running";
      return "";
    },

    workflowNodeRuntimeClass(step) {
      const status = this.workflowNodeRuntimeStatus(step);
      if (status === "running") return "runtime-running";
      if (status === "done" || status === "success") return "runtime-done";
      if (status === "error" || status === "failed" || status === "cancelled") return "runtime-error";
      if (status === "skipped") return "runtime-skipped";
      return "";
    },

    workflowNodeRuntimeText(step) {
      const status = this.workflowNodeRuntimeStatus(step);
      if (status === "running") return "运行中";
      if (status === "done" || status === "success") return "成功";
      if (status === "error" || status === "failed") return "失败";
      if (status === "cancelled") return "已取消";
      if (status === "skipped") return "跳过";
      return "";
    },

    workflowStepDisplay(step) {
      const s = step || {};
      const nodeType = `${s.node_type || "action"}`.trim().toLowerCase();
      const cid = `${s.capability_id || ""}`.trim();
      const action = `${s.action || "auto"}`.trim();
      const sid = `${s.step_id || ""}`.trim();
      if (nodeType === "condition") {
        return `${sid || "condition"} · condition`;
      }
      if (!cid) return sid || "-";
      return `${sid || cid} · ${cid}/${action}`;
    },

    workflowStepInputSummary(step) {
      const nodeType = `${step && step.node_type ? step.node_type : "action"}`.trim().toLowerCase();
      if (nodeType === "condition") {
        const condText = `${step && step.condition_expr ? step.condition_expr : ""}`.trim();
        return condText ? `condition: ${condText.slice(0, 48)}` : "condition: (always true)";
      }
      const parsed = this.parseJsonSafe(step && step.input_json ? step.input_json : "{}", {});
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return "input: {}";
      const keys = Object.keys(parsed);
      if (!keys.length) return "input: {}";
      const short = keys.slice(0, 4).join(", ");
      return keys.length > 4 ? `input: ${short} +${keys.length - 4}` : `input: ${short}`;
    },

    _workflowDefaultNextStepId(index) {
      const idx = Number(index);
      if (!Number.isFinite(idx) || idx < 0) return "";
      if (!Array.isArray(this.workflowSteps) || idx + 1 >= this.workflowSteps.length) return "";
      return this._normalizeWorkflowStepId(this.workflowSteps[idx + 1].step_id, "");
    },

    _workflowPickTargetWithSource(candidates) {
      const items = Array.isArray(candidates) ? candidates : [];
      for (let i = 0; i < items.length; i += 1) {
        const row = Array.isArray(items[i]) ? items[i] : [];
        const to = this._normalizeWorkflowStepId(row[0], "");
        if (to) return { to, source: `${row[1] || "unknown"}`.trim() || "unknown" };
      }
      return { to: "", source: "none" };
    },

    workflowStepRouteRows(step, index) {
      const s = step || {};
      const nodeType = `${s.node_type || "action"}`.trim().toLowerCase();
      const nextStep = this._normalizeWorkflowStepId(s.next_step_id, "");
      const nextSuccess = this._normalizeWorkflowStepId(s.next_on_success, "");
      const nextError = this._normalizeWorkflowStepId(s.next_on_error, "");
      const nextSkip = this._normalizeWorkflowStepId(s.next_on_skip, "");
      const defaultNext = this._workflowDefaultNextStepId(index);

      if (nodeType === "condition") {
        const trueRoute = this._workflowPickTargetWithSource([
          [nextSuccess, "next_on_success"],
          [nextStep, "next_step_id"],
          [defaultNext, "implicit_sequence"],
        ]);
        const falseRoute = this._workflowPickTargetWithSource([
          [nextError, "next_on_error"],
          [nextSkip, "next_on_skip"],
          [nextStep, "next_step_id"],
          [defaultNext, "implicit_sequence"],
        ]);
        return [
          { when: "condition_true", ...trueRoute },
          { when: "condition_false", ...falseRoute },
        ];
      }

      const successRoute = this._workflowPickTargetWithSource([
        [nextSuccess, "next_on_success"],
        [nextStep, "next_step_id"],
        [defaultNext, "implicit_sequence"],
      ]);
      const errorRoute = this._workflowPickTargetWithSource([
        [nextError, "next_on_error"],
        [nextStep, "next_step_id"],
        [defaultNext, "implicit_sequence"],
      ]);
      const skipRoute = this._workflowPickTargetWithSource([
        [nextSkip, "next_on_skip"],
        [nextStep, "next_step_id"],
        [defaultNext, "implicit_sequence"],
      ]);
      return [
        { when: "success", ...successRoute },
        { when: "error", ...errorRoute },
        { when: "skip", ...skipRoute },
      ];
    },

    workflowGraphEdgesPreview() {
      const rows = Array.isArray(this.workflowSteps) ? this.workflowSteps : [];
      const edges = [];
      const seen = new Set();
      for (let i = 0; i < rows.length; i += 1) {
        const step = rows[i] || {};
        const from = this._normalizeWorkflowStepId(step.step_id, `step_${i + 1}`) || `step_${i + 1}`;
        const routes = this.workflowStepRouteRows(step, i);
        routes.forEach((route) => {
          const to = this._normalizeWorkflowStepId(route.to, "");
          if (!to) return;
          const when = `${route.when || ""}`.trim();
          const source = `${route.source || ""}`.trim();
          const key = `${from}::${to}::${when}::${source}`;
          if (seen.has(key)) return;
          seen.add(key);
          edges.push({ from, to, when, source });
        });
      }
      return edges;
    },

    workflowGraphInvalidEdges() {
      const ids = new Set(
        (Array.isArray(this.workflowSteps) ? this.workflowSteps : [])
          .map((step, idx) => this._normalizeWorkflowStepId(step && step.step_id, `step_${idx + 1}`))
          .filter(Boolean),
      );
      return this.workflowGraphEdgesPreview().filter(edge => !ids.has(this._normalizeWorkflowStepId(edge.to, "")));
    },

    setActiveWorkflowStep(index) {
      const idx = Number(index);
      if (!Number.isFinite(idx)) return;
      this.workflowActiveStepIndex = Math.max(0, Math.min(idx, this.workflowSteps.length - 1));
    },

    onWorkflowNodeDragEnd() {
      this.workflowCanvasDragIndex = -1;
      this.workflowCanvasDropIndex = -1;
      this.workflowCanvasNodeDragOffsetX = 0;
      this.workflowCanvasNodeDragOffsetY = 0;
      this._refreshWorkflowCanvasMetrics();
      const ret = this._workflowCommitWithHistory();
      if (ret.error) this.workflowStepJsonError = ret.error;
    },

    parseWorkflowStepsInput() {
      const serialized = this._serializeWorkflowSteps();
      if (serialized.error) {
        this.workflowStepJsonError = serialized.error;
        return { error: serialized.error };
      }
      const parsed = this.parseJsonSafe(this.workflowBuilder.steps_json, null);
      if (!Array.isArray(parsed) || parsed.length === 0) {
        return { error: "工作流步骤 JSON 必须是非空数组" };
      }
      return { steps: parsed };
    },

    applyWorkflowRawJsonToEditor() {
      const ok = this.syncWorkflowStepsFromJson();
      if (!ok) {
        this.capabilityMessage = this.workflowStepJsonError || "步骤 JSON 解析失败";
        return;
      }
      this.capabilityMessage = `已从 JSON 同步 ${this.workflowSteps.length} 个节点`;
    },

    writeWorkflowEditorToJson() {
      const ret = this._serializeWorkflowSteps();
      if (ret.error) {
        this.workflowStepJsonError = ret.error;
        this.capabilityMessage = ret.error;
        return;
      }
      this.capabilityMessage = `已把节点编辑写回 JSON（${ret.steps.length} 步）`;
    },

    parseWorkflowRunInput() {
      const text = `${this.workflowBuilder.input_json || ""}`.trim();
      if (!text) return {};
      const parsed = this.parseJsonSafe(text, null);
      if (parsed === null) return {};
      if (typeof parsed !== "object" || Array.isArray(parsed)) {
        return { error: "工作流输入 JSON 必须是对象" };
      }
      return { input: parsed };
    },

    useWorkflowDefinition(item) {
      if (!item || typeof item !== "object") return;
      this.workflowBuilder.workflow_id = `${item.workflow_id || ""}`.trim();
      this.workflowBuilder.name = `${item.name || ""}`.trim() || "自定义工作流";
      this.workflowBuilder.description = `${item.description || ""}`.trim();
      this.workflowBuilder.start_step_id = this._normalizeWorkflowStepId(item.start_step_id, "");
      this.workflowBuilder.steps_json = this.jsonPretty(Array.isArray(item.steps) ? item.steps : []);
      this.workflowBuilder.run_inline = false;
      this.workflowActiveStepIndex = 0;
      this.syncWorkflowStepsFromJson();
    },

    newWorkflowDefinition() {
      this.workflowBuilder.workflow_id = "";
      this.workflowBuilder.name = "自定义工作流";
      this.workflowBuilder.description = "";
      this.workflowBuilder.start_step_id = "";
      this.workflowBuilder.run_inline = true;
      this.workflowBuilder.steps_json = this.jsonPretty([this._defaultWorkflowStep("", 1)]);
      this.workflowBuilder.input_json = "{}";
      this.workflowActiveStepIndex = 0;
      this.syncWorkflowStepsFromJson();
      this.workflowPlan = null;
      this.workflowRunResult = null;
    },

    async loadWorkflowCatalog() {
      if (!this.projectDir) return;
      const data = await this.api("GET", "/api/workflows/catalog");
      if (data.error) {
        this.capabilityMessage = `工作流目录读取失败：${data.error}`;
        return;
      }
      this.workflowCatalog = Array.isArray(data.catalog) ? data.catalog : [];
      if (!this.workflowQuickAddCapability && this.workflowCatalog.length > 0) {
        this.workflowQuickAddCapability = `${this.workflowCatalog[0].capability_id || ""}`.trim().toLowerCase();
      }
      if (!this.workflowSteps || this.workflowSteps.length === 0) {
        this.syncWorkflowStepsFromJson();
      }
    },

    async loadWorkflowList() {
      if (!this.projectDir) return;
      const data = await this.api("GET", "/api/workflows");
      if (data.error) {
        this.capabilityMessage = `工作流列表读取失败：${data.error}`;
        return;
      }
      this.workflowList = Array.isArray(data.workflows) ? data.workflows : [];
    },

    async loadWorkflowRuns() {
      if (!this.projectDir) return;
      this.workflowHistoryLoading = true;
      const data = await this.api("GET", "/api/workflows/runs?limit=30");
      this.workflowHistoryLoading = false;
      if (data.error) {
        this.capabilityMessage = `工作流历史读取失败：${data.error}`;
        return;
      }
      this.workflowRuns = Array.isArray(data.items) ? data.items : [];
      this.workflowRunsTotal = Number(data.total_count || this.workflowRuns.length || 0);
    },

    async saveWorkflowDefinition() {
      if (!this.projectDir) return;
      const parsed = this.parseWorkflowStepsInput();
      if (parsed.error) {
        this.capabilityMessage = parsed.error;
        return;
      }
      const payload = {
        workflow_id: `${this.workflowBuilder.workflow_id || ""}`.trim(),
        name: `${this.workflowBuilder.name || ""}`.trim(),
        description: `${this.workflowBuilder.description || ""}`.trim(),
        start_step_id: this._normalizeWorkflowStepId(this.workflowBuilder.start_step_id, "") || undefined,
        steps: parsed.steps,
      };
      const data = await this.api("POST", "/api/workflows", payload);
      if (data.error) {
        this.capabilityMessage = `保存工作流失败：${data.error}`;
        return;
      }
      const wf = data.workflow || {};
      this.workflowBuilder.workflow_id = `${wf.workflow_id || this.workflowBuilder.workflow_id || ""}`.trim();
      this.workflowBuilder.name = `${wf.name || this.workflowBuilder.name || "自定义工作流"}`.trim();
      this.workflowBuilder.description = `${wf.description || this.workflowBuilder.description || ""}`.trim();
      this.workflowBuilder.start_step_id = this._normalizeWorkflowStepId(
        wf.start_step_id || this.workflowBuilder.start_step_id,
        "",
      );
      this.workflowBuilder.steps_json = this.jsonPretty(Array.isArray(wf.steps) ? wf.steps : parsed.steps);
      this.syncWorkflowStepsFromJson();
      this.capabilityMessage = `工作流已保存：${this.workflowBuilder.workflow_id || this.workflowBuilder.name}`;
      await this.loadWorkflowList();
    },

    async deleteWorkflowDefinition(workflowId) {
      if (!this.projectDir) return;
      const id = this.normalizeTemplateId(workflowId);
      if (!id) return;
      const data = await this.api("DELETE", `/api/workflows/${encodeURIComponent(id)}`);
      if (data.error) {
        this.capabilityMessage = `删除工作流失败：${data.error}`;
        return;
      }
      this.capabilityMessage = `已删除工作流：${id}`;
      if (`${this.workflowBuilder.workflow_id || ""}`.trim() === id) {
        this.newWorkflowDefinition();
      }
      await this.loadWorkflowList();
      await this.loadWorkflowRuns();
    },

    _buildWorkflowPlanPayload() {
      const parsed = this.parseWorkflowStepsInput();
      if (parsed.error) return { error: parsed.error };
      const inputParsed = this.parseWorkflowRunInput();
      if (inputParsed.error) return { error: inputParsed.error };
      const workflowId = `${this.workflowBuilder.workflow_id || ""}`.trim();
      const runInline = !!this.workflowBuilder.run_inline || !workflowId;
      const payload = {
        dry_run: !!this.workflowBuilder.dry_run,
        start_step_id: this._normalizeWorkflowStepId(this.workflowBuilder.start_step_id, "") || undefined,
        ...inputParsed,
      };
      if (runInline) {
        payload.workflow = {
          workflow_id: workflowId || undefined,
          name: `${this.workflowBuilder.name || "自定义工作流"}`.trim(),
          description: `${this.workflowBuilder.description || ""}`.trim(),
          steps: parsed.steps,
        };
      } else {
        payload.workflow_id = workflowId;
      }
      return payload;
    },

    async planWorkflowDefinition() {
      if (!this.projectDir) return;
      const payload = this._buildWorkflowPlanPayload();
      if (payload.error) {
        this.capabilityMessage = payload.error;
        return;
      }
      const data = await this.api("POST", "/api/workflows/plan", payload);
      if (data.error) {
        this.capabilityMessage = `工作流规划失败：${data.error}`;
        return;
      }
      this.workflowPlan = data.plan || null;
      const graph = (this.workflowPlan && this.workflowPlan.graph) ? this.workflowPlan.graph : {};
      const edgeCount = Number(graph.edge_count || 0);
      this.capabilityMessage = `工作流规划完成：${(this.workflowPlan && this.workflowPlan.total_steps) || 0} 节点 / ${edgeCount} 路由`;
    },

    async runWorkflowDefinition() {
      if (!this.projectDir) return;
      if (this.workflowRunning) return;
      const payload = this._buildWorkflowPlanPayload();
      if (payload.error) {
        this.capabilityMessage = payload.error;
        return;
      }
      this.workflowRunning = true;
      this.workflowRunResult = null;
      this.workflowRunJobId = "";
      this.resetWorkflowRuntimeStatus();

      const data = await this.api("POST", "/api/workflows/run", payload);
      if (data.error) {
        this.workflowRunning = false;
        this.capabilityMessage = `工作流执行失败：${data.error}`;
        return;
      }
      const jobId = `${data.job_id || ""}`.trim();
      if (!jobId) {
        this.workflowRunning = false;
        this.capabilityMessage = "工作流执行失败：未返回 job_id";
        return;
      }
      this.workflowRunJobId = jobId;
      this.capabilityMessage = `工作流已启动：${jobId}`;

      const job = await this.waitForJob(jobId, (j) => this.onWorkflowRunJobTick(j), 3 * 60 * 60 * 1000);
      this.workflowRunning = false;
      this.workflowRunJobId = "";
      if (job.status === "error") {
        if (this.workflowRuntimeRunningStepId) {
          const map = this._workflowDeepCopy(this.workflowRuntimeStatusMap, {}) || {};
          map[this.workflowRuntimeRunningStepId] = "error";
          this.workflowRuntimeStatusMap = map;
        }
        this.capabilityMessage = `工作流执行失败：${job.error || "任务错误"}`;
      } else if (job.status === "cancelled") {
        if (this.workflowRuntimeRunningStepId) {
          const map = this._workflowDeepCopy(this.workflowRuntimeStatusMap, {}) || {};
          map[this.workflowRuntimeRunningStepId] = "cancelled";
          this.workflowRuntimeStatusMap = map;
        }
        this.capabilityMessage = "工作流执行已取消";
      } else {
        this.workflowRunResult = (job.result && job.result.run) ? job.result.run : (job.result || null);
        this._workflowApplyRunResultStatus(this.workflowRunResult, "");
        const summary = (this.workflowRunResult && this.workflowRunResult.summary) ? this.workflowRunResult.summary : {};
        this.capabilityMessage = `工作流执行完成：成功 ${summary.success_steps || 0}，失败 ${summary.failed_steps || 0}`;
      }
      await this.loadWorkflowRuns();
    },

    async rerunWorkflow(runItem, rerunFailedOnly = true) {
      if (!runItem || !runItem.run_id) return;
      if (this.workflowRunning) return;
      this.workflowRunning = true;
      this.resetWorkflowRuntimeStatus();
      const data = await this.api(
        "POST",
        `/api/workflows/runs/${encodeURIComponent(runItem.run_id)}/rerun`,
        {
          dry_run: !!this.workflowBuilder.dry_run,
          rerun_failed_only: !!rerunFailedOnly,
        }
      );
      if (data.error) {
        this.workflowRunning = false;
        this.capabilityMessage = `工作流重跑失败：${data.error}`;
        return;
      }
      const jobId = `${data.job_id || ""}`.trim();
      if (!jobId) {
        this.workflowRunning = false;
        this.capabilityMessage = "工作流重跑失败：未返回 job_id";
        return;
      }
      const job = await this.waitForJob(jobId, (j) => this.onWorkflowRunJobTick(j), 3 * 60 * 60 * 1000);
      this.workflowRunning = false;
      if (job.status === "done") {
        this.workflowRunResult = (job.result && job.result.run) ? job.result.run : this.workflowRunResult;
        this._workflowApplyRunResultStatus(this.workflowRunResult, "");
        const rerunCtx = (this.workflowRunResult && this.workflowRunResult.rerun_context && typeof this.workflowRunResult.rerun_context === "object")
          ? this.workflowRunResult.rerun_context
          : {};
        const nextRunId = this.workflowRunResult && this.workflowRunResult.run_id ? this.workflowRunResult.run_id : jobId;
        const mode = `${rerunCtx.mode || ""}`.trim();
        if (mode === "failed_with_dependencies") {
          const failedCount = Array.isArray(rerunCtx.failed_step_ids) ? rerunCtx.failed_step_ids.length : 0;
          const includedCount = Array.isArray(rerunCtx.included_step_ids) ? rerunCtx.included_step_ids.length : 0;
          this.capabilityMessage = `工作流重跑完成：${runItem.run_id} -> ${nextRunId}（失败节点 ${failedCount}，执行子图 ${includedCount}）`;
        } else {
          this.capabilityMessage = `工作流重跑完成：${runItem.run_id} -> ${nextRunId}`;
        }
      } else if (job.status === "cancelled") {
        if (this.workflowRuntimeRunningStepId) {
          const map = this._workflowDeepCopy(this.workflowRuntimeStatusMap, {}) || {};
          map[this.workflowRuntimeRunningStepId] = "cancelled";
          this.workflowRuntimeStatusMap = map;
        }
        this.capabilityMessage = "工作流重跑已取消";
      } else {
        if (this.workflowRuntimeRunningStepId) {
          const map = this._workflowDeepCopy(this.workflowRuntimeStatusMap, {}) || {};
          map[this.workflowRuntimeRunningStepId] = "error";
          this.workflowRuntimeStatusMap = map;
        }
        this.capabilityMessage = `工作流重跑失败：${job.error || jobId}`;
      }
      await this.loadWorkflowRuns();
    },
    };
  };
})(window);
