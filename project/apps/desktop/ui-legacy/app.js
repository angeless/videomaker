/* ── 视频制作助手前端 (Alpine.js) ──────────────────────────────────── */

document.addEventListener("alpine:init", () => {
  Alpine.data("app", () => ({

    // ── 状态 Store ──────────────────────────────────────────────
    ...((window.VideoEditorModules && typeof window.VideoEditorModules.createAppInitialState === "function") ? window.VideoEditorModules.createAppInitialState() : {}),

    // ── init ────────────────────────────────────────────────────
    ...((window.VideoEditorModules && typeof window.VideoEditorModules.createRuntimeMixin === "function") ? window.VideoEditorModules.createRuntimeMixin() : {}),
    ...((window.VideoEditorModules && typeof window.VideoEditorModules.createSettingsMixin === "function") ? window.VideoEditorModules.createSettingsMixin() : {}),
    ...((window.VideoEditorModules && typeof window.VideoEditorModules.createProjectWorkflowMixin === "function") ? window.VideoEditorModules.createProjectWorkflowMixin() : {}),
    ...((window.VideoEditorModules && typeof window.VideoEditorModules.createCapabilityAdminMixin === "function") ? window.VideoEditorModules.createCapabilityAdminMixin() : {}),
    ...((window.VideoEditorModules && typeof window.VideoEditorModules.createAgentTemplatesMixin === "function") ? window.VideoEditorModules.createAgentTemplatesMixin() : {}),
    ...((window.VideoEditorModules && typeof window.VideoEditorModules.createCommonUtilsMixin === "function") ? window.VideoEditorModules.createCommonUtilsMixin() : {}),

    get selectedCount() {
      return this.selectedAssets.length;
    },

    ...((window.VideoEditorModules && typeof window.VideoEditorModules.createLibraryMixin === "function") ? window.VideoEditorModules.createLibraryMixin() : {}),
    ...((window.VideoEditorModules && typeof window.VideoEditorModules.createEditingCapabilitiesMixin === "function") ? window.VideoEditorModules.createEditingCapabilitiesMixin() : {}),
    ...((window.VideoEditorModules && typeof window.VideoEditorModules.createWorkflowBuilderMixin === "function") ? window.VideoEditorModules.createWorkflowBuilderMixin() : {}),
    ...((window.VideoEditorModules && typeof window.VideoEditorModules.createSemanticPublishMixin === "function") ? window.VideoEditorModules.createSemanticPublishMixin() : {}),
    ...((window.VideoEditorModules && typeof window.VideoEditorModules.createDistributionAudioMixin === "function") ? window.VideoEditorModules.createDistributionAudioMixin() : {}),
    ...((window.VideoEditorModules && typeof window.VideoEditorModules.createMaterialSemanticsMixin === "function") ? window.VideoEditorModules.createMaterialSemanticsMixin() : {}),

    // ── Step 1：素材 ────────────────────────────────────────────

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

    get matchedClips() {
      return this.scriptClips || [];
    },

  }));
});
