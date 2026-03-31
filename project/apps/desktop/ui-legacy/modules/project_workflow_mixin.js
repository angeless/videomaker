(function (global) {
  const ns = (global.VideoEditorModules = global.VideoEditorModules || {});

  ns.createProjectWorkflowMixin = function createProjectWorkflowMixin() {
    return {
      isSelected(uid) {
        return this.selectedAssets.some(item => item.uid === uid);
      },

      toggleSelect(asset) {
        if (!asset || !asset.uid) return;
        if ((asset.asset_kind || "video") !== "video") {
          this.selectionError = "制作流程当前仅支持视频素材，图片不会加入 Step1";
          return;
        }
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

      async createProject() {
        const videosDir = `${this.initVideosDir || this.uiSettings.default_videos_dir || ""}`.trim();
        const projectDir = `${this.initProjectDir || this.uiSettings.default_project_dir || ""}`.trim();
        if (!videosDir) { this.initError = "请选择素材目录"; return; }
        this.initLoading = true;
        this.initError = "";
        const data = await this.api("POST", "/api/init", {
          videos_dir: videosDir,
          project_dir: projectDir,
        });
        this.initLoading = false;
        if (data.error) { this.initError = data.error; return; }
        this.showInit = false;
        await this.fetchStatus();
        this.topModule = "production";
        this.productionView = this.uiSettings.preferred_production_view || "hub";
        await this.loadCapabilityWorkbench();
        this.runCurrentStep();
      },

      async createProjectFromSelection() {
        if (this.isHeavyBusy) {
          this.selectionError = "已有任务在运行，请等待完成后再创建项目";
          return;
        }
        const selectedVideos = this.selectedAssets.filter(item => (item && (item.asset_kind || "video") === "video"));
        if (selectedVideos.length === 0) {
          this.selectionError = "请先从素材库选择至少 1 个视频";
          return;
        }
        if (selectedVideos.length > this.maxSelectedAssets) {
          this.selectionError = `每次最多选择 ${this.maxSelectedAssets} 个素材`;
          return;
        }
        this.selectionLoading = true;
        this.selectionError = "";
        const data = await this.api("POST", "/api/init", {
          selected_video_uids: selectedVideos.map(item => item.uid),
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
        await this.loadCapabilityWorkbench();
      },

      async openProject() {
        const projectDir = `${this.initOpenDir || this.uiSettings.last_project_dir || ""}`.trim();
        if (!projectDir) { this.initError = "请选择项目目录"; return; }
        this.initLoading = true;
        this.initError = "";
        const data = await this.api("POST", "/api/open_project", { project_dir: projectDir });
        this.initLoading = false;
        if (data.error) { this.initError = data.error; return; }
        this.showInit = false;
        this._applyState(data);
        this.topModule = "production";
        this.productionView = this.uiSettings.preferred_production_view || "hub";
        if (this.productionView === "workflow") {
          await this.loadStepData();
        }
        await this.loadCapabilityWorkbench();
      },

      async runCurrentStep() {
        if (!(await this._ensureWorkflowRunnable("执行下一步"))) return;
        if (!this.projectDir) {
          this.showToast("请先选择素材并创建制作项目", "warn");
          return;
        }
        const data = await this.api("POST", "/api/run_step");
        if (data.error) {
          const handled = await this._handleBusyConflict(data, "执行下一步");
          if (!handled) this.showToast(data.error, "danger");
          return;
        }
        this.startPolling(data.job_id);
      },

      async approve(step, fields = {}) {
        if (!(await this._ensureWorkflowRunnable(`审核 Step ${step}`))) return;
        const data = await this.api("POST", `/api/approve/${step}`, { approved: true, ...fields });
        if (data.error) {
          const handled = await this._handleBusyConflict(data, `审核 Step ${step}`);
          if (!handled) this.showToast(data.error, "danger");
          return;
        }
        this.startPolling(data.job_id);
      },

      startPolling(jobId) {
        this.jobId = jobId;
        this.jobStatus = "running";
        this.jobLog = [];
        this.jobProgress = 0;
        this.jobRecovery = null;
        this.jobEta = { available: false, remaining_seconds: null, source: "none", confidence: 0 };
        this._pollLastStateJson = "";
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
        // 仅在 log/progress/status 实际变化时才更新，减少无效重绘
        const newLogJson = JSON.stringify(data.log || []);
        if (newLogJson !== JSON.stringify(this.jobLog)) {
          this.jobLog = data.log || [];
        }
        this.jobProgress = data.progress || 0;
        this.jobStatus = data.status;
        this.jobEta = (data.eta && typeof data.eta === "object")
          ? data.eta
          : { available: false, remaining_seconds: null, source: "none", confidence: 0 };

        // 仅在 state 实际变化时才调 _applyState，避免每秒替换引用导致 Alpine 重绘闪烁
        if (data.state) {
          const stateJson = JSON.stringify(data.state);
          if (stateJson !== (this._pollLastStateJson || "")) {
            this._pollLastStateJson = stateJson;
            const savedPanel = this.activePanel;
            this._applyState(data.state);
            this.activePanel = savedPanel;
          }
        }

        if (data.status === "done" || data.status === "error" || data.status === "cancelled") {
          clearInterval(this.jobTimer);
          this.jobTimer = null;
          this._pollLastStateJson = "";
          // S2: 保存 recovery 信息
          this.jobRecovery = data.recovery || null;
          if (data.status !== "running") {
            this.jobEta = { available: false, remaining_seconds: 0, source: "finished", confidence: 1 };
          }
          if (data.status === "done") {
            this.activePanel = this.currentStep;
            await this.loadStepData();
            await this.loadCapabilityWorkbench();
            // S1: 渲染退化通知
            this._showDegradationToasts();
          }
        }
      },

      formatDurationBrief(totalSeconds) {
        const sec = Number(totalSeconds);
        if (!Number.isFinite(sec) || sec < 0) return "-";
        const s = Math.round(sec);
        if (s < 60) return `${s}s`;
        const mins = Math.floor(s / 60);
        const rem = s % 60;
        if (mins < 60) return rem > 0 ? `${mins}m ${rem}s` : `${mins}m`;
        const hours = Math.floor(mins / 60);
        const mm = mins % 60;
        return mm > 0 ? `${hours}h ${mm}m` : `${hours}h`;
      },

      jobEtaSourceZh(source) {
        const key = `${source || ""}`.trim().toLowerCase();
        const map = {
          blended: "历史+实时",
          progress: "实时进度",
          history: "历史样本",
          history_queue: "历史队列",
        };
        return map[key] || "估算";
      },

      jobEtaLabel() {
        const eta = (this.jobEta && typeof this.jobEta === "object") ? this.jobEta : {};
        if (!eta.available) return "预计剩余：计算中";
        const remain = this.formatDurationBrief(eta.remaining_seconds);
        const source = this.jobEtaSourceZh(eta.source);
        return `预计剩余：${remain}（${source}）`;
      },

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

      parseTopic() {
        const s = this.stepInfo(2);
        if (s.output) {
          try {
            const j = JSON.parse(s.output);
            if (j.topics) { this.topics = j.topics; return; }
          } catch {
            // ignore
          }
        }
        this.topics = [
          { title: "异乡碎片", theme: "生活纪实", emotion: "沉静", duration: "15-20s" },
          { title: "城市脚步", theme: "城市观察", emotion: "律动", duration: "15-20s" },
        ];
      },

      selectTopic(t) {
        this.selectedTopic = t;
      },

      async approveTopic() {
        const step2 = this.stepInfo(2);
        if (step2.status !== "waiting_review") {
          await this.runCurrentStep();
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

      async loadScript() {
        const data = await this.api("GET", "/api/script");
        if (data.clips) {
          this.scriptClips = data.clips;
          this.scriptSubs = data.subtitles || [];
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
            this.showToast(`JSON 格式错误: ${e.message}`, "danger");
            this.scriptSaving = false;
            return;
          }
        } else {
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
            this.scriptSubs = parsed.subtitles || [];
          } catch {
            // ignore
          }
        } else {
          const payload = { clips: this.scriptClips, subtitles: this.scriptSubs };
          this.scriptJson = JSON.stringify(payload, null, 2);
          this.scriptView = "json";
        }
      },

      async approveMatching() {
        await this.approve(4, { notes: "用户确认匹配结果" });
      },

      async loadFrames() {
        const data = await this.api("GET", "/api/frames");
        this.frames = data || [];
      },

      loadRenderOpts() {
        const c = this.config && this.config.render ? this.config.render : this.config;
        if (c.width) this.renderOpts.width = c.width;
        if (c.height) this.renderOpts.height = c.height;
        if (c.fps) this.renderOpts.fps = c.fps;
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
        if (typeof c.rough_target_seconds === "number") this.renderOpts.rough_target_seconds = c.rough_target_seconds;
        if (typeof c.rough_max_clips === "number") this.renderOpts.rough_max_clips = c.rough_max_clips;
        if (typeof c.rough_merge_gap_s === "number") this.renderOpts.rough_merge_gap_s = c.rough_merge_gap_s;
        if (typeof c.rough_remove_phrases === "string") this.renderOpts.rough_remove_phrases = c.rough_remove_phrases;
        if (c.subtitle_font) this.renderOpts.subtitle_font = c.subtitle_font;
        if (c.subtitle_size) this.renderOpts.subtitle_size = c.subtitle_size;
      },

      async approveRender() {
        await this.approve(6, this.renderOpts);
      },

      async loadStages() {
        const data = await this.api("GET", "/api/stage_files");
        this.stageFiles = data || {};
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
        await this.openFinder(`${this.projectDir}/output/final.mp4`);
      },

      async navToStep(n) {
        if (!this.projectDir) return;
        const s = this.stepInfo(n);
        const accessible = n <= this.currentStep
          || s.status === "done"
          || s.status === "waiting_review"
          || s.status === "error";
        if (!accessible) return;
        this.productionView = "workflow";
        this.activePanel = n;
        await this.loadStepData();
      },

      /** S2: 智能重试（优先走 recovery endpoint，回退到 runCurrentStep） */
      async retryWithRecovery() {
        const r = this.jobRecovery;
        if (r && r.can_retry && r.retry_hint && r.retry_hint.endpoint) {
          // 有明确 rerun 端点
          if (r.duplicate_risk) {
            this.showToast("注意: 重试可能产生重复发布，请确认", "warn", 5000);
          }
          let endpoint = r.retry_hint.endpoint;
          // 如果是 content_publish rerun，需要传 run_id
          const result = this.stepInfo(this.activePanel)?.output;
          let body = {};
          if (endpoint.includes("content_publish/rerun") && result) {
            try {
              const parsed = typeof result === "string" ? JSON.parse(result) : result;
              if (parsed.run_id) body.run_id = parsed.run_id;
            } catch { /* ignore */ }
          }
          const data = await this.api("POST", endpoint, body);
          if (data.error) {
            this.showToast(data.error, "danger");
            return;
          }
          if (data.job_id) {
            this.startPolling(data.job_id);
          } else {
            this.showToast("重试已提交", "success");
            this.jobStatus = "";
          }
        } else {
          // 无 recovery endpoint → 回退到普通重试
          await this.runCurrentStep();
        }
      },

      /** S1: 渲染退化 Toast 通知 / S4: AI 退化通知 / S5: 审计降级通知 */
      _showDegradationToasts() {
        // S1: render degradations (step 7)
        const step7 = this.stepInfo(7);
        const degs = step7 && Array.isArray(step7.degradations) ? step7.degradations : [];
        const typeMap = { error: "danger", warning: "warn", info: "info" };
        for (const d of degs) {
          const toastType = typeMap[d.severity] || "warn";
          this.showToast(`渲染退化: ${d.reason || d.feature || "未知"}`, toastType, 8000);
        }
        // S4: AI degradation (steps 2, 3) — structured format
        for (const n of [2, 3]) {
          const step = this.stepInfo(n);
          if (step && step.ai_degraded) {
            const reason = step.ai_degraded_reason || "AI 生成已降级";
            this.showToast(`[Step ${n}] 已降级：${reason}`, "warn", 8000);
          }
        }
        // S5: fetch recent degradation events from audit log
        this._fetchDegradationAudit();
      },

      async _fetchDegradationAudit() {
        try {
          const data = await this.api("GET", "/api/system/audit?operation=degradation&limit=10");
          if (!Array.isArray(data.entries)) return;
          // Only show events from the last 60 seconds to avoid repeating old toasts
          const cutoff = Date.now() - 60_000;
          const shown = this._degradationShownIds || new Set();
          for (const entry of data.entries) {
            if (shown.has(entry.id)) continue;
            const ts = entry.created_at ? new Date(entry.created_at + "Z").getTime() : 0;
            if (ts < cutoff) continue;
            shown.add(entry.id);
            const d = entry.detail || {};
            const module = entry.resource_type || "unknown";
            const reason = d.reason || "降级";
            const fallback = d.fallback_path ? ` → ${d.fallback_path}` : "";
            this.showToast(`[${module}] 已降级：${reason}${fallback}`, "warn", 8000);
          }
          this._degradationShownIds = shown;
        } catch {
          // audit query failure is non-critical
        }
      },

      scrollLog() {
        this.$nextTick(() => {
          const el = document.getElementById("log-box");
          if (el) el.scrollTop = el.scrollHeight;
        });
      },
    };
  };
})(window);
