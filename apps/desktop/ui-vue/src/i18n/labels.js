/**
 * 所有用户可见文案集中管理
 * 原则：不用技术术语，用用户能理解的日常用语
 */

export const labels = {
  // ── 应用 ──
  appTitle: '视频制作助手',
  loading: '正在启动…',

  // ── 启动页 ──
  startup: {
    checking: '正在检查运行环境…',
    loadingSettings: '正在加载设置…',
    ready: '准备就绪',
    failed: '启动检查未通过，请查看详情',
  },

  // ── 引导 ──
  onboarding: {
    title: '欢迎使用视频制作助手',
    step1Title: '欢迎',
    step1Desc: '一站式视频内容生产工具：从素材管理、智能选题、脚本生成，到多平台发布。',
    step1Features: ['素材智能分析', '7 步创作工作流', '多平台一键发布'],
    step2Title: '导入素材',
    step2Desc: '选择你的视频素材文件夹，系统会自动分析内容并建立索引。',
    step2SelectFolder: '选择素材文件夹',
    step2FolderSelected: '已选择',
    step2StartIngest: '开始导入',
    step2Ingesting: '导入中…',
    step2IngestDone: '导入完成',
    step3Title: '开始创作',
    step3Desc: '素材已就绪，选择你想做的事：',
    step3GoLibrary: '浏览素材库',
    step3GoCreate: '开始创作',
    skip: '跳过引导',
    finish: '开始使用',
    next: '下一步',
    prev: '上一步',
    start: '开始',
  },

  // ── 导航 ──
  nav: {
    library: '素材库',
    create: '创作',
    production: '制作',  // 兼容
    tools: '工具箱',
    settings: '设置',
    workflow: '工作流',
  },

  // ── 素材库 ──
  library: {
    title: '素材库',
    search: '搜索素材…',
    searchMode: {
      hybrid: '智能搜索',
      keyword: '关键词',
      vector: '语义',
    },
    mediaType: {
      all: '全部',
      video: '视频',
      image: '图片',
    },
    ingest: '导入素材',
    ingestLocal: '本地视频',
    ingestImage: '本地图片',
    ingestCloud: '云端导入',
    analyzing: '正在分析',
    totalAssets: '素材总数',
    empty: '还没有素材',
    emptyHint: '点击"导入素材"添加视频或图片',
    tags: '标签',
    moreTags: '更多',
    location: '拍摄地点',
    duration: '时长',
    resolution: '分辨率',
  },

  // ── 工作流 ──
  workflow: {
    title: '制作工作流',
    steps: [
      '选择素材',
      '生成选题',
      '生成脚本',
      '素材匹配',
      '帧预览',
      '粗剪',
      '精渲染',
    ],
    start: '开始制作',
    next: '下一步',
    prev: '上一步',
    run: '执行',
    running: '执行中…',
    approve: '确认通过',
    reject: '返回修改',
    cancel: '取消执行',
  },

  // ── 工具台 ──
  tools: {
    title: '工具台',
    groups: {
      creative: '创作链路',
      semantics: '语义与文案',
      distribution: '分发与发布',
      automation: '自动化',
      // 新分组（旅程导向）
      content: '内容策划',
      editing: '剪辑制作',
      enhance: '后期增强',
      distribute: '发布分发',
    },
    items: {
      topic_library: { label: '选题库', hint: '浏览和管理选题模板' },
      topic_copy: { label: '选题文案', hint: '为选题生成文案草稿' },
      text_rough: { label: '文字粗剪', hint: '按句子删减控制时长' },
      short_clip: { label: '短视频快剪', hint: '快速规划精华片段' },
      refinement: { label: '视频精剪', hint: '与剪辑软件协作交接' },
      audio_voice: { label: '配乐配音', hint: '旁白、BGM 和混音' },
      subtitle_calibration: { label: '字幕校准', hint: '中英文字幕和时间轴' },
      image_semantic: { label: '图片语义', hint: '图像分析与语义检索' },
      article_expand: { label: '公众号扩写', hint: '文章结构化扩写' },
      publish_prep: { label: '发布文案', hint: '分平台标题和描述' },
      social_export: { label: '社媒导出', hint: '多平台规格导出' },
      content_publish: { label: '内容发布', hint: '跨平台发布执行' },
      workflow_builder: { label: '自定义工作流', hint: '节点编排与重跑' },
      idempotency_cache: { label: '任务缓存', hint: '去重与重试管理' },
      agent_templates: { label: 'Agent 模板', hint: '技能模板与变量' },
      agent_observability: { label: 'Agent 观测', hint: '成本和运行监控' },
    },
  },

  // ── 面板表单提示（T-0606）──
  panelHints: {
    topicLibrary: {
      categoryPlaceholder: '如：旅行、美食、科技',
    },
    topicCopy: {
      slugLabel: '选题标识',
      slugPlaceholder: '如：snow_adventure',
      targetDurationPlaceholder: '目标时长（秒）',
    },
    textRoughCut: {
      removedPhrasesPlaceholder: '需删除的口头禅，逗号分隔，如：嗯、然后、那个',
    },
    refinement: {
      editorHint: '选择已安装的 NLE 编辑器',
    },
    subtitleCalibration: {
      modeTimelineAlign: '时间轴对齐（自动同步字幕时间码）',
    },
    audioVoice: {
      voiceIdPlaceholder: '语音 ID，如 EXAVITQu4vr4xnSDxMaL',
    },
    imageSemantic: {
      analyzeObjects: '物体识别',
      analyzeScene: '场景分析',
      analyzeMood: '情绪氛围',
    },
    articleExpand: {
      lengthTargetPlaceholder: '目标字数',
    },
  },

  // ── 社媒导出 ──
  socialExport: {
    title: '社媒导出',
    form: {
      inputVideo: '输入视频',
      inputVideoPlaceholder: '留空默认 output/final.mp4',
      quality: '品质',
      qualityOptions: { draft: '草稿', medium: '中等', high: '高品质', premium: '最佳' },
      outputDir: '输出目录',
      outputDirPlaceholder: '留空使用默认目录',
      strictDuration: '严格限制时长',
      strictDurationHint: '超过平台最大时长时自动裁剪',
    },
    actions: {
      plan: '生成导出计划',
      planning: '生成中…',
      validate: '校验规格',
      validating: '校验中…',
      export: '执行导出',
      exporting: '导出中',
    },
    profiles: {
      title: '选择目标平台',
      portrait: '竖屏',
      landscape: '横屏',
      maxDuration: '最长',
      selected: '已选择',
      platforms: '个平台',
    },
    plan: {
      title: '导出计划',
      platform: '平台',
      resolution: '分辨率',
      bitrate: '码率',
      status: '状态',
    },
    result: {
      title: '导出结果',
      platform: '平台',
      outputPath: '输出路径',
      fileSize: '文件大小',
      success: '成功',
      failed: '失败',
      total: '共',
    },
    history: {
      title: '历史记录',
      rerun: '复跑',
      createdAt: '创建时间',
      platforms: '平台数',
    },
  },

  // ── 内容发布 ──
  contentPublish: {
    title: '内容发布',
    platformGroups: {
      domestic: '国内平台',
      global: '国际平台',
      custom: '自定义',
    },
    form: {
      title: '标题',
      description: '描述',
      keywords: '关键词',
      keywordsPlaceholder: '多个关键词用逗号分隔',
      mediaUrls: '媒体链接',
      mediaUrlsPlaceholder: '多个链接用逗号分隔',
      selectPlatforms: '选择发布平台',
      noPlatformSelected: '请至少选择一个平台',
      articleMarkdown: 'Markdown 正文',
      articleHtml: 'HTML 正文',
    },
    actions: {
      plan: '生成发布计划',
      planning: '生成中…',
      publish: '执行发布',
      publishing: '发布中…',
      rerunFailed: '重试失败平台',
      rerunning: '复跑中…',
    },
    advanced: {
      toggle: '高级选项',
      dryRun: '仅预览计划（不实际发布）',
    },
    plan: {
      title: '发布计划',
      badgeDry: '模拟',
      badgeLive: '实际',
      platforms: '平台',
      steps: '步骤',
      status: '状态',
      viewRaw: '查看完整计划',
    },
    result: {
      title: '执行结果',
      total: '总数',
      posted: '成功',
      failed: '失败',
      blocked: '阻塞',
      viewRaw: '查看完整 JSON',
    },
    status: {
      posted: '已发布',
      done: '已完成',
      failed: '失败',
      blocked: '未就绪',
      waiting_auth: '等待授权',
      planned: '待执行',
      dry_run: '模拟',
      unknown: '未知',
    },
    statusIcon: {
      posted: '✅',
      done: '✅',
      failed: '❌',
      blocked: '⚠️',
      waiting_auth: '🔑',
      planned: '⏳',
      dry_run: '🔍',
    },
    errors: {
      auth_failed: '平台授权失败或已过期',
      config_missing: '连接器未配置',
      network_error: '网络连接异常',
      platform_rejected: '平台拒绝了发布请求',
      quota_exceeded: '平台发布频率超限',
      params_invalid: '发布参数不符合平台要求',
      unknown: '未知错误',
    },
    blockedReason: '未配置连接器',
    goToSettings: '前往设置',
    bootstrapFailed: '发布服务初始化失败，请检查网络后重试',
    recovery: {
      title: '问题诊断',
      platformsFailed: '个平台',
      rerunFailed: '重试失败平台',
      rerunAll: '全部重新发布',
      reauth: '重新授权',
      fallback: '发布过程中出现问题，请检查设置后重试',
      genericRetry: '重试',
    },
    history: {
      title: '发布历史',
      refresh: '刷新',
      empty: '暂无发布记录。执行发布后记录将出现在此处。',
      success: '成功',
      fail: '失败',
      total: '共',
    },
  },

  // ── 时间线 ──
  timeline: {
    toggle: '时间线',
    zoomIn: '放大',
    zoomOut: '缩小',
    totalDuration: '总时长',
    clipTrack: '视频',
    subtitleTrack: '字幕',
    audioTrack: '音频',
    noData: '暂无脚本数据，请先完成步骤 3',
  },

  // ── 设置 ──
  settings: {
    title: '设置',
    ai: {
      title: 'AI 配置',
      provider: 'AI 服务商',
      model: 'AI 模型',
      embeddingModel: '嵌入模型 (Embedding)',
      baseUrl: 'API 地址',
      apiKey: 'API Key',
      save: '保存配置',
      saving: '保存中…',
      fillUrl: '填充推荐地址',
      keyMasked: '已配置',
      keyNotSet: '未配置',
      clearKey: '清除 Key',
    },
    ui: {
      title: '界面设置',
      creatorMode: '创作者模式',
      creatorModeHint: '开启后使用更友好的文案风格',
      fontScale: '字体缩放',
      defaultVideosDir: '默认素材目录',
      defaultProjectDir: '默认项目目录',
      autoOpenLast: '启动时自动打开上次项目',
      save: '保存设置',
    },
  },

  // ── 项目 ──
  project: {
    new: '新建项目',
    open: '打开项目',
    projectName: '项目名称',
    projectNamePlaceholder: '例如：加拿大旅行Vlog',
    videosDir: '素材文件夹',
    projectDir: '项目保存位置',
    browse: '选择文件夹',
    create: '创建项目',
    creating: '创建中…',
    opening: '打开中…',
    noProject: '未打开项目',
    rename: '重命名项目',
    renameHint: '双击项目名称可编辑',
  },

  // ── 创作侧栏 ──
  createSidebar: {
    guided: '引导流程',
    guidedWorkflow: '7步工作流',
    ideate: '选题构思',
    organize: '剪辑编排',
    refine: '精剪交接',
    audio: '音频设计',
    subtitle: '字幕制作',
    publish: '发布导出',
    freeform: '自由创作',
    canvas: '工作流画布',
    myWorkflows: '我的工作流',
    newWorkflow: '新建工作流',
  },

  // ── 画布 ──
  canvas: {
    title: '工作流画布',
    addNode: '添加节点',
    save: '保存',
    run: '运行',
    clear: '清空',
    nodesCount: '节点',
    edgesCount: '连线',
    untitled: '未命名工作流',
  },

  // ── 通用 ──
  common: {
    confirm: '确认',
    cancel: '取消',
    save: '保存',
    close: '关闭',
    delete: '删除',
    loading: '加载中…',
    retry: '重试',
    noData: '暂无数据',
    error: '出错了',
    success: '操作成功',
  },
}

export default labels
