(function (global) {
  const ns = (global.VideoEditorModules = global.VideoEditorModules || {});

  ns.createDistributionAudioMixin = function createDistributionAudioMixin() {
    return {
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
        this.capabilityMessage = "社媒导出任务已提交，正在排队/执行…";

        const job = await this.waitForJob(this.socialExportJobId, (j) => {
          this.socialExportProgress = j.progress || 0;
          this.socialExportLog = j.log || [];
          if (j.status === "queued") {
            const pos = Number(j.queue_position || 0);
            this.capabilityMessage = pos > 0 ? `社媒导出排队中，前方还有 ${pos - 1} 个任务` : "社媒导出排队中";
          }
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
        this.capabilityMessage = `已提交批次复跑：${batchId}`;

        const job = await this.waitForJob(this.socialExportJobId, (j) => {
          this.socialExportProgress = j.progress || 0;
          this.socialExportLog = j.log || [];
          if (j.status === "queued") {
            const pos = Number(j.queue_position || 0);
            this.capabilityMessage = pos > 0 ? `批次复跑排队中，前方还有 ${pos - 1} 个任务` : "批次复跑排队中";
          }
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
        this.capabilityMessage = "音频流水线任务已提交，正在排队/执行…";

        const job = await this.waitForJob(this.audioPipelineJobId, (j) => {
          this.audioPipelineProgress = j.progress || 0;
          if (j.status === "queued") {
            const pos = Number(j.queue_position || 0);
            this.capabilityMessage = pos > 0 ? `音频流水线排队中，前方还有 ${pos - 1} 个任务` : "音频流水线排队中";
          }
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
    };
  };
}(window));
