/* ── 视频制作助手前端 (Alpine.js) ──────────────────────────────────── */

document.addEventListener("alpine:init", () => {
  Alpine.data("app", () => ({

    // ── 全局状态 ────────────────────────────────────────────────
    loading:     true,
    projectDir:  "",
    videosDir:   "",
    currentStep: 0,   // 服务器工作流进度（只读，不被导航操作修改）
    activePanel: 0,   // 当前显示的面板（由导航操作控制）
    steps:       [],
    config:      {},
    topModule:   "analysis",      // analysis | production

    // ── 全局素材库（语义分析模块）──────────────────────────────
    libraryStats: {
      total_assets: 0,
      total_locations: 0,
      available_assets: 0,
      local_assets: 0,
      gdrive_assets: 0,
      semantic_dimensions_supported: 0,
      semantic_ready_assets: 0,
      semantic_pending_assets: 0,
    },
    libraryQuery:     "",
    libraryResults:   [],
    libraryLoading:   false,
    libraryMessage:   "",
    libraryPageSize:  120,
    libraryOffset:    0,
    libraryTotalMatches: 0,
    libraryHasMore:   false,
    ingestLocalPath:  "",
    ingestLocalMaxVideos: 600,
    ingestLocalPreviewLoading: false,
    ingestLocalPreviewError: "",
    ingestLocalPreview: null,
    ingestDriveUrl:   "",
    ingestDriveMaxVideos: 80,
    ingestDrivePriority: "",
    ingestDriveMaxScanFolders: 120,
    ingestPreviewLoading: false,
    ingestPreviewError: "",
    ingestPreview: null,
    ingestLoading:    false,
    ingestMessage:    "",
    ingestJobId:      "",
    ingestProgress:   0,
    ingestLog:        [],
    ingestRefresh:    false,
    aiSettings: {
      provider: "openai",
      ai_model: "",
      ai_base_url: "",
      openai_api_key: "",
      anthropic_api_key: "",
      clear_openai_api_key: false,
      clear_anthropic_api_key: false,
    },
    aiStatus: {
      openai_api_key_set: false,
      anthropic_api_key_set: false,
      openai_api_key_masked: "",
      anthropic_api_key_masked: "",
    },
    aiLoading: false,
    aiSaving:  false,
    aiMessage: "",

    // ── 制作模块 Step 1：素材选择（最多 50）────────────────────
    selectedAssets:       [],
    maxSelectedAssets:    50,
    selectionLoading:     false,
    selectionError:       "",
    productionProjectDir: "",

    // ── 新建/打开项目对话框 ─────────────────────────────────────
    showInit:      false,
    initMode:      "new",          // "new" | "open"
    initVideosDir: "",
    initProjectDir: "",
    initOpenDir:   "",
    initLoading:   false,
    initError:     "",

    // ── 当前选题（Step 2）──────────────────────────────────────
    topics:         [],
    selectedTopic:  null,
    topicCustom:    "",

    // ── 脚本（Step 3）──────────────────────────────────────────
    scriptClips:  [],
    scriptSubs:   [],
    scriptJson:   "",
    scriptView:   "visual",        // "visual" | "json"
    scriptSaving: false,

    // ── 帧预览（Step 5）────────────────────────────────────────
    frames: [],

    // ── 粗剪视频（Step 6）──────────────────────────────────────
    roughUrl:   "",
    renderOpts: {
      width: 1080, height: 1920, fps: 30, crf: 18, preset: "medium",
      enable_skin_smooth: true, enable_color_grading: true,
      enable_skill_enhance: true,
      aesthetic_preset: "travel_story",
      transition_style: "fade",
      transition_duration: 0.35,
      skin_smooth_strength: 0.4,
      bgm_path: "", bgm_volume: 0.35, narration_path: "",
      subtitle_font: "PingFangSC-Regular", subtitle_size: 56,
    },

    // ── 精渲染（Step 7）────────────────────────────────────────
    stageFiles:  {},
    finalUrl:    "",
    stageNames: [
      "片段剪切 & 合并",
      "美颜滤镜",
      "色彩调级",
      "字幕压制",
      "BGM 混音",
    ],

    // ── 后台任务 ────────────────────────────────────────────────
    jobId:       null,
    jobStatus:   "",               // running | done | error
    jobLog:      [],
    jobTimer:    null,
    jobProgress: 0,
    systemLoad: {
      cpu_count: 0,
      load_1m: 0,
      load_5m: 0,
      load_15m: 0,
      load_ratio_1m: 0,
    },
    runningHeavyJobs: [],

    // ── 素材列表（Step 1）──────────────────────────────────────
    materials:   {},

    // ── init ────────────────────────────────────────────────────
    async init() {
      await this.fetchStatus();
      await this.loadAiSettings();
      await this.refreshLibrary();
      this.loading = false;

      if (this.projectDir) {
        this.topModule = "production";
        await this.loadStepData();
      } else {
        this.topModule = "analysis";
        this.showInit = false;
      }
    },

    // ── API 工具 ─────────────────────────────────────────────────

    async api(method, path, body) {
      const opts = { method, headers: { "Content-Type": "application/json" } };
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
        return data;
      } catch (err) {
        return { error: `请求失败：${err && err.message ? err.message : "网络异常"}` };
      }
    },

    async fetchStatus() {
      const data = await this.api("GET", "/api/status");
      if (data.ready) this._applyState(data);
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

      // 切换了项目（或首次加载）→ 同步 activePanel 并清空所有缓存
      if (prevDir !== this.projectDir) {
        this.activePanel  = this.currentStep;
        this.materials    = {};
        this.frames       = [];
        this.scriptClips  = [];
        this.scriptSubs   = [];
        this.stageFiles   = {};
        this.finalUrl     = "";
        this.roughUrl     = "";
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

    switchModule(moduleName) {
      this.topModule = moduleName;
      if (moduleName === "analysis") {
        this.searchLibrary();
      } else if (moduleName === "production" && this.projectDir) {
        this.activePanel = this.currentStep;
        this.loadStepData();
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
      while (Date.now() - start < timeoutMs) {
        const j = await this.api("GET", `/api/job/${jobId}`);
        if (j.error) return { status: "error", error: j.error };
        if (onTick) onTick(j);
        if (j.status === "done" || j.status === "error" || j.status === "cancelled") return j;
        await this.sleep(800);
      }
      return { status: "error", error: "任务等待超时，请稍后查看任务状态" };
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
        alert(`取消失败：${data.error}`);
        return;
      }
      this.jobLog = (this.jobLog || []).concat(["[系统] 已发送取消请求，正在安全停止…"]);
    },

    get selectedCount() {
      return this.selectedAssets.length;
    },

    isSelected(uid) {
      return this.selectedAssets.some(item => item.uid === uid);
    },

    toggleSelect(asset) {
      if (!asset || !asset.uid) return;
      const existingIdx = this.selectedAssets.findIndex(item => item.uid === asset.uid);
      if (existingIdx >= 0) {
        this.selectedAssets.splice(existingIdx, 1);
        this.selectionError = "";
        return;
      }
      if (this.selectedAssets.length >= this.maxSelectedAssets) {
        this.selectionError = `最多只能选择 ${this.maxSelectedAssets} 个素材`;
        return;
      }
      this.selectedAssets.push(asset);
      this.selectionError = "";
    },

    removeSelected(uid) {
      const idx = this.selectedAssets.findIndex(item => item.uid === uid);
      if (idx >= 0) this.selectedAssets.splice(idx, 1);
      this.selectionError = "";
    },

    clearSelection() {
      this.selectedAssets = [];
      this.selectionError = "";
    },

    // ── 新建/打开项目 ────────────────────────────────────────────

    setPathValue(target, value) {
      if (!target) return;
      const parts = target.split(".");
      if (parts.length === 1) {
        this[target] = value;
        return;
      }
      let cur = this;
      for (let i = 0; i < parts.length - 1; i += 1) {
        const key = parts[i];
        if (typeof cur[key] !== "object" || cur[key] === null) cur[key] = {};
        cur = cur[key];
      }
      cur[parts[parts.length - 1]] = value;
    },

    async pickFolder(target) {
      const data = await this.api("POST", "/api/dialog/folder");
      if (data.path) {
        this.setPathValue(target, data.path);
        return;
      }
      if (data.error && !data.cancelled) {
        alert(`选择文件夹失败：${data.error}`);
      }
    },

    async pickFile(target) {
      const data = await this.api("POST", "/api/dialog/file");
      if (data.path) {
        this.setPathValue(target, data.path);
        return;
      }
      if (data.error && !data.cancelled) {
        alert(`选择文件失败：${data.error}`);
      }
    },

    async loadAiSettings() {
      this.aiLoading = true;
      const data = await this.api("GET", "/api/settings/ai");
      this.aiLoading = false;
      if (data.error) {
        this.aiMessage = `AI 配置读取失败：${data.error}`;
        return;
      }

      this.aiStatus = {
        openai_api_key_set: !!data.openai_api_key_set,
        anthropic_api_key_set: !!data.anthropic_api_key_set,
        openai_api_key_masked: data.openai_api_key_masked || "",
        anthropic_api_key_masked: data.anthropic_api_key_masked || "",
      };
      this.aiSettings.provider = data.provider || this.aiSettings.provider || "openai";
      this.aiSettings.ai_model = data.ai_model || "";
      this.aiSettings.ai_base_url = data.ai_base_url || "";
      this.aiSettings.openai_api_key = "";
      this.aiSettings.anthropic_api_key = "";
      this.aiSettings.clear_openai_api_key = false;
      this.aiSettings.clear_anthropic_api_key = false;
      this.aiMessage = "";
    },

    async saveAiSettings() {
      this.aiSaving = true;
      this.aiMessage = "";
      const payload = {
        provider: this.aiSettings.provider || "",
        ai_model: this.aiSettings.ai_model || "",
        ai_base_url: this.aiSettings.ai_base_url || "",
        openai_api_key: this.aiSettings.openai_api_key || "",
        anthropic_api_key: this.aiSettings.anthropic_api_key || "",
        clear_openai_api_key: !!this.aiSettings.clear_openai_api_key,
        clear_anthropic_api_key: !!this.aiSettings.clear_anthropic_api_key,
      };
      const data = await this.api("POST", "/api/settings/ai", payload);
      this.aiSaving = false;
      if (data.error) {
        this.aiMessage = `AI 配置保存失败：${data.error}`;
        return;
      }
      this.aiStatus = {
        openai_api_key_set: !!data.openai_api_key_set,
        anthropic_api_key_set: !!data.anthropic_api_key_set,
        openai_api_key_masked: data.openai_api_key_masked || "",
        anthropic_api_key_masked: data.anthropic_api_key_masked || "",
      };
      this.aiSettings.openai_api_key = "";
      this.aiSettings.anthropic_api_key = "";
      this.aiSettings.clear_openai_api_key = false;
      this.aiSettings.clear_anthropic_api_key = false;
      this.aiMessage = "AI 配置已保存，可直接用于后续脚本生成。";
    },

    async createProject() {
      if (!this.initVideosDir) { this.initError = "请选择素材目录"; return; }
      this.initLoading = true;
      this.initError   = "";
      const data = await this.api("POST", "/api/init", {
        videos_dir:  this.initVideosDir,
        project_dir: this.initProjectDir || "",
      });
      this.initLoading = false;
      if (data.error) { this.initError = data.error; return; }
      this.showInit = false;
      await this.fetchStatus();
      this.topModule = "production";
      this.runCurrentStep();
    },

    async createProjectFromSelection() {
      if (this.isHeavyBusy) {
        this.selectionError = "已有任务在运行，请等待完成后再创建项目";
        return;
      }
      if (this.selectedAssets.length === 0) {
        this.selectionError = "请先从素材库选择至少 1 个视频";
        return;
      }
      if (this.selectedAssets.length > this.maxSelectedAssets) {
        this.selectionError = `每次最多选择 ${this.maxSelectedAssets} 个素材`;
        return;
      }
      this.selectionLoading = true;
      this.selectionError = "";
      const data = await this.api("POST", "/api/init", {
        selected_video_uids: this.selectedAssets.map(item => item.uid),
        project_dir: this.productionProjectDir || "",
      });
      this.selectionLoading = false;
      if (data.error) {
        this.selectionError = data.error;
        return;
      }

      if (data.ready || data.project_dir) {
        this._applyState(data);
      } else {
        await this.fetchStatus();
      }
      this.topModule = "production";
      this.activePanel = this.currentStep;
      await this.loadStepData();
    },

    async openProject() {
      if (!this.initOpenDir) { this.initError = "请选择项目目录"; return; }
      this.initLoading = true;
      this.initError   = "";
      const data = await this.api("POST", "/api/open_project", { project_dir: this.initOpenDir });
      this.initLoading = false;
      if (data.error) { this.initError = data.error; return; }
      this.showInit = false;
      this._applyState(data);
      this.topModule = "production";
      await this.loadStepData();
    },

    // ── 素材库（语义分析模块）───────────────────────────────────

    async loadLibraryStats() {
      const data = await this.api("GET", "/api/library/stats");
      if (!data.error) this.libraryStats = data;
    },

    async searchLibrary(query = null, append = false) {
      const q = query === null ? this.libraryQuery : query;
      const normalizedQuery = `${q || ""}`;
      const appendMode = !!append && normalizedQuery.trim() === `${this.libraryQuery || ""}`.trim();
      this.libraryQuery = normalizedQuery;
      const reqOffset = appendMode ? this.libraryOffset : 0;
      this.libraryLoading = true;
      const requestedLimit = Math.max(30, Math.min(parseInt(this.libraryPageSize, 10) || 120, 500));
      const data = await this.api(
        "GET",
        `/api/library/search?q=${encodeURIComponent(this.libraryQuery)}&limit=${requestedLimit}&offset=${reqOffset}`
      );
      this.libraryLoading = false;
      if (data.error) {
        if (!appendMode) this.libraryResults = [];
        this.libraryHasMore = false;
        this.libraryMessage = `搜索失败：${data.error}`;
        return;
      }

      const pageResults = Array.isArray(data.results) ? data.results : [];
      if (appendMode) {
        const existing = new Set((this.libraryResults || []).map(item => item && item.uid).filter(Boolean));
        const merged = this.libraryResults.slice();
        pageResults.forEach((item) => {
          if (!item || !item.uid || existing.has(item.uid)) return;
          existing.add(item.uid);
          merged.push(item);
        });
        this.libraryResults = merged;
      } else {
        this.libraryResults = pageResults;
      }

      this.libraryOffset = reqOffset + pageResults.length;
      this.libraryHasMore = !!data.has_more;
      const totalMatches = Number.isFinite(Number(data.total_matches))
        ? Number(data.total_matches)
        : (this.libraryResults.length || 0);
      this.libraryTotalMatches = totalMatches;

      const shown = this.libraryResults.length;
      if (!this.libraryQuery.trim()) {
        this.libraryMessage = this.libraryHasMore
          ? `已加载 ${shown}/${totalMatches} 条素材，点击“加载更多”继续`
          : `已展示全部素材：${shown} 条`;
      } else {
        this.libraryMessage = this.libraryHasMore
          ? `关键词「${this.libraryQuery}」已加载 ${shown}/${totalMatches} 条`
          : `关键词「${this.libraryQuery}」命中 ${shown} 条`;
      }
    },

    async refreshLibrary() {
      await this.loadLibraryStats();
      this.libraryOffset = 0;
      this.libraryHasMore = false;
      this.libraryTotalMatches = 0;
      await this.searchLibrary(this.libraryQuery || "", false);
    },

    async loadMoreLibrary() {
      if (this.libraryLoading || !this.libraryHasMore) return;
      await this.searchLibrary(this.libraryQuery || "", true);
    },

    async ingestLocalSource() {
      if (!this.ingestLocalPath) return;
      if (this.isHeavyBusy) {
        this.ingestMessage = "已有任务在运行，请等待当前任务完成";
        return;
      }
      this.ingestLoading = true;
      this.ingestMessage = "";
      this.ingestProgress = 0;
      this.ingestLog = [];
      let maxVideos = parseInt(this.ingestLocalMaxVideos, 10);
      if (!Number.isFinite(maxVideos) || maxVideos <= 0) maxVideos = 600;
      if (maxVideos > 5000) maxVideos = 5000;
      this.ingestLocalMaxVideos = maxVideos;

      const data = await this.api("POST", "/api/library/ingest/local", {
        path: this.ingestLocalPath,
        max_videos: maxVideos,
      });
      if (data.error) {
        this.ingestLoading = false;
        this.ingestMessage = `本地分析失败：${data.error}`;
        return;
      }

      this.ingestJobId = data.job_id || "";
      this.ingestMessage = "本地素材分析任务已启动…";
      const job = await this.waitForJob(this.ingestJobId, (j) => {
        this.ingestProgress = j.progress || 0;
        this.ingestLog = j.log || [];
        if (j.system) this.systemLoad = j.system;
      });
      this.ingestLoading = false;
      this.ingestJobId = "";

      if (job.status === "error") {
        this.ingestMessage = `本地分析失败：${job.error || "任务执行失败"}`;
        return;
      }
      if (job.status === "cancelled") {
        this.ingestMessage = "本地分析已取消";
        await this.refreshLibrary();
        return;
      }

      const payload = (job.result && job.result.result) ? job.result : {};
      const r = payload.result || {};
      const refreshedCount = Array.isArray(r.assets) ? r.assets.filter(a => a && a.semantic_refreshed).length : 0;
      this.ingestMessage = `本地素材分析完成：候选 ${r.total_candidates || r.scanned || 0}，本次扫描 ${r.scanned || 0}，入库 ${r.indexed || 0}，重复命中 ${r.dedup_hits || 0}${refreshedCount > 0 ? `，语义刷新 ${refreshedCount}` : ""}${r.truncated ? "（已按上限截断）" : ""}`;
      await this.refreshLibrary();
    },

    async previewLocalSource() {
      if (!this.ingestLocalPath) return;
      if (this.isHeavyBusy) {
        this.ingestLocalPreviewError = "当前有重任务运行中，请稍后再预览";
        return;
      }
      this.ingestLocalPreviewLoading = true;
      this.ingestLocalPreviewError = "";
      this.ingestLocalPreview = null;
      const data = await this.api("POST", "/api/library/preview/local", {
        path: this.ingestLocalPath,
        max_results: 20,
      });
      this.ingestLocalPreviewLoading = false;
      if (data.error) {
        this.ingestLocalPreviewError = data.error;
        return;
      }
      this.ingestLocalPreview = data.preview || null;
    },

    async ingestDriveSource() {
      if (!this.ingestDriveUrl) return;
      if (this.isHeavyBusy) {
        this.ingestMessage = "已有任务在运行，请等待当前任务完成";
        return;
      }
      this.ingestLoading = true;
      this.ingestMessage = "";
      this.ingestProgress = 0;
      this.ingestLog = [];
      let maxVideos = parseInt(this.ingestDriveMaxVideos, 10);
      if (!Number.isFinite(maxVideos) || maxVideos <= 0) maxVideos = 80;
      if (maxVideos > 500) maxVideos = 500;
      this.ingestDriveMaxVideos = maxVideos;
      let maxScanFolders = parseInt(this.ingestDriveMaxScanFolders, 10);
      if (!Number.isFinite(maxScanFolders) || maxScanFolders <= 0) maxScanFolders = 120;
      if (maxScanFolders > 2000) maxScanFolders = 2000;
      this.ingestDriveMaxScanFolders = maxScanFolders;
      const data = await this.api("POST", "/api/library/ingest/gdrive", {
        url: this.ingestDriveUrl,
        refresh: this.ingestRefresh,
        max_videos: maxVideos,
        priority_subdirs: this.ingestDrivePriority || "",
        max_scan_folders: maxScanFolders,
      });
      if (data.error) {
        this.ingestLoading = false;
        this.ingestMessage = `Google Drive 分析失败：${data.error}`;
        return;
      }

      this.ingestJobId = data.job_id || "";
      this.ingestMessage = "Google Drive 分析任务已启动…";
      const job = await this.waitForJob(this.ingestJobId, (j) => {
        this.ingestProgress = j.progress || 0;
        this.ingestLog = j.log || [];
        if (j.system) this.systemLoad = j.system;
      });
      this.ingestLoading = false;
      this.ingestJobId = "";
      if (job.status === "error") {
        this.ingestMessage = `Google Drive 分析失败：${job.error || "任务执行失败"}`;
        return;
      }
      if (job.status === "cancelled") {
        this.ingestMessage = "Google Drive 分析已取消";
        await this.refreshLibrary();
        return;
      }

      const payload = (job.result && job.result.result) ? job.result : {};
      const r = payload.result || {};
      const refreshedCount = Array.isArray(r.assets) ? r.assets.filter(a => a && a.semantic_refreshed).length : 0;
      const modeLabel = r.scan_mode === "cache_only"
        ? "缓存复用"
        : (r.scan_mode === "priority_fast_scan"
            ? "优先扫描"
            : (r.scan_mode === "full_recursive_scan" ? "完整扫描" : "单文件"));
      const folderInfo = typeof r.scanned_folders === "number" ? `，扫描目录 ${r.scanned_folders}` : "";
      this.ingestMessage = `Google Drive 分析完成（${modeLabel}${folderInfo}）：列出 ${r.listed_files || 0}，视频候选 ${r.video_candidates || 0}，下载 ${r.downloaded_videos || 0}，入库 ${r.indexed || 0}，重复命中 ${r.dedup_hits || 0}${refreshedCount > 0 ? `，语义刷新 ${refreshedCount}` : ""}${r.truncated ? "（已按上限截断）" : ""}`;
      await this.refreshLibrary();
    },

    async previewDriveSource() {
      if (!this.ingestDriveUrl) return;
      if (this.isHeavyBusy) {
        this.ingestPreviewError = "当前有重任务运行中，请稍后再预览";
        return;
      }
      this.ingestPreviewLoading = true;
      this.ingestPreviewError = "";
      this.ingestPreview = null;

      let maxScanFolders = parseInt(this.ingestDriveMaxScanFolders, 10);
      if (!Number.isFinite(maxScanFolders) || maxScanFolders <= 0) maxScanFolders = 120;
      if (maxScanFolders > 2000) maxScanFolders = 2000;
      this.ingestDriveMaxScanFolders = maxScanFolders;

      const data = await this.api("POST", "/api/library/preview/gdrive", {
        url: this.ingestDriveUrl,
        priority_subdirs: this.ingestDrivePriority || "",
        max_scan_folders: maxScanFolders,
        max_results: 20,
      });
      this.ingestPreviewLoading = false;
      if (data.error) {
        this.ingestPreviewError = data.error;
        return;
      }
      this.ingestPreview = data.preview || null;
    },

    // ── 运行当前步骤 ──────────────────────────────────────────────

    async runCurrentStep() {
      if (this.isHeavyBusy) {
        alert("已有任务在运行，请稍后再执行");
        return;
      }
      if (!this.projectDir) {
        alert("请先选择素材并创建制作项目");
        return;
      }
      const data = await this.api("POST", "/api/run_step");
      if (data.error) { alert(data.error); return; }
      this.startPolling(data.job_id);
    },

    // ── 审核通过 + 运行下一步 ─────────────────────────────────────

    async approve(step, fields = {}) {
      if (this.isHeavyBusy) {
        alert("已有任务在运行，请稍后再审核");
        return;
      }
      const data = await this.api("POST", `/api/approve/${step}`, { approved: true, ...fields });
      if (data.error) { alert(data.error); return; }
      this.startPolling(data.job_id);
    },

    // ── 轮询后台任务 ──────────────────────────────────────────────

    startPolling(jobId) {
      this.jobId       = jobId;
      this.jobStatus   = "running";
      this.jobLog      = [];
      this.jobProgress = 0;
      clearInterval(this.jobTimer);
      this.jobTimer = setInterval(() => this.pollJob(), 1000);
    },

    async pollJob() {
      if (!this.jobId) return;
      const data = await this.api("GET", `/api/job/${this.jobId}`);
      if (data.error) {
        this.jobStatus = "error";
        this.jobLog = (this.jobLog || []).concat([`[系统] ${data.error}`]);
        clearInterval(this.jobTimer);
        this.jobTimer = null;
        return;
      }
      this.jobLog      = data.log || [];
      this.jobProgress = data.progress || 0;
      this.jobStatus   = data.status;

      if (data.state) {
        // 更新工作流状态但保留当前面板位置
        const savedPanel = this.activePanel;
        this._applyState(data.state);
        this.activePanel = savedPanel;
      }

      if (data.status === "done" || data.status === "error" || data.status === "cancelled") {
        clearInterval(this.jobTimer);
        this.jobTimer = null;
        if (data.status === "done") {
          // 任务完成后跳到新的当前步骤
          this.activePanel = this.currentStep;
          await this.loadStepData();
        }
      }
    },

    // ── 按步骤加载数据 ─────────────────────────────────────────────

    async loadStepData() {
      if (!this.projectDir) return;
      const step = this.activePanel;
      if (step === 1) await this.loadMaterials();
      if (step === 2) this.parseTopic();
      if (step === 3) await this.loadScript();
      if (step === 5) await this.loadFrames();
      if (step === 6) {
        this.roughUrl = `/api/files/preview/rough_cut.mp4?t=${Date.now()}`;
        this.loadRenderOpts();
      }
      if (step === 7) await this.loadStages();
    },

    // ── Step 1：素材 ────────────────────────────────────────────

    async loadMaterials() {
      const data = await this.api("GET", "/api/materials");
      this.materials = data || {};
    },

    get materialsList() {
      if (!this.materials || Array.isArray(this.materials)) return this.materials || [];
      if (this.materials.clips) return this.materials.clips;
      return Object.entries(this.materials).map(([uid, item]) => {
        const meta = (item.analysis && item.analysis.metadata) ? item.analysis.metadata : {};
        const tech = (item.analysis && item.analysis.local_analysis && item.analysis.local_analysis.technical)
          ? item.analysis.local_analysis.technical
          : {};
        return {
          uid,
          id: uid,
          filename: item.filename || uid,
          path: item.path || meta.path || "",
          duration: meta.duration || 0,
          resolution: tech.resolution || "",
        };
      });
    },

    formatDur(sec) {
      if (!sec) return "—";
      const s = parseFloat(sec).toFixed(1);
      return `${s}s`;
    },

    toSemanticZh(value) {
      const raw = `${value || ""}`.trim();
      if (!raw) return "";
      const dict = {
        unknown: "未知",
        general: "通用",
        person: "人物",
        people: "人物",
        mountain: "山地",
        beach: "海边",
        city: "城市",
        indoor: "室内",
        forest: "森林",
        waterfall: "瀑布",
        snow: "雪景",
        church: "教堂",
        bridge: "桥梁",
        castle: "城堡",
        temple: "寺庙",
        gothic: "哥特式",
        architecture: "建筑地标",
        religious: "宗教建筑",
        walking: "行走",
        sports: "运动",
        driving: "驾车",
        talking: "口播",
        food: "美食",
        scenic: "风景",
        morning: "清晨",
        afternoon: "午后",
        sunset: "黄昏",
        night: "夜景",
        spring: "春季",
        summer: "夏季",
        autumn: "秋季",
        winter: "冬季",
        sunny: "晴天",
        cloudy: "多云",
        rain: "雨天",
        fog: "雾天",
        aerial: "航拍",
        tracking: "跟拍",
        pan_tilt: "摇移",
        handheld: "手持",
        static: "固定机位",
        drone: "无人机",
        vehicle: "车载",
        tripod: "三脚架",
        close_up: "特写",
        medium: "中景",
        wide: "远景",
        macro: "微距",
        first_person: "第一视角",
        third_person: "第三视角",
        drone_view: "航拍视角",
        eye_level: "平视",
        vlog: "Vlog",
        cinematic: "电影感",
        documentary: "纪录感",
        tutorial: "教程向",
        travel: "旅行向",
        architecture_tour: "建筑巡礼",
        architecture_documentary: "建筑纪录",
        warm: "暖色",
        cool: "冷色",
        high_contrast: "高对比",
        natural: "自然色",
        hook: "开场钩子",
        broll: "过渡空镜",
        explanation: "讲解段",
        climax: "高潮段",
        establishing: "建立镜头",
        opening: "开场用途",
        context: "交代场景",
        highlight: "高光段落",
        transition: "过渡用途",
        supporting: "补充段落",
        low: "低",
        medium: "中等",
        medium_quality: "中",
        high: "高",
        low_light: "低照度",
        golden_hour: "黄金时刻",
        hard_light: "硬光",
        natural_light: "自然光",
        diffused: "柔光",
        backlit: "逆光",
        portrait: "竖屏",
        landscape: "横屏",
        square: "方屏",
        dynamic: "动感",
        stable: "稳定",
        balanced: "均衡",
        travel_vlog: "旅行Vlog",
        action_montage: "动作混剪",
        landmark_story: "地标故事",
        atmospheric_broll: "氛围空镜",
        hero_shot: "主镜头",
        storytelling_clip: "叙事镜头",
        information: "信息获取",
        inspiration: "灵感启发",
        entertainment: "娱乐观看",
        technical: "技术建议",
        content: "内容建议",
        general_content: "通用内容",
        travel_content: "旅行内容",
        tutorial_content: "教程内容",
        culture_content: "文化内容",
        blue_dominant: "蓝色主导",
        green_dominant: "绿色主导",
        red_dominant: "红色主导",
        bright: "明亮",
        dim: "偏暗",
        balanced_brightness: "亮度均衡",
        vivid: "高饱和",
        desaturated: "低饱和",
        neutral_saturation: "中性饱和",
        fast_motion: "快速运动",
        moderate_motion: "中等运动",
        static_motion: "静态镜头",
        complex_texture: "复杂纹理",
        medium_texture: "中等纹理",
        simple_texture: "简洁纹理",
        high_face_presence: "人物占比高",
        medium_face_presence: "人物占比中",
        low_face_presence: "人物占比低",
        mixed: "混合",
      };

      const translateToken = (token) => {
        const key = `${token || ""}`.trim().toLowerCase();
        if (!key) return "";
        if (dict[key]) return dict[key];
        if (key.startsWith("priority_")) {
          const lv = key.replace("priority_", "");
          const lvMap = { high: "高", medium: "中", low: "低" };
          return `优先级${lvMap[lv] || lv}`;
        }
        return this.toZhSentence(token);
      };

      const key = raw.toLowerCase();
      if (dict[key]) return dict[key];
      if (key.startsWith("priority_")) {
        const lv = key.replace("priority_", "");
        const lvMap = { high: "高", medium: "中", low: "低" };
        return `优先级${lvMap[lv] || lv}`;
      }

      const tokens = raw.split(/[\s,，;；|\/]+/).map(x => x.trim()).filter(Boolean);
      if (tokens.length > 1) {
        const mapped = [];
        tokens.forEach((t) => {
          const zh = translateToken(t);
          if (zh && !mapped.includes(zh)) mapped.push(zh);
        });
        if (mapped.length) return mapped.join(" / ");
      }
      return translateToken(raw) || raw;
    },

    toZhSentence(text) {
      const source = `${text || ""}`.trim();
      if (!source) return "";
      const replaces = [
        ["person", "人物"],
        ["people", "人群"],
        ["snowy", "雪景"],
        ["snow", "雪"],
        ["mountain", "山"],
        ["building", "建筑"],
        ["street", "街道"],
        ["city", "城市"],
        ["vehicle", "车辆"],
        ["nature", "自然风景"],
        ["aerial", "航拍"],
        ["drone", "无人机"],
        ["walking", "行走"],
        ["running", "奔跑"],
        ["calm", "平静"],
        ["energetic", "有活力"],
        ["serene", "宁静"],
        ["church", "教堂"],
        ["cathedral", "大教堂"],
        ["chapel", "礼拜堂"],
        ["basilica", "教堂建筑"],
        ["gothic", "哥特式"],
        ["bridge", "桥梁"],
        ["iron bridge", "铁桥"],
        ["steel bridge", "钢桥"],
        ["castle", "城堡"],
        ["fortress", "要塞"],
        ["temple", "寺庙"],
        ["shrine", "神社"],
        ["monastery", "修道院"],
        ["architecture", "建筑地标"],
        ["landmark", "地标"],
        ["mixed environment scene", "混合环境场景"],
        ["stable framing", "稳定机位"],
        ["bright daylight", "明亮日间光线"],
        ["soft natural light", "柔和自然光"],
        ["low-light", "低照度"],
        ["vivid", "鲜明"],
        ["lively", "活泼"],
        ["moody", "氛围感"],
        ["cinematic", "电影感"],
      ];
      let out = source;
      for (const [en, zh] of replaces) {
        out = out.replace(new RegExp(`\\b${en}\\b`, "gi"), zh);
      }
      return out;
    },

    semanticSummary(asset) {
      if (!asset || !asset.semantic) return "";
      const layers = asset.semantic.index_layers || {};
      const core = layers.core_search_tags || {};
      const coreZh = Array.isArray(core.zh) ? core.zh.filter(Boolean) : [];
      if (coreZh.length > 0) return coreZh.slice(0, 5).join(" · ");
      const s = asset.semantic;
      const parts = [s.setting, s.activity, s.camera_movement, s.time_of_day, s.narrative_role]
        .filter(Boolean)
        .filter(v => v !== "unknown" && v !== "general");
      return parts.map(v => this.toSemanticZh(v)).join(" · ");
    },

    semanticTags(asset, maxCount = 10) {
      const layers = (asset && asset.semantic && asset.semantic.index_layers)
        ? asset.semantic.index_layers
        : null;
      if (layers && layers.core_search_tags) {
        const core = layers.core_search_tags || {};
        const zh = Array.isArray(core.zh) ? core.zh.filter(Boolean) : [];
        const en = Array.isArray(core.en) ? core.en.filter(Boolean).map(x => this.toSemanticZh(x)) : [];
        const out = [];
        zh.forEach((t) => { if (!out.includes(t)) out.push(t); });
        en.forEach((t) => { if (!out.includes(t)) out.push(t); });
        return out.slice(0, maxCount);
      }
      const out = [];
      const pushTag = (val) => {
        const t = `${val || ""}`.trim();
        if (!t) return;
        if (t === "unknown" || t === "general") return;
        const zh = this.toSemanticZh(t);
        if (!out.includes(zh)) out.push(zh);
      };

      const semantic = (asset && asset.semantic) ? asset.semantic : {};
      const keys = [
        "content_type", "setting", "activity", "shot_type", "perspective",
        "visual_style", "narrative_role", "clip_purpose", "audience_intent",
        "use_cases", "business_tags", "topics",
      ];
      keys.forEach((k) => {
        const v = semantic[k];
        if (Array.isArray(v)) v.forEach(pushTag);
        else pushTag(v);
      });

      const kw = Array.isArray(asset && asset.semantic_keywords) ? asset.semantic_keywords : [];
      kw.slice(0, 30).forEach(pushTag);
      return out.slice(0, maxCount);
    },

    secondarySemanticTags(asset, maxCount = 12) {
      const layers = (asset && asset.semantic && asset.semantic.index_layers)
        ? asset.semantic.index_layers
        : null;
      if (!layers || !layers.secondary_tags) return [];
      const sec = layers.secondary_tags || {};
      const zh = Array.isArray(sec.zh) ? sec.zh.filter(Boolean) : [];
      const en = Array.isArray(sec.en) ? sec.en.filter(Boolean).map(x => this.toSemanticZh(x)) : [];
      const out = [];
      zh.forEach((t) => { if (!out.includes(t)) out.push(t); });
      en.forEach((t) => { if (!out.includes(t)) out.push(t); });
      return out.slice(0, maxCount);
    },

    // ── Step 2：选题 ────────────────────────────────────────────

    parseTopic() {
      // 从 step output 解析选题列表（若有 JSON）
      const s = this.stepInfo(2);
      if (s.output) {
        try {
          const j = JSON.parse(s.output);
          if (j.topics) { this.topics = j.topics; return; }
        } catch {}
      }
      // 无 AI 时提供两个通用默认选题
      this.topics = [
        { title: "异乡碎片", theme: "生活纪实", emotion: "沉静", duration: "15-20s" },
        { title: "城市脚步", theme: "城市观察", emotion: "律动", duration: "15-20s" },
      ];
    },

    selectTopic(t) {
      this.selectedTopic = t;
    },

    async approveTopic() {
      if (this.isHeavyBusy) {
        alert("已有任务在运行，请稍后再操作");
        return;
      }
      const step2 = this.stepInfo(2);
      if (step2.status !== "waiting_review") {
        const data = await this.api("POST", "/api/run_step");
        if (data.error) { alert(data.error); return; }
        this.startPolling(data.job_id);
        return;
      }
      const t = this.selectedTopic;
      const topicIndex = t && Number.isFinite(parseInt(t.index, 10)) ? parseInt(t.index, 10) : 1;
      const durMatch = t && t.duration ? String(t.duration).match(/\d+/) : null;
      const targetDuration = durMatch ? parseInt(durMatch[0], 10) : 60;
      await this.approve(2, {
        chosen_topic: topicIndex,
        user_ideas: this.topicCustom || (t ? `${t.title}；${t.theme || ""}` : ""),
        target_duration: Number.isFinite(targetDuration) ? targetDuration : 60,
      });
    },

    // ── Step 3：脚本 ────────────────────────────────────────────

    async loadScript() {
      const data = await this.api("GET", "/api/script");
      if (data.clips) {
        this.scriptClips = data.clips;
        this.scriptSubs  = data.subtitles || [];
      }
      this.scriptJson = JSON.stringify(data, null, 2);
    },

    async saveScript() {
      this.scriptSaving = true;
      if (this.scriptView === "json") {
        try {
          const parsed = JSON.parse(this.scriptJson);
          await this.api("POST", "/api/script", parsed);
        } catch (e) {
          alert("JSON 格式错误: " + e.message);
          this.scriptSaving = false;
          return;
        }
      } else {
        // 可视化模式：从 scriptClips / scriptSubs 重新组装
        const payload = { clips: this.scriptClips, subtitles: this.scriptSubs };
        await this.api("POST", "/api/script", payload);
      }
      this.scriptSaving = false;
    },

    async approveScript() {
      await this.saveScript();
      await this.approve(3);
    },

    toggleScriptView() {
      if (this.scriptView === "json") {
        this.scriptView = "visual";
        try {
          const parsed = JSON.parse(this.scriptJson);
          this.scriptClips = parsed.clips || [];
          this.scriptSubs  = parsed.subtitles || [];
        } catch {}
      } else {
        const payload = { clips: this.scriptClips, subtitles: this.scriptSubs };
        this.scriptJson = JSON.stringify(payload, null, 2);
        this.scriptView = "json";
      }
    },

    // ── Step 4：素材匹配 ────────────────────────────────────────

    async approveMatching() {
      await this.approve(4, { notes: "用户确认匹配结果" });
    },

    get matchedClips() {
      return this.scriptClips || [];
    },

    // ── Step 5：帧预览 ──────────────────────────────────────────

    async loadFrames() {
      const data = await this.api("GET", "/api/frames");
      this.frames = data || [];
    },

    // ── Step 6：粗剪 + 渲染参数 ──────────────────────────────────

    loadRenderOpts() {
      const c = this.config && this.config.render ? this.config.render : this.config;
      if (c.width)  this.renderOpts.width  = c.width;
      if (c.height) this.renderOpts.height = c.height;
      if (c.fps)    this.renderOpts.fps    = c.fps;
      if (c.crf_final) this.renderOpts.crf = c.crf_final;
      if (c.preset_final) this.renderOpts.preset = c.preset_final;
      if (c.bgm_volume) this.renderOpts.bgm_volume = c.bgm_volume;
      if (typeof c.enable_skin_smooth === "boolean") this.renderOpts.enable_skin_smooth = c.enable_skin_smooth;
      if (typeof c.enable_color_grading === "boolean") this.renderOpts.enable_color_grading = c.enable_color_grading;
      if (typeof c.enable_skill_enhance === "boolean") this.renderOpts.enable_skill_enhance = c.enable_skill_enhance;
      if (typeof c.skin_smooth_strength === "number") this.renderOpts.skin_smooth_strength = c.skin_smooth_strength;
      if (c.aesthetic_preset) this.renderOpts.aesthetic_preset = c.aesthetic_preset;
      if (c.transition_style) this.renderOpts.transition_style = c.transition_style;
      if (typeof c.transition_duration === "number") this.renderOpts.transition_duration = c.transition_duration;
      if (c.subtitle_font) this.renderOpts.subtitle_font = c.subtitle_font;
      if (c.subtitle_size) this.renderOpts.subtitle_size = c.subtitle_size;
    },

    async approveRender() {
      await this.approve(6, this.renderOpts);
    },

    // ── Step 7：精渲染进度 ─────────────────────────────────────

    async loadStages() {
      const data = await this.api("GET", "/api/stage_files");
      this.stageFiles = data || {};

      // 若 final.mp4 存在，设置预览 URL
      const fin = data["final.mp4"];
      if (fin && fin.exists) {
        this.finalUrl = `/api/files/output/final.mp4?t=${Date.now()}`;
      }
    },

    stageStatus(fname) {
      const s = this.stageFiles[fname];
      if (!s) return "pending";
      if (s.exists) return "done";
      if (this.jobStatus === "running") return "running";
      return "pending";
    },

    stageSize(fname) {
      const s = this.stageFiles[fname];
      if (!s || !s.exists) return "";
      const mb = (s.size / 1024 / 1024).toFixed(1);
      return `${mb} MB`;
    },

    async openFinder(path) {
      await this.api("POST", "/api/open_in_finder", { path });
    },

    async openFinalInFinder() {
      await this.openFinder(this.projectDir + "/output/final.mp4");
    },

    // ── 导航 ────────────────────────────────────────────────────

    async navToStep(n) {
      if (!this.projectDir) return;
      const s = this.stepInfo(n);
      // 允许跳转：该步已有进展（任何非空状态），或序号 <= 工作流当前步骤
      const accessible = n <= this.currentStep
        || s.status === "done"
        || s.status === "waiting_review"
        || s.status === "error";
      if (!accessible) return;
      this.activePanel = n;   // 只改面板，不改工作流进度
      await this.loadStepData();
    },

    // ── 日志滚动到底部 ────────────────────────────────────────────

    scrollLog() {
      this.$nextTick(() => {
        const el = document.getElementById("log-box");
        if (el) el.scrollTop = el.scrollHeight;
      });
    },

  }));
});
