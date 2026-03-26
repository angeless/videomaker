import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApiStore } from './api.js'
import { useToastStore } from './toast.js'
import { useLibraryGovernanceStore } from './libraryGovernance.js'

export const useLibraryStore = defineStore('library', () => {
  const api = useApiStore()
  const toast = useToastStore()

  // ── 统计 ──
  const stats = ref({
    total_assets: 0,
    video_assets: 0,
    image_assets: 0,
    total_locations: 0,
    available_assets: 0,
    semantic_ready_assets: 0,
    semantic_pending_assets: 0,
    embedding_ready_assets: 0,
    embedding_pending_assets: 0,
    hybrid_search_enabled: false,
    embedding_enabled: false,
  })

  // ── 视图模式 ──
  const viewMode = ref('grid') // 'grid' | 'list'

  // ── 搜索 ──
  const query = ref('')
  const results = ref([])
  const loading = ref(false)
  const message = ref('')
  const pageSize = ref(120)
  const offset = ref(0)
  const totalMatches = ref(0)
  const hasMore = ref(false)
  const searchMode = ref('hybrid')
  const mediaType = ref('all')

  // ── 入库状态 ──
  const ingestLoading = ref(false)
  const ingestMessage = ref('')
  const ingestJobId = ref('')
  const ingestProgress = ref(0)
  const ingestLog = ref([])
  const ingestMeta = ref({ processed: 0, total: 0, current_file: '', percent: 0 })

  // 本地视频入库
  const ingestLocalPath = ref('')
  const ingestLocalMaxVideos = ref(600)
  const ingestLocalPreviewLoading = ref(false)
  const ingestLocalPreviewError = ref('')
  const ingestLocalPreview = ref(null)

  // 本地图片入库
  const ingestImagePath = ref('')
  const ingestImageMaxItems = ref(1200)
  const ingestImagePreviewLoading = ref(false)
  const ingestImagePreviewError = ref('')
  const ingestImagePreview = ref(null)

  // 云端入库
  const ingestDriveUrl = ref('')
  const ingestDriveMaxVideos = ref(500)

  // ── API Methods ──

  async function loadStats() {
    const data = await api.api('GET', '/api/library/stats')
    if (data.error) return
    Object.assign(stats.value, data)
  }

  async function search() {
    loading.value = true
    offset.value = 0
    const params = new URLSearchParams({
      q: query.value,
      mode: searchMode.value,
      media_type: mediaType.value,
      limit: `${pageSize.value}`,
      offset: '0',
    })
    const data = await api.api('GET', `/api/library/search?${params}`)
    loading.value = false
    if (data.error) {
      message.value = data.error
      return
    }
    results.value = data.results || []
    totalMatches.value = data.total_matches ?? data.total ?? results.value.length
    hasMore.value = data.has_more ?? (results.value.length >= pageSize.value)
    message.value = ''
  }

  async function loadMore() {
    offset.value += pageSize.value
    loading.value = true
    const params = new URLSearchParams({
      q: query.value,
      mode: searchMode.value,
      media_type: mediaType.value,
      limit: `${pageSize.value}`,
      offset: `${offset.value}`,
    })
    const data = await api.api('GET', `/api/library/search?${params}`)
    loading.value = false
    if (data.error) return
    const newResults = data.results || []
    results.value = [...results.value, ...newResults]
    hasMore.value = newResults.length >= pageSize.value
  }

  // ── 入库操作 ──

  async function previewLocalIngest() {
    if (!ingestLocalPath.value) {
      toast.show('请先选择素材文件夹', 'warn')
      return
    }
    ingestLocalPreviewLoading.value = true
    ingestLocalPreviewError.value = ''
    const data = await api.api('POST', '/api/library/ingest/local/preview', {
      path: ingestLocalPath.value,
      max_videos: ingestLocalMaxVideos.value,
    })
    ingestLocalPreviewLoading.value = false
    if (data.error) {
      ingestLocalPreviewError.value = data.error
      return
    }
    ingestLocalPreview.value = data
  }

  async function previewImageIngest() {
    if (!ingestImagePath.value) {
      toast.show('请先选择图片文件夹', 'warn')
      return
    }
    ingestImagePreviewLoading.value = true
    ingestImagePreviewError.value = ''
    const data = await api.api('POST', '/api/library/ingest/image/preview', {
      path: ingestImagePath.value,
      max_items: ingestImageMaxItems.value,
    })
    ingestImagePreviewLoading.value = false
    if (data.error) {
      ingestImagePreviewError.value = data.error
      return
    }
    ingestImagePreview.value = data
  }

  async function startLocalIngest() {
    ingestLoading.value = true
    ingestMessage.value = ''
    ingestLog.value = []
    ingestProgress.value = 0
    const data = await api.api('POST', '/api/library/ingest/local/start', {
      path: ingestLocalPath.value,
      max_videos: ingestLocalMaxVideos.value,
    })
    if (data.error) {
      ingestLoading.value = false
      ingestMessage.value = data.error
      return
    }
    ingestJobId.value = data.job_id || ''
    if (ingestJobId.value) {
      pollIngestJob()
    }
  }

  async function startImageIngest() {
    ingestLoading.value = true
    ingestMessage.value = ''
    ingestLog.value = []
    ingestProgress.value = 0
    const data = await api.api('POST', '/api/library/ingest/image/start', {
      path: ingestImagePath.value,
      max_items: ingestImageMaxItems.value,
    })
    if (data.error) {
      ingestLoading.value = false
      ingestMessage.value = data.error
      return
    }
    ingestJobId.value = data.job_id || ''
    if (ingestJobId.value) {
      pollIngestJob()
    }
  }

  let _pollTimer = null
  let _lastJobJson = ''

  async function pollIngestJob() {
    if (!ingestJobId.value) return
    const data = await api.api('GET', `/api/job/${ingestJobId.value}`)
    if (data.error) {
      ingestLoading.value = false
      ingestMessage.value = data.error
      return
    }

    // JSON diff 守卫
    const incoming = JSON.stringify(data)
    if (incoming !== _lastJobJson) {
      _lastJobJson = incoming
      ingestProgress.value = data.progress || 0
      if (Array.isArray(data.log)) {
        ingestLog.value = data.log
      }
      if (data.ingest_meta) {
        Object.assign(ingestMeta.value, data.ingest_meta)
      }
    }

    const status = `${data.status || ''}`.toLowerCase()
    if (status === 'completed' || status === 'done') {
      ingestLoading.value = false
      const count = ingestMeta.value.total || ingestMeta.value.processed || 0
      ingestMessage.value = `入库完成：${count} 个素材`
      toast.show(`入库完成：${count} 个素材`, 'success')
      await loadStats()
      await search()
      return
    }
    if (status === 'error' || status === 'failed') {
      ingestLoading.value = false
      ingestMessage.value = data.error || '入库失败'
      toast.show('素材入库失败', 'danger')
      return
    }

    // 继续轮询
    _pollTimer = setTimeout(() => pollIngestJob(), 1500)
  }

  function stopPolling() {
    if (_pollTimer) {
      clearTimeout(_pollTimer)
      _pollTimer = null
    }
  }

  // ── Governance compatibility layer ──
  // Re-export all governance store properties and methods so that
  // existing consumers of useLibraryStore() continue to work unchanged.
  const gov = useLibraryGovernanceStore()

  return {
    // ── Core state ──
    stats,
    viewMode,
    query,
    results,
    loading,
    message,
    pageSize,
    offset,
    totalMatches,
    hasMore,
    searchMode,
    mediaType,
    ingestLoading,
    ingestMessage,
    ingestJobId,
    ingestProgress,
    ingestMeta,
    ingestLog,
    ingestLocalPath,
    ingestLocalMaxVideos,
    ingestLocalPreviewLoading,
    ingestLocalPreviewError,
    ingestLocalPreview,
    ingestImagePath,
    ingestImageMaxItems,
    ingestImagePreviewLoading,
    ingestImagePreviewError,
    ingestImagePreview,
    ingestDriveUrl,
    ingestDriveMaxVideos,
    // ── Core methods ──
    loadStats,
    search,
    loadMore,
    previewLocalIngest,
    previewImageIngest,
    startLocalIngest,
    startImageIngest,
    pollIngestJob,
    stopPolling,

    // ── Governance re-exports (backward compatibility) ──
    // Phase B state
    duplicateGroups: gov.duplicateGroups,
    duplicateGroupsLoading: gov.duplicateGroupsLoading,
    duplicateStatusFilter: gov.duplicateStatusFilter,
    locationHealth: gov.locationHealth,
    locationHealthLoading: gov.locationHealthLoading,
    locationScanResult: gov.locationScanResult,
    locationScanLoading: gov.locationScanLoading,
    relocateResult: gov.relocateResult,
    relocateLoading: gov.relocateLoading,
    unavailableAssets: gov.unavailableAssets,
    unavailableLoading: gov.unavailableLoading,
    relinkReport: gov.relinkReport,
    relinkReportLoading: gov.relinkReportLoading,
    relinkReportUids: gov.relinkReportUids,
    // Phase B methods
    fetchDuplicateGroups: gov.fetchDuplicateGroups,
    detectDuplicates: gov.detectDuplicates,
    resolveDuplicateGroup: gov.resolveDuplicateGroup,
    ignoreDuplicateGroup: gov.ignoreDuplicateGroup,
    setDuplicatePrimary: gov.setDuplicatePrimary,
    setDuplicateMemberDecision: gov.setDuplicateMemberDecision,
    fetchLocationHealth: gov.fetchLocationHealth,
    scanLocations: gov.scanLocations,
    relocateLocations: gov.relocateLocations,
    fetchUnavailableLocations: gov.fetchUnavailableLocations,
    fetchRelinkReport: gov.fetchRelinkReport,
    // Phase C-1 state
    projectRelinkProjectPath: gov.projectRelinkProjectPath,
    projectRelinkJob: gov.projectRelinkJob,
    projectRelinkLoading: gov.projectRelinkLoading,
    projectRelinkExportData: gov.projectRelinkExportData,
    projectRelinkApplying: gov.projectRelinkApplying,
    projectRelinkApplyResult: gov.projectRelinkApplyResult,
    // Phase C-1 methods
    runProjectRelink: gov.runProjectRelink,
    fetchProjectRelinkJob: gov.fetchProjectRelinkJob,
    exportProjectRelink: gov.exportProjectRelink,
    applyProjectRelink: gov.applyProjectRelink,
    clearProjectRelinkState: gov.clearProjectRelinkState,
    // Phase C-2 state
    projectRelinkJobHistory: gov.projectRelinkJobHistory,
    projectRelinkHistoryLoading: gov.projectRelinkHistoryLoading,
    projectRelinkFilter: gov.projectRelinkFilter,
    projectRelinkCompareResult: gov.projectRelinkCompareResult,
    projectRelinkCompareLoading: gov.projectRelinkCompareLoading,
    projectRelinkValidation: gov.projectRelinkValidation,
    // Phase C-2 methods
    fetchProjectRelinkHistory: gov.fetchProjectRelinkHistory,
    compareProjectRelinkJobs: gov.compareProjectRelinkJobs,
    validateProjectRelink: gov.validateProjectRelink,
    restoreProjectRelinkJob: gov.restoreProjectRelinkJob,
    copyMissingList: gov.copyMissingList,
    // Phase D-1 state
    projectRelinkPreviewApply: gov.projectRelinkPreviewApply,
    projectRelinkPreviewLoading: gov.projectRelinkPreviewLoading,
    projectRelinkRetrying: gov.projectRelinkRetrying,
    projectRelinkApplyConfirmVisible: gov.projectRelinkApplyConfirmVisible,
    projectRelinkSuggestions: gov.projectRelinkSuggestions,
    projectRelinkSuggestionsLoading: gov.projectRelinkSuggestionsLoading,
    projectRelinkMissingStats: gov.projectRelinkMissingStats,
    projectRelinkMissingStatsLoading: gov.projectRelinkMissingStatsLoading,
    // Phase D-1 methods
    retryProjectRelinkJob: gov.retryProjectRelinkJob,
    previewProjectRelinkApply: gov.previewProjectRelinkApply,
    exportMissingItems: gov.exportMissingItems,
    confirmApply: gov.confirmApply,
    cancelApplyConfirm: gov.cancelApplyConfirm,
    fetchCandidateSuggestions: gov.fetchCandidateSuggestions,
    fetchProjectMissingStats: gov.fetchProjectMissingStats,
    // Phase D-2 state
    projectRelinkBindingInProgress: gov.projectRelinkBindingInProgress,
    pendingBindItemId: gov.pendingBindItemId,
    // Phase D-2 methods
    bindProjectRelinkItem: gov.bindProjectRelinkItem,
    unbindProjectRelinkItem: gov.unbindProjectRelinkItem,
    refreshProjectRelinkItems: gov.refreshProjectRelinkItems,
    setPendingBind: gov.setPendingBind,
    clearPendingBind: gov.clearPendingBind,
    // Phase D-3 state
    projectRelinkWorkbench: gov.projectRelinkWorkbench,
    projectRelinkWorkbenchLoading: gov.projectRelinkWorkbenchLoading,
    projectRelinkItemHistory: gov.projectRelinkItemHistory,
    projectRelinkItemHistoryLoading: gov.projectRelinkItemHistoryLoading,
    projectRelinkOutputs: gov.projectRelinkOutputs,
    projectRelinkOutputsLoading: gov.projectRelinkOutputsLoading,
    projectRelinkBatchBinding: gov.projectRelinkBatchBinding,
    pendingBindItemIds: gov.pendingBindItemIds,
    // Phase D-3 methods
    fetchProjectRelinkWorkbench: gov.fetchProjectRelinkWorkbench,
    batchBindProjectRelinkItems: gov.batchBindProjectRelinkItems,
    fetchProjectRelinkItemHistory: gov.fetchProjectRelinkItemHistory,
    undoProjectRelinkItemBind: gov.undoProjectRelinkItemBind,
    fetchProjectRelinkOutputs: gov.fetchProjectRelinkOutputs,
    togglePendingBindItem: gov.togglePendingBindItem,
    clearPendingBindItems: gov.clearPendingBindItems,
    // Phase D-4 state
    projectRelinkJobChain: gov.projectRelinkJobChain,
    projectRelinkJobChainLoading: gov.projectRelinkJobChainLoading,
    projectRelinkVerification: gov.projectRelinkVerification,
    projectRelinkVerifyLoading: gov.projectRelinkVerifyLoading,
    projectRelinkHandover: gov.projectRelinkHandover,
    projectRelinkHandoverLoading: gov.projectRelinkHandoverLoading,
    projectRelinkReanalyzing: gov.projectRelinkReanalyzing,
    // Phase D-4 methods
    reanalyzeProjectRelink: gov.reanalyzeProjectRelink,
    fetchProjectRelinkJobChain: gov.fetchProjectRelinkJobChain,
    verifyProjectRelinkState: gov.verifyProjectRelinkState,
    generateHandoverReport: gov.generateHandoverReport,
    exportHandoverReport: gov.exportHandoverReport,
  }
})
