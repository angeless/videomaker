(function (global) {
  const ns = (global.VideoEditorModules = global.VideoEditorModules || {});

  ns.createSemanticPublishMixin = function createSemanticPublishMixin() {
    return {
      parseJsonSafe(text, fallback = null) {
        try {
          return JSON.parse(`${text || ""}`.trim() || "null");
        } catch {
          return fallback;
        }
      },

      parseDelimitedList(text) {
        return `${text || ""}`
          .replace(/\n/g, ",")
          .replace(/，/g, ",")
          .split(",")
          .map(x => `${x || ""}`.trim())
          .filter(Boolean);
      },

      async planSubtitleCalibration() {
        const payload = {
          input_mode: this.subtitleInput.input_mode || "project",
          mode: this.subtitleInput.mode || "timeline_align",
          translation: this.subtitleInput.translation || "off",
          source_audio: this.subtitleInput.source_audio || "",
        };
        if ((payload.input_mode || "").toLowerCase() === "inline") {
          const subtitles = this.parseJsonSafe(this.subtitleInput.subtitles_json, null);
          if (!Array.isArray(subtitles)) {
            this.capabilityMessage = "字幕 JSON 格式错误，需为数组";
            return;
          }
          payload.subtitles = subtitles;
        }
        const data = await this.api("POST", "/api/capabilities/subtitle_calibration/plan", payload);
        if (data.error) {
          this.capabilityMessage = `字幕校准规划失败：${data.error}`;
          return;
        }
        this.subtitlePlan = data.plan || null;
        this.capabilityMessage = "已生成字幕校准规划";
      },

      async runSubtitleCalibration() {
        const payload = {
          input_mode: this.subtitleInput.input_mode || "project",
          mode: this.subtitleInput.mode || "timeline_align",
          translation: this.subtitleInput.translation || "off",
          source_audio: this.subtitleInput.source_audio || "",
          use_llm: !!this.subtitleInput.use_llm,
          llm_provider: this.subtitleInput.llm_provider || "",
          llm_model: this.subtitleInput.llm_model || "",
        };
        if ((payload.input_mode || "").toLowerCase() === "inline") {
          const subtitles = this.parseJsonSafe(this.subtitleInput.subtitles_json, null);
          if (!Array.isArray(subtitles)) {
            this.capabilityMessage = "字幕 JSON 格式错误，需为数组";
            return;
          }
          payload.subtitles = subtitles;
        }
        const data = await this.api("POST", "/api/capabilities/subtitle_calibration/run", payload);
        if (data.error) {
          this.capabilityMessage = `字幕校准失败：${data.error}`;
          return;
        }
        this.subtitleResult = data.result || null;
        const report = (this.subtitleResult && this.subtitleResult.quality_report) ? this.subtitleResult.quality_report : {};
        this.capabilityMessage = `字幕校准完成：共 ${report.total_subtitles || 0} 条，时间轴调整 ${report.timeline_changed_count || 0} 条`;
      },

      async analyzeImageSemantic() {
        const paths = this.parseDelimitedList(this.imageSemanticInput.image_paths || "");
        let analyzeMax = Number(this.imageSemanticInput.analyze_max_images || 1200);
        if (!Number.isFinite(analyzeMax) || analyzeMax <= 0) analyzeMax = 1200;
        if (analyzeMax > 8000) analyzeMax = 8000;
        this.imageSemanticInput.analyze_max_images = analyzeMax;
        const payload = {
          input_mode: this.imageSemanticInput.input_mode || "inline",
          image_paths: paths,
          retrieval_mode: this.imageSemanticInput.retrieval_mode || "hybrid",
          max_images: analyzeMax,
          auto_ingest: !!this.imageSemanticInput.auto_ingest,
        };
        const data = await this.api("POST", "/api/capabilities/image_semantic/analyze", payload);
        if (data.error) {
          this.capabilityMessage = `图片语义分析失败：${data.error}`;
          return;
        }
        this.imageSemanticAnalyze = data.result || null;
        if (data.ai_status) this.imageSemanticAiStatus = data.ai_status;
        this.capabilityMessage = `图片语义分析完成：${(this.imageSemanticAnalyze && this.imageSemanticAnalyze.analyzed_count) || 0} 个条目`;
      },

      async searchImageSemantic() {
        const payload = {
          query: this.imageSemanticInput.query || "",
          limit: Number(this.imageSemanticInput.limit || 30),
          retrieval_mode: this.imageSemanticInput.retrieval_mode || "hybrid",
        };
        const data = await this.api("POST", "/api/capabilities/image_semantic/search", payload);
        if (data.error) {
          this.capabilityMessage = `图片语义检索失败：${data.error}`;
          return;
        }
        this.imageSemanticSearch = data.result || null;
        if (data.ai_status) this.imageSemanticAiStatus = data.ai_status;
        this.capabilityMessage = `图片语义检索完成：命中 ${(this.imageSemanticSearch && this.imageSemanticSearch.total_hits) || 0} 条`;
      },

      async generateArticleExpand() {
        const payload = {
          input_mode: this.articleExpandInput.input_mode || "inline",
          source_text: this.articleExpandInput.source_text || "",
          key_points: this.articleExpandInput.key_points || "",
          tone: this.articleExpandInput.tone || "professional",
          length_target: Number(this.articleExpandInput.length_target || 1200),
          title_count: Number(this.articleExpandInput.title_count || 5),
          use_llm: !!this.articleExpandInput.use_llm,
          llm_provider: this.articleExpandInput.llm_provider || "",
          llm_model: this.articleExpandInput.llm_model || "",
        };
        const data = await this.api("POST", "/api/capabilities/article_expand/generate", payload);
        if (data.error) {
          this.capabilityMessage = `公众号扩写失败：${data.error}`;
          return;
        }
        this.articleExpandResult = data.result || null;
        const titles = (this.articleExpandResult && this.articleExpandResult.title_candidates) || [];
        this.capabilityMessage = `公众号扩写完成：生成标题 ${titles.length || 0} 条`;
      },

      async loadPublishPrepProfiles() {
        const data = await this.api("GET", "/api/capabilities/publish_prep/profiles");
        if (data.error) {
          this.capabilityMessage = `发布文案 profiles 读取失败：${data.error}`;
          return;
        }
        this.publishPrepProfiles = Array.isArray(data.profiles) ? data.profiles : [];
      },

      async generatePublishPrep() {
        const overrides = this.parseJsonSafe(this.publishPrepInput.profile_overrides_json, null);
        if (overrides === null || typeof overrides !== "object" || Array.isArray(overrides)) {
          this.capabilityMessage = "发布文案 profile_overrides_json 需为 JSON 对象";
          return;
        }
        const payload = {
          input_mode: this.publishPrepInput.input_mode || "inline",
          script_text: this.publishPrepInput.script_text || "",
          voiceover_text: this.publishPrepInput.voiceover_text || "",
          platforms: this.parseDelimitedList(this.publishPrepInput.platforms || ""),
          platform_content_type: this.publishPrepInput.platform_content_type || "video_post",
          use_saved_profiles: !!this.publishPrepInput.use_saved_profiles,
          profile_overrides: overrides,
          use_llm: !!this.publishPrepInput.use_llm,
          llm_provider: this.publishPrepInput.llm_provider || "",
          llm_model: this.publishPrepInput.llm_model || "",
        };
        const data = await this.api("POST", "/api/capabilities/publish_prep/generate", payload);
        if (data.error) {
          this.capabilityMessage = `发布文案生成失败：${data.error}`;
          return;
        }
        this.publishPrepResult = data.result || null;
        const first = (
          this.publishPrepResult &&
          Array.isArray(this.publishPrepResult.platform_results) &&
          this.publishPrepResult.platform_results.length > 0
        )
          ? this.publishPrepResult.platform_results[0]
          : null;
        const content = (first && first.content && typeof first.content === "object") ? first.content : null;
        if (content) {
          this.contentPublishInput.title = `${content.title || this.contentPublishInput.title || ""}`;
          this.contentPublishInput.description = `${content.description || content.body || this.contentPublishInput.description || ""}`;
          if (Array.isArray(content.keywords)) {
            this.contentPublishInput.keywords = content.keywords.join(",");
          }
        }
        const n = (this.publishPrepResult && Array.isArray(this.publishPrepResult.platform_results))
          ? this.publishPrepResult.platform_results.length
          : 0;
        this.capabilityMessage = `发布文案生成完成：覆盖 ${n} 个平台`;
      },

      contentPublishPlatformName(platformId) {
        const pid = `${platformId || ""}`.trim().toLowerCase();
        const list = Array.isArray(this.contentPublishPlatforms) ? this.contentPublishPlatforms : [];
        const hit = list.find(item => `${item && item.platform_id ? item.platform_id : ""}`.trim().toLowerCase() === pid);
        return hit ? `${hit.name || hit.platform_id}` : (pid || "自定义平台");
      },

      _connectorRowTemplate(platformId = "") {
        return {
          platform_id: `${platformId || ""}`.trim().toLowerCase(),
          kind: "webhook",
          endpoint: "",
          method: "POST",
          timeout_s: 25,
          token: "",
          token_masked: "",
          media_file: "",
          privacy_status: "private",
          category_id: "22",
          notify_subscribers: false,
          header_items: [],
        };
      },

      _connectorRowsFromMap(connectors) {
        if (!connectors || typeof connectors !== "object" || Array.isArray(connectors)) {
          return [];
        }
        const rows = [];
        Object.entries(connectors).forEach(([platformId, item]) => {
          if (!item || typeof item !== "object" || Array.isArray(item)) return;
          const row = this._connectorRowTemplate(platformId);
          row.kind = `${item.kind || "webhook"}`.trim().toLowerCase() || "webhook";
          row.endpoint = `${item.endpoint || ""}`.trim();
          row.method = `${item.method || "POST"}`.trim().toUpperCase() || "POST";
          row.timeout_s = Math.max(1, Math.min(Number(item.timeout_s || 25) || 25, 120));
          const masked = `${item.token || ""}`.trim();
          row.token = "";
          row.token_masked = masked && masked.includes("*") ? masked : "";
          row.media_file = `${item.media_file || ""}`.trim();
          row.privacy_status = `${item.privacy_status || "private"}`.trim().toLowerCase() || "private";
          row.category_id = `${item.category_id || "22"}`.trim() || "22";
          row.notify_subscribers = !!item.notify_subscribers;
          const headers = item.headers && typeof item.headers === "object" && !Array.isArray(item.headers)
            ? item.headers
            : {};
          row.header_items = Object.entries(headers).map(([k, v]) => ({
            key: `${k || ""}`.trim(),
            value: `${v || ""}`.trim(),
          }));
          rows.push(row);
        });
        rows.sort((a, b) => `${a.platform_id}`.localeCompare(`${b.platform_id}`));
        return rows;
      },

      _isLikelyMaskedSecret(value) {
        const text = `${value || ""}`.trim();
        if (!text) return false;
        return text.includes("*") && text.length >= 6;
      },

      _normalizeConnectorMapForSave(rawMap) {
        const source = (rawMap && typeof rawMap === "object" && !Array.isArray(rawMap)) ? rawMap : {};
        const out = {};
        Object.entries(source).forEach(([platformId, rowRaw]) => {
          if (!rowRaw || typeof rowRaw !== "object" || Array.isArray(rowRaw)) return;
          const pid = `${platformId || ""}`.trim().toLowerCase();
          if (!pid) return;
          const row = rowRaw;
          let token = `${row.token || ""}`.trim();
          if (this._isLikelyMaskedSecret(token)) token = "__KEEP__";
          const headersRaw = row.headers && typeof row.headers === "object" && !Array.isArray(row.headers) ? row.headers : {};
          const headers = {};
          Object.entries(headersRaw).forEach(([k, v]) => {
            const key = `${k || ""}`.trim();
            if (!key) return;
            let value = `${v || ""}`.trim();
            if (this._isLikelyMaskedSecret(value) && ["authorization", "x-api-key", "x-auth-token"].includes(key.toLowerCase())) {
              value = "__KEEP__";
            }
            headers[key] = value;
          });
          out[pid] = {
            kind: `${row.kind || "webhook"}`.trim().toLowerCase() || "webhook",
            endpoint: `${row.endpoint || ""}`.trim(),
            method: `${row.method || "POST"}`.trim().toUpperCase() || "POST",
            timeout_s: Math.max(1, Math.min(Number(row.timeout_s || 25) || 25, 120)),
            token,
            headers,
          };
          if (out[pid].kind === "youtube_api") {
            out[pid].media_file = `${row.media_file || ""}`.trim();
            out[pid].privacy_status = `${row.privacy_status || "private"}`.trim().toLowerCase() || "private";
            out[pid].category_id = `${row.category_id || "22"}`.trim() || "22";
            out[pid].notify_subscribers = !!row.notify_subscribers;
          }
        });
        return out;
      },

      _connectorMapFromRows() {
        const out = {};
        const rows = Array.isArray(this.publishConnectorRows) ? this.publishConnectorRows : [];
        rows.forEach((row) => {
          if (!row || typeof row !== "object") return;
          const pid = `${row.platform_id || ""}`.trim().toLowerCase();
          if (!pid) return;
          const tokenInput = `${row.token || ""}`.trim();
          const tokenMasked = `${row.token_masked || ""}`.trim();
          const token = tokenInput || (tokenMasked ? "__KEEP__" : "");
          const items = Array.isArray(row.header_items) ? row.header_items : [];
          const headers = {};
          items.forEach((it) => {
            if (!it || typeof it !== "object") return;
            const key = `${it.key || ""}`.trim();
            if (!key) return;
            let value = `${it.value || ""}`.trim();
            if (this._isLikelyMaskedSecret(value) && ["authorization", "x-api-key", "x-auth-token"].includes(key.toLowerCase())) {
              value = "__KEEP__";
            }
            headers[key] = value;
          });
          out[pid] = {
            kind: `${row.kind || "webhook"}`.trim().toLowerCase() || "webhook",
            endpoint: `${row.endpoint || ""}`.trim(),
            method: `${row.method || "POST"}`.trim().toUpperCase() || "POST",
            timeout_s: Math.max(1, Math.min(Number(row.timeout_s || 25) || 25, 120)),
            token,
            headers,
          };
          if (out[pid].kind === "youtube_api") {
            out[pid].media_file = `${row.media_file || ""}`.trim();
            out[pid].privacy_status = `${row.privacy_status || "private"}`.trim().toLowerCase() || "private";
            out[pid].category_id = `${row.category_id || "22"}`.trim() || "22";
            out[pid].notify_subscribers = !!row.notify_subscribers;
          }
        });
        return out;
      },

      syncPublishConnectorJsonFromRows() {
        const map = this._connectorMapFromRows();
        this.contentPublishInput.connectors_json = this.jsonPretty(map);
      },

      addPublishConnectorRow(platformId = "") {
        const pid = `${platformId || ""}`.trim().toLowerCase();
        const rows = Array.isArray(this.publishConnectorRows) ? this.publishConnectorRows : [];
        const exists = rows.find(item => `${item && item.platform_id ? item.platform_id : ""}`.trim().toLowerCase() === pid);
        if (pid && exists) {
          this.publishSettingsMessage = `平台 ${this.contentPublishPlatformName(pid)} 已存在连接器行`;
          return;
        }
        rows.push(this._connectorRowTemplate(pid));
        this.publishConnectorRows = rows;
        this.syncPublishConnectorJsonFromRows();
      },

      removePublishConnectorRow(index) {
        const rows = Array.isArray(this.publishConnectorRows) ? this.publishConnectorRows : [];
        const idx = Number(index);
        if (!Number.isFinite(idx) || idx < 0 || idx >= rows.length) return;
        rows.splice(idx, 1);
        this.publishConnectorRows = rows;
        this.syncPublishConnectorJsonFromRows();
      },

      addPublishConnectorHeader(index) {
        const rows = Array.isArray(this.publishConnectorRows) ? this.publishConnectorRows : [];
        const idx = Number(index);
        if (!Number.isFinite(idx) || idx < 0 || idx >= rows.length) return;
        if (!Array.isArray(rows[idx].header_items)) rows[idx].header_items = [];
        rows[idx].header_items.push({ key: "", value: "" });
        this.publishConnectorRows = rows;
        this.syncPublishConnectorJsonFromRows();
      },

      removePublishConnectorHeader(index, headerIndex) {
        const rows = Array.isArray(this.publishConnectorRows) ? this.publishConnectorRows : [];
        const idx = Number(index);
        const hidx = Number(headerIndex);
        if (!Number.isFinite(idx) || !Number.isFinite(hidx) || idx < 0 || idx >= rows.length) return;
        const items = Array.isArray(rows[idx].header_items) ? rows[idx].header_items : [];
        if (hidx < 0 || hidx >= items.length) return;
        items.splice(hidx, 1);
        rows[idx].header_items = items;
        this.publishConnectorRows = rows;
        this.syncPublishConnectorJsonFromRows();
      },

      async loadPublishSettings() {
        this.publishSettingsLoading = true;
        const data = await this.api("GET", "/api/settings/publish");
        this.publishSettingsLoading = false;
        if (data.error) {
          this.publishSettingsMessage = `发布连接器读取失败：${data.error}`;
          return;
        }
        const connectors = data.connectors && typeof data.connectors === "object" ? data.connectors : {};
        this.contentPublishInput.connectors_json = this.jsonPretty(connectors);
        this.publishConnectorRows = this._connectorRowsFromMap(connectors);
        if (this.publishConnectorRows.length === 0) {
          const youtubeRow = this._connectorRowTemplate("youtube");
          youtubeRow.kind = "youtube_api";
          const douyinRow = this._connectorRowTemplate("douyin");
          this.publishConnectorRows = [youtubeRow, douyinRow];
          this.syncPublishConnectorJsonFromRows();
        }
        this.publishSettingsMessage = "";
      },

      async savePublishSettings() {
        let connectors = null;
        if (this.publishConnectorEditorMode === "json") {
          const parsed = this.parseJsonSafe(this.contentPublishInput.connectors_json, null);
          if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
            this.publishSettingsMessage = "连接器配置必须是 JSON 对象";
            return;
          }
          connectors = this._normalizeConnectorMapForSave(parsed);
        } else {
          connectors = this._connectorMapFromRows();
        }
        this.publishSettingsSaving = true;
        const data = await this.api("POST", "/api/settings/publish", { connectors });
        this.publishSettingsSaving = false;
        if (data.error) {
          this.publishSettingsMessage = `发布连接器保存失败：${data.error}`;
          return;
        }
        const masked = data.connectors && typeof data.connectors === "object" ? data.connectors : {};
        this.contentPublishInput.connectors_json = this.jsonPretty(masked);
        this.publishConnectorRows = this._connectorRowsFromMap(masked);
        this.publishSettingsMessage = `已保存发布连接器（${Number(data.connector_count || 0)} 个）`;
      },

      async loadContentPublishPlatforms() {
        const data = await this.api("GET", "/api/capabilities/content_publish/platforms");
        if (data.error) {
          this.capabilityMessage = `发布平台列表读取失败：${data.error}`;
          return;
        }
        this.contentPublishPlatforms = Array.isArray(data.platforms) ? data.platforms : [];
        if (!`${this.contentPublishInput.connectors_json || ""}`.trim() || `${this.contentPublishInput.connectors_json || ""}`.trim() === "{}") {
          await this.loadPublishSettings();
        }
      },

      async bootstrapContentPublishSession() {
        const payload = {
          input_mode: this.contentPublishInput.input_mode || "project",
          session_id: this.contentPublishInput.session_id || "",
          authenticated: !!this.contentPublishInput.authenticated,
          expires_in_minutes: Number(this.contentPublishInput.expires_in_minutes || 120),
        };
        const data = await this.api("POST", "/api/capabilities/content_publish/session/bootstrap", payload);
        if (data.error) {
          this.capabilityMessage = `发布会话初始化失败：${data.error}`;
          return;
        }
        this.contentPublishSession = data.session || null;
        this.contentPublishInput.session_id = (this.contentPublishSession && this.contentPublishSession.session_id) || "";
        this.capabilityMessage = `发布会话已初始化：${this.contentPublishInput.session_id || "-"}`;
      },

      async buildContentPublishPlan() {
        const payload = {
          input_mode: this.contentPublishInput.input_mode || "project",
          platforms: this.contentPublishInput.platforms || "",
          platform_content_type: this.contentPublishInput.platform_content_type || "video_post",
          dry_run: !!this.contentPublishInput.dry_run,
          session_id: this.contentPublishInput.session_id || "",
          content: {
            title: this.contentPublishInput.title || "",
            description: this.contentPublishInput.description || "",
            keywords: this.parseDelimitedList(this.contentPublishInput.keywords || ""),
            media_urls: this.parseDelimitedList(this.contentPublishInput.media_urls || ""),
            article_markdown: this.contentPublishInput.article_markdown || "",
            article_html: this.contentPublishInput.article_html || "",
          },
        };
        const data = await this.api("POST", "/api/capabilities/content_publish/plan", payload);
        if (data.error) {
          this.capabilityMessage = `发布计划生成失败：${data.error}`;
          return;
        }
        this.contentPublishPlan = data.plan || null;
        this.capabilityMessage = "已生成内容发布计划";
      },

      async runContentPublish() {
        const payload = {
          input_mode: this.contentPublishInput.input_mode || "project",
          session_id: this.contentPublishInput.session_id || "",
          dry_run: !!this.contentPublishInput.dry_run,
          plan: this.contentPublishPlan || undefined,
        };
        const data = await this.api("POST", "/api/capabilities/content_publish/run", payload);
        if (data.error) {
          this.capabilityMessage = `内容发布执行失败：${data.error}`;
          return;
        }
        this.contentPublishRun = data.run || null;
        const status = `${data.state || ""}`.trim();

        // R5: recovery_hint 消费
        const hint = (data.run && data.run.recovery_hint) || null;
        if (hint && hint.can_rerun) {
          this.publishRecoveryHint = hint;
          this.showPublishFailureModal = true;
          this.capabilityMessage = `发布部分失败：${hint.rerun_scope || "unknown"}`;
        } else {
          this.publishRecoveryHint = null;
          this.showPublishFailureModal = false;
          this.capabilityMessage = `内容发布执行完成，状态：${status || "unknown"}`;
        }
      },

      publishRecoveryActionLabel() {
        const scope = (this.publishRecoveryHint && this.publishRecoveryHint.rerun_scope) || "none";
        const labels = {
          failed_only: "重新发布失败平台",
          failed_and_blocked: "重新发布所有失败项",
          fix_config_then_rerun: "前往设置修复配置",
        };
        return labels[scope] || "";
      },

      async handlePublishRecoveryAction() {
        const scope = (this.publishRecoveryHint && this.publishRecoveryHint.rerun_scope) || "none";
        this.showPublishFailureModal = false;
        if (scope === "fix_config_then_rerun") {
          this.capSubTab = "publish_settings";
          return;
        }
        if (scope === "failed_only" || scope === "failed_and_blocked") {
          await this.rerunContentPublishFailed();
        }
      },

      dismissPublishFailureModal() {
        this.showPublishFailureModal = false;
      },

      async rerunContentPublishFailed() {
        const runId = `${this.contentPublishRun && this.contentPublishRun.run_id ? this.contentPublishRun.run_id : ""}`.trim();
        if (!runId) {
          this.capabilityMessage = "暂无可复跑 run_id";
          return;
        }
        const data = await this.api("POST", "/api/capabilities/content_publish/rerun", {
          input_mode: this.contentPublishInput.input_mode || "project",
          run_id: runId,
          session_id: this.contentPublishInput.session_id || "",
          dry_run: !!this.contentPublishInput.dry_run,
          rerun_failed_only: true,
        });
        if (data.error) {
          this.capabilityMessage = `内容发布复跑失败：${data.error}`;
          return;
        }
        this.contentPublishRun = data.run || this.contentPublishRun;
        this.capabilityMessage = `内容发布复跑完成：${data.state || "unknown"}`;
      },
    };
  };
}(window));
