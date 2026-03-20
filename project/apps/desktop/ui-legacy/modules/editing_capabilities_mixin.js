(function (global) {
  const ns = (global.VideoEditorModules = global.VideoEditorModules || {});

  ns.createEditingCapabilitiesMixin = function createEditingCapabilitiesMixin() {
    return {
      async loadTopicLibrary() {
        if (!this.projectDir) return;
        this.topicLibraryLoading = true;
        const q = encodeURIComponent(this.topicLibraryQuery || "");
        const category = encodeURIComponent(this.topicLibraryCategory || "");
        const data = await this.api("GET", `/api/capabilities/topic_library?q=${q}&category=${category}&limit=120`);
        this.topicLibraryLoading = false;
        if (data.error) {
          this.capabilityMessage = `选题库读取失败：${data.error}`;
          return;
        }
        this.topicLibraryItems = Array.isArray(data.topics) ? data.topics : [];
        if (!this.topicCopy.slug && this.topicLibraryItems.length > 0) {
          this.topicCopy.slug = this.topicLibraryItems[0].slug || "";
        }
      },

      async loadTextRoughSource() {
        if (!this.projectDir) return;
        this.textRoughSourceLoading = true;
        this.textRoughSourceError = "";
        if (!this.roughUrl) {
          this.roughUrl = `/api/files/preview/rough_cut.mp4?t=${Date.now()}`;
        }
        const data = await this.api("GET", "/api/capabilities/text_rough_cut/source");
        this.textRoughSourceLoading = false;
        if (data.error) {
          this.textRoughSourceError = data.error;
          return;
        }
        const spans = Array.isArray(data.spans) ? data.spans : [];
        const oldKeepByIndex = new Map((this.textRoughSpans || []).map(x => [Number(x.index), !!x.keep]));
        const keepSet = new Set(this.parseSpanIndexExpr(this.textRoughInput.keep_span_indexes || "", spans.length));
        const dropSet = new Set(this.parseSpanIndexExpr(this.textRoughInput.drop_span_indexes || "", spans.length));
        const hasManualRule = keepSet.size > 0 || dropSet.size > 0;
        this.textRoughSpans = spans.map((span) => {
          const idx = Number(span.index || 0);
          let keep = true;
          if (hasManualRule) {
            if (keepSet.size > 0 && !keepSet.has(idx)) keep = false;
            if (dropSet.has(idx)) keep = false;
          } else if (oldKeepByIndex.has(idx)) {
            keep = oldKeepByIndex.get(idx);
          }
          return { ...span, keep };
        });
        if (!hasManualRule) this.syncTextRoughSelectionInputs();
      },

      parseTextRoughRemovedPhrases() {
        return `${this.textRoughInput.removed_phrases || ""}`
          .replace(/，/g, ",")
          .split(",")
          .map(x => `${x || ""}`.trim().toLowerCase())
          .filter(Boolean);
      },

      spanMatchesTextRoughKeyword(span, keyword = null) {
        const kw = `${keyword === null ? this.textRoughFilterKeyword : keyword || ""}`.trim().toLowerCase();
        if (!kw) return true;
        const text = `${span && span.text ? span.text : ""}`.toLowerCase();
        return text.includes(kw);
      },

      getFilteredTextRoughSpans() {
        const spans = Array.isArray(this.textRoughSpans) ? this.textRoughSpans : [];
        const kw = `${this.textRoughFilterKeyword || ""}`.trim();
        if (!kw) return spans;
        return spans.filter(span => this.spanMatchesTextRoughKeyword(span, kw));
      },

      syncTextRoughSelectionInputs() {
        const spans = Array.isArray(this.textRoughSpans) ? this.textRoughSpans : [];
        if (!spans.length) {
          this.textRoughInput.keep_span_indexes = "";
          this.textRoughInput.drop_span_indexes = "";
          return;
        }
        const keep = [];
        const drop = [];
        for (const span of spans) {
          const idx = Number(span.index || 0);
          if (!Number.isFinite(idx) || idx <= 0) continue;
          if (span.keep) keep.push(idx);
          else drop.push(idx);
        }
        if (keep.length === spans.length) {
          this.textRoughInput.keep_span_indexes = "";
          this.textRoughInput.drop_span_indexes = "";
          return;
        }
        if (keep.length > 0 && keep.length <= drop.length) {
          this.textRoughInput.keep_span_indexes = this.formatSpanIndexExpr(keep);
          this.textRoughInput.drop_span_indexes = "";
          return;
        }
        this.textRoughInput.keep_span_indexes = "";
        this.textRoughInput.drop_span_indexes = this.formatSpanIndexExpr(drop);
      },

      applyTextRoughInputsToSelection() {
        const spans = Array.isArray(this.textRoughSpans) ? this.textRoughSpans : [];
        if (!spans.length) return;
        const keepSet = new Set(this.parseSpanIndexExpr(this.textRoughInput.keep_span_indexes || "", spans.length));
        const dropSet = new Set(this.parseSpanIndexExpr(this.textRoughInput.drop_span_indexes || "", spans.length));
        const hasKeepSet = keepSet.size > 0;
        this.textRoughSpans = spans.map((span) => {
          const idx = Number(span.index || 0);
          let keep = true;
          if (hasKeepSet && !keepSet.has(idx)) keep = false;
          if (dropSet.has(idx)) keep = false;
          return { ...span, keep };
        });
        this.syncTextRoughSelectionInputs();
      },

      setAllTextRoughSelection(keep = true) {
        const spans = Array.isArray(this.textRoughSpans) ? this.textRoughSpans : [];
        if (!spans.length) return;
        this.textRoughSpans = spans.map(span => ({ ...span, keep: !!keep }));
        this.syncTextRoughSelectionInputs();
      },

      invertTextRoughSelection() {
        const spans = Array.isArray(this.textRoughSpans) ? this.textRoughSpans : [];
        if (!spans.length) return;
        this.textRoughSpans = spans.map(span => ({ ...span, keep: !span.keep }));
        this.syncTextRoughSelectionInputs();
      },

      setFilteredTextRoughSelection(keep = true) {
        const spans = Array.isArray(this.textRoughSpans) ? this.textRoughSpans : [];
        if (!spans.length) return;
        const kw = `${this.textRoughFilterKeyword || ""}`.trim();
        if (!kw) {
          this.setAllTextRoughSelection(keep);
          return;
        }
        this.textRoughSpans = spans.map((span) => {
          if (!this.spanMatchesTextRoughKeyword(span, kw)) return span;
          return { ...span, keep: !!keep };
        });
        this.syncTextRoughSelectionInputs();
      },

      removeFillerTextRoughSpans() {
        const spans = Array.isArray(this.textRoughSpans) ? this.textRoughSpans : [];
        if (!spans.length) return;
        const phrases = this.parseTextRoughRemovedPhrases();
        if (!phrases.length) {
          this.capabilityMessage = "请先填写去除口头词，再执行“全删口头词句”";
          return;
        }
        let hit = 0;
        this.textRoughSpans = spans.map((span) => {
          const text = `${span && span.text ? span.text : ""}`.toLowerCase();
          const matched = phrases.some(p => p && text.includes(p));
          if (!matched) return span;
          hit += 1;
          return { ...span, keep: false };
        });
        this.syncTextRoughSelectionInputs();
        this.capabilityMessage = `已批量取消 ${hit} 句口头词相关句子`;
      },

      async jumpTextRoughPreview(seconds) {
        const sec = Number(seconds);
        if (!Number.isFinite(sec) || sec < 0) return;
        const video = this.$refs && this.$refs.textRoughPreviewVideo;
        if (!video) {
          this.capabilityMessage = "未找到预览播放器";
          return;
        }
        try {
          video.currentTime = Math.max(sec - 0.05, 0);
          await video.play();
        } catch {
          // ignore autoplay errors, currentTime has been set
        }
      },

      async bootstrapTopicLibrary() {
        if (!this.projectDir) return;
        const data = await this.api("POST", "/api/capabilities/topic_library/bootstrap", {});
        if (data.error) {
          this.capabilityMessage = `选题库初始化失败：${data.error}`;
          return;
        }
        this.capabilityMessage = `选题库已从素材生成模板 ${data.created || 0} 条`;
        await this.loadTopicLibrary();
      },

      async saveTopicTemplate() {
        if (!this.projectDir) return;
        if (!`${this.topicForm.title || ""}`.trim()) {
          this.capabilityMessage = "请先填写选题标题";
          return;
        }
        const tags = `${this.topicForm.tags || ""}`
          .replace(/，/g, ",")
          .split(",")
          .map(x => x.trim())
          .filter(Boolean);
        const payload = {
          slug: this.topicForm.slug || "",
          title: this.topicForm.title || "",
          category: this.topicForm.category || "travel",
          audience: this.topicForm.audience || "short_video",
          hook_style: this.topicForm.hook_style || "story",
          outline_template: this.topicForm.outline_template || "",
          tags,
          enabled: true,
        };
        const data = await this.api("POST", "/api/capabilities/topic_library", payload);
        if (data.error) {
          this.capabilityMessage = `保存失败：${data.error}`;
          return;
        }
        this.capabilityMessage = `选题模板已保存：${data.slug || this.topicForm.title}`;
        if (data.slug) this.topicCopy.slug = data.slug;
        await this.loadTopicLibrary();
      },

      useTopicTemplate(item) {
        if (!item) return;
        this.topicForm.slug = item.slug || "";
        this.topicForm.title = item.title || "";
        this.topicForm.category = item.category || "travel";
        this.topicForm.audience = item.audience || "short_video";
        this.topicForm.hook_style = item.hook_style || "story";
        this.topicForm.outline_template = item.outline_template || "";
        this.topicForm.tags = Array.isArray(item.tags) ? item.tags.join(",") : "";
        this.topicCopy.slug = item.slug || "";
        this.capabilityTab = "topic_copy";
      },

      async buildTopicCopyDraft() {
        if (!this.projectDir) return;
        const payload = {
          slug: this.topicCopy.slug || "",
          target_duration_s: this.topicCopy.target_duration_s || 60,
        };
        const data = await this.api("POST", "/api/capabilities/topic_copy/draft", payload);
        if (data.error) {
          this.capabilityMessage = `文案草案生成失败：${data.error}`;
          return;
        }
        this.topicCopy.draft = data.draft || null;
        this.capabilityMessage = "已生成选题+文案草案";
      },

      async buildTextRoughPlan() {
        if (!this.projectDir) return;
        const payload = {
          removed_phrases: this.textRoughInput.removed_phrases || "",
          target_duration_s: this.textRoughInput.target_duration_s || 15,
          merge_gap_s: this.textRoughInput.merge_gap_s || 0.15,
          keep_span_indexes: this.textRoughInput.keep_span_indexes || "",
          drop_span_indexes: this.textRoughInput.drop_span_indexes || "",
          apply_removed_phrases: !!this.textRoughInput.apply_removed_phrases,
        };
        const data = await this.api("POST", "/api/capabilities/text_rough_cut/plan", payload);
        if (data.error) {
          this.capabilityMessage = `文字粗剪规划失败：${data.error}`;
          return;
        }
        this.textRoughPlan = data.plan || null;
        const decisions = (this.textRoughPlan && Array.isArray(this.textRoughPlan.decisions))
          ? this.textRoughPlan.decisions
          : [];
        if (decisions.length > 0) {
          if ((this.textRoughSpans || []).length > 0) {
            const keepByIndex = new Map(decisions.map(d => [Number(d.index || 0), !!d.kept]));
            this.textRoughSpans = this.textRoughSpans.map(span => {
              const idx = Number(span.index || 0);
              return keepByIndex.has(idx) ? { ...span, keep: keepByIndex.get(idx) } : span;
            });
          } else {
            this.textRoughSpans = decisions.map(d => ({
              index: Number(d.index || 0),
              start: Number(d.start || 0),
              end: Number(d.end || 0),
              duration_s: Number((Number(d.end || 0) - Number(d.start || 0)).toFixed(3)),
              text: `${d.text || ""}`,
              keep: !!d.kept,
            }));
          }
          this.syncTextRoughSelectionInputs();
        }
        const kept = this.textRoughPlan && this.textRoughPlan.kept_span_count ? this.textRoughPlan.kept_span_count : 0;
        const total = this.textRoughPlan && this.textRoughPlan.total_span_count ? this.textRoughPlan.total_span_count : 0;
        this.capabilityMessage = `已生成文字粗剪规划：保留 ${kept}/${total} 句`;
      },

      async buildShortClipPlan() {
        if (!this.projectDir) return;
        const payload = {
          target_duration_s: this.shortClipInput.target_duration_s || 30,
          max_clips: this.shortClipInput.max_clips || 8,
        };
        const data = await this.api("POST", "/api/capabilities/short_clip/plan", payload);
        if (data.error) {
          this.capabilityMessage = `快剪规划失败：${data.error}`;
          return;
        }
        this.shortClipPlan = data.plan || null;
        this.capabilityMessage = "已生成短视频快剪规划";
      },

      async loadNleConnectors(editor = "") {
        this.nleConnectorsLoading = true;
        const q = `${editor || ""}`.trim();
        const path = q ? `/api/capabilities/refinement/connectors?editor=${encodeURIComponent(q)}` : "/api/capabilities/refinement/connectors";
        const data = await this.api("GET", path);
        this.nleConnectorsLoading = false;
        if (data.error) {
          this.capabilityMessage = `NLE 连接器状态读取失败：${data.error}`;
          return;
        }
        this.nleConnectors = Array.isArray(data.connectors) ? data.connectors : [];
      },

      nleConnectorByEditor(editor) {
        const key = `${editor || ""}`.trim().toLowerCase();
        return (this.nleConnectors || []).find(item => `${item && item.editor ? item.editor : ""}`.trim().toLowerCase() === key) || null;
      },

      async buildRefinePlan() {
        const payload = {
          style: this.refineInput.style || "travel_story",
          editor: this.refineInput.editor || "internal_ffmpeg",
          quality: this.refineInput.quality || "high",
        };
        const data = await this.api("POST", "/api/capabilities/refinement/plan", payload);
        if (data.error) {
          this.capabilityMessage = `精剪策略生成失败：${data.error}`;
          return;
        }
        this.refinePlan = data.plan || null;
        this.capabilityMessage = "已生成精剪策略";
      },

      async buildNleHandoff() {
        if (!this.projectDir) return;
        const payload = {
          editor: this.handoffInput.editor || "finalcut",
          title: this.handoffInput.title || "VideoEditer Timeline",
          fps: this.handoffInput.fps || 30,
        };
        const data = await this.api("POST", "/api/capabilities/refinement/handoff", payload);
        if (data.error) {
          this.capabilityMessage = `NLE 交接包生成失败：${data.error}`;
          return;
        }
        this.handoffResult = data.handoff || null;
        if (data.connector) {
          const current = Array.isArray(this.nleConnectors) ? this.nleConnectors : [];
          const others = current.filter(item => `${item && item.editor ? item.editor : ""}` !== `${data.connector.editor || ""}`);
          this.nleConnectors = [data.connector, ...others];
        }
        this.handoffLaunchResult = null;
        this.capabilityMessage = "已生成 NLE 交接包";
      },

      async executeNleRefinement() {
        if (!this.projectDir) return;
        const payload = {
          editor: this.handoffInput.editor || "finalcut",
          title: this.handoffInput.title || "VideoEditer Timeline",
          fps: this.handoffInput.fps || 30,
          launch: !!this.handoffInput.launch,
          app_name: this.handoffInput.app_name || "",
        };
        const data = await this.api("POST", "/api/capabilities/refinement/execute", payload);
        if (data.error) {
          this.capabilityMessage = `NLE 执行失败：${data.error}`;
          if (data.handoff) this.handoffResult = data.handoff;
          if (data.launch) this.handoffLaunchResult = data.launch;
          return;
        }
        this.handoffResult = data.handoff || null;
        this.handoffLaunchResult = data.launch || null;
        if (data.connector) {
          const current = Array.isArray(this.nleConnectors) ? this.nleConnectors : [];
          const others = current.filter(item => `${item && item.editor ? item.editor : ""}` !== `${data.connector.editor || ""}`);
          this.nleConnectors = [data.connector, ...others];
        }
        this.capabilityMessage = payload.launch ? "已生成交接包并启动外部编辑器" : "已生成交接包（未启动外部编辑器）";
      },

      async collectNleMaster() {
        if (!this.projectDir) return;
        const payload = {
          editor: this.handoffInput.editor || "finalcut",
          source_video: this.handoffInput.master_source || "",
          output_name: this.handoffInput.output_name || "final.mp4",
          copy_mode: this.handoffInput.copy_mode || "copy",
        };
        const data = await this.api("POST", "/api/capabilities/refinement/collect_master", payload);
        if (data.error) {
          this.capabilityMessage = `导回成片失败：${data.error}`;
          return;
        }
        this.handoffCollectResult = data.collect || data.record || null;
        if (data.connector) {
          const current = Array.isArray(this.nleConnectors) ? this.nleConnectors : [];
          const others = current.filter(item => `${item && item.editor ? item.editor : ""}` !== `${data.connector.editor || ""}`);
          this.nleConnectors = [data.connector, ...others];
        }
        const outVideo = (this.handoffCollectResult && this.handoffCollectResult.output_video) ? this.handoffCollectResult.output_video : "";
        if (outVideo.endsWith("/final.mp4") || outVideo.endsWith("\\final.mp4")) {
          this.finalUrl = `/api/files/output/final.mp4?t=${Date.now()}`;
        }
        this.capabilityMessage = `已导回外部精剪成片：${outVideo || "output/final.mp4"}`;
      },
    };
  };
}(window));
