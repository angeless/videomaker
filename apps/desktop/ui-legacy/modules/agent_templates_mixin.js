(function (global) {
  const ns = (global.VideoEditorModules = global.VideoEditorModules || {});

  ns.createAgentTemplatesMixin = function createAgentTemplatesMixin() {
    return {
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
    };
  };
}(window));
