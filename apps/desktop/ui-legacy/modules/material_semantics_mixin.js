(function (global) {
  const ns = (global.VideoEditorModules = global.VideoEditorModules || {});

  ns.createMaterialSemanticsMixin = function createMaterialSemanticsMixin() {
    return {
      async loadMaterials() {
        const data = await this.api("GET", "/api/materials");
        this.materials = data || {};
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
    };
  };
}(window));
