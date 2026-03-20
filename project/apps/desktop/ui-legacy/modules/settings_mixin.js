(function (global) {
  const ns = (global.VideoEditorModules = global.VideoEditorModules || {});

  ns.createSettingsMixin = function createSettingsMixin() {
    return {
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
          this.showToast(`选择文件夹失败：${data.error}`, "danger");
        }
      },

      async pickFile(target) {
        const data = await this.api("POST", "/api/dialog/file");
        if (data.path) {
          this.setPathValue(target, data.path);
          return;
        }
        if (data.error && !data.cancelled) {
          this.showToast(`选择文件失败：${data.error}`, "danger");
        }
      },

      _providerAlias(provider) {
        const p = `${provider || ""}`.trim().toLowerCase();
        if (p === "kimi") return "moonshot";
        if (p === "minimax") return "maxmini";
        return p;
      },

      aiProviderOptions() {
        const providers = (this.aiCatalog && Array.isArray(this.aiCatalog.providers)) ? this.aiCatalog.providers : [];
        if (providers.length > 0) return providers;
        return [
          { provider_id: "openai", label: "OpenAI", default_base_url: "https://api.openai.com/v1", models: [], embedding_models: [] },
        ];
      },

      _providerCatalog(provider = null) {
        const p = this._providerAlias(provider || this.aiSettings.provider);
        return this.aiProviderOptions().find(x => `${x.provider_id || ""}`.toLowerCase() === p) || null;
      },

      aiModelOptions(provider = null) {
        const item = this._providerCatalog(provider);
        const models = item && Array.isArray(item.models) ? item.models : [];
        return models.filter(Boolean);
      },

      embeddingModelOptions(provider = null) {
        const item = this._providerCatalog(provider);
        const models = item && Array.isArray(item.embedding_models) ? item.embedding_models : [];
        return models.filter(Boolean);
      },

      embeddingModelResolved() {
        const current = `${this.aiSettings.embedding_model || ""}`.trim();
        if (current) return current;
        const fallback = `${(this.aiCatalog && this.aiCatalog.default_embedding_model) || "text-embedding-3-small"}`.trim();
        return fallback || "text-embedding-3-small";
      },

      recommendedBaseUrl(provider = null, model = null) {
        const item = this._providerCatalog(provider);
        if (!item) return "";
        const modelId = `${model || this.aiSettings.ai_model || ""}`.trim().toLowerCase();
        const modelBase = (item.model_base_urls && typeof item.model_base_urls === "object") ? item.model_base_urls : {};
        if (modelId) {
          for (const [k, v] of Object.entries(modelBase)) {
            if (`${k || ""}`.trim().toLowerCase() === modelId && `${v || ""}`.trim()) {
              return `${v || ""}`.trim();
            }
          }
        }
        return `${item.default_base_url || ""}`.trim();
      },

      onProviderChanged(forceModelSelection = false) {
        const provider = this._providerAlias(this.aiSettings.provider);
        this.aiSettings.provider = provider || "openai";
        const modelOptions = this.aiModelOptions(provider);
        const currentModel = `${this.aiSettings.ai_model || ""}`.trim();
        if (forceModelSelection && modelOptions.length > 0 && !currentModel) {
          this.aiSettings.ai_model = modelOptions[0];
        } else if (currentModel && modelOptions.length > 0 && !modelOptions.includes(currentModel)) {
          this.aiSettings.ai_model = currentModel;
        }
        const current = `${this.aiSettings.ai_base_url || ""}`.trim();
        const recommended = this.recommendedBaseUrl(provider, this.aiSettings.ai_model);
        if (!recommended) return;
        const allRecommended = this.aiProviderOptions()
          .map(item => this.recommendedBaseUrl(item.provider_id, this.aiSettings.ai_model))
          .filter(Boolean);

        if (!current || allRecommended.includes(current)) {
          this.aiSettings.ai_base_url = recommended;
        }
      },

      onAiModelChanged() {
        const current = `${this.aiSettings.ai_base_url || ""}`.trim();
        const recommended = this.recommendedBaseUrl(this.aiSettings.provider, this.aiSettings.ai_model);
        if (!recommended) return;
        const allRecommended = this.aiProviderOptions()
          .map(item => this.recommendedBaseUrl(item.provider_id, this.aiSettings.ai_model))
          .filter(Boolean);
        if (!current || allRecommended.includes(current)) {
          this.aiSettings.ai_base_url = recommended;
        }
      },

      fillRecommendedBaseUrl() {
        const recommended = this.recommendedBaseUrl(this.aiSettings.provider, this.aiSettings.ai_model);
        if (!recommended) {
          this.aiMessage = "当前 provider 没有预设推荐 Base URL，可手动填写。";
          return;
        }
        this.aiSettings.ai_base_url = recommended;
        this.aiMessage = `已填充推荐 Base URL：${recommended}`;
      },

      openAiSettingsSection() {
        this.topModule = "analysis";
        const node = document.getElementById("ai-settings-card");
        if (!node) return;
        node.scrollIntoView({ behavior: "smooth", block: "start" });
      },

      async saveVectorOpenAiKey() {
        const key = `${this.aiSettings.openai_api_key || ""}`.trim();
        if (!key) {
          this.aiMessage = "请先输入 OpenAI API Key";
          return;
        }
        await this.saveAiSettings();
        await this.refreshLibrary();
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
          secret_storage: (data.secret_storage && typeof data.secret_storage === "object")
            ? data.secret_storage
            : { backend: "", available: false, reason: "" },
        };
        if (data.catalog && typeof data.catalog === "object") {
          this.aiCatalog = {
            default_provider: data.catalog.default_provider || "openai",
            default_embedding_model: data.catalog.default_embedding_model || "text-embedding-3-small",
            providers: Array.isArray(data.catalog.providers) ? data.catalog.providers : [],
          };
        }
        this.aiSettings.provider = data.provider || this.aiSettings.provider || "openai";
        this.aiSettings.ai_model = data.ai_model || "";
        this.aiSettings.embedding_model = data.embedding_model || "";
        this.aiSettings.ai_base_url = data.ai_base_url || "";
        this.aiSettings.openai_api_key = "";
        this.aiSettings.anthropic_api_key = "";
        this.aiSettings.clear_openai_api_key = false;
        this.aiSettings.clear_anthropic_api_key = false;
        this.onProviderChanged(true);
        this.aiMessage = "";
      },

      async saveAiSettings() {
        this.aiSaving = true;
        this.aiMessage = "";
        const payload = {
          provider: this.aiSettings.provider || "",
          ai_model: this.aiSettings.ai_model || "",
          embedding_model: this.aiSettings.embedding_model || "",
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
          secret_storage: (data.secret_storage && typeof data.secret_storage === "object")
            ? data.secret_storage
            : { backend: "", available: false, reason: "" },
        };
        this.aiSettings.openai_api_key = "";
        this.aiSettings.anthropic_api_key = "";
        this.aiSettings.clear_openai_api_key = false;
        this.aiSettings.clear_anthropic_api_key = false;
        this.aiMessage = `AI 配置已保存。当前 Embedding 默认模型：${this.embeddingModelResolved()}`;
        await this.loadLibraryStats();
        await this.refreshTaskQueue();
      },

      productionModeHeading() {
        return this.uiSettings.creator_mode ? "创作模式入口" : "生产模式入口";
      },

      productionViewLabel(view) {
        const key = `${view || ""}`.trim().toLowerCase();
        if (this.uiSettings.creator_mode) {
          if (key === "hub") return "创作工具台";
          if (key === "workflow") return "连线编排";
        }
        if (key === "hub") return "模块中心";
        if (key === "workflow") return "7步流程";
        return key || "-";
      },

      capabilityHubTitle() {
        return this.uiSettings.creator_mode ? "创作工具台（独立功能模块）" : "能力工作台（模块化功能）";
      },

      focusUiSettingsCard() {
        this.topModule = "analysis";
        const node = document.getElementById("ui-settings-card");
        if (!node) return;
        node.scrollIntoView({ behavior: "smooth", block: "start" });
      },

      applyUiSettings() {
        const scale = Math.max(0.85, Math.min(Number(this.uiSettings.font_scale || 1), 1.45));
        this.uiSettings.font_scale = Number.isFinite(scale) ? Number(scale.toFixed(2)) : 1.0;
        document.body.style.zoom = `${this.uiSettings.font_scale}`;
        if (this.uiSettings.preferred_production_view === "workflow" || this.uiSettings.preferred_production_view === "hub") {
          if (this.topModule === "production") {
            this.productionView = this.uiSettings.preferred_production_view;
          }
        }
        if (!this.initVideosDir && this.uiSettings.default_videos_dir) {
          this.initVideosDir = this.uiSettings.default_videos_dir;
        }
        if (!this.initProjectDir && this.uiSettings.default_project_dir) {
          this.initProjectDir = this.uiSettings.default_project_dir;
        }
      },

      async loadUiSettings() {
        this.uiSettingsLoading = true;
        const data = await this.api("GET", "/api/settings/ui");
        this.uiSettingsLoading = false;
        if (data.error) {
          this.uiSettingsMessage = `应用设置读取失败：${data.error}`;
          return;
        }
        this.uiSettings = {
          onboarding_completed: !!data.onboarding_completed,
          creator_mode: data.creator_mode !== false,
          font_scale: Number(data.font_scale || 1.0),
          preferred_production_view: `${data.preferred_production_view || "hub"}`,
          default_videos_dir: data.default_videos_dir || "",
          default_project_dir: data.default_project_dir || "",
          auto_open_last_project: data.auto_open_last_project !== false,
          last_project_dir: data.last_project_dir || "",
        };
        this.uiSettingsMessage = "";
        this.applyUiSettings();
      },

      async saveUiSettings() {
        this.uiSettingsSaving = true;
        const payload = {
          onboarding_completed: !!this.uiSettings.onboarding_completed,
          creator_mode: !!this.uiSettings.creator_mode,
          font_scale: Number(this.uiSettings.font_scale || 1.0),
          preferred_production_view: this.uiSettings.preferred_production_view || "hub",
          default_videos_dir: this.uiSettings.default_videos_dir || "",
          default_project_dir: this.uiSettings.default_project_dir || "",
          auto_open_last_project: !!this.uiSettings.auto_open_last_project,
        };
        const data = await this.api("POST", "/api/settings/ui", payload);
        this.uiSettingsSaving = false;
        if (data.error) {
          this.uiSettingsMessage = `应用设置保存失败：${data.error}`;
          return;
        }
        await this.loadUiSettings();
        this.uiSettingsMessage = "应用设置已保存";
      },

      async dismissOnboardingWizard(markCompleted = false) {
        this.showOnboardingWizard = false;
        if (!markCompleted) return;
        this.uiSettings.onboarding_completed = true;
        await this.saveUiSettings();
      },
    };
  };
}(window));
