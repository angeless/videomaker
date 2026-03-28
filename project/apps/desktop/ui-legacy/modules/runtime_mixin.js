(function (global) {
  const ns = (global.VideoEditorModules = global.VideoEditorModules || {});

  ns.createRuntimeMixin = function createRuntimeMixin() {
    return {
    async init() {
      this.syncWorkflowStepsFromJson();
      this._bindWorkflowCanvasPointerEvents();
      this._bindWorkflowShortcuts();
      await this.bootstrapApiSession();
      await this.loadUiSettings();
      this.applyUiSettings();
      await this.runSystemPreflight(false);
      await this.fetchStatus();
      await this.loadAiSettings();
      await this.refreshTaskQueue();
      await this.refreshLibrary();
      this.loading = false;
      if (!this.taskQueueTimer) {
        this.taskQueueTimer = setInterval(() => this.refreshTaskQueue(), 3000);
      }

      if (this.projectDir) {
        this.topModule = "production";
        this.productionView = this.uiSettings.preferred_production_view || this.productionView || "hub";
        if (this.productionView === "workflow") {
          await this.loadStepData();
        }
        await this.loadCapabilityWorkbench();
      } else {
        this.topModule = "analysis";
        this.showInit = false;
        if (!this.initVideosDir && this.uiSettings.default_videos_dir) {
          this.initVideosDir = this.uiSettings.default_videos_dir;
        }
        if (!this.initProjectDir && this.uiSettings.default_project_dir) {
          this.initProjectDir = this.uiSettings.default_project_dir;
        }
      }
      if (!this.uiSettings.onboarding_completed) {
        this.showOnboardingWizard = true;
      }
    },

    // ── API 工具 ─────────────────────────────────────────────────

    async bootstrapApiSession() {
      try {
        const res = await fetch("/api/session/bootstrap", { method: "GET" });
        const text = await res.text();
        let data = {};
        try {
          data = text ? JSON.parse(text) : {};
        } catch {
          data = {};
        }
        if (!res.ok || data.error) {
          this.apiSessionReady = false;
          return false;
        }
        this.apiSessionToken = `${data.token || ""}`.trim();
        this.apiCsrfToken = `${data.csrf_token || ""}`.trim();
        this.apiSessionRequired = !!data.auth_required;
        this.apiSessionReady = true;
        return true;
      } catch {
        this.apiSessionReady = false;
        return false;
      }
    },

    friendlyErrorMessage(rawError) {
      const text = `${rawError || ""}`.trim();
      if (!text) return "请求失败，请稍后重试。";
      const lowered = text.toLowerCase();
      if (lowered.includes("traceback")) {
        return "系统执行异常。请重试；若持续失败，请在应用设置中导出日志后反馈。";
      }
      if (lowered.includes("no module named")) {
        return "运行环境缺少依赖。请重启应用，启动器会自动补齐依赖。";
      }
      if (lowered.includes("413") || lowered.includes("请求内容过大")) {
        return "本次提交内容过大，请拆成多次执行。";
      }
      if (lowered.includes("api key") || lowered.includes("unauthorized")) {
        return "AI Key 未配置或无效，请先在 AI 配置中保存有效 Key。";
      }
      if (lowered.includes("csrf") || lowered.includes("安全校验")) {
        return "安全校验已过期，请刷新应用后重试。";
      }
      if (lowered.includes("非法来源") || lowered.includes("origin_forbidden")) {
        return "当前请求来源不被允许，请在应用内操作。";
      }
      if (text.length > 300) {
        return "操作失败（已截断技术细节）。请重试或查看诊断日志。";
      }
      return text;
    },

    async api(method, path, body, _retried = false) {
      const opts = { method, headers: { "Content-Type": "application/json" } };
      if (this.apiSessionToken) {
        opts.headers["X-VideoEditor-Token"] = this.apiSessionToken;
      }
      const upperMethod = `${method || "GET"}`.toUpperCase();
      if (this.apiCsrfToken && !["GET", "HEAD", "OPTIONS"].includes(upperMethod)) {
        opts.headers["X-VideoEditor-CSRF"] = this.apiCsrfToken;
      }
      if (body !== undefined) opts.body = JSON.stringify(body);
      try {
        const res = await fetch(path, opts);
        const text = await res.text();
        let data = {};
        try {
          data = text ? JSON.parse(text) : {};
        } catch {
          data = { error: text || "服务端返回非 JSON 响应" };
        }
        if (!res.ok && !data.error) {
          data.error = `请求失败（HTTP ${res.status}）`;
        }
        const code = `${data.code || ""}`.trim();
        if (res.status === 401 && code === "local_auth_required" && !_retried) {
          const ok = await this.bootstrapApiSession();
          if (ok) {
            return this.api(method, path, body, true);
          }
        }
        if (res.status === 403 && code === "csrf_required" && !_retried) {
          const ok = await this.bootstrapApiSession();
          if (ok) {
            return this.api(method, path, body, true);
          }
        }
        if (data.error) {
          data.raw_error = data.error;
          data.error = this.friendlyErrorMessage(data.error);
        }
        return data;
      } catch (err) {
        return { error: `请求失败：${err && err.message ? err.message : "网络异常"}` };
      }
    },

    async fetchStatus() {
      const data = await this.api("GET", "/api/status");
      if (data.ready) {
        this._applyState(data);
      } else if (!data.error && this.projectDir) {
        // BF-001: backend lost project state (e.g. server restart) but frontend still shows project
        this.projectDir = "";
        this.steps = [];
        this.showToast("后端服务已重启，项目状态已重置，请重新打开项目", "warn", 8000);
      }
    },

    preflightBadgeClass(status) {
      const key = `${status || ""}`.trim().toLowerCase();
      if (key === "ok") return "badge-success";
      if (key === "error") return "badge-danger";
      return "badge-warn";
    },

    preflightStatusText(status) {
      const key = `${status || ""}`.trim().toLowerCase();
      if (key === "ok") return "通过";
      if (key === "error") return "阻塞";
      if (key === "warning") return "需关注";
      return key || "未知";
    },

    async runSystemPreflight(force = false) {
      this.preflightLoading = true;
      this.preflightMessage = "";
      const data = await this.api("GET", `/api/system/preflight${force ? "?force=1" : ""}`);
      this.preflightLoading = false;
      if (data.error) {
        this.preflightMessage = `系统自检失败：${data.error}`;
        return;
      }
      const report = (data.preflight && typeof data.preflight === "object") ? data.preflight : null;
      this.preflightReport = report;
      this.preflightLastRunAt = report && report.summary ? `${report.summary.generated_at || ""}` : "";
      if (!report) {
        this.preflightMessage = "系统自检返回空结果";
        return;
      }
      const summary = report.summary || {};
      this.preflightMessage = `自检完成：通过 ${summary.ok || 0}，警告 ${summary.warning || 0}，阻塞 ${summary.error || 0}`;
    },

    _applyState(data) {
      const prevDir = this.projectDir;
      this.projectDir  = data.project_dir || "";
      this.videosDir   = data.videos_dir  || "";
      this.currentStep = data.current_step || 1;
      this.steps       = data.steps || [];
      this.config      = data.config || {};
      this.systemLoad  = data.system || this.systemLoad;
      this.runningHeavyJobs = data.running_jobs || [];
      if (data.task_queue && typeof data.task_queue === "object") {
        this.taskQueue = {
          max_running: Number(data.task_queue.max_running || this.taskQueue.max_running || 1),
          running_count: Number(data.task_queue.running_count || 0),
          queued_count: Number(data.task_queue.queued_count || 0),
          running: Array.isArray(data.task_queue.running) ? data.task_queue.running : [],
          queued: Array.isArray(data.task_queue.queued) ? data.task_queue.queued : [],
        };
      }
      if (Array.isArray(data.social_export_history)) {
        this.socialExportHistory = data.social_export_history;
      }

      // 切换了项目（或首次加载）→ 同步 activePanel 并清空所有缓存
      if (prevDir !== this.projectDir) {
        this.productionView = "hub";
        this.activePanel  = this.currentStep;
        this.materials    = {};
        this.frames       = [];
        this.scriptClips  = [];
        this.scriptSubs   = [];
        this.stageFiles   = {};
        this.finalUrl     = "";
        this.roughUrl     = "";
        this.capabilityMessage = "";
        this.topicLibraryItems = [];
        this.topicForm = {
          slug: "",
          title: "",
          category: "travel",
          audience: "short_video",
          hook_style: "story",
          outline_template: "",
          tags: "",
        };
        this.topicCopy.slug = "";
        this.topicCopy.draft = null;
        this.textRoughPlan = null;
        this.textRoughSpans = [];
        this.textRoughFilterKeyword = "";
        this.textRoughSourceLoading = false;
        this.textRoughSourceError = "";
        this.shortClipPlan = null;
        this.refinePlan = null;
        this.handoffResult = null;
        this.handoffLaunchResult = null;
        this.handoffCollectResult = null;
        this.socialExportPlan = null;
        this.socialExportValidation = null;
        this.socialExportResult = null;
        this.socialExportRunning = false;
        this.socialExportProgress = 0;
        this.socialExportLog = [];
        this.socialExportJobId = "";
        this.socialExportHistory = [];
        this.customExportTemplates = [];
        this.subtitlePlan = null;
        this.subtitleResult = null;
        this.imageSemanticAnalyze = null;
        this.imageSemanticSearch = null;
        this.articleExpandResult = null;
        this.publishPrepProfiles = [];
        this.publishPrepResult = null;
        this.contentPublishPlatforms = [];
        this.contentPublishSession = null;
        this.contentPublishPlan = null;
        this.contentPublishRun = null;
        this.workflowCatalog = [];
        this.workflowList = [];
        this.workflowRuns = [];
        this.workflowRunsTotal = 0;
        this.workflowPlan = null;
        this.workflowRunResult = null;
        this.workflowRunning = false;
        this.workflowRunJobId = "";
        this.workflowHistoryLoading = false;
        this.workflowBuilder = {
          workflow_id: "",
          name: "自定义工作流",
          description: "",
          start_step_id: "",
          dry_run: true,
          run_inline: false,
          steps_json: this.workflowBuilder && this.workflowBuilder.steps_json
            ? this.workflowBuilder.steps_json
            : "[]",
          input_json: "{}",
        };
        this.workflowSteps = [];
        this.workflowStepJsonError = "";
        this.workflowQuickAddCapability = "";
        this.workflowCanvasDragIndex = -1;
        this.workflowCanvasDropIndex = -1;
        this.workflowCanvasNodeDragOffsetX = 0;
        this.workflowCanvasNodeDragOffsetY = 0;
        this.workflowCanvasLinkActive = false;
        this.workflowCanvasLinkFromIndex = -1;
        this.workflowCanvasLinkOutputKey = "";
        this.workflowCanvasLinkPointerX = 0;
        this.workflowCanvasLinkPointerY = 0;
        this.workflowCanvasZoom = 1;
        this.workflowCanvasPanX = 20;
        this.workflowCanvasPanY = 20;
        this.workflowCanvasPanning = false;
        this.workflowCanvasPanStartClientX = 0;
        this.workflowCanvasPanStartClientY = 0;
        this.workflowCanvasPanStartX = 0;
        this.workflowCanvasPanStartY = 0;
        this.workflowCanvasSize = { width: 1200, height: 560 };
        this.workflowUndoStack = [];
        this.workflowRedoStack = [];
        this.workflowHistoryMuted = false;
        this.workflowClipboardNode = null;
        this.workflowRuntimeStatusMap = {};
        this.workflowRuntimeRunningStepId = "";
        this.workflowRuntimeLastRunId = "";
        this.workflowActiveStepIndex = 0;
        this.syncWorkflowStepsFromJson();
        this.audioPlan = null;
        this.audioSynthesis = null;
        this.audioTimeline = null;
        this.audioMixResult = null;
        this.audioBgmPick = null;
        this.audioPipelineRunning = false;
        this.audioPipelineProgress = 0;
        this.audioPipelineJobId = "";
        this.audioPipelineResult = null;
        this.idempotencyCacheLoading = false;
        this.idempotencyCachePruning = false;
        this.idempotencyCacheRecords = [];
        this.idempotencyCacheStats = null;
        this.idempotencyCacheLastPrune = null;
        this.idempotencyCacheInput = {
          source: "merged",
          ttl_seconds: 7 * 24 * 3600,
          include_expired: false,
          limit: 200,
          offset: 0,
          actor_id: "",
          endpoint: "",
          idempotency_key: "",
          project_path: "",
          match_mode: "contains",
        };
        this.idempotencyPruneInput = {
          ttl_seconds: 7 * 24 * 3600,
          remove_expired: true,
          clear_memory: false,
          clear_persisted: false,
          max_entries: "",
        };
        this.agentObservabilitySummary = null;
        this.agentObservabilityItems = [];
        this.agentObservabilityItemsTotal = 0;
        this.agentObservabilityItemsOffset = 0;
        this.agentObservabilityItemsHasMore = false;
        this.agentObservabilityHistoryCount = 0;
        this.agentObservabilityWindowCount = 0;
        this.agentObservabilityWindowLimit = 200;
        this.agentObservabilityLastExport = "";
        this.agentReplayRunningJobId = "";
        this.agentTaskDetailJobId = "";
        this.agentTaskDetailLoading = false;
        this.agentTaskDetailError = "";
        this.agentTaskDetail = null;
        this.agentTaskDetailLastExport = "";
        this.agentTemplates = [];
        this.agentTemplatesLoading = false;
        this.agentTemplateSelectedKeys = [];
        this.agentTemplateSearch = "";
        this.resetAgentTemplateEditor();
      }
    },

    stepInfo(n) {
      return this.steps.find(s => s.n === n) || {};
    },

    stepCls(n) {
      const s = this.stepInfo(n);
      if (s.status === "done" || s.status === "waiting_review") return "done";
      if (s.status === "error") return "error";
      if (n === this.activePanel) return "active";
      if (s.status === "running") return "running";
      return "";
    },

    async switchModule(moduleName) {
      this.topModule = moduleName;
      if (moduleName === "analysis") {
        await this.searchLibrary();
      } else if (moduleName === "production") {
        if (this.projectDir && this.productionView === "workflow") {
          this.activePanel = this.currentStep;
          await this.loadStepData();
        }
        await this.loadCapabilityWorkbench();
      }
    },

    async switchProductionView(viewName) {
      const v = `${viewName || ""}`.trim().toLowerCase();
      this.productionView = v === "workflow" ? "workflow" : "hub";
      this.uiSettings.preferred_production_view = this.productionView;
      await this.api("POST", "/api/settings/ui", { preferred_production_view: this.productionView });
      if (this.productionView === "workflow" && this.projectDir) {
        this.activePanel = this.currentStep;
        await this.loadStepData();
      }
      if (this.productionView === "hub") {
        await this.loadCapabilityWorkbench();
      }
    },

    get isHeavyBusy() {
      return this.ingestLoading || this.selectionLoading || this.jobStatus === "running";
    },

    sleep(ms) {
      return new Promise((resolve) => setTimeout(resolve, ms));
    },

    async waitForJob(jobId, onTick = null, timeoutMs = 60 * 60 * 1000) {
      const start = Date.now();
      let _lastStateJson = "";
      while (Date.now() - start < timeoutMs) {
        const j = await this.api("GET", `/api/job/${jobId}`);
        if (j.error) return { status: "error", error: j.error };
        // 仅在 state 实际变化时才调 _applyState，避免每 800ms 替换引用导致 Alpine 重绘闪烁
        if (j.state && j.state.task_queue) {
          const stateJson = JSON.stringify(j.state);
          if (stateJson !== _lastStateJson) {
            _lastStateJson = stateJson;
            this._applyState(j.state);
          }
        }
        if (onTick) onTick(j);
        if (j.status === "done" || j.status === "error" || j.status === "cancelled") return j;
        await this.sleep(800);
      }
      return { status: "error", error: "任务等待超时，请稍后查看任务状态" };
    },

    async refreshTaskQueue() {
      const data = await this.api("GET", "/api/tasks/queue");
      if (data.error) return;
      const q = (data.task_queue && typeof data.task_queue === "object") ? data.task_queue : {};
      const next = {
        max_running: Number(q.max_running || this.taskQueue.max_running || 1),
        running_count: Number(q.running_count || 0),
        queued_count: Number(q.queued_count || 0),
        running: Array.isArray(q.running) ? q.running : [],
        queued: Array.isArray(q.queued) ? q.queued : [],
      };
      // 仅在数据实际变化时更新，避免每 3s 无变化也触发 Alpine 重绘
      if (JSON.stringify(next) !== JSON.stringify(this.taskQueue)) {
        this.taskQueue = next;
      }
    },

    async cancelJob(jobId) {
      if (!jobId) return { error: "缺少 job_id" };
      return this.api("POST", `/api/job/${jobId}/cancel`, {});
    },

    async cancelIngestJob() {
      if (!this.ingestJobId) return;
      const data = await this.cancelJob(this.ingestJobId);
      if (data.error) {
        this.ingestMessage = `取消失败：${data.error}`;
        return;
      }
      this.ingestMessage = "已发送取消请求，正在安全停止…";
    },

    async cancelWorkflowJob() {
      if (!this.jobId) return;
      const data = await this.cancelJob(this.jobId);
      if (data.error) {
        this.showToast(`取消失败：${data.error}`, "danger");
        return;
      }
      this.jobLog = (this.jobLog || []).concat(["[系统] 已发送取消请求，正在安全停止…"]);
    },

    _jobKindZh(kind) {
      const map = {
        workflow_step: "制作步骤任务",
        library_ingest_local: "本地素材分析",
        library_ingest_local_images: "本地图片分析",
        library_ingest_gdrive: "云端素材分析",
        library_ingest_gdrive_images: "云端图片分析",
        social_export: "社媒导出任务",
        audio_voice: "音频流水线",
        custom_workflow: "自定义工作流",
      };
      return map[kind] || kind || "任务";
    },

    async _handleBusyConflict(data, actionLabel = "当前操作") {
      const jobs = Array.isArray(data && data.running_jobs) ? data.running_jobs : [];
      if (!jobs.length) return false;
      const summary = jobs
        .map((j) => `${this._jobKindZh(j.kind)}(${j.job_id || "unknown"})`)
        .join("、");
      const ingestJob = jobs.find((j) => `${j.kind || ""}`.startsWith("library_ingest"));
      if (!ingestJob) {
        this.showToast(`${actionLabel}被阻塞：${data.error || "有任务运行中"}；正在运行：${summary}`, "warn", 6000);
        return true;
      }
      const ok = confirm(
        `${actionLabel}被阻塞：${data.error || "有任务运行中"}\n` +
        `正在运行：${summary}\n是否先取消素材分析任务再继续？`
      );
      if (!ok) return true;
      const cancelRet = await this.cancelJob(ingestJob.job_id);
      if (cancelRet.error) {
        this.showToast(`取消素材分析失败：${cancelRet.error}`, "danger");
        return true;
      }
      this.ingestMessage = "已发送取消请求，待分析任务安全停止后再继续。";
      return true;
    },

    async _ensureWorkflowRunnable(actionLabel = "当前操作") {
      if (this.jobStatus === "running" || this.jobStatus === "queued") {
        this.showToast("制作流程任务正在运行，请稍后再操作", "warn");
        return false;
      }
      if (this.ingestLoading && this.ingestJobId) {
        const ok = confirm(`${actionLabel}前需要停止当前素材分析任务。是否立即取消该分析任务？`);
        if (!ok) return false;
        const ret = await this.cancelJob(this.ingestJobId);
        if (ret.error) {
          this.showToast(`取消素材分析失败：${ret.error}`, "danger");
          return false;
        }
        this.ingestMessage = "已发送取消请求，待分析任务安全停止后再继续。";
        return false;
      }
      return true;
    },
    };
  };
})(window);
