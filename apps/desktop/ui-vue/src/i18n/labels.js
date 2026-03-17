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
    step1Title: '设置 AI 服务',
    step1Desc: '配置 AI 模型和 API Key，用于智能选题和脚本生成。',
    step2Title: '导入素材',
    step2Desc: '将你的视频、图片素材导入素材库，系统会自动分析内容。',
    step3Title: '开始创作',
    step3Desc: '使用 7 步工作流或独立工具，完成从选题到成品的全流程。',
    skip: '跳过引导',
    finish: '开始使用',
    next: '下一步',
    prev: '上一步',
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
