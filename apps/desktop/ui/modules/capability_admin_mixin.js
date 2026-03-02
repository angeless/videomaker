(function (global) {
  const ns = (global.VideoEditorModules = global.VideoEditorModules || {});

  ns.createCapabilityAdminMixin = function createCapabilityAdminMixin() {
    return {
      async loadLibraryStats() {
        const data = await this.api("GET", "/api/library/stats");
        if (!data.error) {
          this.libraryStats = data;
          this.libraryHybridEnabled = !!data.hybrid_search_enabled;
          this.libraryEmbeddingEnabled = !!data.embedding_enabled;
          this.libraryEmbeddingStatus = `${data.embedding_status || ""}`;
          this.libraryEmbeddingStatusMessage = `${data.embedding_status_message || ""}`;
          this.libraryEmbeddingReadyAssets = parseInt(data.embedding_ready_assets || 0, 10) || 0;
        }
      },

      setLibrarySearchMode(mode) {
        const next = `${mode || ""}`.trim().toLowerCase();
        if (!["hybrid", "keyword", "vector"].includes(next)) return;
        if (this.librarySearchMode === next) return;
        this.librarySearchMode = next;
        this.libraryOffset = 0;
        this.libraryHasMore = false;
        if (this.libraryResults.length > 0 || this.libraryQuery.trim()) {
          this.searchLibrary(this.libraryQuery || "", false);
        }
      },

      setLibraryMediaType(mediaType) {
        const next = `${mediaType || ""}`.trim().toLowerCase();
        if (!["all", "video", "image"].includes(next)) return;
        if (this.libraryMediaType === next) return;
        this.libraryMediaType = next;
        this.libraryOffset = 0;
        this.libraryHasMore = false;
        if (this.libraryResults.length > 0 || this.libraryQuery.trim()) {
          this.searchLibrary(this.libraryQuery || "", false);
        }
      },

      retrievalModeZh(mode) {
        const key = `${mode || ""}`.trim().toLowerCase();
        const map = {
          hybrid: "混合检索",
          keyword: "关键词检索",
          vector: "向量检索",
          browse: "素材浏览",
        };
        return map[key] || key || "未知模式";
      },

      mediaTypeZh(mediaType) {
        const key = `${mediaType || ""}`.trim().toLowerCase();
        const map = {
          all: "全部",
          video: "视频",
          image: "图片",
        };
        return map[key] || "全部";
      },

      embeddingStatusZh(reason) {
        const key = `${reason || ""}`.trim().toLowerCase();
        const map = {
          ready: "向量可用",
          missing_api_key: "未配置 OpenAI API Key",
          missing_openai_sdk: "缺少 openai SDK",
          missing_numpy: "缺少 numpy",
        };
        return map[key] || this.libraryEmbeddingStatusMessage || "向量不可用";
      },

      formatScore(val, digits = 3) {
        const num = Number(val);
        if (!Number.isFinite(num)) return "0";
        return num.toFixed(digits);
      },

      formatVectorScore(val) {
        const num = Number(val);
        if (!Number.isFinite(num)) return "0.000";
        return num.toFixed(3);
      },

      formatDateTime(val) {
        const s = `${val || ""}`.trim();
        if (!s) return "-";
        const d = new Date(s);
        if (Number.isNaN(d.getTime())) return s;
        const pad = (n) => `${n}`.padStart(2, "0");
        return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
      },

      socialExportStatusZh(status) {
        const key = `${status || ""}`.trim().toLowerCase();
        const map = {
          done: "完成",
          partial: "部分失败",
          failed: "失败",
        };
        return map[key] || key || "-";
      },

      formatPercentRate(value) {
        const num = Number(value);
        if (!Number.isFinite(num)) return "0.0%";
        return `${(num * 100).toFixed(1)}%`;
      },

      formatUsd(value, digits = 6) {
        const num = Number(value);
        if (!Number.isFinite(num)) return "$0";
        return `$${num.toFixed(digits)}`;
      },

      agentTaskStatusZh(status) {
        const key = `${status || ""}`.trim().toLowerCase();
        const map = {
          done: "成功",
          error: "失败",
          cancelled: "取消",
          skipped: "跳过",
          running: "运行中",
        };
        return map[key] || key || "-";
      },

      agentTaskModeZh(mode) {
        const key = `${mode || ""}`.trim().toLowerCase();
        const map = {
          single_capability: "单能力",
          skill_sequence: "技能链",
          skill_invoke: "单技能",
        };
        return map[key] || key || "-";
      },

      idempotencySourceZh(source) {
        const key = `${source || ""}`.trim().toLowerCase();
        const map = {
          memory: "内存",
          persisted: "落盘",
          merged: "合并",
        };
        return map[key] || key || "-";
      },

      getAgentTaskFailedNodes() {
        const detail = this.agentTaskDetail || {};
        const chain = detail && detail.chain_view && typeof detail.chain_view === "object" ? detail.chain_view : {};
        const nodesRaw = Array.isArray(chain.nodes) ? chain.nodes : [];
        const fromChain = nodesRaw
          .filter(x => x && `${x.status || ""}`.trim().toLowerCase() === "error")
          .map(x => ({
            node_id: `${x.node_id || ""}`.trim(),
            skill_id: `${x.skill_id || ""}`.trim(),
            capability_id: `${x.capability_id || ""}`.trim(),
            error: `${x.error || ""}`.trim(),
          }));
        if (fromChain.length > 0) return fromChain;

        const summary = detail && detail.result && detail.result.history_summary && typeof detail.result.history_summary === "object"
          ? detail.result.history_summary
          : {};
        const failed = Array.isArray(summary.failed_nodes) ? summary.failed_nodes : [];
        return failed.map((x, idx) => ({
          node_id: `${x && x.step_id ? x.step_id : `failed_${idx + 1}`}`,
          skill_id: `${x && x.skill_id ? x.skill_id : ""}`,
          capability_id: `${x && x.capability_id ? x.capability_id : ""}`,
          error: `${x && x.error ? x.error : ""}`,
        }));
      },

      async loadCapabilityWorkbench() {
        await this.loadCapabilities();
        await this.loadContentPublishPlatforms();
        await this.loadPublishPrepProfiles();
        if (!this.projectDir) {
          const entry = this.capabilityEntryByTab(this.capabilityTab);
          if (this.capabilityModeText(entry && entry.mode ? entry.mode : "hybrid") === "project") {
            this.capabilityTab = "subtitle_calibration";
          }
          return;
        }
        await this.loadTopicLibrary();
        await this.loadTextRoughSource();
        await this.loadNleConnectors();
        await this.loadSocialExportTemplates();
        await this.loadExportProfiles();
        await this.loadSocialExportHistory();
        await this.loadWorkflowCatalog();
        await this.loadWorkflowList();
        await this.loadWorkflowRuns();
        await this.loadIdempotencyCache(true);
        await this.loadAgentObservability();
        await this.loadAgentTemplates();
      },

      jsonPretty(obj) {
        if (obj === null || obj === undefined) return "";
        try {
          return JSON.stringify(obj, null, 2);
        } catch {
          return `${obj}`;
        }
      },

      async loadCapabilities() {
        this.capabilitiesLoading = true;
        const data = await this.api("GET", "/api/capabilities");
        this.capabilitiesLoading = false;
        if (data.error) {
          this.capabilityMessage = `能力列表读取失败：${data.error}`;
          this.capabilityMessageType = "danger";
          return;
        }
        this.capabilities = Array.isArray(data.capabilities) ? data.capabilities : [];
      },

      capabilityModeText(mode) {
        const m = `${mode || "hybrid"}`.trim().toLowerCase();
        if (m === "inline") return "inline";
        if (m === "project") return "project";
        return "hybrid";
      },

      capabilityModeClass(mode) {
        const m = this.capabilityModeText(mode);
        if (m === "inline") return "badge-success";
        if (m === "project") return "badge-warn";
        return "badge-info";
      },

      capabilityEntryByTab(tab) {
        const key = `${tab || ""}`.trim();
        if (!key) return null;
        for (const group of (this.capabilityGroups || [])) {
          const items = Array.isArray(group && group.items) ? group.items : [];
          const hit = items.find(x => `${x && x.tab ? x.tab : ""}`.trim() === key);
          if (hit) return hit;
        }
        return null;
      },

      async openCapabilityTab(tab) {
        const key = `${tab || ""}`.trim();
        if (!key) return;
        this.productionView = "hub";
        this.capabilityTab = key;
        const entry = this.capabilityEntryByTab(key);
        const mode = this.capabilityModeText(entry && entry.mode ? entry.mode : "hybrid");
        if (!this.projectDir && mode === "project") {
          this.capabilityMessage = `模块「${entry && entry.label ? entry.label : key}」需要先打开项目后使用`;
          this.capabilityMessageType = "warn";
          return;
        }
        if (key === "text_rough") await this.loadTextRoughSource();
        if (key === "refinement") await this.loadNleConnectors(this.handoffInput && this.handoffInput.editor ? this.handoffInput.editor : "");
        if (key === "social_export") {
          await this.loadSocialExportTemplates();
          await this.loadExportProfiles();
          await this.loadSocialExportHistory();
        }
        if (key === "publish_prep") await this.loadPublishPrepProfiles();
        if (key === "content_publish") await this.loadContentPublishPlatforms();
        if (key === "workflow_builder") {
          await this.loadWorkflowCatalog();
          await this.loadWorkflowList();
          await this.loadWorkflowRuns();
        }
        if (key === "idempotency_cache") await this.loadIdempotencyCache(true);
        if (key === "agent_templates") await this.loadAgentTemplates();
        if (key === "agent_observability") await this.loadAgentObservability();
      },

      async loadIdempotencyCache(resetOffset = false) {
        if (!this.projectDir) return;
        this.idempotencyCacheLoading = true;
        const input = this.idempotencyCacheInput || {};
        const source = `${input.source || "merged"}`.trim().toLowerCase();
        const sourceFinal = ["memory", "persisted", "merged"].includes(source) ? source : "merged";
        const matchMode = `${input.match_mode || "contains"}`.trim().toLowerCase();
        const matchModeFinal = ["contains", "exact"].includes(matchMode) ? matchMode : "contains";
        const ttlRaw = Number(input.ttl_seconds);
        const ttlFinal = Math.max(0, Math.min(Number.isFinite(ttlRaw) ? Math.floor(ttlRaw) : (7 * 24 * 3600), 365 * 24 * 3600));
        const limitRaw = Number(input.limit);
        const limitFinal = Math.max(1, Math.min(Number.isFinite(limitRaw) ? Math.floor(limitRaw) : 200, 1000));
        const offsetRaw = Number(input.offset);
        const offsetFinal = resetOffset ? 0 : Math.max(0, Number.isFinite(offsetRaw) ? Math.floor(offsetRaw) : 0);
        const includeExpired = !!input.include_expired;
        const actorIdFilter = `${input.actor_id || ""}`.trim();
        const endpointFilter = `${input.endpoint || ""}`.trim();
        const idemKeyFilter = `${input.idempotency_key || ""}`.trim();
        const projectPathFilter = `${input.project_path || ""}`.trim();

        this.idempotencyCacheInput.source = sourceFinal;
        this.idempotencyCacheInput.match_mode = matchModeFinal;
        this.idempotencyCacheInput.ttl_seconds = ttlFinal;
        this.idempotencyCacheInput.limit = limitFinal;
        this.idempotencyCacheInput.offset = offsetFinal;
        this.idempotencyCacheInput.include_expired = includeExpired;
        this.idempotencyCacheInput.actor_id = actorIdFilter;
        this.idempotencyCacheInput.endpoint = endpointFilter;
        this.idempotencyCacheInput.idempotency_key = idemKeyFilter;
        this.idempotencyCacheInput.project_path = projectPathFilter;
        this.idempotencyPruneInput.ttl_seconds = ttlFinal;

        const q = new URLSearchParams();
        q.set("source", sourceFinal);
        q.set("ttl_seconds", `${ttlFinal}`);
        q.set("include_expired", includeExpired ? "true" : "false");
        q.set("limit", `${limitFinal}`);
        q.set("offset", `${offsetFinal}`);
        q.set("match_mode", matchModeFinal);
        if (actorIdFilter) q.set("actor_id", actorIdFilter);
        if (endpointFilter) q.set("endpoint", endpointFilter);
        if (idemKeyFilter) q.set("idempotency_key", idemKeyFilter);
        if (projectPathFilter) q.set("project_path", projectPathFilter);
        const data = await this.api("GET", `/api/capabilities/idempotency/cache?${q.toString()}`);
        this.idempotencyCacheLoading = false;
        if (data.error) {
          this.capabilityMessage = `幂等缓存读取失败：${data.error}`;
          this.capabilityMessageType = "danger";
          return;
        }
        this.idempotencyCacheRecords = Array.isArray(data.records) ? data.records : [];
        this.idempotencyCacheStats = data.stats || null;
        this.idempotencyCacheLastPrune = null;
        if (this.idempotencyCacheStats && Number.isFinite(Number(this.idempotencyCacheStats.offset))) {
          this.idempotencyCacheInput.offset = Math.max(0, Math.floor(Number(this.idempotencyCacheStats.offset)));
        }
      },

      async nextIdempotencyCachePage() {
        if (this.idempotencyCacheLoading) return;
        const stats = this.idempotencyCacheStats || {};
        if (!stats.has_more) return;
        const limit = Math.max(1, Number(this.idempotencyCacheInput.limit || stats.limit || 200));
        const current = Math.max(0, Number(this.idempotencyCacheInput.offset || stats.offset || 0));
        this.idempotencyCacheInput.offset = current + limit;
        await this.loadIdempotencyCache(false);
      },

      async prevIdempotencyCachePage() {
        if (this.idempotencyCacheLoading) return;
        const stats = this.idempotencyCacheStats || {};
        const limit = Math.max(1, Number(this.idempotencyCacheInput.limit || stats.limit || 200));
        const current = Math.max(0, Number(this.idempotencyCacheInput.offset || stats.offset || 0));
        if (current <= 0) return;
        this.idempotencyCacheInput.offset = Math.max(current - limit, 0);
        await this.loadIdempotencyCache(false);
      },

      async pruneIdempotencyCacheDefault() {
        this.idempotencyPruneInput.ttl_seconds = 7 * 24 * 3600;
        this.idempotencyPruneInput.remove_expired = true;
        this.idempotencyPruneInput.clear_memory = false;
        this.idempotencyPruneInput.clear_persisted = false;
        this.idempotencyPruneInput.max_entries = "";
        await this.pruneIdempotencyCache();
      },

      async pruneIdempotencyCache() {
        if (!this.projectDir) return;
        if (this.idempotencyCachePruning) return;
        this.idempotencyCachePruning = true;
        const input = this.idempotencyPruneInput || {};
        const ttlRaw = Number(input.ttl_seconds);
        const ttlFinal = Math.max(0, Math.min(Number.isFinite(ttlRaw) ? Math.floor(ttlRaw) : (7 * 24 * 3600), 365 * 24 * 3600));
        const removeExpired = !!input.remove_expired;
        const clearMemory = !!input.clear_memory;
        const clearPersisted = !!input.clear_persisted;
        const maxEntriesText = `${input.max_entries || ""}`.trim();
        let maxEntries = null;
        if (maxEntriesText) {
          const parsed = Number(maxEntriesText);
          if (Number.isFinite(parsed) && parsed > 0) {
            maxEntries = Math.floor(parsed);
          }
        }

        this.idempotencyPruneInput.ttl_seconds = ttlFinal;
        const payload = {
          ttl_seconds: ttlFinal,
          remove_expired: removeExpired,
          clear_memory: clearMemory,
          clear_persisted: clearPersisted,
        };
        if (maxEntries !== null) payload.max_entries = maxEntries;

        const data = await this.api("POST", "/api/capabilities/idempotency/cache/prune", payload);
        this.idempotencyCachePruning = false;
        if (data.error) {
          this.capabilityMessage = `幂等缓存清理失败：${data.error}`;
          this.capabilityMessageType = "danger";
          return;
        }
        this.idempotencyCacheRecords = Array.isArray(data.records) ? data.records : [];
        this.idempotencyCacheStats = data.stats || null;
        this.idempotencyCacheLastPrune = data.prune || null;
        const prune = this.idempotencyCacheLastPrune || {};
        this.capabilityMessage = `幂等缓存已清理：内存移除 ${prune.memory_removed || 0}，落盘移除 ${prune.persisted_removed || 0}`;
        this.capabilityMessageType = "success";
      },

      async loadAgentObservability(resetHistoryOffset = true) {
        if (!this.projectDir) return;
        this.agentObservabilityLoading = true;
        const actorIdText = `${this.agentObservabilityInput.actor_id || ""}`.trim();
        const limitRaw = Number(this.agentObservabilityInput.limit || 200);
        const topNRaw = Number(this.agentObservabilityInput.top_n || 5);
        const limit = Math.max(1, Math.min(Number.isFinite(limitRaw) ? Math.floor(limitRaw) : 200, 2000));
        const topN = Math.max(1, Math.min(Number.isFinite(topNRaw) ? Math.floor(topNRaw) : 5, 20));
        this.agentObservabilityInput.limit = limit;
        this.agentObservabilityInput.top_n = topN;
        if (resetHistoryOffset) this.agentObservabilityItemsOffset = 0;

        const summaryParams = new URLSearchParams();
        if (actorIdText) summaryParams.set("actor_id", actorIdText);
        summaryParams.set("limit", `${limit}`);
        summaryParams.set("top_n", `${topN}`);
        summaryParams.set("include_items", "false");
        const status = `${this.agentObservabilityInput.status || ""}`.trim().toLowerCase();
        const taskMode = `${this.agentObservabilityInput.task_mode || ""}`.trim().toLowerCase();
        const capabilityId = `${this.agentObservabilityInput.capability_id || ""}`.trim().toLowerCase();
        const skillId = `${this.agentObservabilityInput.skill_id || ""}`.trim().toLowerCase();
        const replaySupported = `${this.agentObservabilityInput.replay_supported || ""}`.trim().toLowerCase();
        const since = `${this.agentObservabilityInput.since || ""}`.trim();
        const until = `${this.agentObservabilityInput.until || ""}`.trim();
        if (status) summaryParams.set("status", status);
        if (taskMode) summaryParams.set("task_mode", taskMode);
        if (capabilityId) summaryParams.set("capability_id", capabilityId);
        if (skillId) summaryParams.set("skill_id", skillId);
        if (replaySupported === "true" || replaySupported === "false") summaryParams.set("replay_supported", replaySupported);
        if (since) summaryParams.set("since", since);
        if (until) summaryParams.set("until", until);

        const includeItems = !!this.agentObservabilityInput.include_items;
        let historyPath = "";
        if (includeItems) {
          const historyParams = new URLSearchParams();
          if (actorIdText) historyParams.set("actor_id", actorIdText);
          historyParams.set("limit", `${limit}`);
          historyParams.set("offset", `${Math.max(Number(this.agentObservabilityItemsOffset || 0), 0)}`);
          historyParams.set("sort", "desc");
          if (status) historyParams.set("status", status);
          if (taskMode) historyParams.set("task_mode", taskMode);
          if (capabilityId) historyParams.set("capability_id", capabilityId);
          if (skillId) historyParams.set("skill_id", skillId);
          if (replaySupported === "true" || replaySupported === "false") {
            historyParams.set("replay_supported", replaySupported);
          }
          if (since) historyParams.set("since", since);
          if (until) historyParams.set("until", until);
          historyPath = `/api/agent/tasks/history?${historyParams.toString()}`;
        }

        const reqs = [
          this.api("GET", `/api/agent/observability?${summaryParams.toString()}`),
        ];
        if (historyPath) reqs.push(this.api("GET", historyPath));
        const [summaryData, historyData] = await Promise.all(reqs);
        this.agentObservabilityLoading = false;

        if (summaryData.error) {
          this.capabilityMessage = `Agent 观测读取失败：${summaryData.error}`;
          this.capabilityMessageType = "danger";
          return;
        }
        this.agentObservabilitySummary = summaryData.summary || null;
        this.agentObservabilityHistoryCount = Number(summaryData.history_count || 0);
        this.agentObservabilityWindowCount = Number(summaryData.window_count || 0);
        this.agentObservabilityWindowLimit = Number(summaryData.window_limit || limit);

        if (!includeItems) {
          this.agentObservabilityItems = [];
          this.agentObservabilityItemsTotal = 0;
          this.agentObservabilityItemsHasMore = false;
          this.agentObservabilityItemsOffset = 0;
          this.agentTaskDetailJobId = "";
          this.agentTaskDetail = null;
          this.agentTaskDetailError = "";
          return;
        }

        if (historyData && historyData.error) {
          this.agentObservabilityItems = [];
          this.agentObservabilityItemsTotal = 0;
          this.agentObservabilityItemsHasMore = false;
          this.capabilityMessage = `Agent 历史读取失败：${historyData.error}`;
          this.capabilityMessageType = "danger";
          return;
        }
        this.agentObservabilityItems = Array.isArray(historyData && historyData.items) ? historyData.items : [];
        this.agentObservabilityItemsTotal = Number((historyData && historyData.total_count) || 0);
        this.agentObservabilityItemsHasMore = !!(historyData && historyData.has_more);
        this.agentObservabilityItemsOffset = Number((historyData && historyData.offset) || 0);
        if (this.agentTaskDetailJobId) {
          const exists = this.agentObservabilityItems.some(x => `${x && x.job_id ? x.job_id : ""}`.trim() === this.agentTaskDetailJobId);
          if (!exists) {
            this.agentTaskDetailJobId = "";
            this.agentTaskDetail = null;
            this.agentTaskDetailError = "";
          }
        }
      },

      async nextAgentObservabilityItemsPage() {
        if (!this.projectDir) return;
        if (this.agentObservabilityLoading) return;
        if (!this.agentObservabilityItemsHasMore) return;
        const step = Math.max(Number(this.agentObservabilityInput.limit || 200), 1);
        this.agentObservabilityItemsOffset = Math.max(Number(this.agentObservabilityItemsOffset || 0), 0) + step;
        await this.loadAgentObservability(false);
      },

      async prevAgentObservabilityItemsPage() {
        if (!this.projectDir) return;
        if (this.agentObservabilityLoading) return;
        const step = Math.max(Number(this.agentObservabilityInput.limit || 200), 1);
        const current = Math.max(Number(this.agentObservabilityItemsOffset || 0), 0);
        if (current <= 0) return;
        this.agentObservabilityItemsOffset = Math.max(current - step, 0);
        await this.loadAgentObservability(false);
      },

      async applyAgentFailedTopFilter(item) {
        if (!item || typeof item !== "object") return;
        this.agentObservabilityInput.status = "error";
        this.agentObservabilityInput.task_mode = "";
        this.agentObservabilityInput.capability_id = `${item.capability_id || ""}`.trim().toLowerCase();
        this.agentObservabilityInput.skill_id = `${item.skill_id || ""}`.trim().toLowerCase();
        this.agentObservabilityInput.replay_supported = "";
        this.agentObservabilityInput.since = "";
        this.agentObservabilityInput.until = "";
        this.agentObservabilityItemsOffset = 0;
        await this.loadAgentObservability(true);
      },

      async exportAgentObservability(format = "json") {
        if (!this.projectDir) return;
        const fmt = `${format || "json"}`.trim().toLowerCase();
        if (!["json", "csv"].includes(fmt)) return;
        this.agentObservabilityExporting = fmt;
        const payload = {
          format: fmt,
          actor_id: `${this.agentObservabilityInput.actor_id || ""}`.trim(),
          limit: Number(this.agentObservabilityInput.limit || 200),
          top_n: Number(this.agentObservabilityInput.top_n || 5),
          status: `${this.agentObservabilityInput.status || ""}`.trim().toLowerCase(),
          task_mode: `${this.agentObservabilityInput.task_mode || ""}`.trim().toLowerCase(),
          capability_id: `${this.agentObservabilityInput.capability_id || ""}`.trim().toLowerCase(),
          skill_id: `${this.agentObservabilityInput.skill_id || ""}`.trim().toLowerCase(),
          replay_supported: `${this.agentObservabilityInput.replay_supported || ""}`.trim().toLowerCase(),
          since: `${this.agentObservabilityInput.since || ""}`.trim(),
          until: `${this.agentObservabilityInput.until || ""}`.trim(),
        };
        const data = await this.api("POST", "/api/agent/observability/export", payload);
        this.agentObservabilityExporting = "";
        if (data.error) {
          this.capabilityMessage = `Agent 观测导出失败：${data.error}`;
          this.capabilityMessageType = "danger";
          return;
        }
        this.agentObservabilityLastExport = `${data.output || ""}`;
        if (data.summary) this.agentObservabilitySummary = data.summary;
        this.capabilityMessage = `Agent 观测已导出 ${fmt.toUpperCase()}：${this.agentObservabilityLastExport || "-"}`;
        this.capabilityMessageType = "success";
      },

      async openAgentObservabilityExport() {
        const path = `${this.agentObservabilityLastExport || ""}`.trim();
        if (!path) {
          this.capabilityMessage = "暂无 Agent 观测导出文件";
          this.capabilityMessageType = "warn";
          return;
        }
        await this.openFinder(path);
      },

      async replayAgentTask(item) {
        if (!this.projectDir) return;
        const sourceJobId = `${item && item.job_id ? item.job_id : ""}`.trim();
        if (!sourceJobId) {
          this.capabilityMessage = "缺少任务ID，无法重放";
          this.capabilityMessageType = "warn";
          return "";
        }
        if (this.agentReplayRunningJobId) return "";
        this.agentReplayRunningJobId = sourceJobId;
        const data = await this.api("POST", `/api/agent/tasks/${encodeURIComponent(sourceJobId)}/replay`, {
          clear_idempotency: true,
          new_trace_id: `replay_${Date.now()}`,
        });
        if (data.error || !data.ok) {
          this.agentReplayRunningJobId = "";
          this.capabilityMessage = `任务重放失败：${data && data.error ? data.error : "调用失败"}`;
          this.capabilityMessageType = "danger";
          return "";
        }
        const newJobId = `${data.new_job_id || (data.response && data.response.job_id) || ""}`.trim();
        if (!newJobId) {
          this.agentReplayRunningJobId = "";
          this.capabilityMessage = "重放请求已发送，但未返回新任务ID";
          this.capabilityMessageType = "warn";
          return "";
        }
        this.capabilityMessage = `已启动任务重放：${sourceJobId} -> ${newJobId}`;
        this.capabilityMessageType = "info";
        const job = await this.waitForJob(newJobId, null, 3 * 60 * 60 * 1000);
        this.agentReplayRunningJobId = "";
        if (job.status === "done") {
          this.capabilityMessage = `任务重放完成：${newJobId}`;
          this.capabilityMessageType = "success";
        } else if (job.status === "cancelled") {
          this.capabilityMessage = `任务重放已取消：${newJobId}`;
          this.capabilityMessageType = "warn";
        } else {
          this.capabilityMessage = `任务重放失败：${job.error || newJobId}`;
          this.capabilityMessageType = "danger";
        }
        await this.loadAgentObservability();
        return newJobId;
      },

      async viewAgentTaskDetail(item) {
        if (!this.projectDir) return;
        const jobId = `${item && item.job_id ? item.job_id : ""}`.trim();
        if (!jobId) {
          this.agentTaskDetailError = "缺少任务ID";
          return;
        }
        if (this.agentTaskDetailLoading) return;
        this.agentTaskDetailLoading = true;
        this.agentTaskDetailError = "";
        this.agentTaskDetailJobId = jobId;
        this.agentTaskDetailLastExport = "";
        const data = await this.api("GET", `/api/agent/tasks/${encodeURIComponent(jobId)}`);
        this.agentTaskDetailLoading = false;
        if (data.error) {
          this.agentTaskDetail = null;
          this.agentTaskDetailError = data.error;
          return;
        }
        this.agentTaskDetail = data;
      },

      async replayAgentTaskDetail() {
        const currentJobId = `${this.agentTaskDetailJobId || ""}`.trim();
        if (!currentJobId) {
          this.capabilityMessage = "请先选择一个任务详情";
          this.capabilityMessageType = "warn";
          return;
        }
        const newJobId = await this.replayAgentTask({ job_id: currentJobId });
        if (newJobId) {
          await this.viewAgentTaskDetail({ job_id: newJobId });
        }
      },

      async exportAgentTaskDetail(format = "json") {
        if (!this.projectDir) return;
        const jobId = `${this.agentTaskDetailJobId || ""}`.trim();
        if (!jobId) {
          this.capabilityMessage = "请先选择一个任务详情";
          this.capabilityMessageType = "warn";
          return;
        }
        const fmt = `${format || "json"}`.trim().toLowerCase();
        if (!["json", "csv"].includes(fmt)) return;
        const payload = {
          format: fmt,
          include_logs: fmt === "json",
          include_result: fmt === "json",
        };
        const data = await this.api("POST", `/api/agent/tasks/${encodeURIComponent(jobId)}/export`, payload);
        if (data.error || !data.ok) {
          this.capabilityMessage = `任务导出失败：${data && data.error ? data.error : "调用失败"}`;
          this.capabilityMessageType = "danger";
          return;
        }
        this.agentTaskDetailLastExport = `${data.output || ""}`;
        this.capabilityMessage = `任务已导出 ${fmt.toUpperCase()}：${this.agentTaskDetailLastExport || "-"}`;
        this.capabilityMessageType = "success";
      },

      async openAgentTaskDetailExport() {
        const path = `${this.agentTaskDetailLastExport || ""}`.trim();
        if (!path) {
          this.capabilityMessage = "暂无任务导出文件";
          this.capabilityMessageType = "warn";
          return;
        }
        await this.openFinder(path);
      },
    };
  };
})(window);
