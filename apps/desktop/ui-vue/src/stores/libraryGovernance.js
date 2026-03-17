import { defineStore } from 'pinia'
import { ref } from 'vue'
import { useApiStore } from './api.js'
import { useToastStore } from './toast.js'

export const useLibraryGovernanceStore = defineStore('libraryGovernance', () => {
  const api = useApiStore()
  const toast = useToastStore()

  // ── Phase B: 重复 / 位置 / Relink ──

  const duplicateGroups = ref([])
  const duplicateGroupsLoading = ref(false)
  const duplicateStatusFilter = ref('')

  const locationHealth = ref(null)
  const locationHealthLoading = ref(false)
  const locationScanResult = ref(null)
  const locationScanLoading = ref(false)
  const relocateResult = ref(null)
  const relocateLoading = ref(false)
  const unavailableAssets = ref([])
  const unavailableLoading = ref(false)

  const relinkReport = ref(null)
  const relinkReportLoading = ref(false)
  const relinkReportUids = ref('')

  // ── 通用异步 job 轮询器（硬约束 3：所有异步 job 统一走此方法）──
  function _pollGenericJob(jobId, onDone, onError) {
    let timer = null
    async function poll() {
      const data = await api.api('GET', `/api/job/${jobId}`)
      if (data.error) {
        if (onError) onError(data)
        return
      }
      const status = `${data.status || ''}`.toLowerCase()
      if (status === 'completed' || status === 'done') {
        if (onDone) onDone(data)
        return
      }
      if (status === 'error' || status === 'failed') {
        toast.show(data.error || '任务失败', 'danger')
        if (onError) onError(data)
        return
      }
      timer = setTimeout(poll, 1500)
    }
    poll()
  }

  // ── 重复组管理（硬约束 1：全部可操作；硬约束 2：操作后自动刷新）──
  async function fetchDuplicateGroups() {
    duplicateGroupsLoading.value = true
    const qs = duplicateStatusFilter.value ? `?status=${duplicateStatusFilter.value}` : ''
    const data = await api.api('GET', `/api/library/duplicates${qs}`)
    duplicateGroupsLoading.value = false
    if (data.error) { toast.show(data.error, 'danger'); return }
    duplicateGroups.value = data.groups || []
  }

  async function detectDuplicates() {
    duplicateGroupsLoading.value = true
    const data = await api.api('POST', '/api/library/duplicates/detect')
    if (data.error) { duplicateGroupsLoading.value = false; toast.show(data.error, 'danger'); return }
    if (data.job_id) {
      _pollGenericJob(data.job_id, () => {
        duplicateGroupsLoading.value = false
        toast.show('重复检测完成', 'success')
        fetchDuplicateGroups() // 硬约束 2：自动刷新
      }, () => { duplicateGroupsLoading.value = false })
    }
  }

  async function resolveDuplicateGroup(groupId) {
    const data = await api.api('POST', `/api/library/duplicates/${groupId}/resolve`)
    if (data.error) { toast.show(data.error, 'danger'); return }
    toast.show('重复组已解决', 'success')
    await fetchDuplicateGroups() // 硬约束 2
  }

  async function ignoreDuplicateGroup(groupId) {
    const data = await api.api('POST', `/api/library/duplicates/${groupId}/ignore`)
    if (data.error) { toast.show(data.error, 'danger'); return }
    toast.show('重复组已忽略', 'info')
    await fetchDuplicateGroups() // 硬约束 2
  }

  async function setDuplicatePrimary(groupId, uid) {
    const data = await api.api('POST', `/api/library/duplicates/${groupId}/primary`, { uid })
    if (data.error) { toast.show(data.error, 'danger'); return }
    toast.show('已设置主文件', 'success')
    await fetchDuplicateGroups() // 硬约束 2
  }

  async function setDuplicateMemberDecision(groupId, memberId, decision) {
    const data = await api.api('POST', `/api/library/duplicates/${groupId}/members/${memberId}/decision`, { decision })
    if (data.error) { toast.show(data.error, 'danger'); return }
    await fetchDuplicateGroups() // 硬约束 2
  }

  // ── 路径健康（硬约束 5：统计使用真实后端口径 — GET /fingerprint/health）──
  async function fetchLocationHealth() {
    locationHealthLoading.value = true
    const data = await api.api('GET', '/api/library/fingerprint/health')
    locationHealthLoading.value = false
    if (data.error) return
    locationHealth.value = data
  }

  async function scanLocations() {
    locationScanLoading.value = true
    locationScanResult.value = null
    const data = await api.api('POST', '/api/library/locations/scan')
    if (data.error) { locationScanLoading.value = false; toast.show(data.error, 'danger'); return }
    if (data.job_id) {
      _pollGenericJob(data.job_id, (result) => {
        locationScanLoading.value = false
        locationScanResult.value = result?.result || result
        toast.show('位置扫描完成', 'success')
        fetchLocationHealth() // 硬约束 2：自动刷新
        fetchUnavailableLocations() // 硬约束 2
      }, () => { locationScanLoading.value = false })
    }
  }

  async function relocateLocations(rootPaths) {
    relocateLoading.value = true
    relocateResult.value = null
    const data = await api.api('POST', '/api/library/locations/relocate', { root_paths: rootPaths || [] })
    if (data.error) { relocateLoading.value = false; toast.show(data.error, 'danger'); return }
    if (data.job_id) {
      _pollGenericJob(data.job_id, (result) => {
        relocateLoading.value = false
        relocateResult.value = result?.result || result
        toast.show('重定位完成', 'success')
        fetchLocationHealth() // 硬约束 2
        fetchUnavailableLocations() // 硬约束 2
      }, () => { relocateLoading.value = false })
    }
  }

  async function fetchUnavailableLocations() {
    unavailableLoading.value = true
    const data = await api.api('GET', '/api/library/locations/unavailable')
    unavailableLoading.value = false
    if (data.error) return
    unavailableAssets.value = data.assets || []
  }

  // ── Relink 报告（硬约束 6：GET/POST 返回结构一致 — 都是 {report: [...]})──
  async function fetchRelinkReport() {
    relinkReportLoading.value = true
    const uids = relinkReportUids.value.split(/[,\s]+/).map(s => s.trim()).filter(Boolean)
    const data = await api.api('POST', '/api/library/relink-report', { uids })
    relinkReportLoading.value = false
    if (data.error) { toast.show(data.error, 'danger'); return }
    relinkReport.value = data.report || []
  }

  // ── Phase C-1: 工程素材 Relink ──
  const projectRelinkProjectPath = ref('')
  const projectRelinkJob = ref(null)
  const projectRelinkLoading = ref(false)
  const projectRelinkExportData = ref(null)
  const projectRelinkApplying = ref(false)
  const projectRelinkApplyResult = ref(null)

  async function runProjectRelink(projectPath, projectType = 'jianying') {
    projectRelinkLoading.value = true
    projectRelinkJob.value = null
    projectRelinkApplyResult.value = null
    const data = await api.api('POST', '/api/library/project-relink', {
      project_path: projectPath,
      project_type: projectType,
    })
    projectRelinkLoading.value = false
    if (data.error) { toast.show(data.error, 'danger'); return }
    projectRelinkJob.value = data
  }

  async function fetchProjectRelinkJob(jobId) {
    projectRelinkLoading.value = true
    const data = await api.api('GET', `/api/library/project-relink/${jobId}`)
    projectRelinkLoading.value = false
    if (data.error) { toast.show(data.error, 'danger'); return }
    projectRelinkJob.value = data.job || data
  }

  async function exportProjectRelink(jobId) {
    const data = await api.api('GET', `/api/library/project-relink/${jobId}/export`)
    if (data.error) { toast.show(data.error, 'danger'); return }
    const mapData = data.relink_map || data
    const blob = new Blob([JSON.stringify(mapData, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `relink_map_${jobId}.json`
    a.click()
    URL.revokeObjectURL(url)
    toast.show('已导出 Relink Map', 'success')
  }

  async function applyProjectRelink(jobId, outputPath, force = false) {
    projectRelinkApplying.value = true
    projectRelinkApplyResult.value = null
    const body = {}
    if (outputPath) body.output_path = outputPath
    if (force) body.force = true
    const data = await api.api('POST', `/api/library/project-relink/${jobId}/apply`, body)
    projectRelinkApplying.value = false
    if (data.error) {
      if (data.already_applied) {
        toast.show('所有可恢复项已应用过，如需重新生成请使用 force 模式', 'warning')
      } else {
        toast.show(data.error, 'danger')
      }
      return
    }
    projectRelinkApplyResult.value = data.result || data
    toast.show(`已生成修复副本，修复了 ${(data.result || {}).applied || 0} 个引用`, 'success')
  }

  function clearProjectRelinkState() {
    projectRelinkProjectPath.value = ''
    projectRelinkJob.value = null
    projectRelinkLoading.value = false
    projectRelinkExportData.value = null
    projectRelinkApplying.value = false
    projectRelinkApplyResult.value = null
    projectRelinkFilter.value = 'all'
    projectRelinkJobHistory.value = []
    projectRelinkCompareResult.value = null
    projectRelinkValidation.value = null
    // D-1
    projectRelinkPreviewApply.value = null
    projectRelinkPreviewLoading.value = false
    projectRelinkRetrying.value = false
    projectRelinkApplyConfirmVisible.value = false
    projectRelinkSuggestions.value = []
    projectRelinkSuggestionsLoading.value = false
    projectRelinkMissingStats.value = null
    projectRelinkMissingStatsLoading.value = false
    projectRelinkBindingInProgress.value = false
    pendingBindItemId.value = null
    // D-3
    projectRelinkWorkbench.value = null
    projectRelinkWorkbenchLoading.value = false
    projectRelinkItemHistory.value = []
    projectRelinkItemHistoryLoading.value = false
    projectRelinkOutputs.value = []
    projectRelinkOutputsLoading.value = false
    projectRelinkBatchBinding.value = false
    pendingBindItemIds.value = []
    // D-4
    projectRelinkJobChain.value = []
    projectRelinkJobChainLoading.value = false
    projectRelinkVerification.value = null
    projectRelinkVerifyLoading.value = false
    projectRelinkHandover.value = null
    projectRelinkHandoverLoading.value = false
    projectRelinkReanalyzing.value = false
  }

  // ── Phase C-2: 工程治理增强 ──
  const projectRelinkJobHistory = ref([])
  const projectRelinkHistoryLoading = ref(false)
  const projectRelinkFilter = ref('all')
  const projectRelinkCompareResult = ref(null)
  const projectRelinkCompareLoading = ref(false)
  const projectRelinkValidation = ref(null)

  async function fetchProjectRelinkHistory(projectPath, limit = 20) {
    projectRelinkHistoryLoading.value = true
    const params = new URLSearchParams({ limit: String(limit) })
    if (projectPath) params.set('project_path', projectPath)
    const data = await api.api('GET', `/api/library/project-relink/list?${params}`)
    projectRelinkHistoryLoading.value = false
    projectRelinkJobHistory.value = data.jobs || []
  }

  async function compareProjectRelinkJobs(jobIdA, jobIdB) {
    projectRelinkCompareLoading.value = true
    const data = await api.api('GET', `/api/library/project-relink/compare?job_id_a=${jobIdA}&job_id_b=${jobIdB}`)
    projectRelinkCompareLoading.value = false
    projectRelinkCompareResult.value = data
  }

  async function validateProjectRelink(projectPath, projectType = 'jianying') {
    const data = await api.api('POST', '/api/library/project-relink/validate', {
      project_path: projectPath, project_type: projectType
    })
    projectRelinkValidation.value = data
    return data
  }

  async function restoreProjectRelinkJob(jobId) {
    await fetchProjectRelinkJob(jobId)
  }

  function copyMissingList() {
    const items = projectRelinkJob.value?.items || []
    const missing = items.filter(i => i.status === 'missing' || i.status === 'unmatched')
    const text = missing.map(i => `${i.asset_name}\t${i.old_path}\t${i.status}`).join('\n')
    navigator.clipboard.writeText(text)
      .then(() => toast.show(`已复制 ${missing.length} 条缺失记录`, 'success'))
      .catch(() => toast.show('复制失败', 'danger'))
  }

  // ── Phase D-1: Task Center + Missing Fix ──
  const projectRelinkPreviewApply = ref(null)
  const projectRelinkPreviewLoading = ref(false)
  const projectRelinkRetrying = ref(false)
  const projectRelinkApplyConfirmVisible = ref(false)
  const projectRelinkSuggestions = ref([])
  const projectRelinkSuggestionsLoading = ref(false)
  const projectRelinkMissingStats = ref(null)
  const projectRelinkMissingStatsLoading = ref(false)
  // D-2: Manual binding
  const projectRelinkBindingInProgress = ref(false)
  const pendingBindItemId = ref(null)
  // D-3: Workbench + batch + history + outputs
  const projectRelinkWorkbench = ref(null)
  const projectRelinkWorkbenchLoading = ref(false)
  const projectRelinkItemHistory = ref([])
  const projectRelinkItemHistoryLoading = ref(false)
  const projectRelinkOutputs = ref([])
  const projectRelinkOutputsLoading = ref(false)
  const projectRelinkBatchBinding = ref(false)
  const pendingBindItemIds = ref([])  // batch mode multi-select
  // D-4: long-term sync + handover
  const projectRelinkJobChain = ref([])
  const projectRelinkJobChainLoading = ref(false)
  const projectRelinkVerification = ref(null)
  const projectRelinkVerifyLoading = ref(false)
  const projectRelinkHandover = ref(null)
  const projectRelinkHandoverLoading = ref(false)
  const projectRelinkReanalyzing = ref(false)

  async function retryProjectRelinkJob(jobId) {
    projectRelinkRetrying.value = true
    const data = await api.api('POST', `/api/library/project-relink/${jobId}/retry`)
    projectRelinkRetrying.value = false
    if (data.error) { toast.show(data.error, 'danger'); return }
    projectRelinkJob.value = data
    toast.show('重试任务已完成', 'success')
    const p = projectRelinkProjectPath.value.trim()
    fetchProjectRelinkHistory(p || undefined)
  }

  async function previewProjectRelinkApply(jobId) {
    projectRelinkPreviewLoading.value = true
    const data = await api.api('GET', `/api/library/project-relink/${jobId}/preview-apply`)
    projectRelinkPreviewLoading.value = false
    if (data.error) { toast.show(data.error, 'danger'); return }
    projectRelinkPreviewApply.value = data
    projectRelinkApplyConfirmVisible.value = true
  }

  async function exportMissingItems(jobId, format = 'json') {
    if (format === 'csv') {
      const resp = await fetch(`/api/library/project-relink/${jobId}/export-missing?format=csv`)
      if (!resp.ok) { toast.show('导出失败', 'danger'); return }
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `missing_items_${jobId}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } else {
      const data = await api.api('GET', `/api/library/project-relink/${jobId}/export-missing?format=json`)
      if (data.error) { toast.show(data.error, 'danger'); return }
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `missing_items_${jobId}.json`
      a.click()
      URL.revokeObjectURL(url)
    }
    toast.show(`已导出缺失清单 (${format.toUpperCase()})`, 'success')
  }

  function confirmApply() {
    const jobId = projectRelinkJob.value?.job_id
    if (!jobId) return
    projectRelinkApplyConfirmVisible.value = false
    projectRelinkPreviewApply.value = null
    applyProjectRelink(jobId)
  }

  function cancelApplyConfirm() {
    projectRelinkApplyConfirmVisible.value = false
    projectRelinkPreviewApply.value = null
  }

  async function fetchCandidateSuggestions(jobId) {
    projectRelinkSuggestionsLoading.value = true
    const data = await api.api('GET', `/api/library/project-relink/${jobId}/suggest-candidates`)
    projectRelinkSuggestionsLoading.value = false
    if (data.error) return
    projectRelinkSuggestions.value = data.suggestions || []
  }

  async function fetchProjectMissingStats(projectPath) {
    projectRelinkMissingStatsLoading.value = true
    const data = await api.api('GET', `/api/library/project-relink/missing-stats?project_path=${encodeURIComponent(projectPath)}`)
    projectRelinkMissingStatsLoading.value = false
    if (data.error) return
    projectRelinkMissingStats.value = data
  }

  // ── Phase D-2: Manual Binding ──

  async function bindProjectRelinkItem(itemId, uid, decisionSource = 'candidate') {
    projectRelinkBindingInProgress.value = true
    const data = await api.api('POST', `/api/library/project-relink/item/${itemId}/bind`, {
      uid, decision_source: decisionSource,
    })
    projectRelinkBindingInProgress.value = false
    if (data.error) { toast.show(data.error, 'danger'); return null }
    toast.show('已绑定素材', 'success')
    // Refresh job to reflect updated items + summary
    if (projectRelinkJob.value?.job_id) {
      await fetchProjectRelinkJob(projectRelinkJob.value.job_id)
    }
    pendingBindItemId.value = null
    return data.item
  }

  async function unbindProjectRelinkItem(itemId) {
    projectRelinkBindingInProgress.value = true
    const data = await api.api('POST', `/api/library/project-relink/item/${itemId}/unbind`)
    projectRelinkBindingInProgress.value = false
    if (data.error) { toast.show(data.error, 'danger'); return null }
    toast.show('已解除绑定', 'success')
    if (projectRelinkJob.value?.job_id) {
      await fetchProjectRelinkJob(projectRelinkJob.value.job_id)
    }
    return data.item
  }

  async function refreshProjectRelinkItems(jobId) {
    const data = await api.api('POST', `/api/library/project-relink/${jobId}/refresh-items`)
    if (data.error) { toast.show(data.error, 'danger'); return }
    toast.show(`已刷新路径: ${(data.result || {}).changed || 0} 个变更`, 'success')
    if (projectRelinkJob.value?.job_id === jobId) {
      await fetchProjectRelinkJob(jobId)
    }
  }

  function setPendingBind(itemId) {
    pendingBindItemId.value = itemId
  }

  function clearPendingBind() {
    pendingBindItemId.value = null
  }

  // ── D-3: Workbench, batch, history, outputs ──
  async function fetchProjectRelinkWorkbench(jobId) {
    projectRelinkWorkbenchLoading.value = true
    const data = await api.api('GET', `/api/library/project-relink/${jobId}/workbench`)
    projectRelinkWorkbenchLoading.value = false
    if (data.error) return
    projectRelinkWorkbench.value = data
  }

  async function batchBindProjectRelinkItems(bindings, decisionSource = 'candidate') {
    projectRelinkBatchBinding.value = true
    const data = await api.api('POST', `/api/library/project-relink/batch-bind`, {
      bindings,
      decision_source: decisionSource,
    })
    projectRelinkBatchBinding.value = false
    if (data.error) { toast.show('批量绑定失败', 'error'); return data }
    toast.show(`批量绑定完成: ${data.success_count} 成功, ${data.failed_count} 失败`, 'success')
    pendingBindItemIds.value = []
    if (projectRelinkJob.value?.job_id) {
      await fetchProjectRelinkJob(projectRelinkJob.value.job_id)
      await fetchProjectRelinkWorkbench(projectRelinkJob.value.job_id)
    }
    return data
  }

  async function fetchProjectRelinkItemHistory(itemId) {
    projectRelinkItemHistoryLoading.value = true
    const data = await api.api('GET', `/api/library/project-relink/item/${itemId}/history`)
    projectRelinkItemHistoryLoading.value = false
    if (data.error) return
    projectRelinkItemHistory.value = data.history || []
  }

  async function undoProjectRelinkItemBind(itemId) {
    projectRelinkBindingInProgress.value = true
    const data = await api.api('POST', `/api/library/project-relink/item/${itemId}/undo-bind`)
    projectRelinkBindingInProgress.value = false
    if (data.error) { toast.show(data.error, 'error'); return }
    toast.show('已撤销绑定', 'success')
    if (projectRelinkJob.value?.job_id) {
      await fetchProjectRelinkJob(projectRelinkJob.value.job_id)
      await fetchProjectRelinkWorkbench(projectRelinkJob.value.job_id)
    }
  }

  async function fetchProjectRelinkOutputs(jobId) {
    projectRelinkOutputsLoading.value = true
    const data = await api.api('GET', `/api/library/project-relink/${jobId}/outputs`)
    projectRelinkOutputsLoading.value = false
    if (data.error) return
    projectRelinkOutputs.value = data.outputs || []
  }

  function togglePendingBindItem(itemId) {
    const idx = pendingBindItemIds.value.indexOf(itemId)
    if (idx >= 0) pendingBindItemIds.value.splice(idx, 1)
    else pendingBindItemIds.value.push(itemId)
  }

  function clearPendingBindItems() {
    pendingBindItemIds.value = []
  }

  // ── Phase D-4: Long-term sync + Handover closure ──

  async function reanalyzeProjectRelink(projectPath, projectType = 'jianying') {
    projectRelinkReanalyzing.value = true
    const data = await api.api('POST', '/api/library/project-relink/reanalyze', {
      project_path: projectPath,
      project_type: projectType,
    })
    projectRelinkReanalyzing.value = false
    if (data.error) { toast.show(data.error, 'danger'); return }
    projectRelinkJob.value = data
    toast.show(`重新分析完成，继承 ${data.inherited_bindings || 0} 个人工绑定`, 'success')
    const p = projectRelinkProjectPath.value.trim()
    fetchProjectRelinkHistory(p || undefined)
    if (data.job_id) {
      fetchProjectRelinkWorkbench(data.job_id)
      fetchProjectRelinkJobChain(p || projectPath)
    }
  }

  async function fetchProjectRelinkJobChain(projectPath) {
    projectRelinkJobChainLoading.value = true
    const data = await api.api('GET', `/api/library/project-relink/job-chain?project_path=${encodeURIComponent(projectPath)}`)
    projectRelinkJobChainLoading.value = false
    if (data.error) return
    projectRelinkJobChain.value = data.chain || []
  }

  async function verifyProjectRelinkState(jobId) {
    projectRelinkVerifyLoading.value = true
    const data = await api.api('POST', `/api/library/project-relink/${jobId}/verify`)
    projectRelinkVerifyLoading.value = false
    if (data.error) { toast.show(data.error, 'danger'); return }
    projectRelinkVerification.value = data
    if (data.all_valid) toast.show('全部路径验证通过', 'success')
    else toast.show(`${data.stale_count} 个路径已失效`, 'warning')
  }

  async function generateHandoverReport(jobId, autoVerify = true) {
    projectRelinkHandoverLoading.value = true
    const data = await api.api('POST', `/api/library/project-relink/${jobId}/handover`, { auto_verify: autoVerify })
    projectRelinkHandoverLoading.value = false
    if (data.error) { toast.show(data.error, 'danger'); return }
    projectRelinkHandover.value = data.report || data
    toast.show('交接报告已生成', 'success')
  }

  async function exportHandoverReport(jobId, format = 'json') {
    if (format === 'markdown') {
      const resp = await fetch(`/api/library/project-relink/${jobId}/export-handover?format=markdown`)
      if (!resp.ok) { toast.show('导出失败', 'danger'); return }
      const blob = await resp.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `handover_report_${jobId}.md`
      a.click()
      URL.revokeObjectURL(url)
    } else {
      const data = await api.api('GET', `/api/library/project-relink/${jobId}/export-handover?format=json`)
      if (data.error) { toast.show(data.error, 'danger'); return }
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `handover_report_${jobId}.json`
      a.click()
      URL.revokeObjectURL(url)
    }
    toast.show(`已导出交接报告 (${format.toUpperCase()})`, 'success')
  }

  return {
    // Phase B state
    duplicateGroups, duplicateGroupsLoading, duplicateStatusFilter,
    locationHealth, locationHealthLoading,
    locationScanResult, locationScanLoading,
    relocateResult, relocateLoading,
    unavailableAssets, unavailableLoading,
    relinkReport, relinkReportLoading, relinkReportUids,
    // Phase B methods
    fetchDuplicateGroups, detectDuplicates,
    resolveDuplicateGroup, ignoreDuplicateGroup,
    setDuplicatePrimary, setDuplicateMemberDecision,
    fetchLocationHealth, scanLocations, relocateLocations,
    fetchUnavailableLocations, fetchRelinkReport,
    // Phase C-1 state
    projectRelinkProjectPath, projectRelinkJob, projectRelinkLoading,
    projectRelinkExportData, projectRelinkApplying, projectRelinkApplyResult,
    // Phase C-1 methods
    runProjectRelink, fetchProjectRelinkJob, exportProjectRelink,
    applyProjectRelink, clearProjectRelinkState,
    // Phase C-2 state
    projectRelinkJobHistory, projectRelinkHistoryLoading,
    projectRelinkFilter, projectRelinkCompareResult,
    projectRelinkCompareLoading, projectRelinkValidation,
    // Phase C-2 methods
    fetchProjectRelinkHistory, compareProjectRelinkJobs,
    validateProjectRelink, restoreProjectRelinkJob, copyMissingList,
    // Phase D-1 state
    projectRelinkPreviewApply, projectRelinkPreviewLoading,
    projectRelinkRetrying, projectRelinkApplyConfirmVisible,
    projectRelinkSuggestions, projectRelinkSuggestionsLoading,
    projectRelinkMissingStats, projectRelinkMissingStatsLoading,
    // Phase D-1 methods
    retryProjectRelinkJob, previewProjectRelinkApply,
    exportMissingItems, confirmApply, cancelApplyConfirm,
    fetchCandidateSuggestions, fetchProjectMissingStats,
    // Phase D-2 state
    projectRelinkBindingInProgress, pendingBindItemId,
    // Phase D-2 methods
    bindProjectRelinkItem, unbindProjectRelinkItem,
    refreshProjectRelinkItems, setPendingBind, clearPendingBind,
    // Phase D-3 state
    projectRelinkWorkbench, projectRelinkWorkbenchLoading,
    projectRelinkItemHistory, projectRelinkItemHistoryLoading,
    projectRelinkOutputs, projectRelinkOutputsLoading,
    projectRelinkBatchBinding, pendingBindItemIds,
    // Phase D-3 methods
    fetchProjectRelinkWorkbench, batchBindProjectRelinkItems,
    fetchProjectRelinkItemHistory, undoProjectRelinkItemBind,
    fetchProjectRelinkOutputs, togglePendingBindItem, clearPendingBindItems,
    // Phase D-4 state
    projectRelinkJobChain, projectRelinkJobChainLoading,
    projectRelinkVerification, projectRelinkVerifyLoading,
    projectRelinkHandover, projectRelinkHandoverLoading,
    projectRelinkReanalyzing,
    // Phase D-4 methods
    reanalyzeProjectRelink, fetchProjectRelinkJobChain,
    verifyProjectRelinkState, generateHandoverReport, exportHandoverReport,
  }
})
