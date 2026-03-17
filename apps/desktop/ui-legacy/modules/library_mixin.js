(function (global) {
  const ns = (global.VideoEditorModules = global.VideoEditorModules || {});

  ns.createLibraryMixin = function createLibraryMixin() {
    return {
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
      this.ingestMessage = "本地素材分析任务已提交，正在排队/执行…";
      const job = await this.waitForJob(this.ingestJobId, (j) => {
        this.ingestProgress = j.progress || 0;
        this.ingestLog = j.log || [];
        if (j.status === "queued") {
          const pos = Number(j.queue_position || 0);
          this.ingestMessage = pos > 0 ? `任务排队中，前方还有 ${pos - 1} 个任务` : "任务排队中，等待执行";
        }
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
      this.ingestMessage = "本地图片语义分析任务已提交，正在排队/执行…";
      const job = await this.waitForJob(this.ingestJobId, (j) => {
        this.ingestProgress = j.progress || 0;
        this.ingestLog = j.log || [];
        if (j.status === "queued") {
          const pos = Number(j.queue_position || 0);
          this.ingestMessage = pos > 0 ? `任务排队中，前方还有 ${pos - 1} 个任务` : "任务排队中，等待执行";
        }
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
      this.ingestLoading = true;
      this.ingestMessage = "";
      this.ingestProgress = 0;
      this.ingestLog = [];
      let maxImages = parseInt(this.ingestDriveImageMaxItems, 10);
      if (!Number.isFinite(maxImages) || maxImages <= 0) maxImages = 1200;
      if (maxImages > 8000) maxImages = 8000;
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
      this.ingestMessage = "Google Drive 图片分析任务已提交，正在排队/执行…";
      const job = await this.waitForJob(this.ingestJobId, (j) => {
        this.ingestProgress = j.progress || 0;
        this.ingestLog = j.log || [];
        if (j.status === "queued") {
          const pos = Number(j.queue_position || 0);
          this.ingestMessage = pos > 0 ? `任务排队中，前方还有 ${pos - 1} 个任务` : "任务排队中，等待执行";
        }
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
      this.ingestLoading = true;
      this.ingestMessage = "";
      this.ingestProgress = 0;
      this.ingestLog = [];
      let maxVideos = parseInt(this.ingestDriveMaxVideos, 10);
      if (!Number.isFinite(maxVideos) || maxVideos <= 0) maxVideos = 500;
      if (maxVideos > 5000) maxVideos = 5000;
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
      this.ingestMessage = "Google Drive 分析任务已提交，正在排队/执行…";
      const job = await this.waitForJob(this.ingestJobId, (j) => {
        this.ingestProgress = j.progress || 0;
        this.ingestLog = j.log || [];
        if (j.status === "queued") {
          const pos = Number(j.queue_position || 0);
          this.ingestMessage = pos > 0 ? `任务排队中，前方还有 ${pos - 1} 个任务` : "任务排队中，等待执行";
        }
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
    };
  };
})(window);
