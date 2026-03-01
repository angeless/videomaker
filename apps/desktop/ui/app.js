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
    productionView: "hub",        // hub | workflow

    // ── 全局素材库（语义分析模块）──────────────────────────────
    libraryStats: {
      total_assets: 0,
      video_assets: 0,
      image_assets: 0,
      total_locations: 0,
      available_assets: 0,
      local_assets: 0,
      gdrive_assets: 0,
      semantic_dimensions_supported: 0,
      semantic_ready_assets: 0,
      semantic_pending_assets: 0,
      embedding_ready_assets: 0,
      embedding_pending_assets: 0,
      hybrid_search_enabled: false,
      embedding_enabled: false,
    },
    libraryQuery:     "",
    libraryResults:   [],
    libraryLoading:   false,
    libraryMessage:   "",
    libraryPageSize:  120,
    libraryOffset:    0,
    libraryTotalMatches: 0,
    libraryHasMore:   false,
    librarySearchMode: "hybrid", // hybrid | keyword | vector
    libraryMediaType: "all", // all | video | image
    libraryRetrievalMode: "browse",
    libraryLastMode: "hybrid",
    libraryLastMediaType: "all",
    libraryHybridEnabled: false,
    libraryEmbeddingEnabled: false,
    libraryEmbeddingReadyAssets: 0,
    libraryEmbeddingStatus: "",
    libraryEmbeddingStatusMessage: "",
    ingestLocalPath:  "",
    ingestLocalMaxVideos: 600,
    ingestLocalPreviewLoading: false,
    ingestLocalPreviewError: "",
    ingestLocalPreview: null,
    ingestImagePath:  "",
    ingestImageMaxItems: 1200,
    ingestImagePreviewLoading: false,
    ingestImagePreviewError: "",
    ingestImagePreview: null,
    ingestDriveUrl:   "",
    ingestDriveMaxVideos: 80,
    ingestDrivePriority: "",
    ingestDriveMaxScanFolders: 120,
    ingestDriveImageUrl: "",
    ingestDriveImageMaxItems: 200,
    ingestDriveImagePriority: "",
    ingestDriveImageMaxScanFolders: 120,
    ingestImageDrivePreviewLoading: false,
    ingestImageDrivePreviewError: "",
    ingestImageDrivePreview: null,
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
      embedding_model: "",
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
    aiTesting: false,
    aiTestResult: null,
    aiMessage: "",
    preflightChecks: [],
    preflightLoading: false,

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
      rough_target_seconds: 15,
      rough_max_clips: 8,
      rough_merge_gap_s: 0.15,
      rough_remove_phrases: "嗯,啊,然后,就是,那个",
      skin_smooth_strength: 0.4,
      pore_reduction: 0.6,
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

    // ── 能力工作台（Capability）──────────────────────────────────
    capabilityTab: "topic_library",
    capabilityMessage: "",
    capabilityGroups: [
      {
        key: "creative",
        title: "创作链路",
        items: [
          { tab: "topic_library", label: "选题库", hint: "模板库与素材初始化", mode: "project" },
          { tab: "topic_copy", label: "选题+文案", hint: "选题映射文案草稿", mode: "project" },
          { tab: "text_rough", label: "文字粗剪", hint: "句级删减与时长控制", mode: "project" },
          { tab: "short_clip", label: "短视频快剪", hint: "精华片段快速规划", mode: "project" },
          { tab: "refinement", label: "视频精剪", hint: "NLE 交接与导回", mode: "project" },
          { tab: "audio_voice", label: "配乐配音", hint: "旁白/BGM/混音", mode: "project" },
        ],
      },
      {
        key: "semantics",
        title: "语义与文案",
        items: [
          { tab: "subtitle_calibration", label: "字幕校准", hint: "中英文+时间轴", mode: "hybrid" },
          { tab: "image_semantic", label: "图片语义", hint: "图像分析与语义检索", mode: "hybrid" },
          { tab: "article_expand", label: "公众号扩写", hint: "文章结构化扩写", mode: "hybrid" },
          { tab: "publish_prep", label: "发布文案", hint: "分平台标题/描述/关键词", mode: "hybrid" },
        ],
      },
      {
        key: "distribution",
        title: "分发与发布",
        items: [
          { tab: "social_export", label: "社媒导出", hint: "多平台规格导出", mode: "hybrid" },
          { tab: "content_publish", label: "内容发布", hint: "跨平台发布执行", mode: "hybrid" },
        ],
      },
      {
        key: "automation",
        title: "自动化与治理",
        items: [
          { tab: "workflow_builder", label: "自定义工作流", hint: "节点编排与重跑", mode: "hybrid" },
          { tab: "idempotency_cache", label: "幂等缓存", hint: "去重与重试治理", mode: "hybrid" },
          { tab: "agent_templates", label: "Agent 模板", hint: "技能模板与变量", mode: "hybrid" },
          { tab: "agent_observability", label: "Agent 观测", hint: "成本/失败/重放", mode: "hybrid" },
        ],
      },
    ],
    capabilities: [],
    capabilitiesLoading: false,
    topicLibraryLoading: false,
    topicLibraryQuery: "",
    topicLibraryCategory: "",
    topicLibraryItems: [],
    topicForm: {
      slug: "",
      title: "",
      category: "travel",
      audience: "short_video",
      hook_style: "story",
      outline_template: "",
      tags: "",
    },
    topicCopy: {
      slug: "",
      target_duration_s: 60,
      draft: null,
    },
    textRoughInput: {
      removed_phrases: "嗯,啊,然后,就是,那个",
      target_duration_s: 15,
      merge_gap_s: 0.15,
      keep_span_indexes: "",
      drop_span_indexes: "",
      apply_removed_phrases: true,
    },
    textRoughSpans: [],
    textRoughFilterKeyword: "",
    textRoughSourceLoading: false,
    textRoughSourceError: "",
    textRoughPlan: null,
    shortClipInput: {
      target_duration_s: 30,
      max_clips: 8,
    },
    shortClipPlan: null,
    refineInput: {
      style: "travel_story",
      editor: "internal_ffmpeg",
      quality: "high",
    },
    refinePlan: null,
    handoffInput: {
      editor: "finalcut",
      title: "VideoEditer Timeline",
      fps: 30,
      launch: true,
      app_name: "",
      master_source: "",
      output_name: "final.mp4",
      copy_mode: "copy",
    },
    handoffResult: null,
    handoffLaunchResult: null,
    handoffCollectResult: null,
    socialExportInput: {
      input_video: "",
      platforms: "tiktok短视频,微信短视频,抖音短视频,小红书短视频,微信公众号,b站视频,YouTube视频",
      quality: "high",
      output_dir: "",
      strict_duration_limit: true,
    },
    socialExportPlan: null,
    socialExportValidation: null,
    socialExportResult: null,
    socialExportRunning: false,
    socialExportProgress: 0,
    socialExportLog: [],
    socialExportJobId: "",
    socialExportHistory: [],
    socialExportHistoryLoading: false,
    exportProfiles: [],
    customExportTemplates: [],
    socialTemplateForm: {
      platform_id: "",
      name: "",
      width: 1080,
      height: 1920,
      fps: 30,
      video_bitrate: "10M",
      audio_bitrate: "192k",
      max_duration_s: 180,
    },
    subtitleInput: {
      input_mode: "project",
      mode: "timeline_align",
      translation: "off",
      source_audio: "",
      use_llm: false,
      llm_provider: "",
      llm_model: "",
      subtitles_json: "[]",
    },
    subtitlePlan: null,
    subtitleResult: null,
    imageSemanticInput: {
      input_mode: "inline",
      image_paths: "",
      query: "",
      limit: 30,
      retrieval_mode: "hybrid",
      auto_ingest: true,
    },
    imageSemanticAnalyze: null,
    imageSemanticSearch: null,
    articleExpandInput: {
      input_mode: "inline",
      source_text: "",
      key_points: "",
      tone: "professional",
      length_target: 1200,
      title_count: 5,
      use_llm: false,
      llm_provider: "",
      llm_model: "",
    },
    articleExpandResult: null,
    publishPrepInput: {
      input_mode: "inline",
      script_text: "",
      voiceover_text: "",
      platforms: "xiaohongshu,ixigua,douyin,wechat_channels,wechat_mp,youtube,instagram,twitter,threads,facebook,blog",
      platform_content_type: "video_post",
      use_saved_profiles: true,
      use_llm: false,
      llm_provider: "",
      llm_model: "",
      profile_overrides_json: "{}",
    },
    publishPrepProfiles: [],
    publishPrepResult: null,
    contentPublishInput: {
      input_mode: "project",
      platforms: "xiaohongshu,ixigua,douyin,wechat_channels,wechat_mp,youtube,instagram,twitter,threads,facebook,blog",
      platform_content_type: "video_post",
      dry_run: true,
      session_id: "",
      authenticated: false,
      expires_in_minutes: 120,
      title: "",
      description: "",
      keywords: "",
      media_urls: "",
      article_markdown: "",
      article_html: "",
    },
    contentPublishPlatforms: [],
    contentPublishSession: null,
    contentPublishPlan: null,
    contentPublishRun: null,
    workflowCatalog: [],
    workflowList: [],
    workflowRuns: [],
    workflowRunsTotal: 0,
    workflowPlan: null,
    workflowRunResult: null,
    workflowRunning: false,
    workflowRunJobId: "",
    workflowHistoryLoading: false,
    workflowBuilder: {
      workflow_id: "",
      name: "自定义工作流",
      description: "",
      start_step_id: "",
      dry_run: true,
      run_inline: false,
      steps_json: `[
  {
    "step_id": "step_subtitle",
    "capability_id": "subtitle_calibration",
    "action": "run",
    "input_mode": "inline",
    "input": {
      "input_mode": "inline",
      "mode": "text_only",
      "translation": "off",
      "subtitles": [
        {"index": 1, "start_time": 0.0, "end_time": 1.2, "cn_text": "示例字幕一"},
        {"index": 2, "start_time": 1.3, "end_time": 2.5, "cn_text": "示例字幕二"}
      ]
    }
  },
  {
    "step_id": "step_publish_copy",
    "capability_id": "publish_prep",
    "action": "generate",
    "input_mode": "inline",
    "input": {
      "input_mode": "inline",
      "platforms": ["douyin", "youtube"],
      "script_text": "标题参考：{{steps.step_subtitle.response.result.quality_report.total_subtitles}}条字幕",
      "voiceover_text": "这里可以拼接上一步输出"
    }
      }
]`,
      input_json: "{}",
    },
    workflowSteps: [],
    workflowStepJsonError: "",
    workflowQuickAddCapability: "",
    workflowCanvasDragIndex: -1,
    workflowCanvasDropIndex: -1,
    workflowActiveStepIndex: 0,
    audioInput: {
      mood: "travel_story",
      provider: "elevenlabs",
      voice_id: "",
      api_key: "",
      model_id: "eleven_multilingual_v2",
      output_dir: "",
      dry_run: true,
      timeline_output: "",
      master_input: "",
      bgm_audio: "",
      auto_pick_bgm: true,
      bgm_library_dir: "",
      bgm_provider: "local_library",
      bgm_endpoint: "",
      bgm_api_key: "",
      bgm_download: true,
      bgm_cache_enabled: true,
      bgm_strict_schema: false,
      bgm_force_refresh: false,
      bgm_cache_max_age_days: 0,
      bgm_loop: true,
      bgm_fade_out_s: 2.0,
      mix_output: "",
      replace_master: true,
      origin_volume: 0.8,
      narration_volume: 1.0,
      bgm_volume: 0.25,
      enable_ducking: true,
      ducking_threshold: 0.03,
      ducking_ratio: 8.0,
      ducking_attack_ms: 15,
      ducking_release_ms: 250,
    },
    audioPlan: null,
    audioSynthesis: null,
    audioTimeline: null,
    audioMixResult: null,
    audioBgmPick: null,
    audioPipelineRunning: false,
    audioPipelineProgress: 0,
    audioPipelineJobId: "",
    audioPipelineResult: null,
    idempotencyCacheInput: {
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
    },
    idempotencyCacheLoading: false,
    idempotencyCachePruning: false,
    idempotencyCacheRecords: [],
    idempotencyCacheStats: null,
    idempotencyCacheLastPrune: null,
    idempotencyPruneInput: {
      ttl_seconds: 7 * 24 * 3600,
      remove_expired: true,
      clear_memory: false,
      clear_persisted: false,
      max_entries: "",
    },
    agentObservabilityInput: {
      actor_id: "",
      limit: 200,
      top_n: 5,
      include_items: true,
      status: "",
      task_mode: "",
      capability_id: "",
      skill_id: "",
      replay_supported: "",
      since: "",
      until: "",
    },
    agentObservabilityLoading: false,
    agentObservabilitySummary: null,
    agentObservabilityItems: [],
    agentObservabilityItemsTotal: 0,
    agentObservabilityItemsOffset: 0,
    agentObservabilityItemsHasMore: false,
    agentObservabilityHistoryCount: 0,
    agentObservabilityWindowCount: 0,
    agentObservabilityWindowLimit: 200,
    agentObservabilityExporting: "",
    agentObservabilityLastExport: "",
    agentReplayRunningJobId: "",
    agentTaskDetailJobId: "",
    agentTaskDetailLoading: false,
    agentTaskDetailError: "",
    agentTaskDetail: null,
    agentTaskDetailLastExport: "",
    agentTemplateFilters: {
      capability_id: "",
      scope: "",
      actor_id: "",
      include_system: true,
      resolve: true,
    },
    agentTemplateSearch: "",
    agentTemplatesLoading: false,
    agentTemplates: [],
    agentTemplateSelectedKeys: [],
    agentTemplateBulk: {
      target: "overrides",
      key: "",
      value: "",
      parse_json: false,
    },
    agentTemplateEditor: {
      template_id: "",
      name: "",
      capability_id: "",
      scope: "project",
      actor_id: "",
      tags: "",
      base_template_id: "",
      content_json: "{}",
      overrides_json: "{}",
      variables_json: "[]",
    },

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
      this.syncWorkflowStepsFromJson();
      await this.fetchStatus();
      await this.loadAiSettings();
      await this.refreshLibrary();
      this.loading = false;

      if (this.projectDir) {
        this.topModule = "production";
        if (this.productionView === "workflow") {
          await this.loadStepData();
        }
        await this.loadCapabilityWorkbench();
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

    _jobKindZh(kind) {
      const map = {
        workflow_step: "制作步骤任务",
        library_ingest_local: "本地素材分析",
        library_ingest_gdrive: "云端素材分析",
        social_export: "社媒导出任务",
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
        alert(`${actionLabel}被阻塞：${data.error || "有任务运行中"}\n正在运行：${summary}`);
        return true;
      }
      const ok = confirm(
        `${actionLabel}被阻塞：${data.error || "有任务运行中"}\n` +
        `正在运行：${summary}\n是否先取消素材分析任务再继续？`
      );
      if (!ok) return true;
      const cancelRet = await this.cancelJob(ingestJob.job_id);
      if (cancelRet.error) {
        alert(`取消素材分析失败：${cancelRet.error}`);
        return true;
      }
      this.ingestMessage = "已发送取消请求，待分析任务安全停止后再继续。";
      return true;
    },

    async _ensureWorkflowRunnable(actionLabel = "当前操作") {
      if (this.jobStatus === "running") {
        alert("制作流程任务正在运行，请稍后再操作");
        return false;
      }
      if (this.ingestLoading && this.ingestJobId) {
        const ok = confirm(`${actionLabel}前需要停止当前素材分析任务。是否立即取消该分析任务？`);
        if (!ok) return false;
        const ret = await this.cancelJob(this.ingestJobId);
        if (ret.error) {
          alert(`取消素材分析失败：${ret.error}`);
          return false;
        }
        this.ingestMessage = "已发送取消请求，待分析任务安全停止后再继续。";
        return false;
      }
      return true;
    },

    get selectedCount() {
      return this.selectedAssets.length;
    },

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

    _providerAlias(provider) {
      const p = `${provider || ""}`.trim().toLowerCase();
      if (p === "kimi") return "moonshot";
      if (p === "minimax") return "maxmini";
      return p;
    },

    recommendedBaseUrl(provider = null) {
      const p = this._providerAlias(provider || this.aiSettings.provider);
      const map = {
        openai: "https://api.openai.com/v1",
        moonshot: "https://api.moonshot.cn/v1",
        qwen: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        gemini: "https://generativelanguage.googleapis.com/v1beta/openai",
        maxmini: "https://api.minimax.chat/v1",
      };
      return map[p] || "";
    },

    onProviderChanged() {
      const current = `${this.aiSettings.ai_base_url || ""}`.trim();
      const recommended = this.recommendedBaseUrl();
      if (!recommended) return;
      const allRecommended = [
        this.recommendedBaseUrl("openai"),
        this.recommendedBaseUrl("moonshot"),
        this.recommendedBaseUrl("qwen"),
        this.recommendedBaseUrl("gemini"),
        this.recommendedBaseUrl("maxmini"),
      ].filter(Boolean);

      if (!current || allRecommended.includes(current)) {
        this.aiSettings.ai_base_url = recommended;
      }
    },

    fillRecommendedBaseUrl() {
      const recommended = this.recommendedBaseUrl();
      if (!recommended) {
        this.aiMessage = "当前 provider 没有预设推荐 Base URL，可手动填写。";
        return;
      }
      this.aiSettings.ai_base_url = recommended;
      this.aiMessage = `已填充推荐 Base URL：${recommended}`;
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
      this.aiSettings.embedding_model = data.embedding_model || "";
      this.aiSettings.ai_base_url = data.ai_base_url || "";
      this.aiSettings.openai_api_key = "";
      this.aiSettings.anthropic_api_key = "";
      this.aiSettings.clear_openai_api_key = false;
      this.aiSettings.clear_anthropic_api_key = false;
      if (!this.aiSettings.ai_base_url) {
        this.onProviderChanged();
      }
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
      };
      this.aiSettings.openai_api_key = "";
      this.aiSettings.anthropic_api_key = "";
      this.aiSettings.clear_openai_api_key = false;
      this.aiSettings.clear_anthropic_api_key = false;
      this.aiMessage = "AI 配置已保存。Base URL 可留空，模型可在上方直接修改。";
      await this.loadLibraryStats();
    },

    async testAiConnection() {
      this.aiTesting = true;
      this.aiTestResult = null;
      this.aiMessage = "";
      const data = await this.api("POST", "/api/settings/ai/test", {});
      this.aiTesting = false;
      this.aiTestResult = data;
    },

    async runPreflight() {
      this.preflightLoading = true;
      const data = await this.api("GET", "/api/system/preflight");
      this.preflightLoading = false;
      this.preflightChecks = (data && data.checks) ? data.checks : [];
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
      await this.loadCapabilityWorkbench();
    },

    // ── 素材库（语义分析模块）───────────────────────────────────

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

    normalizeTemplateId(value) {
      const text = `${value || ""}`.trim().toLowerCase();
      if (!text) return "";
      let out = "";
      for (const ch of text) {
        if ((ch >= "a" && ch <= "z") || (ch >= "0" && ch <= "9") || ch === "_") out += ch;
        else if (ch === "-" || ch === " " || ch === "/") out += "_";
      }
      while (out.includes("__")) out = out.replace(/__+/g, "_");
      return out.replace(/^_+|_+$/g, "").slice(0, 64);
    },

    parseSpanIndexExpr(value, maxIndex = 0) {
      const text = `${value || ""}`.trim();
      if (!text) return [];
      const normalized = text.replace(/[，；;、\s]+/g, ",");
      const out = new Set();
      const maxN = Number(maxIndex || 0);
      for (const token of normalized.split(",")) {
        const part = `${token || ""}`.trim();
        if (!part) continue;
        if (part.includes("-")) {
          const [leftRaw, rightRaw] = part.split("-", 2);
          const left = parseInt(leftRaw, 10);
          const right = parseInt(rightRaw, 10);
          if (!Number.isFinite(left) || !Number.isFinite(right)) continue;
          let lo = Math.max(Math.min(left, right), 1);
          let hi = Math.max(left, right);
          if (maxN > 0) hi = Math.min(hi, maxN);
          if (hi < lo) continue;
          for (let i = lo; i <= hi; i += 1) out.add(i);
          continue;
        }
        const idx = parseInt(part, 10);
        if (!Number.isFinite(idx) || idx <= 0) continue;
        if (maxN > 0 && idx > maxN) continue;
        out.add(idx);
      }
      return Array.from(out).sort((a, b) => a - b);
    },

    formatSpanIndexExpr(indexes) {
      const arr = Array.isArray(indexes)
        ? indexes.map(x => parseInt(x, 10)).filter(x => Number.isFinite(x) && x > 0).sort((a, b) => a - b)
        : [];
      if (!arr.length) return "";
      const parts = [];
      let start = arr[0];
      let prev = arr[0];
      for (let i = 1; i < arr.length; i += 1) {
        const cur = arr[i];
        if (cur === prev || cur === prev + 1) {
          prev = cur;
          continue;
        }
        parts.push(start === prev ? `${start}` : `${start}-${prev}`);
        start = cur;
        prev = cur;
      }
      parts.push(start === prev ? `${start}` : `${start}-${prev}`);
      return parts.join(",");
    },

    async searchLibrary(query = null, append = false) {
      const q = query === null ? this.libraryQuery : query;
      const normalizedQuery = `${q || ""}`;
      const reqMode = `${this.librarySearchMode || "hybrid"}`.trim().toLowerCase();
      const reqMediaType = `${this.libraryMediaType || "all"}`.trim().toLowerCase();
      const appendMode = !!append
        && normalizedQuery.trim() === `${this.libraryQuery || ""}`.trim()
        && reqMode === `${this.libraryLastMode || "hybrid"}`.trim().toLowerCase()
        && reqMediaType === `${this.libraryLastMediaType || "all"}`.trim().toLowerCase();
      this.libraryQuery = normalizedQuery;
      const reqOffset = appendMode ? this.libraryOffset : 0;
      this.libraryLoading = true;
      const requestedLimit = Math.max(30, Math.min(parseInt(this.libraryPageSize, 10) || 120, 500));
      const data = await this.api(
        "GET",
        `/api/library/search?q=${encodeURIComponent(this.libraryQuery)}&mode=${encodeURIComponent(reqMode)}&media_type=${encodeURIComponent(reqMediaType)}&limit=${requestedLimit}&offset=${reqOffset}`
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
      this.libraryRetrievalMode = `${data.retrieval_mode || (this.libraryQuery.trim() ? reqMode : "browse")}`.trim().toLowerCase();
      this.libraryLastMode = reqMode;
      this.libraryLastMediaType = reqMediaType;
      this.libraryHybridEnabled = !!data.hybrid_search_enabled;
      this.libraryEmbeddingEnabled = !!data.embedding_enabled;
      this.libraryEmbeddingStatus = `${data.embedding_status || ""}`;
      this.libraryEmbeddingStatusMessage = `${data.embedding_status_message || ""}`;
      this.libraryEmbeddingReadyAssets = parseInt(data.embedding_ready_assets || 0, 10) || 0;
      const totalMatches = Number.isFinite(Number(data.total_matches))
        ? Number(data.total_matches)
        : (this.libraryResults.length || 0);
      this.libraryTotalMatches = totalMatches;
      const mediaLabel = this.mediaTypeZh(this.libraryLastMediaType || reqMediaType);

      const shown = this.libraryResults.length;
      if (!this.libraryQuery.trim()) {
        this.libraryMessage = this.libraryHasMore
          ? `已加载 ${shown}/${totalMatches} 条${mediaLabel}素材，点击“加载更多”继续`
          : `已展示全部${mediaLabel}素材：${shown} 条（${this.retrievalModeZh(this.libraryRetrievalMode)}）`;
      } else {
        this.libraryMessage = this.libraryHasMore
          ? `关键词「${this.libraryQuery}」已加载 ${shown}/${totalMatches} 条${mediaLabel}素材（${this.retrievalModeZh(this.libraryRetrievalMode)}）`
          : `关键词「${this.libraryQuery}」命中 ${shown} 条${mediaLabel}素材（${this.retrievalModeZh(this.libraryRetrievalMode)}）`;
      }
      if (this.librarySearchMode === "vector" && !this.libraryEmbeddingEnabled) {
        this.libraryMessage += `；${this.embeddingStatusZh(this.libraryEmbeddingStatus)}`;
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

    async ingestImageSource() {
      if (!this.ingestImagePath) return;
      if (this.isHeavyBusy) {
        this.ingestMessage = "已有任务在运行，请等待当前任务完成";
        return;
      }
      this.ingestLoading = true;
      this.ingestMessage = "";
      this.ingestProgress = 0;
      this.ingestLog = [];
      let maxImages = parseInt(this.ingestImageMaxItems, 10);
      if (!Number.isFinite(maxImages) || maxImages <= 0) maxImages = 1200;
      if (maxImages > 8000) maxImages = 8000;
      this.ingestImageMaxItems = maxImages;

      const data = await this.api("POST", "/api/library/ingest/local/images", {
        path: this.ingestImagePath,
        max_images: maxImages,
      });
      if (data.error) {
        this.ingestLoading = false;
        this.ingestMessage = `图片分析失败：${data.error}`;
        return;
      }

      this.ingestJobId = data.job_id || "";
      this.ingestMessage = "本地图片语义分析任务已启动…";
      const job = await this.waitForJob(this.ingestJobId, (j) => {
        this.ingestProgress = j.progress || 0;
        this.ingestLog = j.log || [];
        if (j.system) this.systemLoad = j.system;
      });
      this.ingestLoading = false;
      this.ingestJobId = "";

      if (job.status === "error") {
        this.ingestMessage = `图片分析失败：${job.error || "任务执行失败"}`;
        return;
      }
      if (job.status === "cancelled") {
        this.ingestMessage = "图片分析已取消";
        await this.refreshLibrary();
        return;
      }

      const payload = (job.result && job.result.result) ? job.result : {};
      const r = payload.result || {};
      const refreshedCount = Array.isArray(r.assets) ? r.assets.filter(a => a && a.semantic_refreshed).length : 0;
      this.ingestMessage = `图片语义分析完成：候选 ${r.total_candidates || r.scanned || 0}，本次扫描 ${r.scanned || 0}，入库 ${r.indexed || 0}，重复命中 ${r.dedup_hits || 0}${refreshedCount > 0 ? `，语义刷新 ${refreshedCount}` : ""}${r.truncated ? "（已按上限截断）" : ""}`;
      await this.refreshLibrary();
    },

    async previewImageSource() {
      if (!this.ingestImagePath) return;
      if (this.isHeavyBusy) {
        this.ingestImagePreviewError = "当前有重任务运行中，请稍后再预览";
        return;
      }
      this.ingestImagePreviewLoading = true;
      this.ingestImagePreviewError = "";
      this.ingestImagePreview = null;
      const data = await this.api("POST", "/api/library/preview/local/images", {
        path: this.ingestImagePath,
        max_results: 20,
      });
      this.ingestImagePreviewLoading = false;
      if (data.error) {
        this.ingestImagePreviewError = data.error;
        return;
      }
      this.ingestImagePreview = data.preview || null;
    },

    async ingestDriveImageSource() {
      if (!this.ingestDriveImageUrl) return;
      if (this.isHeavyBusy) {
        this.ingestMessage = "已有任务在运行，请等待当前任务完成";
        return;
      }
      this.ingestLoading = true;
      this.ingestMessage = "";
      this.ingestProgress = 0;
      this.ingestLog = [];
      let maxImages = parseInt(this.ingestDriveImageMaxItems, 10);
      if (!Number.isFinite(maxImages) || maxImages <= 0) maxImages = 200;
      if (maxImages > 2000) maxImages = 2000;
      this.ingestDriveImageMaxItems = maxImages;
      let maxScanFolders = parseInt(this.ingestDriveImageMaxScanFolders, 10);
      if (!Number.isFinite(maxScanFolders) || maxScanFolders <= 0) maxScanFolders = 120;
      if (maxScanFolders > 2000) maxScanFolders = 2000;
      this.ingestDriveImageMaxScanFolders = maxScanFolders;
      const data = await this.api("POST", "/api/library/ingest/gdrive/images", {
        url: this.ingestDriveImageUrl,
        refresh: this.ingestRefresh,
        max_images: maxImages,
        priority_subdirs: this.ingestDriveImagePriority || "",
        max_scan_folders: maxScanFolders,
      });
      if (data.error) {
        this.ingestLoading = false;
        this.ingestMessage = `Google Drive 图片分析失败：${data.error}`;
        return;
      }

      this.ingestJobId = data.job_id || "";
      this.ingestMessage = "Google Drive 图片分析任务已启动…";
      const job = await this.waitForJob(this.ingestJobId, (j) => {
        this.ingestProgress = j.progress || 0;
        this.ingestLog = j.log || [];
        if (j.system) this.systemLoad = j.system;
      });
      this.ingestLoading = false;
      this.ingestJobId = "";
      if (job.status === "error") {
        this.ingestMessage = `Google Drive 图片分析失败：${job.error || "任务执行失败"}`;
        return;
      }
      if (job.status === "cancelled") {
        this.ingestMessage = "Google Drive 图片分析已取消";
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
      this.ingestMessage = `Google Drive 图片分析完成（${modeLabel}${folderInfo}）：列出 ${r.listed_files || 0}，图片候选 ${r.image_candidates || 0}，下载 ${r.downloaded_images || 0}，入库 ${r.indexed || 0}，重复命中 ${r.dedup_hits || 0}${refreshedCount > 0 ? `，语义刷新 ${refreshedCount}` : ""}${r.truncated ? "（已按上限截断）" : ""}`;
      await this.refreshLibrary();
    },

    async previewDriveImageSource() {
      if (!this.ingestDriveImageUrl) return;
      if (this.isHeavyBusy) {
        this.ingestImageDrivePreviewError = "当前有重任务运行中，请稍后再预览";
        return;
      }
      this.ingestImageDrivePreviewLoading = true;
      this.ingestImageDrivePreviewError = "";
      this.ingestImageDrivePreview = null;

      let maxScanFolders = parseInt(this.ingestDriveImageMaxScanFolders, 10);
      if (!Number.isFinite(maxScanFolders) || maxScanFolders <= 0) maxScanFolders = 120;
      if (maxScanFolders > 2000) maxScanFolders = 2000;
      this.ingestDriveImageMaxScanFolders = maxScanFolders;

      const data = await this.api("POST", "/api/library/preview/gdrive/images", {
        url: this.ingestDriveImageUrl,
        priority_subdirs: this.ingestDriveImagePriority || "",
        max_scan_folders: maxScanFolders,
        max_results: 20,
      });
      this.ingestImageDrivePreviewLoading = false;
      if (data.error) {
        this.ingestImageDrivePreviewError = data.error;
        return;
      }
      this.ingestImageDrivePreview = data.preview || null;
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
      if (!(await this._ensureWorkflowRunnable("执行下一步"))) return;
      if (!this.projectDir) {
        alert("请先选择素材并创建制作项目");
        return;
      }
      const data = await this.api("POST", "/api/run_step");
      if (data.error) {
        const handled = await this._handleBusyConflict(data, "执行下一步");
        if (!handled) alert(data.error);
        return;
      }
      this.startPolling(data.job_id);
    },

    // ── 审核通过 + 运行下一步 ─────────────────────────────────────

    async approve(step, fields = {}) {
      if (!(await this._ensureWorkflowRunnable(`审核 Step ${step}`))) return;
      const data = await this.api("POST", `/api/approve/${step}`, { approved: true, ...fields });
      if (data.error) {
        const handled = await this._handleBusyConflict(data, `审核 Step ${step}`);
        if (!handled) alert(data.error);
        return;
      }
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
          await this.loadCapabilityWorkbench();
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
      if (step === 4) { await this.loadScript(); await this.loadMaterials(); }
      if (step === 5) await this.loadFrames();
      if (step === 6) {
        this.roughUrl = `/api/files/preview/rough_cut.mp4?t=${Date.now()}`;
        this.loadRenderOpts();
      }
      if (step === 7) await this.loadStages();
    },

    // ── Capability Workbench ──────────────────────────────────────

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
        return;
      }
      if (key === "text_rough") await this.loadTextRoughSource();
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
        return;
      }
      this.idempotencyCacheRecords = Array.isArray(data.records) ? data.records : [];
      this.idempotencyCacheStats = data.stats || null;
      this.idempotencyCacheLastPrune = data.prune || null;
      const prune = this.idempotencyCacheLastPrune || {};
      this.capabilityMessage = `幂等缓存已清理：内存移除 ${prune.memory_removed || 0}，落盘移除 ${prune.persisted_removed || 0}`;
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
        return;
      }
      this.agentObservabilityLastExport = `${data.output || ""}`;
      if (data.summary) this.agentObservabilitySummary = data.summary;
      this.capabilityMessage = `Agent 观测已导出 ${fmt.toUpperCase()}：${this.agentObservabilityLastExport || "-"}`;
    },

    async openAgentObservabilityExport() {
      const path = `${this.agentObservabilityLastExport || ""}`.trim();
      if (!path) {
        this.capabilityMessage = "暂无 Agent 观测导出文件";
        return;
      }
      await this.openFinder(path);
    },

    async replayAgentTask(item) {
      if (!this.projectDir) return;
      const sourceJobId = `${item && item.job_id ? item.job_id : ""}`.trim();
      if (!sourceJobId) {
        this.capabilityMessage = "缺少任务ID，无法重放";
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
        return "";
      }
      const newJobId = `${data.new_job_id || (data.response && data.response.job_id) || ""}`.trim();
      if (!newJobId) {
        this.agentReplayRunningJobId = "";
        this.capabilityMessage = "重放请求已发送，但未返回新任务ID";
        return "";
      }
      this.capabilityMessage = `已启动任务重放：${sourceJobId} -> ${newJobId}`;
      const job = await this.waitForJob(newJobId, null, 3 * 60 * 60 * 1000);
      this.agentReplayRunningJobId = "";
      if (job.status === "done") {
        this.capabilityMessage = `任务重放完成：${newJobId}`;
      } else if (job.status === "cancelled") {
        this.capabilityMessage = `任务重放已取消：${newJobId}`;
      } else {
        this.capabilityMessage = `任务重放失败：${job.error || newJobId}`;
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
        return;
      }
      this.agentTaskDetailLastExport = `${data.output || ""}`;
      this.capabilityMessage = `任务已导出 ${fmt.toUpperCase()}：${this.agentTaskDetailLastExport || "-"}`;
    },

    async openAgentTaskDetailExport() {
      const path = `${this.agentTaskDetailLastExport || ""}`.trim();
      if (!path) {
        this.capabilityMessage = "暂无任务导出文件";
        return;
      }
      await this.openFinder(path);
    },

    agentTemplateKey(item) {
      if (!item || typeof item !== "object") return "";
      const scope = `${item.scope || ""}`.trim().toLowerCase();
      const actor = `${item.actor_id || ""}`.trim();
      const tid = `${item.template_id || ""}`.trim();
      return `${scope}|${actor}|${tid}`;
    },

    agentTemplateScopeZh(scope) {
      const key = `${scope || ""}`.trim().toLowerCase();
      const map = {
        system: "系统",
        project: "项目",
        agent: "Agent",
      };
      return map[key] || key || "-";
    },

    getFilteredAgentTemplates() {
      const templates = Array.isArray(this.agentTemplates) ? this.agentTemplates : [];
      const q = `${this.agentTemplateSearch || ""}`.trim().toLowerCase();
      if (!q) return templates;
      return templates.filter((item) => {
        const tags = Array.isArray(item.tags) ? item.tags.join(",") : "";
        const target = [
          item.template_id || "",
          item.name || "",
          item.capability_id || "",
          item.scope || "",
          item.actor_id || "",
          tags,
          item.base_template_id || "",
        ].join(" ").toLowerCase();
        return target.includes(q);
      });
    },

    isAgentTemplateSelected(item) {
      const key = this.agentTemplateKey(item);
      if (!key) return false;
      return (this.agentTemplateSelectedKeys || []).includes(key);
    },

    toggleAgentTemplateSelected(item) {
      const key = this.agentTemplateKey(item);
      if (!key) return;
      const set = new Set(this.agentTemplateSelectedKeys || []);
      if (set.has(key)) set.delete(key);
      else set.add(key);
      this.agentTemplateSelectedKeys = Array.from(set);
    },

    clearAgentTemplateSelection() {
      this.agentTemplateSelectedKeys = [];
    },

    toggleSelectAllEditableAgentTemplates() {
      const filtered = this.getFilteredAgentTemplates();
      const editable = filtered.filter(x => !x.readonly).map(x => this.agentTemplateKey(x)).filter(Boolean);
      if (!editable.length) {
        this.agentTemplateSelectedKeys = [];
        return;
      }
      const selected = new Set(this.agentTemplateSelectedKeys || []);
      const allPicked = editable.every(k => selected.has(k));
      if (allPicked) {
        editable.forEach((k) => selected.delete(k));
      } else {
        editable.forEach((k) => selected.add(k));
      }
      this.agentTemplateSelectedKeys = Array.from(selected);
    },

    _cloneData(value, fallback = {}) {
      try {
        return JSON.parse(JSON.stringify(value));
      } catch {
        return fallback;
      }
    },

    useAgentTemplateEditor(item) {
      if (!item || typeof item !== "object") return;
      this.agentTemplateEditor = {
        template_id: `${item.template_id || ""}`,
        name: `${item.name || ""}`,
        capability_id: `${item.capability_id || ""}`,
        scope: `${item.scope || "project"}`,
        actor_id: `${item.actor_id || ""}`,
        tags: Array.isArray(item.tags) ? item.tags.join(",") : "",
        base_template_id: `${item.base_template_id || ""}`,
        content_json: this.jsonPretty(this._cloneData(item.content, {})) || "{}",
        overrides_json: this.jsonPretty(this._cloneData(item.overrides, {})) || "{}",
        variables_json: this.jsonPretty(this._cloneData(item.variables, [])) || "[]",
      };
      this.capabilityTab = "agent_templates";
    },

    resetAgentTemplateEditor() {
      this.agentTemplateEditor = {
        template_id: "",
        name: "",
        capability_id: "",
        scope: "project",
        actor_id: this.agentTemplateFilters.actor_id || "",
        tags: "",
        base_template_id: "",
        content_json: "{}",
        overrides_json: "{}",
        variables_json: "[]",
      };
    },

    async loadAgentTemplates() {
      if (!this.projectDir) return;
      this.agentTemplatesLoading = true;
      const f = this.agentTemplateFilters || {};
      const params = new URLSearchParams();
      params.set("include_system", f.include_system ? "true" : "false");
      params.set("resolve", f.resolve ? "true" : "false");
      if (`${f.capability_id || ""}`.trim()) params.set("capability_id", `${f.capability_id || ""}`.trim());
      if (`${f.scope || ""}`.trim()) params.set("scope", `${f.scope || ""}`.trim());
      if (`${f.actor_id || ""}`.trim()) params.set("actor_id", `${f.actor_id || ""}`.trim());
      params.set("actor_type", "agent");
      const data = await this.api("GET", `/api/agent/templates?${params.toString()}`);
      this.agentTemplatesLoading = false;
      if (data.error) {
        this.capabilityMessage = `Agent 模板读取失败：${data.error}`;
        return;
      }
      this.agentTemplates = Array.isArray(data.templates) ? data.templates : [];
      const validKeys = new Set(this.agentTemplates.map(x => this.agentTemplateKey(x)).filter(Boolean));
      this.agentTemplateSelectedKeys = (this.agentTemplateSelectedKeys || []).filter(k => validKeys.has(k));
    },

    _parseAgentTemplateInlineValue(rawText, parseJson) {
      const text = `${rawText || ""}`.trim();
      if (!parseJson) return text;
      if (!text) return "";
      const first = text[0] || "";
      const startsJsonToken = first === "{" || first === "[" || first === "\"" || first === "-" || (first >= "0" && first <= "9");
      const literalJsonToken = /^(true|false|null)$/i.test(text);
      if (!startsJsonToken && !literalJsonToken) return text;
      try {
        return JSON.parse(text);
      } catch {
        throw new Error("变量值 JSON 解析失败（字符串请直接填文本，或使用双引号包裹）");
      }
    },

    _buildAgentTemplatePayloadFromItem(item, targetKey, targetValue, targetBucket) {
      const scope = `${item.scope || "project"}`.trim().toLowerCase();
      const payload = {
        template_id: `${item.template_id || ""}`.trim(),
        name: `${item.name || ""}`.trim(),
        capability_id: `${item.capability_id || ""}`.trim(),
        scope,
        actor_id: `${item.actor_id || ""}`.trim(),
        tags: Array.isArray(item.tags) ? this._cloneData(item.tags, []) : [],
        base_template_id: `${item.base_template_id || ""}`.trim(),
        content: this._cloneData(item.content, {}),
        overrides: this._cloneData(item.overrides, {}),
        variables: Array.isArray(item.variables) ? this._cloneData(item.variables, []) : [],
      };
      const bucketName = targetBucket === "content" ? "content" : "overrides";
      if (!payload[bucketName] || typeof payload[bucketName] !== "object" || Array.isArray(payload[bucketName])) {
        payload[bucketName] = {};
      }
      payload[bucketName][targetKey] = targetValue;
      return payload;
    },

    async applyBulkFillAgentTemplates() {
      if (!this.projectDir) return;
      const key = `${this.agentTemplateBulk.key || ""}`.trim();
      if (!key) {
        this.capabilityMessage = "请先填写变量 key";
        return;
      }
      let value;
      try {
        value = this._parseAgentTemplateInlineValue(this.agentTemplateBulk.value, !!this.agentTemplateBulk.parse_json);
      } catch (err) {
        this.capabilityMessage = `${err && err.message ? err.message : "变量值解析失败"}`;
        return;
      }
      const selectedSet = new Set(this.agentTemplateSelectedKeys || []);
      const targets = (this.agentTemplates || []).filter(x => !x.readonly && selectedSet.has(this.agentTemplateKey(x)));
      if (!targets.length) {
        this.capabilityMessage = "请先勾选至少一个可写模板";
        return;
      }
      const bucket = this.agentTemplateBulk.target === "content" ? "content" : "overrides";
      let success = 0;
      const failed = [];
      for (const item of targets) {
        const payload = this._buildAgentTemplatePayloadFromItem(item, key, value, bucket);
        const resp = await this.api("POST", "/api/agent/templates", payload);
        if (resp.error) {
          failed.push(`${payload.template_id}: ${resp.error}`);
          continue;
        }
        success += 1;
      }
      if (!failed.length) {
        this.capabilityMessage = `批量变量回填完成：成功 ${success} 个模板`;
      } else {
        this.capabilityMessage = `批量变量回填完成：成功 ${success}，失败 ${failed.length}（${failed[0]}）`;
      }
      await this.loadAgentTemplates();
    },

    async saveAgentTemplateFromEditor() {
      if (!this.projectDir) return;
      const e = this.agentTemplateEditor || {};
      const templateId = `${e.template_id || ""}`.trim();
      const name = `${e.name || ""}`.trim();
      const capabilityId = `${e.capability_id || ""}`.trim();
      const scope = `${e.scope || "project"}`.trim().toLowerCase();
      let actorId = `${e.actor_id || ""}`.trim();
      if (!templateId || !name || !capabilityId) {
        this.capabilityMessage = "请填写模板ID、名称、能力ID";
        return;
      }
      if (!["project", "agent"].includes(scope)) {
        this.capabilityMessage = "模板 scope 仅支持 project 或 agent";
        return;
      }
      if (scope === "agent" && !actorId) {
        actorId = `${this.agentTemplateFilters.actor_id || ""}`.trim();
      }
      if (scope === "agent" && !actorId) {
        this.capabilityMessage = "agent 模板需要 actor_id";
        return;
      }
      let content = {};
      let overrides = {};
      let variables = [];
      try {
        content = JSON.parse(`${e.content_json || "{}"}` || "{}");
      } catch {
        this.capabilityMessage = "content JSON 格式错误";
        return;
      }
      try {
        overrides = JSON.parse(`${e.overrides_json || "{}"}` || "{}");
      } catch {
        this.capabilityMessage = "overrides JSON 格式错误";
        return;
      }
      try {
        variables = JSON.parse(`${e.variables_json || "[]"}` || "[]");
      } catch {
        this.capabilityMessage = "variables JSON 格式错误";
        return;
      }
      const tags = `${e.tags || ""}`
        .replace(/，/g, ",")
        .split(",")
        .map(x => `${x || ""}`.trim())
        .filter(Boolean);
      const payload = {
        template_id: templateId,
        name,
        capability_id: capabilityId,
        scope,
        actor_id: scope === "agent" ? actorId : "",
        tags,
        base_template_id: `${e.base_template_id || ""}`.trim(),
        content,
        overrides,
        variables,
      };
      const data = await this.api("POST", "/api/agent/templates", payload);
      if (data.error) {
        this.capabilityMessage = `模板保存失败：${data.error}`;
        return;
      }
      this.capabilityMessage = `模板已保存：${templateId}`;
      await this.loadAgentTemplates();
    },

    async deleteAgentTemplate(item = null) {
      if (!this.projectDir) return;
      const target = item && typeof item === "object"
        ? item
        : {
            template_id: `${this.agentTemplateEditor.template_id || ""}`,
            scope: `${this.agentTemplateEditor.scope || "project"}`,
            actor_id: `${this.agentTemplateEditor.actor_id || ""}`,
            readonly: false,
          };
      const templateId = `${target.template_id || ""}`.trim();
      const scope = `${target.scope || ""}`.trim().toLowerCase();
      const actorId = `${target.actor_id || ""}`.trim();
      if (!templateId) {
        this.capabilityMessage = "请先选择要删除的模板";
        return;
      }
      if (target.readonly || scope === "system") {
        this.capabilityMessage = "system 模板只读，不能删除";
        return;
      }
      if (!["project", "agent"].includes(scope)) {
        this.capabilityMessage = "删除模板时 scope 必须是 project 或 agent";
        return;
      }
      if (scope === "agent" && !actorId) {
        this.capabilityMessage = "删除 agent 模板需要 actor_id";
        return;
      }
      const q = new URLSearchParams();
      q.set("scope", scope);
      if (scope === "agent") q.set("actor_id", actorId);
      q.set("actor_type", "agent");
      const data = await this.api("DELETE", `/api/agent/templates/${encodeURIComponent(templateId)}?${q.toString()}`);
      if (data.error) {
        this.capabilityMessage = `模板删除失败：${data.error}`;
        return;
      }
      this.capabilityMessage = `模板已删除：${templateId}`;
      if (`${this.agentTemplateEditor.template_id || ""}`.trim() === templateId) {
        this.resetAgentTemplateEditor();
      }
      await this.loadAgentTemplates();
    },

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
      const outVideo = (this.handoffCollectResult && this.handoffCollectResult.output_video) ? this.handoffCollectResult.output_video : "";
      if (outVideo.endsWith("/final.mp4") || outVideo.endsWith("\\final.mp4")) {
        this.finalUrl = `/api/files/output/final.mp4?t=${Date.now()}`;
      }
      this.capabilityMessage = `已导回外部精剪成片：${outVideo || "output/final.mp4"}`;
    },

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
      const payload = {
        input_mode: this.imageSemanticInput.input_mode || "inline",
        image_paths: paths,
        retrieval_mode: this.imageSemanticInput.retrieval_mode || "hybrid",
        limit: Number(this.imageSemanticInput.limit || 30),
        auto_ingest: !!this.imageSemanticInput.auto_ingest,
      };
      const data = await this.api("POST", "/api/capabilities/image_semantic/analyze", payload);
      if (data.error) {
        this.capabilityMessage = `图片语义分析失败：${data.error}`;
        return;
      }
      this.imageSemanticAnalyze = data.result || null;
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

    async loadContentPublishPlatforms() {
      const data = await this.api("GET", "/api/capabilities/content_publish/platforms");
      if (data.error) {
        this.capabilityMessage = `发布平台列表读取失败：${data.error}`;
        return;
      }
      this.contentPublishPlatforms = Array.isArray(data.platforms) ? data.platforms : [];
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
      this.capabilityMessage = `内容发布执行完成，状态：${status || "unknown"}`;
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
      this.workflowStepJsonError = "";
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
      return { steps: out };
    },

    addWorkflowStep(capabilityId = "") {
      const nextIndex = (Array.isArray(this.workflowSteps) ? this.workflowSteps.length : 0) + 1;
      const row = this._defaultWorkflowStep(capabilityId, nextIndex);
      this.workflowSteps.push(row);
      this._serializeWorkflowSteps();
      this.workflowActiveStepIndex = this.workflowSteps.length - 1;
    },

    addWorkflowConditionStep() {
      const nextIndex = (Array.isArray(this.workflowSteps) ? this.workflowSteps.length : 0) + 1;
      const row = this._defaultWorkflowStep("", nextIndex, "condition");
      this.workflowSteps.push(row);
      this._serializeWorkflowSteps();
      this.workflowActiveStepIndex = this.workflowSteps.length - 1;
    },

    removeWorkflowStep(index) {
      const idx = Number(index);
      if (!Number.isFinite(idx) || idx < 0 || idx >= this.workflowSteps.length) return;
      this.workflowSteps.splice(idx, 1);
      if (this.workflowSteps.length === 0) {
        this.workflowSteps.push(this._defaultWorkflowStep("", 1));
      }
      this._serializeWorkflowSteps();
      this.workflowActiveStepIndex = Math.max(0, Math.min(idx, this.workflowSteps.length - 1));
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
      this._serializeWorkflowSteps();
      this.workflowActiveStepIndex = target;
    },

    onWorkflowStepCapabilityChange(index) {
      const idx = Number(index);
      if (!Number.isFinite(idx) || idx < 0 || idx >= this.workflowSteps.length) return;
      const row = this.workflowSteps[idx];
      if (`${row.node_type || "action"}`.trim().toLowerCase() !== "action") {
        this._serializeWorkflowSteps();
        return;
      }
      const actions = this.workflowActionsForCapability(row.capability_id);
      if (!actions.includes(`${row.action || ""}`.trim().toLowerCase())) {
        row.action = actions[0] || "auto";
      }
      this._serializeWorkflowSteps();
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
      this._serializeWorkflowSteps();
    },

    onWorkflowStepChanged() {
      this._serializeWorkflowSteps();
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

    onWorkflowNodeDragStart(index, ev) {
      const idx = Number(index);
      if (!Number.isFinite(idx) || idx < 0 || idx >= this.workflowSteps.length) return;
      this.workflowCanvasDragIndex = idx;
      this.workflowCanvasDropIndex = idx;
      if (ev && ev.dataTransfer) {
        ev.dataTransfer.effectAllowed = "move";
        try {
          ev.dataTransfer.setData("text/plain", `${idx}`);
        } catch {}
      }
    },

    onWorkflowNodeDragOver(index, ev) {
      const idx = Number(index);
      if (!Number.isFinite(idx) || idx < 0 || idx >= this.workflowSteps.length) return;
      if (ev && typeof ev.preventDefault === "function") ev.preventDefault();
      if (this.workflowCanvasDragIndex < 0) return;
      this.workflowCanvasDropIndex = idx;
    },

    onWorkflowNodeDrop(index, ev) {
      const idx = Number(index);
      if (ev && typeof ev.preventDefault === "function") ev.preventDefault();
      let from = this.workflowCanvasDragIndex;
      if (!(Number.isFinite(from) && from >= 0)) {
        if (ev && ev.dataTransfer) {
          const raw = ev.dataTransfer.getData("text/plain");
          from = Number(raw);
        }
      }
      if (!Number.isFinite(from) || from < 0 || from >= this.workflowSteps.length) {
        this.onWorkflowNodeDragEnd();
        return;
      }
      if (!Number.isFinite(idx) || idx < 0 || idx >= this.workflowSteps.length) {
        this.onWorkflowNodeDragEnd();
        return;
      }
      if (from === idx) {
        this.onWorkflowNodeDragEnd();
        return;
      }
      const moved = this.workflowSteps.splice(from, 1)[0];
      this.workflowSteps.splice(idx, 0, moved);
      this.workflowActiveStepIndex = idx;
      this._serializeWorkflowSteps();
      this.onWorkflowNodeDragEnd();
    },

    onWorkflowCanvasDropToEnd(ev) {
      if (ev && typeof ev.preventDefault === "function") ev.preventDefault();
      let from = this.workflowCanvasDragIndex;
      if (!(Number.isFinite(from) && from >= 0)) {
        if (ev && ev.dataTransfer) {
          const raw = ev.dataTransfer.getData("text/plain");
          from = Number(raw);
        }
      }
      if (!Number.isFinite(from) || from < 0 || from >= this.workflowSteps.length) {
        this.onWorkflowNodeDragEnd();
        return;
      }
      const moved = this.workflowSteps.splice(from, 1)[0];
      this.workflowSteps.push(moved);
      this.workflowActiveStepIndex = this.workflowSteps.length - 1;
      this._serializeWorkflowSteps();
      this.onWorkflowNodeDragEnd();
    },

    onWorkflowNodeDragEnd() {
      this.workflowCanvasDragIndex = -1;
      this.workflowCanvasDropIndex = -1;
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

      const job = await this.waitForJob(jobId, null, 3 * 60 * 60 * 1000);
      this.workflowRunning = false;
      this.workflowRunJobId = "";
      if (job.status === "error") {
        this.capabilityMessage = `工作流执行失败：${job.error || "任务错误"}`;
      } else if (job.status === "cancelled") {
        this.capabilityMessage = "工作流执行已取消";
      } else {
        this.workflowRunResult = (job.result && job.result.run) ? job.result.run : (job.result || null);
        const summary = (this.workflowRunResult && this.workflowRunResult.summary) ? this.workflowRunResult.summary : {};
        this.capabilityMessage = `工作流执行完成：成功 ${summary.success_steps || 0}，失败 ${summary.failed_steps || 0}`;
      }
      await this.loadWorkflowRuns();
    },

    async rerunWorkflow(runItem, rerunFailedOnly = true) {
      if (!runItem || !runItem.run_id) return;
      if (this.workflowRunning) return;
      this.workflowRunning = true;
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
      const job = await this.waitForJob(jobId, null, 3 * 60 * 60 * 1000);
      this.workflowRunning = false;
      if (job.status === "done") {
        this.workflowRunResult = (job.result && job.result.run) ? job.result.run : this.workflowRunResult;
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
        this.capabilityMessage = "工作流重跑已取消";
      } else {
        this.capabilityMessage = `工作流重跑失败：${job.error || jobId}`;
      }
      await this.loadWorkflowRuns();
    },

    async loadSocialExportTemplates() {
      if (!this.projectDir) return;
      const data = await this.api("GET", "/api/capabilities/social_export/templates");
      if (data.error) {
        this.capabilityMessage = `自定义模板读取失败：${data.error}`;
        return;
      }
      this.customExportTemplates = Array.isArray(data.templates) ? data.templates : [];
    },

    useExportProfile(profile) {
      if (!profile) return;
      const pid = `${profile.platform_id || ""}`.trim();
      if (!pid) return;
      const current = `${this.socialExportInput.platforms || ""}`.trim();
      if (!current) {
        this.socialExportInput.platforms = pid;
        return;
      }
      const tokens = current
        .replace(/，/g, ",")
        .split(",")
        .map(x => x.trim())
        .filter(Boolean);
      if (tokens.includes(pid)) return;
      tokens.push(pid);
      this.socialExportInput.platforms = tokens.join(",");
    },

    fillTemplateFormFromProfile(profile) {
      if (!profile) return;
      this.socialTemplateForm.platform_id = `${profile.platform_id || ""}`.trim();
      this.socialTemplateForm.name = `${profile.name || ""}`.trim();
      this.socialTemplateForm.width = Number(profile.width || 1080);
      this.socialTemplateForm.height = Number(profile.height || 1920);
      this.socialTemplateForm.fps = Number(profile.fps || 30);
      this.socialTemplateForm.video_bitrate = `${profile.video_bitrate || "10M"}`.trim();
      this.socialTemplateForm.audio_bitrate = `${profile.audio_bitrate || "192k"}`.trim();
      this.socialTemplateForm.max_duration_s = Number(profile.max_duration_s || 180);
    },

    async saveSocialExportTemplate() {
      if (!this.projectDir) return;
      const pid = this.normalizeTemplateId(this.socialTemplateForm.platform_id || this.socialTemplateForm.name);
      if (!pid) {
        this.capabilityMessage = "模板 ID 不能为空";
        return;
      }
      const payload = {
        platform_id: pid,
        name: `${this.socialTemplateForm.name || ""}`.trim() || pid,
        width: Number(this.socialTemplateForm.width || 1080),
        height: Number(this.socialTemplateForm.height || 1920),
        fps: Number(this.socialTemplateForm.fps || 30),
        video_bitrate: `${this.socialTemplateForm.video_bitrate || "10M"}`.trim() || "10M",
        audio_bitrate: `${this.socialTemplateForm.audio_bitrate || "192k"}`.trim() || "192k",
        max_duration_s: Number(this.socialTemplateForm.max_duration_s || 180),
      };
      const data = await this.api("POST", "/api/capabilities/social_export/templates", payload);
      if (data.error) {
        this.capabilityMessage = `模板保存失败：${data.error}`;
        return;
      }
      this.capabilityMessage = `模板已保存：${payload.platform_id}`;
      this.customExportTemplates = Array.isArray(data.templates) ? data.templates : this.customExportTemplates;
      await this.loadExportProfiles();
    },

    async deleteSocialExportTemplate(templateId) {
      if (!this.projectDir) return;
      const pid = this.normalizeTemplateId(templateId);
      if (!pid) return;
      const data = await this.api("DELETE", `/api/capabilities/social_export/templates/${encodeURIComponent(pid)}`);
      if (data.error) {
        this.capabilityMessage = `模板删除失败：${data.error}`;
        return;
      }
      this.capabilityMessage = `模板已删除：${pid}`;
      this.customExportTemplates = Array.isArray(data.templates) ? data.templates : [];
      await this.loadExportProfiles();
    },

    async loadExportProfiles() {
      const data = await this.api("GET", "/api/capabilities/social_export/profiles");
      if (data.error) {
        this.capabilityMessage = `社媒导出模板读取失败：${data.error}`;
        return;
      }
      this.exportProfiles = Array.isArray(data.profiles) ? data.profiles : [];
    },

    async loadSocialExportHistory() {
      if (!this.projectDir) return;
      this.socialExportHistoryLoading = true;
      const data = await this.api("GET", "/api/capabilities/social_export/history?limit=50");
      this.socialExportHistoryLoading = false;
      if (data.error) {
        this.capabilityMessage = `导出历史读取失败：${data.error}`;
        return;
      }
      this.socialExportHistory = Array.isArray(data.history) ? data.history : [];
    },

    async buildSocialExportPlan() {
      if (!this.projectDir) return;
      const payload = {
        input_video: this.socialExportInput.input_video || "",
        platforms: this.socialExportInput.platforms || "",
        quality: this.socialExportInput.quality || "high",
        output_dir: this.socialExportInput.output_dir || "",
        strict_duration_limit: !!this.socialExportInput.strict_duration_limit,
      };
      const data = await this.api("POST", "/api/capabilities/social_export/plan", payload);
      if (data.error) {
        this.capabilityMessage = `导出计划生成失败：${data.error}`;
        return;
      }
      this.socialExportPlan = data.plan || null;
      this.socialExportResult = null;
      this.capabilityMessage = "已生成社媒导出计划";
    },

    async validateSocialExportSource() {
      if (!this.projectDir) return;
      const payload = {
        input_video: this.socialExportInput.input_video || "",
        platforms: this.socialExportInput.platforms || "",
        strict_duration_limit: !!this.socialExportInput.strict_duration_limit,
      };
      const data = await this.api("POST", "/api/capabilities/social_export/validate_source", payload);
      if (data.error) {
        this.capabilityMessage = `源视频规格校验失败：${data.error}`;
        return;
      }
      this.socialExportValidation = data.report || null;
      const summary = (this.socialExportValidation && this.socialExportValidation.summary) ? this.socialExportValidation.summary : {};
      this.capabilityMessage = `规格校验完成：目标平台 ${summary.total_platforms || 0} 个，需要变换 ${summary.transform_required_platforms || 0} 个`;
    },

    async runSocialExport() {
      if (!this.projectDir) return;
      if (this.socialExportRunning) return;
      this.socialExportRunning = true;
      this.socialExportProgress = 0;
      this.socialExportLog = [];
      this.socialExportResult = null;

      const payload = {
        input_video: this.socialExportInput.input_video || "",
        platforms: this.socialExportInput.platforms || "",
        quality: this.socialExportInput.quality || "high",
        output_dir: this.socialExportInput.output_dir || "",
        strict_duration_limit: !!this.socialExportInput.strict_duration_limit,
      };
      const data = await this.api("POST", "/api/capabilities/social_export/run", payload);
      if (data.error) {
        this.socialExportRunning = false;
        this.capabilityMessage = `启动导出失败：${data.error}`;
        return;
      }
      this.socialExportJobId = data.job_id || "";
      this.capabilityMessage = "社媒导出任务已启动";

      const job = await this.waitForJob(this.socialExportJobId, (j) => {
        this.socialExportProgress = j.progress || 0;
        this.socialExportLog = j.log || [];
      }, 3 * 60 * 60 * 1000);
      this.socialExportRunning = false;
      this.socialExportJobId = "";

      if (job.status === "error") {
        this.capabilityMessage = `社媒导出失败：${job.error || "任务执行失败"}`;
        return;
      }
      if (job.status === "cancelled") {
        this.capabilityMessage = "社媒导出已取消";
        return;
      }
      const result = (job.result && job.result.result) ? job.result.result : (job.result || {});
      const plan = (job.result && job.result.plan) ? job.result.plan : null;
      this.socialExportResult = result || null;
      if (plan) this.socialExportPlan = plan;
      this.capabilityMessage = `社媒导出完成：成功 ${result.success || 0}，失败 ${result.failed || 0}`;
      await this.loadSocialExportHistory();
    },

    async rerunSocialExportBatch(batchId) {
      if (!this.projectDir) return;
      if (!batchId) return;
      if (this.socialExportRunning) return;
      this.socialExportRunning = true;
      this.socialExportProgress = 0;
      this.socialExportLog = [];
      this.socialExportResult = null;

      const data = await this.api("POST", "/api/capabilities/social_export/rerun", { batch_id: batchId });
      if (data.error) {
        this.socialExportRunning = false;
        this.capabilityMessage = `复跑失败：${data.error}`;
        return;
      }
      this.socialExportJobId = data.job_id || "";
      this.capabilityMessage = `已启动批次复跑：${batchId}`;

      const job = await this.waitForJob(this.socialExportJobId, (j) => {
        this.socialExportProgress = j.progress || 0;
        this.socialExportLog = j.log || [];
      }, 3 * 60 * 60 * 1000);
      this.socialExportRunning = false;
      this.socialExportJobId = "";

      if (job.status === "error") {
        this.capabilityMessage = `社媒导出复跑失败：${job.error || "任务执行失败"}`;
        return;
      }
      if (job.status === "cancelled") {
        this.capabilityMessage = "社媒导出复跑已取消";
        return;
      }
      const result = (job.result && job.result.result) ? job.result.result : (job.result || {});
      const plan = (job.result && job.result.plan) ? job.result.plan : null;
      this.socialExportResult = result || null;
      if (plan) this.socialExportPlan = plan;
      this.capabilityMessage = `社媒导出复跑完成：成功 ${result.success || 0}，失败 ${result.failed || 0}`;
      await this.loadSocialExportHistory();
    },

    async buildAudioVoicePlan() {
      if (!this.projectDir) return;
      const payload = { mood: this.audioInput.mood || "travel_story" };
      const data = await this.api("POST", "/api/capabilities/audio_voice/plan", payload);
      if (data.error) {
        this.capabilityMessage = `配乐配音规划失败：${data.error}`;
        return;
      }
      this.audioPlan = data.plan || null;
      this.capabilityMessage = "已生成配乐和配音规划";
    },

    async synthesizeAudioVoice() {
      if (!this.projectDir) return;
      const payload = {
        mood: this.audioInput.mood || "travel_story",
        provider: this.audioInput.provider || "elevenlabs",
        voice_id: this.audioInput.voice_id || "",
        api_key: this.audioInput.api_key || "",
        model_id: this.audioInput.model_id || "eleven_multilingual_v2",
        output_dir: this.audioInput.output_dir || "",
        dry_run: !!this.audioInput.dry_run,
      };
      const data = await this.api("POST", "/api/capabilities/audio_voice/synthesize", payload);
      if (data.error) {
        this.capabilityMessage = `配音合成失败：${data.error}`;
        return;
      }
      this.audioPlan = data.plan || this.audioPlan;
      this.audioSynthesis = data.synthesis || null;
      const total = (this.audioSynthesis && this.audioSynthesis.total_segments) ? this.audioSynthesis.total_segments : 0;
      const dry = this.audioSynthesis && this.audioSynthesis.dry_run;
      this.capabilityMessage = dry ? `已生成配音 dry-run 计划：${total} 段` : `配音合成完成：${total} 段`;
    },

    async buildAudioVoiceTimeline() {
      if (!this.projectDir) return;
      const payload = {
        output_audio: this.audioInput.timeline_output || "",
        dry_run: !!this.audioInput.dry_run,
      };
      const data = await this.api("POST", "/api/capabilities/audio_voice/build_track", payload);
      if (data.error) {
        this.capabilityMessage = `旁白轨生成失败：${data.error}`;
        return;
      }
      this.audioTimeline = data.timeline || null;
      this.capabilityMessage = this.audioInput.dry_run ? "已生成旁白轨 dry-run 计划" : "旁白轨生成完成";
    },

    async pickAudioBgm() {
      if (!this.projectDir) return;
      const payload = {
        mood: this.audioInput.mood || "travel_story",
        bgm_provider: this.audioInput.bgm_provider || "local_library",
        bgm_library_dir: this.audioInput.bgm_library_dir || "",
        bgm_endpoint: this.audioInput.bgm_endpoint || "",
        bgm_api_key: this.audioInput.bgm_api_key || "",
        bgm_download: !!this.audioInput.bgm_download,
        bgm_cache_enabled: !!this.audioInput.bgm_cache_enabled,
        bgm_strict_schema: !!this.audioInput.bgm_strict_schema,
        bgm_force_refresh: !!this.audioInput.bgm_force_refresh,
        bgm_cache_max_age_days: Number(this.audioInput.bgm_cache_max_age_days || 0),
      };
      const data = await this.api("POST", "/api/capabilities/audio_voice/pick_bgm", payload);
      if (data.error) {
        this.capabilityMessage = `自动配乐失败：${data.error}`;
        return;
      }
      this.audioBgmPick = data.pick || null;
      const selected = this.audioBgmPick && this.audioBgmPick.selected_track ? this.audioBgmPick.selected_track : "";
      const selectedUrl = this.audioBgmPick && this.audioBgmPick.selected_url ? this.audioBgmPick.selected_url : "";
      if (selected) {
        this.audioInput.bgm_audio = selected;
        this.capabilityMessage = `已自动选中 BGM：${selected.split("/").pop()}`;
      } else if (selectedUrl) {
        this.audioInput.bgm_audio = selectedUrl;
        this.capabilityMessage = "已使用远端配乐 URL（若需本地文件请开启“远端配乐自动下载到本地”）";
      } else {
        this.capabilityMessage = "未找到可用 BGM，请手动选择";
      }
    },

    async mixAudioToMaster() {
      if (!this.projectDir) return;
      const payload = {
        mood: this.audioInput.mood || "travel_story",
        input_video: this.audioInput.master_input || "",
        narration_audio: this.audioInput.timeline_output || "",
        bgm_audio: this.audioInput.bgm_audio || "",
        auto_pick_bgm: !!this.audioInput.auto_pick_bgm,
        bgm_provider: this.audioInput.bgm_provider || "local_library",
        bgm_library_dir: this.audioInput.bgm_library_dir || "",
        bgm_endpoint: this.audioInput.bgm_endpoint || "",
        bgm_api_key: this.audioInput.bgm_api_key || "",
        bgm_download: !!this.audioInput.bgm_download,
        bgm_cache_enabled: !!this.audioInput.bgm_cache_enabled,
        bgm_strict_schema: !!this.audioInput.bgm_strict_schema,
        bgm_force_refresh: !!this.audioInput.bgm_force_refresh,
        bgm_cache_max_age_days: Number(this.audioInput.bgm_cache_max_age_days || 0),
        bgm_loop: !!this.audioInput.bgm_loop,
        bgm_fade_out_s: Number(this.audioInput.bgm_fade_out_s || 0),
        output_video: this.audioInput.mix_output || "",
        replace_master: !!this.audioInput.replace_master,
        origin_volume: Number(this.audioInput.origin_volume || 0.8),
        narration_volume: Number(this.audioInput.narration_volume || 1.0),
        bgm_volume: Number(this.audioInput.bgm_volume || 0.25),
        enable_ducking: !!this.audioInput.enable_ducking,
        ducking_threshold: Number(this.audioInput.ducking_threshold || 0.03),
        ducking_ratio: Number(this.audioInput.ducking_ratio || 8.0),
        ducking_attack_ms: Number(this.audioInput.ducking_attack_ms || 15),
        ducking_release_ms: Number(this.audioInput.ducking_release_ms || 250),
        dry_run: !!this.audioInput.dry_run,
      };
      const data = await this.api("POST", "/api/capabilities/audio_voice/mix_master", payload);
      if (data.error) {
        this.capabilityMessage = `成片混音失败：${data.error}`;
        return;
      }
      this.audioMixResult = data.mix || null;
      this.audioBgmPick = data.bgm_pick || this.audioBgmPick;
      const outVideo = (this.audioMixResult && this.audioMixResult.output_video) ? this.audioMixResult.output_video : "";
      if (!this.audioInput.dry_run && this.audioInput.replace_master && outVideo.endsWith("/final.mp4")) {
        this.finalUrl = `/api/files/output/final.mp4?t=${Date.now()}`;
      }
      this.capabilityMessage = this.audioInput.dry_run ? "已生成混音 dry-run 计划" : "成片混音完成";
    },

    async runAudioVoicePipeline() {
      if (!this.projectDir) return;
      if (this.audioPipelineRunning) return;
      this.audioPipelineRunning = true;
      this.audioPipelineProgress = 0;
      this.audioPipelineResult = null;
      const payload = {
        mood: this.audioInput.mood || "travel_story",
        provider: this.audioInput.provider || "elevenlabs",
        voice_id: this.audioInput.voice_id || "",
        api_key: this.audioInput.api_key || "",
        model_id: this.audioInput.model_id || "eleven_multilingual_v2",
        output_dir: this.audioInput.output_dir || "",
        output_audio: this.audioInput.timeline_output || "",
        input_video: this.audioInput.master_input || "",
        bgm_audio: this.audioInput.bgm_audio || "",
        auto_pick_bgm: !!this.audioInput.auto_pick_bgm,
        bgm_provider: this.audioInput.bgm_provider || "local_library",
        bgm_library_dir: this.audioInput.bgm_library_dir || "",
        bgm_endpoint: this.audioInput.bgm_endpoint || "",
        bgm_api_key: this.audioInput.bgm_api_key || "",
        bgm_download: !!this.audioInput.bgm_download,
        bgm_cache_enabled: !!this.audioInput.bgm_cache_enabled,
        bgm_strict_schema: !!this.audioInput.bgm_strict_schema,
        bgm_force_refresh: !!this.audioInput.bgm_force_refresh,
        bgm_cache_max_age_days: Number(this.audioInput.bgm_cache_max_age_days || 0),
        bgm_loop: !!this.audioInput.bgm_loop,
        bgm_fade_out_s: Number(this.audioInput.bgm_fade_out_s || 0),
        output_video: this.audioInput.mix_output || "",
        replace_master: !!this.audioInput.replace_master,
        origin_volume: Number(this.audioInput.origin_volume || 0.8),
        narration_volume: Number(this.audioInput.narration_volume || 1.0),
        bgm_volume: Number(this.audioInput.bgm_volume || 0.25),
        enable_ducking: !!this.audioInput.enable_ducking,
        ducking_threshold: Number(this.audioInput.ducking_threshold || 0.03),
        ducking_ratio: Number(this.audioInput.ducking_ratio || 8.0),
        ducking_attack_ms: Number(this.audioInput.ducking_attack_ms || 15),
        ducking_release_ms: Number(this.audioInput.ducking_release_ms || 250),
        dry_run: !!this.audioInput.dry_run,
      };
      const data = await this.api("POST", "/api/capabilities/audio_voice/run", payload);
      if (data.error) {
        this.audioPipelineRunning = false;
        this.capabilityMessage = `音频流水线启动失败：${data.error}`;
        return;
      }
      this.audioPipelineJobId = data.job_id || "";
      this.capabilityMessage = "音频流水线任务已启动";

      const job = await this.waitForJob(this.audioPipelineJobId, (j) => {
        this.audioPipelineProgress = j.progress || 0;
      }, 3 * 60 * 60 * 1000);
      this.audioPipelineRunning = false;
      this.audioPipelineJobId = "";

      if (job.status === "error") {
        this.capabilityMessage = `音频流水线失败：${job.error || "任务执行失败"}`;
        return;
      }
      if (job.status === "cancelled") {
        this.capabilityMessage = "音频流水线已取消";
        return;
      }
      const summary = job.result || {};
      this.audioPipelineResult = summary;
      this.audioPlan = summary.plan || this.audioPlan;
      this.audioBgmPick = summary.bgm_pick || this.audioBgmPick;
      this.audioSynthesis = summary.synthesis || this.audioSynthesis;
      this.audioTimeline = summary.timeline || this.audioTimeline;
      this.audioMixResult = summary.mix || this.audioMixResult;
      const outVideo = summary.mix && summary.mix.output_video ? summary.mix.output_video : "";
      if (!this.audioInput.dry_run && this.audioInput.replace_master && outVideo.endsWith("/final.mp4")) {
        this.finalUrl = `/api/files/output/final.mp4?t=${Date.now()}`;
      }
      this.capabilityMessage = this.audioInput.dry_run ? "音频流水线 dry-run 完成" : "音频流水线完成";
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

    assetKindZh(kind) {
      const k = `${kind || ""}`.trim().toLowerCase();
      if (k === "image") return "图片";
      if (k === "video") return "视频";
      return "素材";
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
      // 保存修改后的 scriptClips 到后端
      const payload = { clips: this.scriptClips, subtitles: this.scriptSubs };
      await this.api("POST", "/api/script", payload);
      await this.approve(4, { notes: "用户确认匹配结果" });
    },

    reassignClipMaterial(clipIndex, newVideoId) {
      if (clipIndex < 0 || clipIndex >= this.scriptClips.length) return;
      const clip = this.scriptClips[clipIndex];
      const mat = this.materialsList.find(m => m.uid === newVideoId || m.id === newVideoId);
      clip.video_id = newVideoId;
      if (mat) {
        clip.video_path = mat.path || mat.filename || newVideoId;
      }
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
      if (typeof c.pore_reduction === "number") this.renderOpts.pore_reduction = c.pore_reduction;
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
      this.productionView = "workflow";
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
