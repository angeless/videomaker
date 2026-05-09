"""Core library mixin for GlobalMediaLibrary.

Extracted from global_media_library.py — contains asset analysis (semantic
bundle, LLM tagging, vision enrichment), search (hybrid rank, tag recall,
FTS, vector search), and ingestion (video/image file processing, thumbnail
generation, local path discovery).

This is the largest extracted mixin, containing the interconnected core
logic that powers the library's semantic analysis and search capabilities.
"""

from __future__ import annotations

import base64
import hashlib
import importlib
import json
import logging
import os
import re
import sqlite3
import time
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import parse_qs, urlparse

try:
    import numpy as np
except Exception:
    np = None

try:
    import cv2
except Exception:
    cv2 = None

try:
    from modules.step1_material_analysis.video_asset_toolkit import VideoAssetToolkit
except Exception:
    VideoAssetToolkit = None

try:
    from modules.step1_material_analysis.indexer.fingerprint import VideoHasher
except Exception:
    VideoHasher = None

try:
    from modules.step1_material_analysis.usability_scorer import score_asset as _score_asset
except ImportError:
    _score_asset = None

from modules.library._constants import *  # noqa: F403
from modules.library._constants import (  # noqa: F401
    _KIND_TO_SLOT, _TOPCATEGORY_TO_CODE, _TAG_CATEGORY_TO_SLOT,
    _FIELD_TO_SLOT, _SEED_DATA_DIR,
)

_gml_logger = logging.getLogger("modules.library.global_media_library")
logger = logging.getLogger(__name__)


class CoreMixin:
    """Core library methods: analysis, search, ingestion, thumbnails."""

    @staticmethod
    def _is_video_file(path: Path) -> bool:
        return path.suffix.lower() in VIDEO_EXTENSIONS

    @staticmethod
    def _is_image_file(path: Path) -> bool:
        return path.suffix.lower() in IMAGE_EXTENSIONS

    @staticmethod
    def _infer_asset_kind(filename: Optional[str], path_text: Optional[str]) -> str:
        raw = str(path_text or filename or "").strip()
        suffix = Path(raw).suffix.lower()
        if suffix in VIDEO_EXTENSIONS:
            return "video"
        if suffix in IMAGE_EXTENSIONS:
            return "image"
        return "unknown"

    @staticmethod
    def _normalize_media_type(media_type: Optional[str]) -> str:
        m = str(media_type or "").strip().lower()
        if m in {"video", "videos"}:
            return "video"
        if m in {"image", "images", "photo", "photos", "picture", "pictures"}:
            return "image"
        return "all"

    @staticmethod
    def _media_type_where_sql(media_type: str, alias: str = "") -> str:
        m = CoreMixin._normalize_media_type(media_type)
        if m == "all":
            return ""
        col = f"{alias}.filename" if alias else "filename"
        if m == "video":
            exts = sorted(VIDEO_EXTENSIONS)
        else:
            exts = sorted(IMAGE_EXTENSIONS)
        return "(" + " OR ".join([f"lower({col}) GLOB '*{ext}'" for ext in exts]) + ")"

    @staticmethod
    def _run_with_retry(fn, attempts: int = 3, base_delay: float = 1.5):
        last_error = None
        for i in range(attempts):
            try:
                return fn()
            except Exception as exc:
                last_error = exc
                if i >= attempts - 1:
                    raise
                time.sleep(base_delay * (2 ** i))
        if last_error is not None:
            raise last_error
        return None

    def _discover_videos(self, input_path: Path) -> List[Path]:
        if input_path.is_file() and self._is_video_file(input_path):
            return [input_path]
        if input_path.is_dir():
            return sorted(
                p for p in input_path.rglob("*")
                if p.is_file() and self._is_video_file(p)
            )
        return []

    def _discover_images(self, input_path: Path) -> List[Path]:
        if input_path.is_file() and self._is_image_file(input_path):
            return [input_path]
        if input_path.is_dir():
            return sorted(
                p for p in input_path.rglob("*")
                if p.is_file() and self._is_image_file(p)
            )
        return []

    # Public adapter surface for app_api; do not call private helpers跨模块。
    def discover_videos(self, input_path: Path) -> List[Path]:
        return self._discover_videos(input_path)

    def discover_images(self, input_path: Path) -> List[Path]:
        return self._discover_images(input_path)

    # _compute_sha256 → FingerprintMixin

    @staticmethod
    def _parse_fps(raw) -> Optional[float]:
        if raw is None:
            return None
        s = str(raw).strip()
        if not s:
            return None
        if "/" in s:
            num, den = s.split("/", 1)
            try:
                den_f = float(den)
                if den_f == 0:
                    return None
                return float(num) / den_f
            except Exception:
                return None
        try:
            return float(s)
        except Exception:
            return None

    @staticmethod
    def _parse_resolution(resolution: Optional[str]) -> tuple[Optional[int], Optional[int]]:
        if not resolution or "x" not in str(resolution):
            return None, None
        try:
            w, h = str(resolution).lower().split("x", 1)
            return int(w), int(h)
        except Exception:
            return None, None

    # _compute_phash, _compute_image_phash → FingerprintMixin

    # _phash_distance, FINGERPRINT_VERSION → FingerprintMixin

    # _compute_content_fingerprint, _compute_thumbnail_hash → FingerprintMixin

    def _toolkit_instance(self) -> VideoAssetToolkit:
        if self._toolkit is None:
            self._toolkit = VideoAssetToolkit()
        return self._toolkit

    @staticmethod
    def _vision_enrich_enabled() -> bool:
        if str(os.environ.get("VIDEOEDITOR_DISABLE_VISION_ENRICH", "")).strip() == "1":
            return False
        return bool(str(os.environ.get("OPENAI_API_KEY", "")).strip())

    @staticmethod
    def _llm_tagging_enabled() -> bool:
        if str(os.environ.get("VIDEOEDITOR_DISABLE_SEMANTIC_LLM", "")).strip() == "1":
            return False
        return bool(str(os.environ.get("OPENAI_API_KEY", "")).strip())

    @staticmethod
    def _classify_provider(model_version: Any) -> str:
        """Classify a model_version string into a stable provider tag.

        v0.19 Wave 1 Task L6 (dev-plan-v0.19.0.md). M1 (badge UI) reads
        `_meta.provider` to render provider-specific styling. Wave 2 (L2)
        populates real Claude/LLaVA model_versions; this classifier
        already routes them correctly so the field shape is stable.

        Returns one of: ``heuristic`` | ``openai`` | ``claude`` | ``llava`` |
        ``unknown``.
        """
        if not isinstance(model_version, str):
            return "unknown"
        s = model_version.strip().lower()
        if not s:
            return "unknown"
        if s.startswith("heuristic"):
            return "heuristic"
        if s.startswith("gpt-") or s.startswith("openai/") or s.startswith("openai-"):
            return "openai"
        if s.startswith("claude") or s.startswith("anthropic/") or s.startswith("anthropic-"):
            return "claude"
        if "llava" in s:
            return "llava"
        return "unknown"

    @staticmethod
    def _llm_tagging_status() -> Dict[str, Any]:
        """Status for LLM-powered semantic tagging — drives M2 banner UI.

        v0.19 Wave 1 Task M2 (dev-plan-v0.19.0.md). Detects whether **any**
        provider key is configured (OpenAI or Anthropic) so the banner can
        guide users to Settings before they discover degraded tags.

        Note: this method is a *detection helper* for UI; it does NOT change
        the gate semantics of `_llm_tagging_enabled()` (which still routes
        through OpenAI only — that flip happens in L1, Wave 2).

        Returns:
            {enabled, reason, message, providers}
            reason ∈ {"ready", "missing_api_key", "disabled"}
        """
        has_openai = bool(str(os.environ.get("OPENAI_API_KEY", "")).strip())
        has_anthropic = bool(str(os.environ.get("ANTHROPIC_API_KEY", "")).strip())
        providers = {"openai": has_openai, "anthropic": has_anthropic}

        if str(os.environ.get("VIDEOEDITOR_DISABLE_SEMANTIC_LLM", "")).strip() == "1":
            return {
                "enabled": False,
                "reason": "disabled",
                "message": "AI 标签已通过 VIDEOEDITOR_DISABLE_SEMANTIC_LLM 显式禁用",
                "providers": providers,
            }

        if not (has_openai or has_anthropic):
            return {
                "enabled": False,
                "reason": "missing_api_key",
                "message": "未配置 OpenAI 或 Anthropic API Key — 素材标签将退回到颜色规则推断",
                "providers": providers,
            }

        return {
            "enabled": True,
            "reason": "ready",
            "message": "AI 标签已就绪",
            "providers": providers,
        }

    # ------------------------------------------------------------------
    # Thumbnail generation

    def _thumbnail_dir(self) -> Path:
        return self.db_path.parent / "thumbnails"

    def thumbnail_path(self, uid: str) -> Optional[str]:
        """Return the absolute path to a thumbnail if it exists, else None."""
        if not uid:
            return None
        p = self._thumbnail_dir() / uid[:2] / f"{uid}.jpg"
        return str(p) if p.exists() else None

    def _generate_thumbnail(self, uid: str, file_path: Path, asset_kind: str = "video") -> bool:
        """Generate a 320px JPEG thumbnail for an asset. Returns True on success."""
        if cv2 is None:
            return False
        try:
            thumb_dir = self._thumbnail_dir() / uid[:2]
            thumb_dir.mkdir(parents=True, exist_ok=True)
            out_path = thumb_dir / f"{uid}.jpg"
            if out_path.exists():
                return True

            frame = None
            if asset_kind == "image" or self._is_image_file(file_path):
                frame = cv2.imread(str(file_path))
            else:
                cap = cv2.VideoCapture(str(file_path))
                if not cap.isOpened():
                    cap.release()
                    return False
                try:
                    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                    target = int(max(total - 1, 0) * 0.35) if total > 0 else 0
                    cap.set(cv2.CAP_PROP_POS_FRAMES, target)
                    ok, frame = cap.read()
                    if not ok or frame is None:
                        return False
                finally:
                    cap.release()

            if frame is None:
                return False
            h, w = frame.shape[:2]
            if max(h, w) > 320:
                scale = 320.0 / max(h, w)
                frame = cv2.resize(frame, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
            cv2.imwrite(str(out_path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 80])
            return out_path.exists()
        except Exception:
            return False

    def generate_missing_thumbnails(self, progress_cb=None) -> Dict[str, int]:
        """Generate thumbnails for all assets that don't have one yet."""
        stats = {"generated": 0, "skipped": 0, "failed": 0}
        with self._connect() as conn:
            rows = conn.execute("SELECT uid, primary_path, filename FROM assets").fetchall()
        for i, row in enumerate(rows):
            uid = row["uid"]
            if self.thumbnail_path(uid):
                stats["skipped"] += 1
                continue
            fpath = Path(row["primary_path"] or "")
            if not fpath.exists():
                stats["failed"] += 1
                continue
            kind = self._infer_asset_kind(row["filename"], str(fpath))
            if self._generate_thumbnail(uid, fpath, kind):
                stats["generated"] += 1
            else:
                stats["failed"] += 1
            if progress_cb and len(rows) > 0:
                progress_cb(int((i + 1) * 100 / len(rows)))
        return stats

    # ------------------------------------------------------------------
    # Keyframe extraction (data URLs for LLM vision)

    @staticmethod
    def _extract_keyframe_data_urls(
        path: Path,
        ratios: Optional[List[float]] = None,
        jpeg_quality: int = 82,
    ) -> List[str]:
        if self._is_image_file(path):
            img_url = self._extract_image_data_url(path, jpeg_quality=jpeg_quality)
            return [img_url] if img_url else []
        if cv2 is None:
            return []
        ratios = ratios or [0.12, 0.42, 0.75]
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            cap.release()
            return []
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        frame_indexes = []
        if total <= 0:
            frame_indexes = [0]
        else:
            for r in ratios:
                try:
                    idx = int(max(0.0, min(1.0, float(r))) * max(total - 1, 0))
                except Exception:
                    idx = 0
                frame_indexes.append(idx)
        dedup_indexes = []
        seen = set()
        for idx in frame_indexes:
            if idx in seen:
                continue
            seen.add(idx)
            dedup_indexes.append(idx)

        out: List[str] = []
        try:
            for frame_idx in dedup_indexes:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                ok, encoded = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
                if not ok:
                    continue
                b64 = base64.b64encode(encoded.tobytes()).decode("ascii")
                out.append(f"data:image/jpeg;base64,{b64}")
        finally:
            cap.release()
        return out

    @staticmethod
    def _extract_keyframe_data_url(path: Path) -> Optional[str]:
        urls = CoreMixin._extract_keyframe_data_urls(path, ratios=[0.35], jpeg_quality=82)
        return urls[0] if urls else None

    @staticmethod
    def _extract_image_data_url(path: Path, jpeg_quality: int = 86) -> Optional[str]:
        if cv2 is None:
            return None
        img = cv2.imread(str(path))
        if img is None:
            return None
        ok, encoded = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), jpeg_quality])
        if not ok:
            return None
        b64 = base64.b64encode(encoded.tobytes()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"

    def _vision_enrich_tags(self, path: Path) -> Dict:
        if not self._vision_enrich_enabled():
            return {}
        data_url = self._extract_keyframe_data_url(path)
        if not data_url:
            return {}
        try:
            import openai
            client = openai.OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
            model = os.environ.get("OPENAI_VISION_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"
            prompt = (
                "你是素材语义标注器（图片/视频均可）。请识别画面里的建筑类型、地标线索、桥梁类型和场景要素。"
                "只返回 JSON，不要解释。格式："
                "{\"scene\":\"\",\"keywords\":[],\"landmarks\":[],\"architecture_style\":[]}"
                "关键词尽量中英混合，最多12个。"
            )
            rsp = client.chat.completions.create(
                model=model,
                max_tokens=280,
                temperature=0.1,
                messages=[
                    {"role": "system", "content": "你是严格 JSON 输出助手。"},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url, "detail": "low"}},
                        ],
                    },
                ],
            )
            raw = (rsp.choices[0].message.content or "").strip()
            if not raw:
                return {}
            raw = raw.strip("` \n")
            if raw.startswith("json"):
                raw = raw[4:].strip()
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                return {}
            return parsed
        except Exception:
            return {}

    @staticmethod
    def _safe_json_loads(raw: Optional[str], default):
        if not raw:
            return default
        try:
            return json.loads(raw)
        except Exception:
            return default

    @staticmethod
    def _empty_structured_tag_schema() -> Dict[str, Any]:
        return {
            "tags": {
                cat: {"zh": [], "en": [], "confidence": 0.0}
                for cat in TAG_TAXONOMY
            },
            "quality_checks": {
                "generic_terms_removed": True,
                "duplicate_terms_removed": True,
                "covers_literal_and_abstract": False,
                "search_ready": False,
            },
        }

    @staticmethod
    def _seed_concept_library() -> Dict[str, List[tuple[str, str]]]:
        return {
            "concepts": [
                ("生活方式", "lifestyle"), ("自由", "freedom"), ("成就", "achievement"),
                ("自律", "discipline"), ("松弛感", "relaxed vibe"), ("治愈", "healing"),
                ("孤独", "loneliness"), ("连接", "connection"), ("成长", "growth"),
                ("焦虑", "anxiety"), ("逃离", "escape"), ("仪式感", "ritual"),
                ("高效", "productivity"), ("极简", "minimalism"), ("都市感", "urban"),
                ("自然疗愈", "nature therapy"), ("数字游民", "digital nomad"),
                ("远程工作", "remote work"), ("探索", "exploration"), ("归属感", "belonging"),
                ("亲密", "intimacy"), ("健康", "wellness"), ("怀旧", "nostalgia"),
                ("创造力", "creativity"), ("可持续", "sustainability"), ("平衡", "balance"),
            ],
            "use_cases": [
                ("旅行vlog", "travel vlog"), ("城市宣传", "city promo"),
                ("酒店民宿", "hotel/airbnb"), ("咖啡品牌", "coffee brand"),
                ("健身瑜伽", "fitness/yoga"), ("心理疗愈", "mental health"),
                ("创业职场", "startup/career"), ("纪录片", "doc style"),
                ("广告片", "commercial"), ("社媒短视频", "social short"),
                ("教育培训", "education"), ("产品评测", "product review"),
                ("婚礼活动", "wedding"), ("音乐MV", "music video"),
                ("房产展示", "real estate"), ("企业宣传", "corporate"),
            ],
            "mood": [
                ("治愈", "healing"), ("宁静", "calm"), ("活力", "energetic"),
                ("史诗感", "epic"), ("孤独", "lonely"), ("温暖", "warm"),
                ("紧张", "tense"), ("轻松", "relaxed"), ("忧郁", "melancholic"),
                ("欢快", "joyful"), ("神秘", "mysterious"), ("浪漫", "romantic"),
                ("庄严", "solemn"), ("激昂", "passionate"), ("慵懒", "lazy"),
            ],
            "style": [
                ("电影感", "cinematic"), ("纪实", "documentary"), ("vlog", "vlog"),
                ("广告感", "commercial style"), ("手持纪实", "handheld doc"),
                ("航拍", "aerial"), ("夜景氛围", "night aesthetic"), ("极简", "minimal"),
                ("复古", "retro"), ("赛博朋克", "cyberpunk"), ("水墨风", "ink wash"),
                ("胶片感", "film grain"), ("高饱和", "high saturation"),
                ("低饱和", "desaturated"), ("延时", "timelapse"),
            ],
            "objects": [
                ("建筑", "building"), ("桥梁", "bridge"), ("植物", "plant"),
                ("花朵", "flower"), ("手机", "phone"), ("电脑", "computer"),
                ("书籍", "book"), ("灯光", "light"), ("镜子", "mirror"),
                ("窗户", "window"), ("门", "door"), ("杯子", "cup"),
                ("家具", "furniture"), ("乐器", "instrument"), ("画作", "painting"),
            ],
            "actions": [
                ("行走", "walking"), ("奔跑", "running"), ("跳跃", "jumping"),
                ("游泳", "swimming"), ("骑行", "cycling"), ("烹饪", "cooking"),
                ("阅读", "reading"), ("写作", "writing"), ("舞蹈", "dancing"),
                ("拍照", "photographing"), ("交谈", "chatting"), ("拥抱", "hugging"),
                ("冥想", "meditating"), ("攀登", "climbing"), ("驾驶", "driving"),
            ],
            "scene": [
                ("街道", "street"), ("咖啡馆", "cafe"), ("图书馆", "library"),
                ("公园", "park"), ("海边", "seaside"), ("山顶", "summit"),
                ("市集", "market"), ("车站", "station"), ("机场", "airport"),
                ("教室", "classroom"), ("办公室", "office"), ("厨房", "kitchen"),
                ("卧室", "bedroom"), ("阳台", "balcony"), ("屋顶", "rooftop"),
            ],
            "materials_textures": [
                ("木质", "wood"), ("金属", "metal"), ("玻璃", "glass"),
                ("石材", "stone"), ("混凝土", "concrete"), ("皮革", "leather"),
                ("丝绸", "silk"), ("棉麻", "linen"), ("陶瓷", "ceramic"),
                ("竹子", "bamboo"), ("纸张", "paper"), ("砖块", "brick"),
                ("大理石", "marble"), ("铁锈", "rust"), ("毛绒", "plush"),
            ],
            "architecture_style": [
                ("哥特式", "gothic"), ("巴洛克", "baroque"), ("现代主义", "modernist"),
                ("中式传统", "chinese traditional"), ("日式和风", "japanese style"),
                ("地中海", "mediterranean"), ("工业风", "industrial"),
                ("包豪斯", "bauhaus"), ("新古典", "neoclassical"),
                ("后现代", "postmodern"), ("装饰艺术", "art deco"),
                ("极简建筑", "minimalist architecture"),
            ],
            "food_cuisine": [
                ("中餐", "chinese food"), ("日料", "japanese food"),
                ("西餐", "western food"), ("甜点", "dessert"), ("咖啡", "coffee"),
                ("茶", "tea"), ("鸡尾酒", "cocktail"), ("烧烤", "barbecue"),
                ("面包", "bread"), ("沙拉", "salad"), ("火锅", "hotpot"),
                ("寿司", "sushi"), ("披萨", "pizza"), ("冰淇淋", "ice cream"),
            ],
            "animal_species": [
                ("猫", "cat"), ("狗", "dog"), ("鸟类", "bird"),
                ("鱼类", "fish"), ("蝴蝶", "butterfly"), ("马", "horse"),
                ("海豚", "dolphin"), ("鹿", "deer"), ("兔子", "rabbit"),
                ("松鼠", "squirrel"), ("海鸥", "seagull"), ("蜜蜂", "bee"),
            ],
            "vehicle_transport": [
                ("汽车", "car"), ("自行车", "bicycle"), ("摩托车", "motorcycle"),
                ("火车", "train"), ("飞机", "airplane"), ("船", "boat"),
                ("电车", "tram"), ("缆车", "cable car"), ("帆船", "sailboat"),
                ("滑板", "skateboard"),
            ],
            "clothing_fashion": [
                ("西装", "suit"), ("连衣裙", "dress"), ("运动装", "sportswear"),
                ("汉服", "hanfu"), ("和服", "kimono"), ("牛仔", "denim"),
                ("配饰", "accessories"), ("帽子", "hat"), ("围巾", "scarf"),
                ("运动鞋", "sneakers"),
            ],
            "body_language": [
                ("微笑", "smiling"), ("思考", "thinking"), ("指向", "pointing"),
                ("鼓掌", "clapping"), ("挥手", "waving"), ("叉腰", "hands on hips"),
                ("俯身", "leaning"), ("仰望", "looking up"), ("低头", "head down"),
                ("双臂交叉", "arms crossed"),
            ],
            "spatial_relations": [
                ("前景", "foreground"), ("背景", "background"), ("左侧", "left side"),
                ("右侧", "right side"), ("中心", "center"), ("边缘", "edge"),
                ("对称", "symmetry"), ("引导线", "leading line"),
            ],
            "cultural_elements": [
                ("节日", "festival"), ("传统", "tradition"), ("宗教", "religion"),
                ("民俗", "folklore"), ("书法", "calligraphy"), ("手工艺", "craft"),
                ("庙会", "temple fair"), ("婚俗", "wedding customs"),
                ("茶道", "tea ceremony"), ("花道", "ikebana"),
                ("舞龙", "dragon dance"), ("灯笼", "lantern"),
            ],
            "brand_product": [
                ("科技产品", "tech product"), ("美妆", "beauty/cosmetics"),
                ("时装", "fashion brand"), ("运动品牌", "sports brand"),
                ("家居", "home brand"), ("汽车品牌", "auto brand"),
                ("奢侈品", "luxury"), ("快消品", "FMCG"),
                ("母婴", "baby/maternity"), ("宠物用品", "pet products"),
            ],
            "audio_mood": [
                ("轻音乐", "light music"), ("电子乐", "electronic"),
                ("古典", "classical"), ("爵士", "jazz"), ("环境音", "ambient"),
                ("节奏感", "rhythmic"), ("人声清唱", "a cappella"),
                ("自然声", "nature sounds"), ("白噪音", "white noise"),
            ],
            "color_palette": [
                ("暖色调", "warm tones"), ("冷色调", "cool tones"),
                ("莫兰迪", "morandi"), ("撞色", "color blocking"),
                ("黑白", "monochrome"), ("渐变", "gradient"),
                ("高对比", "high contrast"), ("柔和", "soft palette"),
                ("金色", "golden"), ("蓝调", "blue tones"),
            ],
            "composition": [
                ("三分法", "rule of thirds"), ("居中", "centered"),
                ("对角线", "diagonal"), ("框中框", "frame within frame"),
                ("留白", "negative space"), ("黄金螺旋", "golden spiral"),
                ("俯拍", "overhead"), ("仰拍", "low angle"),
            ],
            "nature_landscape": [
                ("山脉", "mountains"), ("湖泊", "lake"), ("河流", "river"),
                ("瀑布", "waterfall"), ("沙漠", "desert"), ("草原", "grassland"),
                ("冰川", "glacier"), ("珊瑚礁", "coral reef"), ("峡谷", "canyon"),
                ("火山", "volcano"), ("湿地", "wetland"), ("洞穴", "cave"),
            ],
            "weather_atmosphere": [
                ("晴天", "sunny"), ("多云", "cloudy"), ("雨天", "rainy"),
                ("雪天", "snowy"), ("雾", "foggy"), ("彩虹", "rainbow"),
                ("暴风雨", "storm"), ("星空", "starry"), ("极光", "aurora"),
            ],
            "social_context": [
                ("独处", "solitude"), ("约会", "date"), ("家庭", "family"),
                ("朋友聚会", "friends gathering"), ("团队", "team"),
                ("派对", "party"), ("会议", "meeting"), ("社区", "community"),
                ("仪式", "ceremony"), ("游行", "parade"),
            ],
            "industry_domain": [
                ("科技", "technology"), ("医疗", "healthcare"), ("教育", "education"),
                ("金融", "finance"), ("零售", "retail"), ("餐饮", "food service"),
                ("房地产", "real estate"), ("旅游", "tourism"),
                ("制造业", "manufacturing"), ("创意产业", "creative industry"),
                ("体育", "sports"), ("娱乐", "entertainment"),
            ],
            "narrative_technique": [
                ("蒙太奇", "montage"), ("平行叙事", "parallel narrative"),
                ("倒叙", "flashback"), ("悬念", "suspense"),
                ("象征", "symbolism"), ("隐喻", "metaphor"),
                ("对比", "contrast"), ("重复", "repetition"),
            ],
        }

    @staticmethod
    def _bilingual_term_map() -> Dict[str, str]:
        pairs = [
            # landmark / place
            ("教堂", "church"), ("大教堂", "cathedral"), ("礼拜堂", "chapel"),
            ("桥梁", "bridge"), ("铁桥", "iron bridge"), ("钢桥", "steel bridge"),
            ("城堡", "castle"), ("寺庙", "temple"), ("修道院", "monastery"),
            ("建筑", "architecture"), ("地标", "landmark"), ("城市", "city"),
            ("街道", "street"), ("山地", "mountain"), ("海边", "beach"),
            ("森林", "forest"), ("树木", "tree"), ("自然", "nature"),
            ("风景", "landscape"), ("天空", "sky"), ("水域", "water"),
            ("雪景", "snow"), ("日落", "sunset"), ("夜景", "night"),
            ("咖啡馆", "cafe"), ("公园", "park"), ("广场", "plaza"),
            ("屋顶", "rooftop"), ("小巷", "alley"), ("市中心", "downtown"),
            ("天际线", "skyline"), ("老城区", "old town"),
            # camera / style
            ("航拍", "aerial"), ("手持", "handheld"), ("固定机位", "static"),
            ("特写", "close-up"), ("远景", "wide shot"), ("延时", "timelapse"),
            ("复古", "retro"), ("赛博朋克", "cyberpunk"), ("胶片感", "film grain"),
            ("水墨风", "ink wash"), ("高饱和", "high saturation"), ("低饱和", "desaturated"),
            # mood / concept
            ("治愈", "healing"), ("松弛感", "relaxed vibe"), ("探索", "exploration"),
            ("怀旧", "nostalgia"), ("创造力", "creativity"), ("可持续", "sustainability"),
            ("平衡", "balance"), ("忧郁", "melancholic"), ("欢快", "joyful"),
            ("神秘", "mysterious"), ("浪漫", "romantic"), ("庄严", "solemn"),
            ("激昂", "passionate"), ("慵懒", "lazy"),
            # use case
            ("旅行vlog", "travel vlog"), ("旅行vlog", "travel_vlog"),
            ("城市宣传", "city promo"), ("纪录片", "doc style"),
            ("广告片", "commercial"), ("教育培训", "education"),
            ("产品评测", "product review"), ("婚礼活动", "wedding"),
            ("音乐MV", "music video"), ("房产展示", "real estate"),
            ("企业宣传", "corporate"), ("社媒短视频", "social short"),
            # action
            ("动作混剪", "action_montage"), ("地标故事", "landmark_story"),
            ("氛围空镜", "atmospheric_broll"), ("主镜头", "hero_shot"),
            ("叙事镜头", "storytelling_clip"), ("人物", "person"),
            ("人群", "people"), ("车辆", "vehicle"), ("活动", "activity"),
            ("室外", "outdoor"), ("室内", "indoor"),
            ("行走", "walking"), ("奔跑", "running"), ("跳跃", "jumping"),
            ("游泳", "swimming"), ("骑行", "cycling"), ("烹饪", "cooking"),
            ("阅读", "reading"), ("写作", "writing"), ("舞蹈", "dancing"),
            ("拍照", "photographing"), ("交谈", "chatting"), ("拥抱", "hugging"),
            ("冥想", "meditating"), ("攀登", "climbing"), ("驾驶", "driving"),
            # material
            ("木质", "wood"), ("金属", "metal"), ("玻璃", "glass"),
            ("石材", "stone"), ("混凝土", "concrete"), ("皮革", "leather"),
            ("丝绸", "silk"), ("棉麻", "linen"), ("陶瓷", "ceramic"),
            ("竹子", "bamboo"), ("纸张", "paper"), ("砖块", "brick"),
            ("大理石", "marble"), ("铁锈", "rust"), ("毛绒", "plush"),
            # architecture
            ("哥特式", "gothic"), ("巴洛克", "baroque"), ("现代主义", "modernist"),
            ("中式传统", "chinese traditional"), ("日式和风", "japanese style"),
            ("地中海", "mediterranean"), ("工业风", "industrial"),
            ("包豪斯", "bauhaus"), ("新古典", "neoclassical"),
            ("后现代", "postmodern"), ("装饰艺术", "art deco"),
            # food
            ("中餐", "chinese food"), ("日料", "japanese food"),
            ("西餐", "western food"), ("甜点", "dessert"), ("咖啡", "coffee"),
            ("茶", "tea"), ("鸡尾酒", "cocktail"), ("烧烤", "barbecue"),
            ("面包", "bread"), ("沙拉", "salad"), ("火锅", "hotpot"),
            ("寿司", "sushi"), ("披萨", "pizza"), ("冰淇淋", "ice cream"),
            # animal
            ("猫", "cat"), ("狗", "dog"), ("鸟类", "bird"),
            ("鱼类", "fish"), ("蝴蝶", "butterfly"), ("马", "horse"),
            ("海豚", "dolphin"), ("鹿", "deer"), ("兔子", "rabbit"),
            ("海鸥", "seagull"), ("蜜蜂", "bee"), ("松鼠", "squirrel"),
            # vehicle
            ("汽车", "car"), ("自行车", "bicycle"), ("摩托车", "motorcycle"),
            ("火车", "train"), ("飞机", "airplane"), ("船", "boat"),
            ("电车", "tram"), ("缆车", "cable car"), ("帆船", "sailboat"),
            ("滑板", "skateboard"),
            # clothing
            ("西装", "suit"), ("连衣裙", "dress"), ("运动装", "sportswear"),
            ("汉服", "hanfu"), ("和服", "kimono"), ("牛仔", "denim"),
            ("配饰", "accessories"), ("帽子", "hat"), ("围巾", "scarf"),
            ("运动鞋", "sneakers"),
            # body language
            ("微笑", "smiling"), ("思考", "thinking"), ("指向", "pointing"),
            ("鼓掌", "clapping"), ("挥手", "waving"), ("叉腰", "hands on hips"),
            ("俯身", "leaning"), ("仰望", "looking up"), ("低头", "head down"),
            ("双臂交叉", "arms crossed"),
            # cultural
            ("节日", "festival"), ("传统", "tradition"), ("宗教", "religion"),
            ("民俗", "folklore"), ("书法", "calligraphy"), ("手工艺", "craft"),
            ("庙会", "temple fair"), ("婚俗", "wedding customs"),
            ("茶道", "tea ceremony"), ("花道", "ikebana"),
            ("舞龙", "dragon dance"), ("灯笼", "lantern"),
            # brand / product
            ("科技产品", "tech product"), ("美妆", "beauty/cosmetics"),
            ("时装", "fashion brand"), ("运动品牌", "sports brand"),
            ("家居", "home brand"), ("奢侈品", "luxury"), ("快消品", "FMCG"),
            # audio
            ("轻音乐", "light music"), ("电子乐", "electronic"),
            ("古典", "classical"), ("爵士", "jazz"), ("环境音", "ambient"),
            ("节奏感", "rhythmic"), ("自然声", "nature sounds"),
            # color palette
            ("暖色调", "warm tones"), ("冷色调", "cool tones"),
            ("莫兰迪", "morandi"), ("撞色", "color blocking"),
            ("黑白", "monochrome"), ("渐变", "gradient"),
            ("高对比", "high contrast"), ("柔和", "soft palette"),
            # composition
            ("三分法", "rule of thirds"), ("居中", "centered"),
            ("对角线", "diagonal"), ("框中框", "frame within frame"),
            ("留白", "negative space"), ("黄金螺旋", "golden spiral"),
            ("俯拍", "overhead"), ("仰拍", "low angle"),
            # nature
            ("山脉", "mountains"), ("湖泊", "lake"), ("河流", "river"),
            ("瀑布", "waterfall"), ("沙漠", "desert"), ("草原", "grassland"),
            ("冰川", "glacier"), ("珊瑚礁", "coral reef"), ("峡谷", "canyon"),
            ("火山", "volcano"), ("湿地", "wetland"), ("洞穴", "cave"),
            # weather
            ("晴天", "sunny"), ("多云", "cloudy"), ("雨天", "rainy"),
            ("雪天", "snowy"), ("雾", "foggy"), ("彩虹", "rainbow"),
            ("暴风雨", "storm"), ("星空", "starry"), ("极光", "aurora"),
            # social
            ("独处", "solitude"), ("约会", "date"), ("家庭", "family"),
            ("朋友聚会", "friends gathering"), ("团队", "team"),
            ("派对", "party"), ("会议", "meeting"), ("社区", "community"),
            # industry
            ("科技", "technology"), ("医疗", "healthcare"), ("教育", "education"),
            ("金融", "finance"), ("零售", "retail"), ("餐饮", "food service"),
            ("房地产", "real estate"), ("旅游", "tourism"),
            ("制造业", "manufacturing"), ("创意产业", "creative industry"),
            ("体育", "sports"), ("娱乐", "entertainment"),
            # narrative
            ("蒙太奇", "montage"), ("平行叙事", "parallel narrative"),
            ("倒叙", "flashback"), ("悬念", "suspense"),
            ("象征", "symbolism"), ("隐喻", "metaphor"),
            ("对比", "contrast"), ("重复", "repetition"),
        ]
        for cat_pairs in CoreMixin._seed_concept_library().values():
            pairs.extend(cat_pairs)
        mapping: Dict[str, str] = {}
        for zh, en in pairs:
            zh_key = str(zh).strip().lower()
            en_key = str(en).strip().lower()
            if zh_key and en_key:
                mapping[zh_key] = en
                mapping[en_key] = zh
        return mapping

    @staticmethod
    def _split_terms(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, list):
            out = []
            for item in value:
                out.extend(CoreMixin._split_terms(item))
            return out
        text = str(value).strip()
        if not text:
            return []
        return [x.strip() for x in re.split(r"[\n,，;；|/]+", text) if x.strip()]

    @staticmethod
    def _normalize_terms(items: Iterable[str], lang: str = "en", max_items: int = 18) -> List[str]:
        out = []
        seen = set()
        for item in items:
            text = str(item or "").strip()
            if not text:
                continue
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue
            if lang == "en":
                text = text.lower()
            key = text.lower()
            if key in GENERIC_TAG_TERMS:
                continue
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
            if len(out) >= max_items:
                break
        return out

    @staticmethod
    def _safe_json_object_from_text(raw: Any) -> Dict[str, Any]:
        if isinstance(raw, dict):
            return raw
        text = str(raw or "").strip()
        if not text:
            return {}
        text = text.strip("` \n")
        if text.lower().startswith("json"):
            text = text[4:].strip()
        try:
            parsed = json.loads(text)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            pass
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return {}
        try:
            parsed = json.loads(m.group(0))
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _clamp_confidence(value: Any, default: float = 0.55) -> float:
        try:
            f = float(value)
        except Exception:
            f = default
        if f < 0.0:
            return 0.0
        if f > 1.0:
            return 1.0
        return round(f, 3)

    @staticmethod
    def _seed_expand_terms(category: str, evidence_text: str) -> Dict[str, List[str]]:
        pool = CoreMixin._seed_concept_library().get(category, [])
        if not pool:
            return {"zh": [], "en": []}
        text = str(evidence_text or "").lower()
        pool_dict = {str(zh): str(en) for zh, en in pool}
        zh_terms = []
        en_terms = []
        for zh, en in pool:
            if str(zh).lower() in text or str(en).lower() in text:
                zh_terms.append(zh)
                en_terms.append(en)
        if not zh_terms and category == "concepts":
            if any(k in text for k in ["beach", "ocean", "coast", "forest", "mountain", "nature", "sunset", "疗愈", "自然"]):
                zh_terms.extend(["自然疗愈", "治愈", "探索", "逃离", "松弛感"])
            if any(k in text for k in ["city", "urban", "street", "night", "城市", "街头"]):
                zh_terms.extend(["都市感", "连接", "成长", "归属感"])
            if any(k in text for k in ["person", "people", "vlog", "talk", "人物", "口播"]):
                zh_terms.extend(["生活方式", "连接", "亲密"])
            if any(k in text for k in ["laptop", "cafe", "workspace", "remote", "工作", "咖啡"]):
                zh_terms.extend(["数字游民", "远程工作", "高效"])
            if any(k in text for k in ["sports", "ski", "action", "运动", "滑雪"]):
                zh_terms.extend(["成就", "自律", "探索"])
            for zh in zh_terms[:]:
                en = pool_dict.get(zh)
                if en:
                    en_terms.append(en)
        if not zh_terms and category == "use_cases":
            if any(k in text for k in ["travel", "trip", "journey", "mountain", "beach", "city", "旅行", "地标"]):
                zh_terms.extend(["旅行vlog", "城市宣传", "社媒短视频"])
            if any(k in text for k in ["hotel", "room", "interior", "室内", "民宿"]):
                zh_terms.extend(["酒店民宿", "广告片"])
            if any(k in text for k in ["coffee", "cafe", "咖啡"]):
                zh_terms.extend(["咖啡品牌", "社媒短视频"])
            if any(k in text for k in ["fitness", "yoga", "sports", "健身", "瑜伽"]):
                zh_terms.extend(["健身瑜伽", "社媒短视频"])
            if any(k in text for k in ["documentary", "interview", "history", "church", "cathedral", "纪录"]):
                zh_terms.extend(["纪录片", "城市宣传"])
            if any(k in text for k in ["office", "laptop", "career", "创业", "职场"]):
                zh_terms.extend(["创业职场", "社媒短视频"])
            for zh in zh_terms[:]:
                en = pool_dict.get(zh)
                if en:
                    en_terms.append(en)
        return {"zh": zh_terms, "en": en_terms}

    @staticmethod
    def _openai_client():
        api_key = str(os.environ.get("OPENAI_API_KEY", "")).strip()
        if not api_key:
            return None
        try:
            import openai
        except Exception:
            return None
        kwargs = {"api_key": api_key}
        base_url = str(os.environ.get("OPENAI_BASE_URL", "")).strip()
        if base_url:
            kwargs["base_url"] = base_url
        try:
            return openai.OpenAI(**kwargs)
        except Exception:
            return None

    def _call_openai_json(self, messages: List[Dict[str, Any]], max_tokens: int = 1200, temperature: float = 0.15) -> Dict[str, Any]:
        client = self._openai_client()
        if client is None:
            return {}
        model = (
            str(os.environ.get("OPENAI_MODEL", "")).strip()
            or str(os.environ.get("OPENAI_VISION_MODEL", "")).strip()
            or "gpt-4o-mini"
        )
        try:
            rsp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            content = (rsp.choices[0].message.content or "").strip()
            return self._safe_json_object_from_text(content)
        except Exception:
            return {}

    def _call_openai_text(self, messages: List[Dict[str, Any]], max_tokens: int = 1200, temperature: float = 0.15) -> str:
        client = self._openai_client()
        if client is None:
            return ""
        model = (
            str(os.environ.get("OPENAI_MODEL", "")).strip()
            or str(os.environ.get("OPENAI_VISION_MODEL", "")).strip()
            or "gpt-4o-mini"
        )
        try:
            rsp = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            return str(rsp.choices[0].message.content or "").strip()
        except Exception:
            return ""

    @staticmethod
    def _has_openai_sdk() -> bool:
        try:
            import openai  # noqa: F401
            return True
        except Exception:
            return False

    def _embedding_runtime_status(self) -> Dict[str, Any]:
        has_key = bool(str(os.environ.get("OPENAI_API_KEY", "")).strip())
        has_sdk = self._has_openai_sdk()
        has_numpy = np is not None
        if not has_key:
            return {
                "enabled": False,
                "reason": "missing_api_key",
                "message": "未配置 OpenAI API Key",
            }
        if not has_sdk:
            return {
                "enabled": False,
                "reason": "missing_openai_sdk",
                "message": "未安装 openai SDK",
            }
        if not has_numpy:
            return {
                "enabled": False,
                "reason": "missing_numpy",
                "message": "未安装 numpy",
            }
        return {
            "enabled": True,
            "reason": "ready",
            "message": "向量能力已启用",
        }

    @staticmethod
    def _embedding_model() -> str:
        return (
            str(os.environ.get("OPENAI_EMBEDDING_MODEL", "")).strip()
            or str(os.environ.get("OPENAI_EMBED_MODEL", "")).strip()
            or DEFAULT_EMBEDDING_MODEL
        )

    @staticmethod
    def _embedding_content_hash(content: str) -> str:
        return hashlib.sha256((content or "").strip().encode("utf-8")).hexdigest()

    def _build_embedding_source(
        self,
        filename: Optional[str],
        semantic_text: Optional[str],
        keywords_json: Any,
        semantic_json: Any,
        analysis_json: Any = None,
    ) -> str:
        parts: List[str] = []
        if filename:
            parts.append(str(filename).strip())
        if semantic_text:
            parts.append(str(semantic_text).strip())

        keywords = self._safe_json_loads(keywords_json, [])
        if isinstance(keywords, list) and keywords:
            parts.extend([str(x).strip() for x in keywords if str(x).strip()])

        semantic = semantic_json
        if isinstance(semantic_json, str):
            semantic = self._safe_json_loads(semantic_json, {})
        if isinstance(semantic, dict):
            layers = semantic.get("index_layers", {}) if isinstance(semantic.get("index_layers"), dict) else {}
            core = layers.get("core_search_tags", {}) if isinstance(layers, dict) else {}
            secondary = layers.get("secondary_tags", {}) if isinstance(layers, dict) else {}
            for bucket in (core, secondary):
                if isinstance(bucket, dict):
                    for lang in ("zh", "en"):
                        vals = bucket.get(lang, [])
                        if isinstance(vals, list):
                            parts.extend([str(x).strip() for x in vals if str(x).strip()])

            for key in ("scene_description", "mood", "setting", "time_of_day", "activity", "visual_style"):
                val = semantic.get(key)
                if isinstance(val, str) and val.strip():
                    parts.append(val.strip())
                elif isinstance(val, list):
                    parts.extend([str(x).strip() for x in val if str(x).strip()])

        # R4: Include ASR transcription text from analysis_json
        analysis = analysis_json
        if isinstance(analysis_json, str):
            analysis = self._safe_json_loads(analysis_json, {})
        if isinstance(analysis, dict):
            asr = str(analysis.get("asr_text", "") or "").strip()
            if not asr:
                tx = analysis.get("transcription")
                if isinstance(tx, dict):
                    asr = str(tx.get("text", "") or "").strip()
            if asr:
                # Cap transcription at 2000 chars to preserve room for other signals
                parts.append(asr[:2000])

        compact = " | ".join([p for p in parts if p])
        if len(compact) > 6000:
            compact = compact[:6000]
        return compact

    def _call_openai_embedding(self, text: str) -> List[float]:
        query = str(text or "").strip()
        if not query:
            return []
        client = self._openai_client()
        if client is None:
            return []
        try:
            rsp = client.embeddings.create(
                model=self._embedding_model(),
                input=query,
            )
            data = getattr(rsp, "data", []) or []
            if not data:
                return []
            vec = getattr(data[0], "embedding", None)
            if not isinstance(vec, list):
                return []
            return [float(x) for x in vec]
        except Exception:
            return []

    def _get_query_embedding(self, query: str) -> List[float]:
        q = str(query or "").strip().lower()
        if not q:
            return []
        # Use EmbeddingCache if available, fallback to legacy dict cache
        if hasattr(self, "_embedding_cache") and self._embedding_cache is not None:
            cached_vec = self._embedding_cache.get(q)
            if cached_vec:
                return cached_vec
            vec = self._call_openai_embedding(q)
            if vec:
                self._embedding_cache.put(q, vec)
            return vec
        else:
            # Legacy fallback (should not reach here after integration)
            now_ts = time.time()
            cached = self._query_embedding_cache.get(q)
            if cached and (now_ts - float(cached.get("ts", 0.0))) < 3600:
                vec_c = cached.get("vec")
                if isinstance(vec_c, list) and vec_c:
                    return vec_c
            vec = self._call_openai_embedding(q)
            if vec:
                self._query_embedding_cache[q] = {"ts": now_ts, "vec": vec}
                if len(self._query_embedding_cache) > 128:
                    oldest = sorted(
                        self._query_embedding_cache.items(),
                        key=lambda kv: float(kv[1].get("ts", 0.0))
                    )[:32]
                    for k, _ in oldest:
                        self._query_embedding_cache.pop(k, None)
            return vec

    def _invalidate_vector_cache(self):
        self._vector_cache = {
            "model": "",
            "updated_at": "",
            "uids": [],
            "matrix": None,
        }
        # Also reset VectorIndex if present
        if hasattr(self, "_vector_index") and self._vector_index is not None:
            self._vector_index._reset()

    def _refresh_vector_cache(self, conn: sqlite3.Connection, model: str):
        if np is None:
            return

        meta = conn.execute(
            """
            SELECT COUNT(*) AS cnt, COALESCE(MAX(updated_at), '') AS max_updated
            FROM asset_embeddings
            WHERE model = ? AND embedding_version = ?
            """,
            (model, EMBEDDING_SCHEMA_VERSION),
        ).fetchone()
        cnt = int(meta["cnt"] or 0)
        max_updated = str(meta["max_updated"] or "")
        cached = self._vector_cache
        if (
            cached.get("model") == model
            and cached.get("updated_at") == max_updated
            and cached.get("uids_count", 0) == cnt
            and self._vector_index is not None
            and self._vector_index.count == cnt
        ):
            return

        rows = conn.execute(
            """
            SELECT uid, embedding_json
            FROM asset_embeddings
            WHERE model = ? AND embedding_version = ?
            """,
            (model, EMBEDDING_SCHEMA_VERSION),
        ).fetchall()

        uids: List[str] = []
        vectors: List[List[float]] = []
        dim = None
        for row in rows:
            vec = self._safe_json_loads(row["embedding_json"], [])
            if not isinstance(vec, list) or not vec:
                continue
            try:
                arr = [float(x) for x in vec]
            except Exception:
                continue
            if dim is None:
                dim = len(arr)
            if len(arr) != dim:
                continue
            uids.append(str(row["uid"]))
            vectors.append(arr)

        if not vectors:
            self._vector_cache = {
                "model": model,
                "updated_at": max_updated,
                "uids_count": 0,
            }
            if self._vector_index is not None:
                self._vector_index._reset()
            return

        matrix = np.array(vectors, dtype=np.float32)
        # Rebuild VectorIndex (handles normalisation internally)
        if self._vector_index is not None:
            self._vector_index.rebuild(uids, matrix)
            self._vector_index.save()

        self._vector_cache = {
            "model": model,
            "updated_at": max_updated,
            "uids_count": len(uids),
        }

    def _vector_search(self, conn: sqlite3.Connection, query: str, top_k: int = 1200) -> Dict[str, float]:
        if np is None or self._vector_index is None:
            return {}
        qvec = self._get_query_embedding(query)
        if not qvec:
            return {}
        model = self._embedding_model()
        self._refresh_vector_cache(conn, model)
        if self._vector_index.count == 0:
            return {}
        return self._vector_index.search(qvec, top_k=top_k, threshold=0.08)

    def _upsert_embedding_for_asset(
        self,
        conn: sqlite3.Connection,
        uid: str,
        filename: Optional[str],
        semantic_text: Optional[str],
        keywords_json: Any,
        semantic_json: Any,
        analysis_json: Any = None,
    ) -> bool:
        source = self._build_embedding_source(
            filename=filename,
            semantic_text=semantic_text,
            keywords_json=keywords_json,
            semantic_json=semantic_json,
            analysis_json=analysis_json,
        )
        if not source:
            return False
        content_hash = self._embedding_content_hash(source)
        model = self._embedding_model()
        existing = conn.execute(
            """
            SELECT content_hash, model, embedding_version
            FROM asset_embeddings
            WHERE uid = ?
            """,
            (uid,),
        ).fetchone()
        if (
            existing
            and str(existing["content_hash"] or "") == content_hash
            and str(existing["model"] or "") == model
            and str(existing["embedding_version"] or "") == EMBEDDING_SCHEMA_VERSION
        ):
            return False

        vec = self._call_openai_embedding(source)
        if not vec:
            return False

        conn.execute(
            """
            INSERT INTO asset_embeddings (
                uid, model, embedding_json, embedding_dim,
                content_hash, embedding_version, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(uid) DO UPDATE SET
                model=excluded.model,
                embedding_json=excluded.embedding_json,
                embedding_dim=excluded.embedding_dim,
                content_hash=excluded.content_hash,
                embedding_version=excluded.embedding_version,
                updated_at=excluded.updated_at
            """,
            (
                uid,
                model,
                json.dumps(vec, ensure_ascii=False),
                len(vec),
                content_hash,
                EMBEDDING_SCHEMA_VERSION,
                self._now(),
            ),
        )
        self._invalidate_vector_cache()
        return True

    def _refresh_embeddings_incremental(self, conn: sqlite3.Connection, max_items: int = 12) -> int:
        _re_t0 = time.perf_counter()
        if max_items <= 0:
            return 0
        client = self._openai_client()
        if client is None:
            return 0
        rows = conn.execute(
            """
            SELECT a.uid, a.filename, a.semantic_text, a.keywords_json, a.semantic_json,
                   a.analysis_json,
                   e.content_hash, e.model, e.embedding_version
            FROM assets a
            LEFT JOIN asset_embeddings e ON e.uid = a.uid
            ORDER BY a.updated_at DESC
            LIMIT 600
            """
        ).fetchall()
        done = 0
        model = self._embedding_model()
        for row in rows:
            source = self._build_embedding_source(
                filename=row["filename"],
                semantic_text=row["semantic_text"],
                keywords_json=row["keywords_json"],
                semantic_json=row["semantic_json"],
                analysis_json=row["analysis_json"],
            )
            if not source:
                continue
            expected_hash = self._embedding_content_hash(source)
            same = (
                str(row["content_hash"] or "") == expected_hash
                and str(row["model"] or "") == model
                and str(row["embedding_version"] or "") == EMBEDDING_SCHEMA_VERSION
            )
            if same:
                continue
            if self._upsert_embedding_for_asset(
                conn=conn,
                uid=str(row["uid"]),
                filename=row["filename"],
                semantic_text=row["semantic_text"],
                keywords_json=row["keywords_json"],
                semantic_json=row["semantic_json"],
                analysis_json=row["analysis_json"],
            ):
                done += 1
                if done >= max_items:
                    break
        _re_elapsed = (time.perf_counter() - _re_t0) * 1000
        _gml_logger.info("[perf] refresh_embeddings: %.1fms refreshed=%d", _re_elapsed, done)
        try:
            from modules.app_api.services.perf_log import record as _perf_rec
            _perf_rec("refresh_embeddings", _re_elapsed, {"refreshed": done})
        except Exception:
            pass
        return done

    def _heuristic_structured_tags(self, evidence: Dict[str, Any]) -> Dict[str, Any]:
        schema = self._empty_structured_tag_schema()
        mapping = self._bilingual_term_map()

        def _push(cat: str, value: Any):
            text = str(value or "").strip()
            if not text:
                return
            lowered = text.lower()
            if self._contains_cjk(text):
                schema["tags"][cat]["zh"].append(text)
                if lowered in mapping:
                    schema["tags"][cat]["en"].append(mapping[lowered])
            else:
                schema["tags"][cat]["en"].append(lowered)
                if lowered in mapping:
                    schema["tags"][cat]["zh"].append(mapping[lowered])

        for item in evidence.get("objects", []) or []:
            _push("objects", item)
        for item in [evidence.get("activity"), evidence.get("camera_movement"), evidence.get("narrative_role")]:
            _push("actions", item)
        for item in [evidence.get("setting"), evidence.get("time_of_day"), evidence.get("weather"), evidence.get("scene_description")]:
            _push("scene", item)
        for item in [evidence.get("mood"), evidence.get("emotion_intensity")]:
            for part in self._split_terms(item):
                _push("mood", part)
        for item in [evidence.get("visual_style"), evidence.get("shot_type"), evidence.get("perspective"), evidence.get("color_tone")]:
            _push("style", item)
        for item in evidence.get("use_cases", []) or []:
            _push("use_cases", item)

        # 概念层：用 seed 做补全，避免只停留在物体层
        seed_concepts = self._seed_expand_terms("concepts", evidence.get("evidence_text", ""))
        for zh in seed_concepts["zh"]:
            _push("concepts", zh)
        for en in seed_concepts["en"]:
            _push("concepts", en)

        seed_use_cases = self._seed_expand_terms("use_cases", evidence.get("evidence_text", ""))
        for zh in seed_use_cases["zh"]:
            _push("use_cases", zh)
        for en in seed_use_cases["en"]:
            _push("use_cases", en)

        for cat in TAG_CATEGORIES:
            zh_terms = self._normalize_terms(schema["tags"][cat]["zh"], lang="zh")
            en_terms = self._normalize_terms(schema["tags"][cat]["en"], lang="en")
            if not zh_terms and en_terms:
                zh_terms = [mapping.get(t.lower(), t) for t in en_terms[:10]]
                zh_terms = self._normalize_terms(zh_terms, lang="zh")
            if not en_terms and zh_terms:
                en_terms = [mapping.get(t.lower(), t) for t in zh_terms[:10]]
                en_terms = self._normalize_terms(en_terms, lang="en")
            conf = 0.62
            if cat in {"objects", "scene"} and (zh_terms or en_terms):
                conf = 0.72
            if cat in {"concepts", "use_cases"} and len(zh_terms) + len(en_terms) >= 6:
                conf = 0.68
            schema["tags"][cat] = {
                "zh": zh_terms[:18],
                "en": en_terms[:18],
                "confidence": conf,
            }

        return schema

    def _normalize_structured_tags(self, raw: Dict[str, Any], evidence_text: str) -> Dict[str, Any]:
        normalized = self._empty_structured_tag_schema()
        mapping = self._bilingual_term_map()
        source_tags = raw.get("tags", raw) if isinstance(raw, dict) else {}
        if not isinstance(source_tags, dict):
            source_tags = {}

        for cat in TAG_CATEGORIES:
            node = source_tags.get(cat, {})
            if isinstance(node, list):
                node = {"en": node}
            if not isinstance(node, dict):
                node = {}
            zh_terms = self._split_terms(node.get("zh"))
            en_terms = self._split_terms(node.get("en"))
            seed_terms = self._seed_expand_terms(cat, evidence_text)
            zh_terms.extend(seed_terms["zh"])
            en_terms.extend(seed_terms["en"])

            zh_terms = self._normalize_terms(zh_terms, lang="zh")
            en_terms = self._normalize_terms(en_terms, lang="en")

            if not zh_terms and en_terms:
                zh_terms = self._normalize_terms([mapping.get(x.lower(), x) for x in en_terms], lang="zh")
            if not en_terms and zh_terms:
                en_terms = self._normalize_terms([mapping.get(x.lower(), x) for x in zh_terms], lang="en")

            min_target = 8 if cat in {"concepts", "use_cases"} else 4
            if len(zh_terms) < min_target or len(en_terms) < min_target:
                seed_fill = self._seed_expand_terms(cat, evidence_text)
                zh_terms = self._normalize_terms(zh_terms + seed_fill["zh"], lang="zh")
                en_terms = self._normalize_terms(en_terms + seed_fill["en"], lang="en")

            normalized["tags"][cat] = {
                "zh": zh_terms[:18],
                "en": en_terms[:18],
                "confidence": self._clamp_confidence(node.get("confidence"), default=0.6),
            }

        objects_count = len(normalized["tags"]["objects"]["zh"]) + len(normalized["tags"]["objects"]["en"])
        scene_count = len(normalized["tags"]["scene"]["zh"]) + len(normalized["tags"]["scene"]["en"])
        concept_count = len(normalized["tags"]["concepts"]["zh"]) + len(normalized["tags"]["concepts"]["en"])
        use_case_count = len(normalized["tags"]["use_cases"]["zh"]) + len(normalized["tags"]["use_cases"]["en"])
        total_terms = 0
        for cat in TAG_CATEGORIES:
            total_terms += len(normalized["tags"][cat]["zh"]) + len(normalized["tags"][cat]["en"])
        normalized["quality_checks"] = {
            "generic_terms_removed": True,
            "duplicate_terms_removed": True,
            "covers_literal_and_abstract": bool(objects_count + scene_count > 0 and concept_count + use_case_count > 0),
            "search_ready": total_terms >= 20,
        }
        return normalized

    def _flatten_structured_tag_terms(self, schema: Dict[str, Any]) -> List[str]:
        tags = schema.get("tags", {}) if isinstance(schema, dict) else {}
        out: List[str] = []
        for cat in TAG_CATEGORIES:
            node = tags.get(cat, {})
            if not isinstance(node, dict):
                continue
            zh_list = node.get("zh", [])
            en_list = node.get("en", [])
            for item in zh_list if isinstance(zh_list, list) else []:
                text = str(item or "").strip()
                if text:
                    out.append(text)
                    out.append(f"{cat}:{text}")
            for item in en_list if isinstance(en_list, list) else []:
                text = str(item or "").strip().lower()
                if text:
                    out.append(text)
                    out.append(f"{cat}:{text}")
        return self._dedupe_list(out)

    @staticmethod
    def _build_tag_schema_json() -> str:
        """Dynamically build the JSON schema string from TAG_TAXONOMY (25 categories)."""
        cats = {}
        for cat in TAG_TAXONOMY:
            cats[cat] = {"zh": [], "en": [], "confidence": 0.0}
        schema = {
            "tags": cats,
            "quality_checks": {
                "generic_terms_removed": True,
                "duplicate_terms_removed": True,
                "covers_literal_and_abstract": True,
                "search_ready": True,
            },
        }
        return json.dumps(schema, ensure_ascii=False)

    def _llm_structured_tags(self, path: Path, evidence: Dict[str, Any], draft_schema: Dict[str, Any]) -> Dict[str, Any]:
        if not self._llm_tagging_enabled():
            return {}

        keyframes = self._extract_keyframe_data_urls(path)

        # Build category list string for prompt
        cat_list = ", ".join(f"{c}({TAG_TAXONOMY[c]['zh']})" for c in TAG_TAXONOMY)
        schema_json = self._build_tag_schema_json()

        system_prompt = (
            "You are a professional stock-media semantic tagging editor.\n"
            "Goal: produce search-optimized tags for a media asset management system.\n"
            "Do NOT describe the media. Produce tags that maximize future retrievability.\n"
            "Output JSON only and keep tags concise, lowercase, search-friendly.\n"
            f"Tag categories (25 total): {cat_list}\n"
            "Internally expand semantic dimensions: marketing themes, storytelling arcs, industry use, "
            "emotions, social context, season/time/weather, camera language, audio mood, "
            "materials/textures, architecture, food, animals, vehicles, clothing, body language, "
            "spatial relations, color palette, composition, nature, narrative technique.\n"
            "Fill relevant categories only. Skip categories with no evidence.\n"
            f"Return schema: {schema_json}"
        )

        user_text = (
            "Structured evidence:\n"
            f"{json.dumps(evidence, ensure_ascii=False)}\n\n"
            "Draft tags:\n"
            f"{json.dumps(draft_schema, ensure_ascii=False)}\n\n"
            "Improve tags:\n"
            "- remove weak/generic terms\n"
            "- add high-value commercial concepts\n"
            "- normalize vocabulary\n"
            "- keep category diversity across all 25 categories\n"
            "- do not invent unsupported specifics\n"
            "- if Chinese evidence exists, provide both zh and en arrays"
        )
        user_content: List[Dict[str, Any]] = [{"type": "text", "text": user_text}]
        for url in keyframes[:3]:
            user_content.append({"type": "image_url", "image_url": {"url": url, "detail": "low"}})

        primary = self._call_openai_json(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=2500,
            temperature=0.12,
        )
        if not primary:
            return {}

        refine_prompt = (
            "You are given draft tags across 25 categories. Improve them:\n"
            "- remove weak, generic, overly broad tags\n"
            "- add missing high-value commercial concepts\n"
            "- normalize to consistent vocabulary\n"
            f"- ensure category diversity across: {cat_list}\n"
            "- keep each list compact and useful\n"
            "- do not invent specifics not supported by evidence\n"
            "Return JSON in the same schema, replacing the draft."
        )
        refined = self._call_openai_json(
            messages=[
                {"role": "system", "content": "Return JSON only."},
                {
                    "role": "user",
                    "content": (
                        refine_prompt
                        + "\nEvidence:\n"
                        + json.dumps(evidence, ensure_ascii=False)
                        + "\nDraft:\n"
                        + json.dumps(primary, ensure_ascii=False)
                    ),
                },
            ],
            max_tokens=2000,
            temperature=0.08,
        )
        result = refined if refined else primary
        # Inject model name for _meta tracking
        if result and isinstance(result, dict):
            model_name = (
                str(os.environ.get("OPENAI_MODEL", "")).strip()
                or str(os.environ.get("OPENAI_VISION_MODEL", "")).strip()
                or "gpt-4o-mini"
            )
            result["_model"] = model_name
        return result

    @staticmethod
    def _canonical_tag_catalog() -> Dict[str, Dict[str, str]]:
        return {
            # landmark (10)
            "church": {"zh": "教堂", "en": "church", "class": "landmark"},
            "temple": {"zh": "寺庙", "en": "temple", "class": "landmark"},
            "mosque": {"zh": "清真寺", "en": "mosque", "class": "landmark"},
            "bridge": {"zh": "桥梁", "en": "bridge", "class": "landmark"},
            "tower": {"zh": "塔", "en": "tower", "class": "landmark"},
            "castle": {"zh": "城堡", "en": "castle", "class": "landmark"},
            "statue": {"zh": "雕像", "en": "statue", "class": "landmark"},
            "mountain": {"zh": "山地", "en": "mountain", "class": "landmark"},
            "beach": {"zh": "海滩", "en": "beach", "class": "landmark"},
            "forest": {"zh": "森林", "en": "forest", "class": "landmark"},
            # place (10)
            "street": {"zh": "街道", "en": "street", "class": "place"},
            "downtown": {"zh": "市中心", "en": "downtown", "class": "place"},
            "old town": {"zh": "老城区", "en": "old town", "class": "place"},
            "skyline": {"zh": "天际线", "en": "skyline", "class": "place"},
            "plaza": {"zh": "广场", "en": "plaza", "class": "place"},
            "alley": {"zh": "小巷", "en": "alley", "class": "place"},
            "city": {"zh": "城市", "en": "city", "class": "place"},
            "cafe": {"zh": "咖啡馆", "en": "cafe", "class": "place"},
            "park": {"zh": "公园", "en": "park", "class": "place"},
            "rooftop": {"zh": "屋顶", "en": "rooftop", "class": "place"},
            # people (2)
            "person": {"zh": "人物", "en": "person", "class": "people"},
            "people": {"zh": "人群", "en": "people", "class": "people"},
            # object (12)
            "car": {"zh": "汽车", "en": "car", "class": "object"},
            "road": {"zh": "道路", "en": "road", "class": "object"},
            "building": {"zh": "建筑", "en": "building", "class": "object"},
            "tree": {"zh": "树木", "en": "tree", "class": "object"},
            "water": {"zh": "水域", "en": "water", "class": "object"},
            "boat": {"zh": "船", "en": "boat", "class": "object"},
            "food": {"zh": "食物", "en": "food", "class": "object"},
            "snow": {"zh": "雪景", "en": "snow", "class": "object"},
            "flower": {"zh": "花朵", "en": "flower", "class": "object"},
            "window": {"zh": "窗户", "en": "window", "class": "object"},
            "door": {"zh": "门", "en": "door", "class": "object"},
            "light": {"zh": "灯光", "en": "light", "class": "object"},
            # time (9)
            "daytime": {"zh": "白天", "en": "daytime", "class": "time"},
            "afternoon": {"zh": "下午", "en": "afternoon", "class": "time"},
            "night": {"zh": "夜晚", "en": "night", "class": "time"},
            "sunrise": {"zh": "日出", "en": "sunrise", "class": "time"},
            "sunset": {"zh": "日落", "en": "sunset", "class": "time"},
            "spring": {"zh": "春季", "en": "spring", "class": "time"},
            "summer": {"zh": "夏季", "en": "summer", "class": "time"},
            "autumn": {"zh": "秋季", "en": "autumn", "class": "time"},
            "winter": {"zh": "冬季", "en": "winter", "class": "time"},
            # action (15)
            "walking": {"zh": "行走", "en": "walking", "class": "action"},
            "running": {"zh": "奔跑", "en": "running", "class": "action"},
            "driving": {"zh": "驾驶", "en": "driving", "class": "action"},
            "talking": {"zh": "讲述", "en": "talking", "class": "action"},
            "hiking": {"zh": "徒步", "en": "hiking", "class": "action"},
            "skiing": {"zh": "滑雪", "en": "skiing", "class": "action"},
            "surfing": {"zh": "冲浪", "en": "surfing", "class": "action"},
            "cooking": {"zh": "烹饪", "en": "cooking", "class": "action"},
            "reading": {"zh": "阅读", "en": "reading", "class": "action"},
            "dancing": {"zh": "舞蹈", "en": "dancing", "class": "action"},
            "swimming": {"zh": "游泳", "en": "swimming", "class": "action"},
            "cycling": {"zh": "骑行", "en": "cycling", "class": "action"},
            "meditating": {"zh": "冥想", "en": "meditating", "class": "action"},
            "climbing": {"zh": "攀登", "en": "climbing", "class": "action"},
            "jumping": {"zh": "跳跃", "en": "jumping", "class": "action"},
            # abstract / concept (14)
            "lifestyle": {"zh": "生活方式", "en": "lifestyle", "class": "abstract"},
            "travel vlog": {"zh": "旅行vlog", "en": "travel vlog", "class": "abstract"},
            "city promo": {"zh": "城市宣传", "en": "city promo", "class": "abstract"},
            "opening hook": {"zh": "开场钩子", "en": "opening hook", "class": "abstract"},
            "use case": {"zh": "使用场景", "en": "use case", "class": "abstract"},
            "exploration": {"zh": "探索", "en": "exploration", "class": "abstract"},
            "healing": {"zh": "治愈", "en": "healing", "class": "abstract"},
            "relaxed vibe": {"zh": "松弛感", "en": "relaxed vibe", "class": "abstract"},
            "cinematic": {"zh": "电影感", "en": "cinematic", "class": "abstract"},
            "documentary": {"zh": "纪录感", "en": "documentary", "class": "abstract"},
            "nostalgia": {"zh": "怀旧", "en": "nostalgia", "class": "abstract"},
            "sustainability": {"zh": "可持续", "en": "sustainability", "class": "abstract"},
            "creativity": {"zh": "创造力", "en": "creativity", "class": "abstract"},
            "balance": {"zh": "平衡", "en": "balance", "class": "abstract"},
            # material (12)
            "wood": {"zh": "木质", "en": "wood", "class": "material"},
            "metal": {"zh": "金属", "en": "metal", "class": "material"},
            "glass": {"zh": "玻璃", "en": "glass", "class": "material"},
            "stone": {"zh": "石材", "en": "stone", "class": "material"},
            "concrete": {"zh": "混凝土", "en": "concrete", "class": "material"},
            "leather": {"zh": "皮革", "en": "leather", "class": "material"},
            "silk": {"zh": "丝绸", "en": "silk", "class": "material"},
            "ceramic": {"zh": "陶瓷", "en": "ceramic", "class": "material"},
            "bamboo": {"zh": "竹子", "en": "bamboo", "class": "material"},
            "marble": {"zh": "大理石", "en": "marble", "class": "material"},
            "brick": {"zh": "砖块", "en": "brick", "class": "material"},
            "rust": {"zh": "铁锈", "en": "rust", "class": "material"},
            # architecture (10)
            "gothic": {"zh": "哥特式", "en": "gothic", "class": "architecture"},
            "baroque": {"zh": "巴洛克", "en": "baroque", "class": "architecture"},
            "modernist": {"zh": "现代主义", "en": "modernist", "class": "architecture"},
            "art deco": {"zh": "装饰艺术", "en": "art deco", "class": "architecture"},
            "industrial": {"zh": "工业风", "en": "industrial", "class": "architecture"},
            "bauhaus": {"zh": "包豪斯", "en": "bauhaus", "class": "architecture"},
            "neoclassical": {"zh": "新古典", "en": "neoclassical", "class": "architecture"},
            "postmodern": {"zh": "后现代", "en": "postmodern", "class": "architecture"},
            "mediterranean": {"zh": "地中海", "en": "mediterranean", "class": "architecture"},
            "chinese traditional": {"zh": "中式传统", "en": "chinese traditional", "class": "architecture"},
            # food (12)
            "chinese food": {"zh": "中餐", "en": "chinese food", "class": "food"},
            "japanese food": {"zh": "日料", "en": "japanese food", "class": "food"},
            "dessert": {"zh": "甜点", "en": "dessert", "class": "food"},
            "coffee": {"zh": "咖啡", "en": "coffee", "class": "food"},
            "tea": {"zh": "茶", "en": "tea", "class": "food"},
            "cocktail": {"zh": "鸡尾酒", "en": "cocktail", "class": "food"},
            "barbecue": {"zh": "烧烤", "en": "barbecue", "class": "food"},
            "bread": {"zh": "面包", "en": "bread", "class": "food"},
            "sushi": {"zh": "寿司", "en": "sushi", "class": "food"},
            "pizza": {"zh": "披萨", "en": "pizza", "class": "food"},
            "hotpot": {"zh": "火锅", "en": "hotpot", "class": "food"},
            "ice cream": {"zh": "冰淇淋", "en": "ice cream", "class": "food"},
            # animal (10)
            "cat": {"zh": "猫", "en": "cat", "class": "animal"},
            "dog": {"zh": "狗", "en": "dog", "class": "animal"},
            "bird": {"zh": "鸟类", "en": "bird", "class": "animal"},
            "fish": {"zh": "鱼类", "en": "fish", "class": "animal"},
            "horse": {"zh": "马", "en": "horse", "class": "animal"},
            "butterfly": {"zh": "蝴蝶", "en": "butterfly", "class": "animal"},
            "dolphin": {"zh": "海豚", "en": "dolphin", "class": "animal"},
            "deer": {"zh": "鹿", "en": "deer", "class": "animal"},
            "rabbit": {"zh": "兔子", "en": "rabbit", "class": "animal"},
            "seagull": {"zh": "海鸥", "en": "seagull", "class": "animal"},
            # vehicle (8)
            "bicycle": {"zh": "自行车", "en": "bicycle", "class": "vehicle"},
            "motorcycle": {"zh": "摩托车", "en": "motorcycle", "class": "vehicle"},
            "train": {"zh": "火车", "en": "train", "class": "vehicle"},
            "airplane": {"zh": "飞机", "en": "airplane", "class": "vehicle"},
            "tram": {"zh": "电车", "en": "tram", "class": "vehicle"},
            "cable car": {"zh": "缆车", "en": "cable car", "class": "vehicle"},
            "sailboat": {"zh": "帆船", "en": "sailboat", "class": "vehicle"},
            "skateboard": {"zh": "滑板", "en": "skateboard", "class": "vehicle"},
            # clothing (8)
            "suit": {"zh": "西装", "en": "suit", "class": "clothing"},
            "dress": {"zh": "连衣裙", "en": "dress", "class": "clothing"},
            "sportswear": {"zh": "运动装", "en": "sportswear", "class": "clothing"},
            "hanfu": {"zh": "汉服", "en": "hanfu", "class": "clothing"},
            "kimono": {"zh": "和服", "en": "kimono", "class": "clothing"},
            "denim": {"zh": "牛仔", "en": "denim", "class": "clothing"},
            "hat": {"zh": "帽子", "en": "hat", "class": "clothing"},
            "scarf": {"zh": "围巾", "en": "scarf", "class": "clothing"},
            # body_language (8)
            "smiling": {"zh": "微笑", "en": "smiling", "class": "body_language"},
            "thinking": {"zh": "思考", "en": "thinking", "class": "body_language"},
            "pointing": {"zh": "指向", "en": "pointing", "class": "body_language"},
            "clapping": {"zh": "鼓掌", "en": "clapping", "class": "body_language"},
            "waving": {"zh": "挥手", "en": "waving", "class": "body_language"},
            "looking up": {"zh": "仰望", "en": "looking up", "class": "body_language"},
            "head down": {"zh": "低头", "en": "head down", "class": "body_language"},
            "arms crossed": {"zh": "双臂交叉", "en": "arms crossed", "class": "body_language"},
            # nature (10)
            "lake": {"zh": "湖泊", "en": "lake", "class": "nature"},
            "river": {"zh": "河流", "en": "river", "class": "nature"},
            "waterfall": {"zh": "瀑布", "en": "waterfall", "class": "nature"},
            "desert": {"zh": "沙漠", "en": "desert", "class": "nature"},
            "grassland": {"zh": "草原", "en": "grassland", "class": "nature"},
            "glacier": {"zh": "冰川", "en": "glacier", "class": "nature"},
            "canyon": {"zh": "峡谷", "en": "canyon", "class": "nature"},
            "volcano": {"zh": "火山", "en": "volcano", "class": "nature"},
            "wetland": {"zh": "湿地", "en": "wetland", "class": "nature"},
            "cave": {"zh": "洞穴", "en": "cave", "class": "nature"},
            # weather (8)
            "sunny": {"zh": "晴天", "en": "sunny", "class": "weather"},
            "cloudy": {"zh": "多云", "en": "cloudy", "class": "weather"},
            "rainy": {"zh": "雨天", "en": "rainy", "class": "weather"},
            "foggy": {"zh": "雾", "en": "foggy", "class": "weather"},
            "rainbow": {"zh": "彩虹", "en": "rainbow", "class": "weather"},
            "storm": {"zh": "暴风雨", "en": "storm", "class": "weather"},
            "starry": {"zh": "星空", "en": "starry", "class": "weather"},
            "aurora": {"zh": "极光", "en": "aurora", "class": "weather"},
            # cultural (8)
            "festival": {"zh": "节日", "en": "festival", "class": "cultural"},
            "tradition": {"zh": "传统", "en": "tradition", "class": "cultural"},
            "calligraphy": {"zh": "书法", "en": "calligraphy", "class": "cultural"},
            "craft": {"zh": "手工艺", "en": "craft", "class": "cultural"},
            "tea ceremony": {"zh": "茶道", "en": "tea ceremony", "class": "cultural"},
            "lantern": {"zh": "灯笼", "en": "lantern", "class": "cultural"},
            "dragon dance": {"zh": "舞龙", "en": "dragon dance", "class": "cultural"},
            "temple fair": {"zh": "庙会", "en": "temple fair", "class": "cultural"},
            # composition (6)
            "rule of thirds": {"zh": "三分法", "en": "rule of thirds", "class": "composition"},
            "centered": {"zh": "居中", "en": "centered", "class": "composition"},
            "diagonal": {"zh": "对角线", "en": "diagonal", "class": "composition"},
            "negative space": {"zh": "留白", "en": "negative space", "class": "composition"},
            "frame within frame": {"zh": "框中框", "en": "frame within frame", "class": "composition"},
            "leading line": {"zh": "引导线", "en": "leading line", "class": "composition"},
            # social (6)
            "solitude": {"zh": "独处", "en": "solitude", "class": "social"},
            "family": {"zh": "家庭", "en": "family", "class": "social"},
            "friends gathering": {"zh": "朋友聚会", "en": "friends gathering", "class": "social"},
            "team": {"zh": "团队", "en": "team", "class": "social"},
            "party": {"zh": "派对", "en": "party", "class": "social"},
            "ceremony": {"zh": "仪式", "en": "ceremony", "class": "social"},
            # industry (8)
            "technology": {"zh": "科技", "en": "technology", "class": "industry"},
            "healthcare": {"zh": "医疗", "en": "healthcare", "class": "industry"},
            "education": {"zh": "教育", "en": "education", "class": "industry"},
            "finance": {"zh": "金融", "en": "finance", "class": "industry"},
            "retail": {"zh": "零售", "en": "retail", "class": "industry"},
            "tourism": {"zh": "旅游", "en": "tourism", "class": "industry"},
            "sports": {"zh": "体育", "en": "sports", "class": "industry"},
            "entertainment": {"zh": "娱乐", "en": "entertainment", "class": "industry"},
            # narrative (6)
            "montage": {"zh": "蒙太奇", "en": "montage", "class": "narrative"},
            "flashback": {"zh": "倒叙", "en": "flashback", "class": "narrative"},
            "suspense": {"zh": "悬念", "en": "suspense", "class": "narrative"},
            "symbolism": {"zh": "象征", "en": "symbolism", "class": "narrative"},
            "metaphor": {"zh": "隐喻", "en": "metaphor", "class": "narrative"},
            "contrast": {"zh": "对比", "en": "contrast", "class": "narrative"},
        }

    @staticmethod
    def _canonical_alias_map() -> Dict[str, str]:
        catalog = CoreMixin._canonical_tag_catalog()
        alias: Dict[str, str] = {}
        for key, meta in catalog.items():
            alias[key.lower()] = key
            alias[str(meta.get("en", "")).strip().lower()] = key
            alias[str(meta.get("zh", "")).strip().lower()] = key
        alias.update({
            "cathedral": "church",
            "chapel": "church",
            "basilica": "church",
            "大教堂": "church",
            "礼拜堂": "church",
            "圣堂": "church",
            "教会": "church",
            "古教堂": "church",
            "iron bridge": "bridge",
            "steel bridge": "bridge",
            "viaduct": "bridge",
            "overpass": "bridge",
            "铁桥": "bridge",
            "钢桥": "bridge",
            "大桥": "bridge",
            "桥": "bridge",
            "shrine": "temple",
            "monastery": "temple",
            "abbey": "temple",
            "修道院": "temple",
            "神社": "temple",
            "fortress": "castle",
            "古堡": "castle",
            "尖塔": "tower",
            "塔楼": "tower",
            "雕塑": "statue",
            "石像": "statue",
            "山": "mountain",
            "雪山": "mountain",
            "海边": "beach",
            "沙滩": "beach",
            "海岸": "beach",
            "树林": "forest",
            "林地": "forest",
            "city center": "downtown",
            "city centre": "downtown",
            "cbd": "downtown",
            "市中心": "downtown",
            "中心城区": "downtown",
            "historic center": "old town",
            "historic centre": "old town",
            "oldtown": "old town",
            "old town": "old town",
            "古城": "old town",
            "老城区": "old town",
            "老街区": "old town",
            "city skyline": "skyline",
            "天际线": "skyline",
            "高楼群": "skyline",
            "square": "plaza",
            "广场": "plaza",
            "lane": "alley",
            "小巷": "alley",
            "巷子": "alley",
            "street view": "street",
            "街道": "street",
            "街头": "street",
            "town": "city",
            "urban": "city",
            "城区": "city",
            "白天": "daytime",
            "day": "daytime",
            "日间": "daytime",
            "午后": "afternoon",
            "下午": "afternoon",
            "夜景": "night",
            "夜晚": "night",
            "晚上": "night",
            "日出": "sunrise",
            "清晨": "sunrise",
            "dawn": "sunrise",
            "日落": "sunset",
            "傍晚": "sunset",
            "黄昏": "sunset",
            "walk": "walking",
            "walks": "walking",
            "行走": "walking",
            "徒步": "hiking",
            "hike": "hiking",
            "drive": "driving",
            "驾驶": "driving",
            "talk": "talking",
            "speak": "talking",
            "讲解": "talking",
            "口播": "talking",
            "ski": "skiing",
            "滑雪": "skiing",
            "surf": "surfing",
            "冲浪": "surfing",
            "travel_vlog": "travel vlog",
            "travel vlog": "travel vlog",
            "旅行vlog": "travel vlog",
            "city_promo": "city promo",
            "city promo": "city promo",
            "opening hook": "opening hook",
            "hook": "opening hook",
            "开场钩子": "opening hook",
            "use_case": "use case",
            "use cases": "use case",
            "使用场景": "use case",
            "lifestyle": "lifestyle",
            "生活方式": "lifestyle",
        })
        return alias

    def _normalize_tag_to_key(self, term: str) -> Optional[str]:
        text = re.sub(r"\s+", " ", str(term or "").strip().lower().replace("_", " "))
        if not text:
            return None
        alias_map = self._canonical_alias_map()
        if text in alias_map:
            return alias_map[text]
        for alias, key in sorted(alias_map.items(), key=lambda x: len(x[0]), reverse=True):
            if len(alias) < 3:
                continue
            if re.search(r"^[a-z0-9\s\-]+$", alias):
                if re.search(rf"\b{re.escape(alias)}\b", text):
                    return key
            elif alias in text:
                return key
        return None

    def _entry_from_key(self, key: str) -> Optional[Dict[str, str]]:
        catalog = self._canonical_tag_catalog()
        meta = catalog.get(key)
        if not meta:
            return None
        return {
            "key": key,
            "zh": str(meta.get("zh", "")).strip(),
            "en": str(meta.get("en", "")).strip().lower(),
            "class": str(meta.get("class", "object")).strip(),
        }

    def _term_to_entry(self, term: str, fallback_class: str = "object") -> Optional[Dict[str, str]]:
        text = re.sub(r"\s+", " ", str(term or "").strip())
        if not text:
            return None
        lowered = text.lower()
        if lowered in GENERIC_TAG_TERMS:
            return None
        if any(
            marker in lowered
            for marker in (
                "unknown",
                "mixed environment",
                "stable framing",
                "soft natural light",
                "bright daylight",
                "low-light",
                "audio present",
            )
        ):
            return None
        if lowered in {
            "static", "handheld", "aerial", "drone", "outdoor", "indoor",
            "固定机位", "手持", "航拍", "室外", "室内",
        }:
            return None
        if ";" in text:
            return None
        canonical = self._normalize_tag_to_key(text)
        if canonical:
            return self._entry_from_key(canonical)

        # 仅保留短词/短语，避免把句子塞进检索标签。
        if len(text) > 24 or len(text.split()) > 3:
            return None
        if any(ch in text for ch in "\n\t[]{}<>"):
            return None

        bi_map = self._bilingual_term_map()
        zh = ""
        en = ""
        if self._contains_cjk(text):
            zh = text
            en = str(bi_map.get(lowered, "")).strip().lower()
        else:
            en = lowered
            zh = str(bi_map.get(lowered, "")).strip()
        if not zh and not en:
            return None
        key = f"custom:{en or zh.lower()}"
        return {"key": key, "zh": zh, "en": en, "class": fallback_class}

    def _landmark_gate(self, evidence: Dict[str, Any]) -> List[str]:
        text_parts = []
        for k in ("scene_description", "mood", "transcript", "evidence_text"):
            v = evidence.get(k)
            if v:
                text_parts.append(str(v))
        for frame in evidence.get("keyframes", []) or []:
            if isinstance(frame, dict):
                text_parts.append(str(frame.get("caption", "")))
        for item in evidence.get("ocr", []) or []:
            if isinstance(item, dict):
                text_parts.append(str(item.get("text", "")))
        for obj in evidence.get("objects", []) or []:
            text_parts.append(str(obj))
        source = " ".join(text_parts).lower()
        if not source:
            return []

        gate_aliases = {
            "church": ["church", "cathedral", "chapel", "basilica", "教堂", "大教堂", "礼拜堂"],
            "temple": ["temple", "shrine", "monastery", "abbey", "寺庙", "神社", "修道院"],
            "mosque": ["mosque", "清真寺"],
            "bridge": ["bridge", "viaduct", "overpass", "铁桥", "钢桥", "桥梁", "大桥", "桥"],
            "tower": ["tower", "尖塔", "塔楼", "钟楼", "塔"],
            "castle": ["castle", "fortress", "古堡", "城堡", "要塞"],
            "statue": ["statue", "sculpture", "雕像", "雕塑", "石像"],
            "mountain": ["mountain", "alpine", "mount", "高山", "山地", "山脉", "雪山"],
            "beach": ["beach", "coast", "shore", "海滩", "海边", "沙滩", "海岸"],
            "forest": ["forest", "woods", "树林", "森林", "林地"],
        }
        hits: List[str] = []
        for key, aliases in gate_aliases.items():
            if any(a in source for a in aliases):
                hits.append(key)
        hits = self._dedupe_list(hits)
        return hits[:3]

    def _infer_time_tag_keys(self, evidence: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        time_of_day = str(evidence.get("time_of_day", "") or "").strip().lower()
        season = str(evidence.get("season", "") or "").strip().lower()
        source = str(evidence.get("evidence_text", "") or "").lower()
        if time_of_day in {"sunset"} or any(x in source for x in ["sunset", "日落", "黄昏", "dusk"]):
            out.append("sunset")
        elif time_of_day in {"night"} or any(x in source for x in ["night", "夜景", "夜晚", "晚上"]):
            out.append("night")
        elif time_of_day in {"afternoon"} or any(x in source for x in ["afternoon", "午后", "下午"]):
            out.append("afternoon")
        elif time_of_day in {"morning"} or any(x in source for x in ["sunrise", "日出", "清晨", "dawn"]):
            out.append("sunrise")
        else:
            out.append("daytime")
        if season in {"spring", "summer", "autumn", "winter"}:
            out.append(season)
        return self._dedupe_list(out)

    def _city_specific_place_keys(self, evidence_text: str) -> List[str]:
        text = str(evidence_text or "").lower()
        hits: List[str] = []
        if any(k in text for k in ["skyline", "city skyline", "天际线", "高楼", "高楼群"]):
            hits.append("skyline")
        if any(k in text for k in ["old town", "historic", "古城", "老城区", "老街区"]):
            hits.append("old town")
        if any(k in text for k in ["plaza", "square", "广场"]):
            hits.append("plaza")
        if any(k in text for k in ["alley", "lane", "小巷", "巷子"]):
            hits.append("alley")
        if any(k in text for k in ["downtown", "city center", "cbd", "市中心", "中心城区"]):
            hits.append("downtown")

        has_city_signal = any(k in text for k in ["city", "urban", "street", "城市", "街头", "城区", "都市"])
        if not hits and has_city_signal:
            hits.append("street")
        return self._dedupe_list(hits)[:2]

    @staticmethod
    def _parse_section_terms(value: str) -> List[str]:
        return [x.strip() for x in re.split(r"[，,;；|/]+", str(value or "")) if x.strip()]

    def _parse_plain_text_index_layers(self, raw_text: str) -> Dict[str, Any]:
        parsed = {
            "core_search_tags": {"zh": [], "en": []},
            "secondary_tags": {"zh": [], "en": []},
            "tech_meta": {},
        }
        if not raw_text:
            return parsed
        section = ""
        for raw_line in str(raw_text).splitlines():
            line = raw_line.strip()
            if not line:
                continue
            upper = line.upper()
            if upper == "[CORE]":
                section = "core"
                continue
            if upper == "[SECONDARY]":
                section = "secondary"
                continue
            if upper == "[TECH_META]":
                section = "tech"
                continue
            if section == "core" and line.lower().startswith("zh:"):
                parsed["core_search_tags"]["zh"] = self._parse_section_terms(line.split(":", 1)[1])
                continue
            if section == "core" and line.lower().startswith("en:"):
                parsed["core_search_tags"]["en"] = [x.lower() for x in self._parse_section_terms(line.split(":", 1)[1])]
                continue
            if section == "secondary" and line.lower().startswith("zh:"):
                parsed["secondary_tags"]["zh"] = self._parse_section_terms(line.split(":", 1)[1])
                continue
            if section == "secondary" and line.lower().startswith("en:"):
                parsed["secondary_tags"]["en"] = [x.lower() for x in self._parse_section_terms(line.split(":", 1)[1])]
                continue
            if section == "tech":
                if ":" not in line:
                    continue
                k, v = line.split(":", 1)
                parsed["tech_meta"][k.strip().lower()] = v.strip()
        return parsed

    def _llm_refine_index_layers(
        self,
        evidence: Dict[str, Any],
        draft_layers: Dict[str, Any],
        landmark_gate: List[str],
    ) -> Dict[str, Any]:
        if not self._llm_tagging_enabled():
            return {}
        prompt = (
            "You are a video asset indexing assistant. Your output is used for keyword search.\n\n"
            "Generate tags in THREE LAYERS:\n"
            "A) core_search_tags (user-visible, highest priority for retrieval)\n"
            "B) secondary_tags (index-only, not shown by default)\n"
            "C) tech_meta (stored only, never shown; includes resolution/duration/orientation)\n\n"
            "Rules:\n"
            "- NO duplicates across tags.\n"
            "- Merge synonyms (e.g., church/cathedral = church; 教堂/大教堂 = 教堂).\n"
            "- core_search_tags must prioritize concrete visible entities:\n"
            "  landmark/place > people > objects > time > actions.\n"
            "- If a landmark category is visible (church, bridge, tower, castle, mosque, temple, mountain, beach, forest), it MUST appear in core_search_tags.\n"
            "- Avoid generic tags: video, footage, scene, content, hook, main shot, general, activity.\n"
            "- Provide both Chinese and English tags.\n"
            "- Output as plain text sections (not JSON).\n\n"
            "Output format exactly:\n\n"
            "[CORE]\n"
            "zh: ...\n"
            "en: ...\n\n"
            "[SECONDARY]\n"
            "zh: ...\n"
            "en: ...\n\n"
            "[TECH_META]\n"
            "orientation: portrait|landscape\n"
            "resolution: WxH\n"
            "duration_sec: number\n"
            "motion_level: low|moderate|high\n"
        )
        user_msg = (
            "landmark_gate(must inject to CORE if present): "
            + ", ".join(landmark_gate or [])
            + "\n\nEvidence:\n"
            + json.dumps(evidence, ensure_ascii=False)
            + "\n\nDraft layers:\n"
            + json.dumps(draft_layers, ensure_ascii=False)
            + "\n\nYou are given draft tags. Fix them:\n"
            "1) remove duplicates and generic terms\n"
            "2) enforce landmark/place/person/object/time/action order in [CORE]\n"
            "3) add missing concrete entities that improve search recall\n"
            "4) move abstract terms into [SECONDARY]\n"
            "5) ensure [TECH_META] has orientation + resolution, and no tech terms appear in [CORE]/[SECONDARY]\n"
            "Return only in the required plain text format."
        )
        output = self._call_openai_text(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=900,
            temperature=0.05,
        )
        if not output:
            return {}
        return self._parse_plain_text_index_layers(output)

    def _normalize_index_layers(
        self,
        raw_layers: Dict[str, Any],
        evidence: Dict[str, Any],
        forced_landmarks: List[str],
        tech_meta_default: Dict[str, Any],
    ) -> Dict[str, Any]:
        buckets = {
            "landmark": [],
            "place": [],
            "people": [],
            "object": [],
            "time": [],
            "action": [],
        }
        bucket_seen = {k: set() for k in buckets}
        secondary_entries: List[Dict[str, str]] = []
        secondary_seen = set()

        def _push_bucket(entry: Dict[str, str]):
            cls = entry.get("class", "object")
            key = entry.get("key", "")
            if cls not in buckets:
                cls = "object"
            if key in bucket_seen[cls]:
                return
            bucket_seen[cls].add(key)
            buckets[cls].append(entry)

        def _push_secondary(entry: Dict[str, str]):
            key = entry.get("key", "")
            if not key or key in secondary_seen:
                return
            secondary_seen.add(key)
            secondary_entries.append(entry)

        core_src = raw_layers.get("core_search_tags", {}) if isinstance(raw_layers, dict) else {}
        sec_src = raw_layers.get("secondary_tags", {}) if isinstance(raw_layers, dict) else {}
        core_terms = []
        if isinstance(core_src, dict):
            core_terms.extend(core_src.get("zh", []) if isinstance(core_src.get("zh"), list) else [])
            core_terms.extend(core_src.get("en", []) if isinstance(core_src.get("en"), list) else [])
        secondary_terms = []
        if isinstance(sec_src, dict):
            secondary_terms.extend(sec_src.get("zh", []) if isinstance(sec_src.get("zh"), list) else [])
            secondary_terms.extend(sec_src.get("en", []) if isinstance(sec_src.get("en"), list) else [])

        for term in core_terms:
            entry = self._term_to_entry(term, fallback_class="object")
            if not entry:
                continue
            if str(entry.get("key", "")).startswith("custom:"):
                _push_secondary(entry)
                continue
            if entry.get("class") == "abstract":
                _push_secondary(entry)
            else:
                _push_bucket(entry)
        for term in secondary_terms:
            entry = self._term_to_entry(term, fallback_class="abstract")
            if not entry:
                continue
            _push_secondary(entry)

        # 强制 landmark_gate 注入
        for key in forced_landmarks or []:
            entry = self._entry_from_key(key)
            if entry:
                _push_bucket(entry)

        # people: 如果检测到人物，则确保 person 在 core。
        people_presence = str(evidence.get("people_presence", "") or "").lower()
        if people_presence in {"present", "high_face_presence", "medium_face_presence"}:
            person_entry = self._entry_from_key("person")
            if person_entry:
                _push_bucket(person_entry)

        # 城市场景必须给具体可见类别，避免只留 city。
        place_keys = {x["key"] for x in buckets["place"]}
        if "city" in place_keys or not place_keys:
            specific = self._city_specific_place_keys(str(evidence.get("evidence_text", "")))
            for key in specific:
                e = self._entry_from_key(key)
                if e:
                    _push_bucket(e)
            if "city" in {x["key"] for x in buckets["place"]}:
                city_entries = [x for x in buckets["place"] if x["key"] == "city"]
                buckets["place"] = [x for x in buckets["place"] if x["key"] != "city"]
                for city_e in city_entries:
                    _push_secondary(city_e)

        # time 维度固定为 daytime/afternoon/night/sunrise/sunset + season(optional)
        for key in self._infer_time_tag_keys(evidence):
            e = self._entry_from_key(key)
            if e:
                _push_bucket(e)

        # 防止 tech 字段污染 core/secondary
        tech_words = {"portrait", "landscape", "resolution", "duration", "motion", "fps", "1080p", "4k"}
        for cls in list(buckets.keys()):
            cleaned = []
            for e in buckets[cls]:
                joined = f"{e.get('zh', '')} {e.get('en', '')}".lower()
                if any(w in joined for w in tech_words):
                    continue
                cleaned.append(e)
            buckets[cls] = cleaned
        cleaned_secondary = []
        for e in secondary_entries:
            joined = f"{e.get('zh', '')} {e.get('en', '')}".lower()
            if any(w in joined for w in tech_words):
                continue
            cleaned_secondary.append(e)
        secondary_entries = cleaned_secondary

        order = ["landmark", "place", "people", "object", "time", "action"]
        core_entries: List[Dict[str, str]] = []
        core_keys_seen = set()
        for cls in order:
            for e in buckets[cls]:
                key = e.get("key", "")
                if not key or key in core_keys_seen:
                    continue
                core_keys_seen.add(key)
                core_entries.append(e)

        # secondary 不允许与 core 重复
        sec_final: List[Dict[str, str]] = []
        sec_seen = set()
        for e in secondary_entries:
            key = e.get("key", "")
            if not key or key in core_keys_seen or key in sec_seen:
                continue
            sec_seen.add(key)
            sec_final.append(e)

        core_zh = self._normalize_terms([e.get("zh", "") for e in core_entries], lang="zh", max_items=22)
        core_en = self._normalize_terms([e.get("en", "") for e in core_entries], lang="en", max_items=22)
        sec_zh = self._normalize_terms([e.get("zh", "") for e in sec_final], lang="zh", max_items=28)
        sec_en = self._normalize_terms([e.get("en", "") for e in sec_final], lang="en", max_items=28)
        bi_map = self._bilingual_term_map()
        if not core_zh and core_en:
            core_zh = self._normalize_terms([bi_map.get(x.lower(), x) for x in core_en], lang="zh", max_items=22)
        if not core_en and core_zh:
            core_en = self._normalize_terms([bi_map.get(x.lower(), x) for x in core_zh], lang="en", max_items=22)
        if not sec_zh and sec_en:
            sec_zh = self._normalize_terms([bi_map.get(x.lower(), x) for x in sec_en], lang="zh", max_items=28)
        if not sec_en and sec_zh:
            sec_en = self._normalize_terms([bi_map.get(x.lower(), x) for x in sec_zh], lang="en", max_items=28)

        tm = dict(tech_meta_default or {})
        raw_tm = raw_layers.get("tech_meta", {}) if isinstance(raw_layers, dict) else {}
        if isinstance(raw_tm, dict):
            orientation = str(raw_tm.get("orientation", tm.get("orientation", ""))).strip().lower()
            tm["orientation"] = "portrait" if orientation == "portrait" else "landscape"
            resolution = str(raw_tm.get("resolution", tm.get("resolution", ""))).strip()
            tm["resolution"] = resolution if re.match(r"^\d{2,5}x\d{2,5}$", resolution) else str(tm.get("resolution", ""))
            try:
                tm["duration_sec"] = float(raw_tm.get("duration_sec", tm.get("duration_sec", 0)))
            except Exception:
                pass
            mv = str(raw_tm.get("motion_level", tm.get("motion_level", ""))).strip().lower()
            tm["motion_level"] = mv if mv in {"low", "moderate", "high"} else str(tm.get("motion_level", "low"))

        return {
            "core_search_tags": {"zh": core_zh, "en": core_en},
            "secondary_tags": {"zh": sec_zh, "en": sec_en},
            "tech_meta": {
                "orientation": "portrait" if str(tm.get("orientation", "")).lower() == "portrait" else "landscape",
                "resolution": str(tm.get("resolution", "")).strip(),
                "duration_sec": round(float(tm.get("duration_sec", 0) or 0), 3),
                "motion_level": str(tm.get("motion_level", "low")).strip().lower()
                if str(tm.get("motion_level", "")).strip().lower() in {"low", "moderate", "high"}
                else "low",
            },
            "landmark_gate": self._dedupe_list(forced_landmarks or [])[:3],
        }

    def _draft_index_layers_from_structured(
        self,
        structured_tags: Dict[str, Any],
        evidence: Dict[str, Any],
        forced_landmarks: List[str],
        tech_meta_default: Dict[str, Any],
    ) -> Dict[str, Any]:
        tags = structured_tags.get("tags", {}) if isinstance(structured_tags, dict) else {}
        draft = {
            "core_search_tags": {"zh": [], "en": []},
            "secondary_tags": {"zh": [], "en": []},
            "tech_meta": dict(tech_meta_default or {}),
        }

        def _append(dst: str, vals: List[str], limit: int = 20):
            arr = draft[dst]
            if not isinstance(arr, dict):
                return
            for x in vals:
                text = str(x or "").strip()
                if not text:
                    continue
                if self._contains_cjk(text):
                    arr.setdefault("zh", []).append(text)
                else:
                    arr.setdefault("en", []).append(text.lower())
                if len(arr.get("zh", [])) + len(arr.get("en", [])) >= limit:
                    break

        scene_node = tags.get("scene", {}) if isinstance(tags.get("scene"), dict) else {}
        objects_node = tags.get("objects", {}) if isinstance(tags.get("objects"), dict) else {}
        actions_node = tags.get("actions", {}) if isinstance(tags.get("actions"), dict) else {}
        mood_node = tags.get("mood", {}) if isinstance(tags.get("mood"), dict) else {}
        style_node = tags.get("style", {}) if isinstance(tags.get("style"), dict) else {}
        concept_node = tags.get("concepts", {}) if isinstance(tags.get("concepts"), dict) else {}
        use_case_node = tags.get("use_cases", {}) if isinstance(tags.get("use_cases"), dict) else {}

        _append("core_search_tags", (scene_node.get("zh", []) or []) + (scene_node.get("en", []) or []), limit=16)
        _append("core_search_tags", (objects_node.get("zh", []) or []) + (objects_node.get("en", []) or []), limit=20)
        _append("core_search_tags", (actions_node.get("zh", []) or []) + (actions_node.get("en", []) or []), limit=24)

        for k in forced_landmarks or []:
            e = self._entry_from_key(k)
            if e:
                draft["core_search_tags"]["zh"].append(e["zh"])
                draft["core_search_tags"]["en"].append(e["en"])

        # 抽象词默认进 secondary
        _append("secondary_tags", (mood_node.get("zh", []) or []) + (mood_node.get("en", []) or []), limit=30)
        _append("secondary_tags", (concept_node.get("zh", []) or []) + (concept_node.get("en", []) or []), limit=34)
        _append("secondary_tags", (style_node.get("zh", []) or []) + (style_node.get("en", []) or []), limit=38)
        _append("secondary_tags", (use_case_node.get("zh", []) or []) + (use_case_node.get("en", []) or []), limit=42)

        return self._normalize_index_layers(draft, evidence, forced_landmarks, tech_meta_default)

    def _flatten_index_layer_terms(self, index_layers: Dict[str, Any]) -> List[str]:
        out: List[str] = []
        core = index_layers.get("core_search_tags", {}) if isinstance(index_layers, dict) else {}
        secondary = index_layers.get("secondary_tags", {}) if isinstance(index_layers, dict) else {}
        for layer_name, node in (("core", core), ("secondary", secondary)):
            if not isinstance(node, dict):
                continue
            for lang_key in ("zh", "en"):
                vals = node.get(lang_key, [])
                if not isinstance(vals, list):
                    continue
                for item in vals:
                    term = str(item or "").strip()
                    if not term:
                        continue
                    if lang_key == "en":
                        term = term.lower()
                    out.append(term)
                    out.append(f"{layer_name}:{term}")
        return self._dedupe_list(out)

    @staticmethod
    def _dedupe_list(items: Iterable[str]) -> List[str]:
        out = []
        seen = set()
        for item in items:
            text = str(item or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
        return out

    @staticmethod
    def _contains_cjk(text: str) -> bool:
        return bool(re.search(r"[\u4e00-\u9fff]", text or ""))

    @staticmethod
    def _split_filename_tokens(stem: str) -> List[str]:
        raw = re.split(r"[_\-\s\.\(\)\[\],]+", stem or "")
        tokens = []
        for part in raw:
            t = part.strip()
            if not t:
                continue
            if len(t) == 1 and not CoreMixin._contains_cjk(t):
                continue
            tokens.append(t)
        return tokens

    def _split_path_tokens(self, path: Path, depth: int = 6) -> List[str]:
        try:
            parts = list(path.parts)
        except Exception:
            return []
        out: List[str] = []
        for part in parts[-max(depth, 1):]:
            p = str(part).strip().replace("\\", "/")
            if not p or p in {"/", "."}:
                continue
            leaf = Path(p).stem if "." in p else p
            out.extend(self._split_filename_tokens(leaf))
        return self._dedupe_list(out)

    def _metadata_terms(self, tags: Dict) -> List[str]:
        if not isinstance(tags, dict):
            return []
        terms: List[str] = []
        for k, v in tags.items():
            key = str(k or "").strip().lower()
            val = str(v or "").strip()
            if not key or not val:
                continue
            val = val[:160]
            terms.append(val)
            terms.extend(self._split_filename_tokens(val))
            if any(
                marker in key
                for marker in (
                    "location", "title", "comment", "description",
                    "keyword", "subject", "artist", "make", "model",
                    "software", "copyright", "com.apple.quicktime",
                )
            ):
                terms.append(key.replace("_", " "))
                terms.append(f"{key}:{val}")
        return self._dedupe_list(terms)

    @staticmethod
    def _query_synonyms(token: str) -> List[str]:
        t = str(token or "").strip().lower()
        if not t:
            return []
        rules = [
            (["教堂", "大教堂", "教会", "church", "cathedral", "chapel", "basilica"],
             ["教堂", "大教堂", "church", "cathedral", "chapel", "basilica", "教会", "宗教建筑", "朝圣"]),
            (["哥特", "哥特式", "gothic"],
             ["哥特", "哥特式", "gothic", "gothic architecture", "尖拱", "飞扶壁"]),
            (["铁桥", "钢桥", "桥梁", "桥", "bridge", "viaduct", "overpass", "大桥", "拱桥"],
             ["铁桥", "桥", "bridge", "iron bridge", "steel bridge", "viaduct", "overpass", "大桥", "拱桥"]),
            (["城堡", "castle", "fortress"],
             ["城堡", "castle", "fortress", "古堡", "中世纪"]),
            (["寺庙", "庙", "temple", "shrine"],
             ["寺庙", "temple", "shrine", "古建筑", "religious"]),
            (["修道院", "monastery", "abbey"],
             ["修道院", "monastery", "abbey", "church"]),
            (["清真寺", "mosque"],
             ["清真寺", "mosque", "religious", "宗教建筑"]),
            (["塔", "塔楼", "tower", "bell tower"],
             ["塔", "塔楼", "tower", "地标", "landmark"]),
            (["雕像", "雕塑", "statue", "sculpture"],
             ["雕像", "雕塑", "statue", "sculpture", "landmark"]),
            (["山", "高山", "mountain", "alpine"],
             ["山地", "高山", "mountain", "alpine"]),
            (["海滩", "沙滩", "beach", "coast", "shore"],
             ["海滩", "沙滩", "海边", "beach", "coast"]),
            (["森林", "树林", "forest", "woods"],
             ["森林", "树林", "forest", "woods"]),
        ]
        out: List[str] = []
        for keys, vals in rules:
            if any(k in t for k in keys):
                out.extend(vals)
        return out

    @staticmethod
    def _label_aliases() -> Dict[str, List[str]]:
        return {
            "mountain": ["mountain", "alpine", "高山", "山地", "雪山"],
            "beach": ["beach", "ocean", "coast", "海边", "沙滩", "海岸"],
            "city": ["city", "urban", "street", "城市", "街头", "城区"],
            "forest": ["forest", "woods", "tree", "森林", "树林"],
            "waterfall": ["waterfall", "river", "stream", "瀑布", "河流", "溪流"],
            "snow": ["snow", "ice", "winter", "雪地", "冰川", "滑雪"],
            "indoor": ["indoor", "room", "室内", "房间"],
            "walking": ["walk", "hike", "徒步", "散步", "行走"],
            "sports": ["sports", "ski", "snowboard", "运动", "滑雪", "冲浪"],
            "driving": ["drive", "car", "road", "驾驶", "公路"],
            "talking": ["talk", "speak", "vlog", "解说", "讲述"],
            "food": ["food", "eat", "cook", "美食", "探店", "餐厅"],
            "scenic": ["scenic", "landscape", "风景", "航拍", "观景"],
            "aerial": ["aerial", "drone", "航拍", "无人机"],
            "tracking": ["tracking", "follow", "跟拍", "追踪"],
            "handheld": ["handheld", "手持"],
            "static": ["static", "tripod", "固定机位", "静止"],
            "close_up": ["close-up", "特写", "近景"],
            "medium": ["medium shot", "中景"],
            "wide": ["wide", "landscape", "全景", "远景", "大景"],
            "macro": ["macro", "微距"],
            "first_person": ["first person", "fpv", "第一视角", "主观视角"],
            "third_person": ["third person", "第三视角"],
            "drone_view": ["drone view", "航拍视角", "俯拍"],
            "eye_level": ["eye level", "平视"],
            "warm": ["warm", "golden", "暖色", "金色"],
            "cool": ["cool", "blue", "冷色", "蓝调"],
            "high_contrast": ["contrast", "高对比", "强烈光影"],
            "natural": ["natural", "neutral", "自然色"],
            "morning": ["morning", "sunrise", "清晨", "早上", "日出"],
            "afternoon": ["afternoon", "noon", "中午", "午后"],
            "sunset": ["sunset", "dusk", "黄昏", "日落", "傍晚"],
            "night": ["night", "evening", "夜景", "夜晚", "晚上"],
            "rain": ["rain", "storm", "雨天", "下雨"],
            "fog": ["fog", "mist", "雾天", "薄雾"],
            "sunny": ["sunny", "sunlight", "晴天", "阳光"],
            "cloudy": ["cloudy", "overcast", "阴天", "多云"],
            "travel_vlog": ["travel vlog", "旅行vlog", "旅拍", "旅行记录"],
            "action_montage": ["action montage", "动作剪辑", "燃向混剪"],
            "landmark_story": ["landmark story", "地标故事", "建筑地标", "人文地标", "architecture story"],
            "atmospheric_broll": ["atmospheric broll", "氛围空镜", "治愈空镜"],
            "hero_shot": ["hero shot", "主视觉", "主打镜头"],
            "storytelling_clip": ["storytelling", "叙事镜头", "口播讲述"],
            "hook": ["hook", "开场钩子", "前三秒"],
            "establishing": ["establishing shot", "环境建立镜头", "开场全景"],
            "climax": ["climax", "高潮段", "高能"],
            "explanation": ["explanation", "讲解段", "信息段"],
            "broll": ["b-roll", "过渡镜头", "补充素材"],
            "portrait": ["portrait", "竖屏", "9:16"],
            "landscape": ["landscape", "横屏", "16:9"],
            "square": ["square", "方屏", "1:1"],
            "church": ["church", "cathedral", "chapel", "basilica", "教堂", "大教堂"],
            "gothic": ["gothic", "gothic style", "哥特", "哥特式", "尖拱", "飞扶壁"],
            "bridge": ["bridge", "iron bridge", "steel bridge", "viaduct", "桥", "铁桥", "钢桥", "桥梁"],
            "castle": ["castle", "fortress", "城堡", "古堡", "中世纪建筑"],
            "temple": ["temple", "shrine", "寺庙", "神社", "宗教建筑"],
            "architecture": ["architecture", "building", "建筑", "地标", "landmark"],
            "religious": ["religious", "church", "cathedral", "宗教", "教堂", "寺庙"],
        }

    def _expand_label_aliases(self, labels: Iterable[str]) -> List[str]:
        aliases = self._label_aliases()
        expanded = []
        for label in labels:
            key = str(label or "").strip()
            if not key:
                continue
            expanded.append(key)
            expanded.extend(aliases.get(key, []))
        return self._dedupe_list(expanded)

    @staticmethod
    def _contains_any(text: str, terms: List[str]) -> bool:
        t = text.lower()
        return any(term in t for term in terms)

    @staticmethod
    def _infer_by_keyword(text: str, mapping: Dict[str, List[str]], default: str = "unknown") -> str:
        t = text.lower()
        best_label = default
        best_score = 0
        for label, terms in mapping.items():
            score = 0
            for term in terms:
                if term in t:
                    score += 1
            if score > best_score:
                best_score = score
                best_label = label
        return best_label

    def _infer_time_of_day(self, creation_time: Optional[str], text: str) -> str:
        t = text.lower()
        if self._contains_any(t, ["sunrise", "dawn", "morning", "清晨", "早上", "日出"]):
            return "morning"
        if self._contains_any(t, ["afternoon", "noon", "中午", "午后"]):
            return "afternoon"
        if self._contains_any(t, ["sunset", "dusk", "golden hour", "傍晚", "黄昏", "日落"]):
            return "sunset"
        if self._contains_any(t, ["night", "evening", "夜晚", "晚上", "深夜"]):
            return "night"

        if creation_time and "T" in creation_time:
            try:
                s = str(creation_time)
                # Only use hour-based classification when the timestamp has NO timezone info,
                # meaning it was already stored as local time (e.g. exiftool output, image mtime).
                # UTC timestamps (ending with Z or +00:00) cannot be reliably converted to
                # shooting-location local time, so return "unknown" to avoid misclassification
                # (e.g. iPhone video shot at 10am China time stored as 02:00Z → "night" is wrong).
                has_tz = s.endswith("Z") or "+" in s[10:] or s.endswith("+00:00")
                if has_tz:
                    return "unknown"
                hour = int(s.split("T", 1)[1][:2])
                if 5 <= hour < 11:
                    return "morning"
                if 11 <= hour < 16:
                    return "afternoon"
                if 16 <= hour < 20:
                    return "sunset"
                return "night"
            except Exception:
                pass
        return "unknown"

    @staticmethod
    def _infer_emotion_intensity(mood: str, text: str) -> str:
        source = f"{mood} {text}".lower()
        if any(k in source for k in ["intense", "energetic", "excited", "紧张", "激烈", "刺激"]):
            return "high"
        if any(k in source for k in ["calm", "serene", "gentle", "平静", "舒缓", "治愈"]):
            return "low"
        return "medium"

    @staticmethod
    def _infer_quality_tier(quality_score) -> str:
        try:
            q = float(quality_score)
        except Exception:
            return "unknown"
        if q >= 0.85:
            return "high"
        if q >= 0.65:
            return "medium"
        return "low"

    @staticmethod
    def _infer_season(text: str) -> str:
        t = text.lower()
        if any(k in t for k in ["winter", "snow", "ice", "冬", "雪"]):
            return "winter"
        if any(k in t for k in ["spring", "blossom", "花", "春"]):
            return "spring"
        if any(k in t for k in ["summer", "beach", "sunny", "夏", "海边"]):
            return "summer"
        if any(k in t for k in ["autumn", "fall", "枫", "秋"]):
            return "autumn"
        return "unknown"

    @staticmethod
    def _infer_lighting(time_of_day: str, weather: str, text: str) -> str:
        t = text.lower()
        if "backlit" in t or "逆光" in t:
            return "backlit"
        if weather == "fog":
            return "diffused"
        if weather == "night" or time_of_day == "night":
            return "low_light"
        if time_of_day in {"sunrise", "sunset"}:
            return "golden_hour"
        if weather == "sunny":
            return "hard_light"
        return "natural_light"

    @staticmethod
    def _infer_duration_bucket(duration_seconds: float) -> str:
        if duration_seconds <= 0:
            return "unknown"
        if duration_seconds <= 3:
            return "ultra_short"
        if duration_seconds <= 8:
            return "short"
        if duration_seconds <= 20:
            return "medium"
        if duration_seconds <= 60:
            return "long"
        return "extended"

    @staticmethod
    def _infer_orientation(width: Optional[int], height: Optional[int]) -> tuple[str, str]:
        if not width or not height:
            return "unknown", "unknown"
        ratio = float(width) / float(height)
        if ratio < 0.8:
            return "portrait", "9:16_like"
        if ratio > 1.3:
            return "landscape", "16:9_like"
        return "square", "1:1_like"

    @staticmethod
    def _infer_content_type(activity: str, people_presence: str, setting: str, visual_style: str) -> str:
        if activity == "talking":
            return "talking_head"
        if activity == "architecture_tour" or setting in {"church", "bridge", "castle", "temple"}:
            return "architecture_documentary"
        if activity in {"sports", "driving"}:
            return "action"
        if setting in {"mountain", "beach", "forest", "waterfall", "snow"}:
            return "scenery"
        if visual_style in {"vlog", "travel"} and people_presence == "present":
            return "travel_lifestyle"
        return "general"

    @staticmethod
    def _infer_action_intensity(activity: str, camera_movement: str, emotion_intensity: str) -> str:
        if activity in {"sports", "driving"}:
            return "high"
        if camera_movement in {"tracking", "handheld"} and emotion_intensity == "high":
            return "high"
        if activity in {"walking", "scenic"}:
            return "medium"
        return "low"

    @staticmethod
    def _infer_stability_level(camera_movement: str, action_intensity: str) -> str:
        if camera_movement in {"static", "pan_tilt"} and action_intensity != "high":
            return "stable"
        if camera_movement in {"handheld", "tracking"} or action_intensity == "high":
            return "dynamic"
        return "balanced"

    @staticmethod
    def _infer_audience_intent(content_type: str, activity: str, narrative_role: str) -> str:
        if activity == "talking" or narrative_role == "explanation":
            return "information"
        if content_type == "architecture_documentary" or activity == "architecture_tour":
            return "information"
        if content_type in {"scenery", "travel_lifestyle"}:
            return "inspiration"
        if content_type == "action":
            return "entertainment"
        return "general"

    @staticmethod
    def _infer_clip_purpose(narrative_role: str, use_cases: List[str]) -> str:
        if narrative_role == "hook":
            return "opening"
        if narrative_role == "establishing":
            return "context"
        if narrative_role == "climax":
            return "highlight"
        if "atmospheric_broll" in use_cases:
            return "transition"
        return "supporting"

    @staticmethod
    def _tokenize_query(query: str) -> List[str]:
        raw = re.split(r"[\s,，;；|/]+", query.strip().lower())
        tokens: List[str] = []
        for part in raw:
            p = part.strip()
            if not p:
                continue
            tokens.append(p)
            if re.search(r"[\u4e00-\u9fff]", p) and len(p) >= 4:
                for n in (2, 3, 4):
                    for i in range(0, len(p) - n + 1):
                        tokens.append(p[i:i + n])
        deduped = []
        seen = set()
        for t in tokens:
            if len(t) <= 1:
                continue
            if t in seen:
                continue
            seen.add(t)
            deduped.append(t)

        expanded = list(deduped)
        for t in deduped:
            expanded.extend(CoreMixin._query_synonyms(t))

        final = []
        seen2 = set()
        for t in expanded:
            text = str(t or "").strip().lower()
            if len(text) <= 1:
                continue
            if text in seen2:
                continue
            seen2.add(text)
            final.append(text)
        return final[:120]

    @staticmethod
    def _relaxed_query_tokens(tokens: List[str]) -> List[str]:
        raw = [str(t or "").strip().lower() for t in tokens if str(t or "").strip()]
        if not raw:
            return []
        out = list(raw)
        token_text = " ".join(raw)
        if any(k in token_text for k in ["教堂", "church", "cathedral", "chapel", "basilica", "religious", "朝圣"]):
            out.extend(["architecture", "religious", "building", "landmark", "城市", "建筑", "朝圣"])
        if any(k in token_text for k in ["哥特", "gothic"]):
            out.extend(["gothic", "architecture", "building", "中世纪", "castle", "cathedral", "古建筑"])
        if any(k in token_text for k in ["铁桥", "桥", "bridge", "viaduct", "overpass"]):
            out.extend(["bridge", "river", "water", "city", "architecture", "landscape", "桥"])

        dedup = []
        seen = set()
        for t in out:
            if t in seen:
                continue
            seen.add(t)
            dedup.append(t)
        return dedup[:80]

    # ── Phase 2: Evidence persistence + tag resolution ──

    # Sentinel: returned by _resolve_tag_id when term is a stopword
    _STOPWORD_SENTINEL = -1

    def _resolve_tag_id(
        self, term: str, conn: sqlite3.Connection, *, _cache: Optional[Dict] = None,
        context: str = "ingest",
    ) -> Optional[int]:
        """Resolve a term to a tag_id via the matching chain.

        Chain: stopword → exact tag_name → normalized_name → alias → custom_tag.
        Returns tag_id, _STOPWORD_SENTINEL (-1) for stopwords, or None for unknown.

        context="ingest": existing behaviour (may write learning_candidate in future).
        context="search": purely read-only, no side-effects.
        """
        if not term or not term.strip():
            return None
        normalized = term.lower().strip()
        if len(normalized) < 2:
            return None

        # Check cache first
        if _cache is not None and normalized in _cache:
            return _cache[normalized]

        # 1. Stopword check
        stop = conn.execute(
            "SELECT 1 FROM learning_stopword WHERE normalized_text = ?",
            (normalized,),
        ).fetchone()
        if stop:
            if _cache is not None:
                _cache[normalized] = self._STOPWORD_SENTINEL
            return self._STOPWORD_SENTINEL

        # 2. Exact match tag.tag_name
        row = conn.execute(
            "SELECT tag_id FROM tag WHERE tag_name = ? AND is_active = 1 LIMIT 1",
            (term.strip(),),
        ).fetchone()
        if row:
            tid = row[0]
            if _cache is not None:
                _cache[normalized] = tid
            return tid

        # 3. Normalized match
        row = conn.execute(
            "SELECT tag_id FROM tag WHERE normalized_name = ? AND is_active = 1 LIMIT 1",
            (normalized,),
        ).fetchone()
        if row:
            tid = row[0]
            if _cache is not None:
                _cache[normalized] = tid
            return tid

        # 4. Alias match
        row = conn.execute(
            "SELECT tag_id FROM tag_alias WHERE normalized_alias = ? LIMIT 1",
            (normalized,),
        ).fetchone()
        if row:
            tid = row[0]
            if _cache is not None:
                _cache[normalized] = tid
            return tid

        # 5. Custom tag match
        row = conn.execute(
            "SELECT parent_system_tag_id FROM custom_tag WHERE normalized_name = ? AND status != 'archived' LIMIT 1",
            (normalized,),
        ).fetchone()
        if row and row[0]:
            tid = row[0]
            if _cache is not None:
                _cache[normalized] = tid
            return tid

        # No match
        if _cache is not None:
            _cache[normalized] = None
        return None

    # ── Phase 3: helpers for tag recall ──

    def _classify_resolution(
        self, term: str, tag_id: int, conn: sqlite3.Connection,
    ) -> str:
        """Classify how *term* resolved to *tag_id*.

        Returns one of: exact, normalized, alias, custom.
        """
        normalized = term.lower().strip()
        row = conn.execute(
            "SELECT tag_name, normalized_name FROM tag WHERE tag_id = ? LIMIT 1",
            (tag_id,),
        ).fetchone()
        if row:
            if row[0] == term.strip():
                return "exact"
            if row[1] == normalized:
                return "normalized"
        alias_row = conn.execute(
            "SELECT 1 FROM tag_alias WHERE tag_id = ? AND normalized_alias = ? LIMIT 1",
            (tag_id, normalized),
        ).fetchone()
        if alias_row:
            return "alias"
        custom_row = conn.execute(
            "SELECT 1 FROM custom_tag WHERE parent_system_tag_id = ? AND normalized_name = ? LIMIT 1",
            (tag_id, normalized),
        ).fetchone()
        if custom_row:
            return "custom"
        return "exact"  # fallback

    _tag_name_cache: Dict[int, str] = {}

    def _get_tag_name_cached(self, tag_id: int, conn: sqlite3.Connection) -> str:
        """Return tag_name for tag_id, using instance-level cache."""
        if tag_id in self._tag_name_cache:
            return self._tag_name_cache[tag_id]
        row = conn.execute(
            "SELECT tag_name FROM tag WHERE tag_id = ? LIMIT 1", (tag_id,),
        ).fetchone()
        name = row[0] if row else f"tag_{tag_id}"
        self._tag_name_cache[tag_id] = name
        return name

    def _classify_query(
        self,
        query: str,
        resolved_tags: Dict[str, int],
        resolution_info: Dict[str, Dict],
        conn: sqlite3.Connection,
    ) -> str:
        """Classify query type for dynamic weight selection.

        Returns: exact_tag | alias_tag | composed_query | abstract_intent
        """
        n_resolved = len(resolved_tags)

        if n_resolved >= 2:
            return "composed_query"

        if n_resolved == 0:
            return "abstract_intent"

        # n_resolved == 1: check for abstract intent signals
        q_lower = query.lower()
        if any(kw in q_lower for kw in ABSTRACT_INTENT_KEYWORDS):
            return "abstract_intent"

        # Single resolved tag — classify by hit_type
        info = next(iter(resolution_info.values()), {})
        hit_type = info.get("hit_type", "exact")
        if hit_type in ("exact", "normalized"):
            return "exact_tag"
        if hit_type in ("alias", "custom"):
            return "alias_tag"
        return "exact_tag"

    def _persist_evidence_and_tags(
        self, uid: str, semantic_json: Dict, conn: sqlite3.Connection,
    ) -> int:
        """Dual-write: persist evidence + compute & write asset_tag_result.

        Extracts terms from structured_tags and flat semantic fields,
        resolves to tag_id, computes scores with rule corrections,
        writes evidence + asset_tag_result rows.

        Returns the number of tag results written.
        """
        if not semantic_json or not isinstance(semantic_json, dict):
            return 0

        structured_tags = semantic_json.get("structured_tags", {})
        if not isinstance(structured_tags, dict):
            return 0
        tags_dict = structured_tags.get("tags", structured_tags)
        if not isinstance(tags_dict, dict):
            return 0

        now = self._now()
        tag_cache = {}  # term → tag_id (per-call resolution cache)
        tag_scores = {}  # tag_id → {base_score, source_summary, slot, term, decision_reasons}
        unresolved = []  # (term, category_hint)
        model_version = (semantic_json.get("_meta") or {}).get("model_version", "unknown")

        # ── Idempotency: clear prior evidence for this asset ──
        try:
            conn.execute("DELETE FROM evidence WHERE asset_id = ?", (uid,))
        except Exception:
            pass

        # ── A. Extract from structured_tags (25 categories) ──
        for cat, cat_data in tags_dict.items():
            if not isinstance(cat_data, dict):
                continue
            zh_terms = cat_data.get("zh", [])
            if not isinstance(zh_terms, list):
                continue
            confidence = float(cat_data.get("confidence", 0.6))
            slot = _TAG_CATEGORY_TO_SLOT.get(cat, "object")

            for term in zh_terms:
                if not isinstance(term, str) or not term.strip():
                    continue
                tag_id = self._resolve_tag_id(term, conn, _cache=tag_cache)
                if tag_id is None or tag_id == self._STOPWORD_SENTINEL:
                    if tag_id is None:  # genuinely unknown → learning candidate
                        t = term.strip()
                        if t and len(t) >= 2:
                            unresolved.append((t, cat))
                    # stopword → silently skip (no learning_candidate)
                    continue

                source_weight = SCORING_CONFIG["source_weight"].get("llm", 1.0)
                weighted = min(confidence * source_weight, 1.0)

                # Write evidence (one per tag per source_kind)
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO evidence
                           (asset_id, tag_id, semantic_slot, source_kind, source_model,
                            raw_value, base_score, weighted_score, created_at)
                           VALUES (?, ?, ?, 'llm', ?, ?, ?, ?, ?)""",
                        (uid, tag_id, slot, model_version,
                         term, confidence, weighted, now),
                    )
                except Exception:
                    pass

                # Keep best score per tag_id
                if tag_id not in tag_scores or weighted > tag_scores[tag_id]["base_score"]:
                    tag_scores[tag_id] = {
                        "base_score": weighted,
                        "source_summary": "llm",
                        "slot": slot,
                        "term": term,
                    }

        # ── B. Extract from flat semantic fields ──
        for field, slot in _FIELD_TO_SLOT.items():
            val = semantic_json.get(field)
            if not val or not isinstance(val, str) or val in ("unknown", "general", "none"):
                continue
            tag_id = self._resolve_tag_id(val, conn, _cache=tag_cache)
            if tag_id and tag_id != self._STOPWORD_SENTINEL and tag_id not in tag_scores:
                source_weight = SCORING_CONFIG["source_weight"].get("llm", 1.0)
                weighted = min(0.70 * source_weight, 1.0)
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO evidence
                           (asset_id, tag_id, semantic_slot, source_kind, source_model,
                            raw_value, base_score, weighted_score, created_at)
                           VALUES (?, ?, ?, 'llm', ?, ?, ?, ?, ?)""",
                        (uid, tag_id, slot, model_version, val, 0.70, weighted, now),
                    )
                except Exception:
                    pass
                tag_scores[tag_id] = {
                    "base_score": weighted,
                    "source_summary": "llm",
                    "slot": slot,
                    "term": val,
                }

        # ── C. Rule corrections ──
        tag_ids_present = set(tag_scores.keys())

        # C1. Hierarchy bonus — child confirmed → parent gets bonus
        hierarchy_bonus = {}
        for tag_id in list(tag_ids_present):
            parents = conn.execute(
                "SELECT to_tag_id FROM tag_relation WHERE from_tag_id = ? AND relation_type = 'child'",
                (tag_id,),
            ).fetchall()
            for pr in parents:
                pid = pr[0]
                hierarchy_bonus[pid] = max(
                    hierarchy_bonus.get(pid, 0.0),
                    SCORING_CONFIG["hierarchy_bonus"],
                )

        # C2. Conflict penalty — conflicting tags penalize each other
        conflict_penalty = {}
        for tag_id in list(tag_ids_present):
            conflicts = conn.execute(
                "SELECT to_tag_id FROM tag_relation WHERE from_tag_id = ? AND relation_type = 'conflict'",
                (tag_id,),
            ).fetchall()
            for cr in conflicts:
                if cr[0] in tag_ids_present:
                    conflict_penalty[tag_id] = max(
                        conflict_penalty.get(tag_id, 0.0),
                        SCORING_CONFIG["conflict_penalty"],
                    )
                    conflict_penalty[cr[0]] = max(
                        conflict_penalty.get(cr[0], 0.0),
                        SCORING_CONFIG["conflict_penalty"],
                    )

        # C3. Cooccurrence bonus
        cooccurrence_bonus = {}
        cooc_rules = conn.execute(
            "SELECT target_tag_id, min_match_count, score_bonus, expr_json "
            "FROM composite_rule WHERE rule_type = 'cooccurrence' AND is_active = 1",
        ).fetchall()
        for rule in cooc_rules:
            expr = json.loads(rule[3] or "{}")
            if_tags = expr.get("if_tags", [])
            matched = 0
            for t in if_tags:
                resolved = self._resolve_tag_id(t, conn, _cache=tag_cache)
                if resolved and resolved in tag_ids_present:
                    matched += 1
            if matched >= rule[1]:
                target = rule[0]
                cooccurrence_bonus[target] = max(
                    cooccurrence_bonus.get(target, 0.0),
                    rule[2],
                )

        # C4. Negative penalty
        negative_penalty = {}
        neg_rules = conn.execute(
            "SELECT target_tag_id, penalty_value, expr_json "
            "FROM composite_rule WHERE rule_type = 'negative' AND is_active = 1",
        ).fetchall()
        for rule in neg_rules:
            target = rule[0]
            if target not in tag_ids_present:
                continue
            expr = json.loads(rule[2] or "{}")
            penalty_val = rule[1]
            # require_any: target tag needs at least one support tag
            require_any = expr.get("require_any", [])
            if require_any:
                has_support = any(
                    self._resolve_tag_id(t, conn, _cache=tag_cache) in tag_ids_present
                    for t in require_any
                )
                if not has_support:
                    negative_penalty[target] = max(
                        negative_penalty.get(target, 0.0), penalty_val,
                    )
            # negative_any: if negative tag is present, penalize target
            negative_any = expr.get("negative_any", [])
            for neg_term in negative_any:
                neg_id = self._resolve_tag_id(neg_term, conn, _cache=tag_cache)
                if neg_id and neg_id in tag_ids_present:
                    negative_penalty[target] = max(
                        negative_penalty.get(target, 0.0), penalty_val,
                    )

        # ── D. Write asset_tag_result ──
        write_threshold = SCORING_CONFIG["write_threshold"]
        display_threshold = SCORING_CONFIG["display_threshold"]
        bands = SCORING_CONFIG["confidence_bands"]
        written = 0

        for tag_id, info in tag_scores.items():
            base = info["base_score"]
            cooc = cooccurrence_bonus.get(tag_id, 0.0)
            hier = hierarchy_bonus.get(tag_id, 0.0)
            conf = conflict_penalty.get(tag_id, 0.0)
            neg = negative_penalty.get(tag_id, 0.0)

            final_score = max(0.0, min(1.0, base + cooc + hier - conf - neg))
            effective_score = max(0.0, min(1.0, final_score))  # user_adjustment=0 initially

            if effective_score < write_threshold:
                continue

            if effective_score >= bands["high"]:
                band = "high"
            elif effective_score >= bands["medium"]:
                band = "medium"
            else:
                band = "low"

            is_displayed = 1 if effective_score >= display_threshold else 0
            decision_reason = json.dumps(
                [{"source": info["source_summary"], "term": info["term"],
                  "score": round(base, 3)}],
                ensure_ascii=False,
            )

            try:
                conn.execute(
                    """INSERT OR REPLACE INTO asset_tag_result
                       (asset_id, segment_id, tag_id, result_scope,
                        base_score, source_bonus, cooccurrence_bonus, hierarchy_bonus,
                        conflict_penalty, negative_penalty,
                        final_score, user_adjustment, effective_score,
                        rank_no, is_displayed, source_summary, confidence_band,
                        user_confirm_state, decision_reason, created_at, updated_at)
                       VALUES (?, '', ?, 'asset',
                               ?, 0.0, ?, ?,
                               ?, ?,
                               ?, 0.0, ?,
                               0, ?, ?, ?,
                               'none', ?, ?, ?)""",
                    (uid, tag_id,
                     base, cooc, hier,
                     conf, neg,
                     final_score, effective_score,
                     is_displayed, info["source_summary"], band,
                     decision_reason, now, now),
                )
                written += 1
            except Exception:
                pass

        # ── E. Write unresolved terms to learning_candidate ──
        for term, cat in unresolved:
            normalized = term.lower().strip()
            try:
                conn.execute(
                    """INSERT INTO learning_candidate
                       (candidate_text, normalized_text, category_hint, source_kind,
                        occurrence_count, asset_count)
                       VALUES (?, ?, ?, 'llm', 1, 1)
                       ON CONFLICT(normalized_text, source_kind) DO UPDATE SET
                           occurrence_count = occurrence_count + 1,
                           asset_count = asset_count + 1""",
                    (term, normalized, cat),
                )
            except Exception:
                pass

        # ── F. Enforce evidence limits ──
        ev_count = conn.execute(
            "SELECT count(*) FROM evidence WHERE asset_id = ?", (uid,),
        ).fetchone()[0]
        if ev_count > EVIDENCE_LIMITS["max_per_asset"]:
            conn.execute(
                """DELETE FROM evidence WHERE evidence_id IN (
                       SELECT evidence_id FROM evidence
                       WHERE asset_id = ?
                       ORDER BY weighted_score ASC
                       LIMIT ?
                   )""",
                (uid, ev_count - EVIDENCE_LIMITS["max_per_asset"]),
            )

        return written

    def _build_semantic_bundle(
        self,
        path: Path,
        analysis: Dict,
        scene_description: Optional[str],
        mood: Optional[str],
        objects: List[str],
        quality_score,
    ) -> Dict:
        metadata = analysis.get("metadata", {}) if isinstance(analysis, dict) else {}
        local = analysis.get("local_analysis", {}) if isinstance(analysis, dict) else {}
        technical = local.get("technical", {}) if isinstance(local, dict) else {}
        tags = metadata.get("tags") if isinstance(metadata, dict) else {}
        tags = tags if isinstance(tags, dict) else {}
        tag_values = [str(v).strip() for v in tags.values() if isinstance(v, (str, int, float))]
        metadata_terms = self._metadata_terms(tags)
        recommendations = analysis.get("recommendations", []) if isinstance(analysis, dict) else []
        rec_text = " ".join(
            f"{str(r.get('type', ''))} {str(r.get('priority', ''))} {str(r.get('message', ''))} {str(r.get('action', ''))}"
            for r in recommendations
            if isinstance(r, dict)
        )

        scene_text = str(scene_description or "")
        mood_text = str(mood or "")
        object_list = [str(o).strip() for o in (objects or []) if str(o).strip()]
        object_text = " ".join(object_list)
        filename_text = path.stem
        filename_tokens = self._split_filename_tokens(filename_text)
        path_tokens = self._split_path_tokens(path)

        duration_f = 0.0
        try:
            duration_f = float(metadata.get("duration") or 0.0)
        except Exception:
            duration_f = 0.0

        width, height = self._parse_resolution(technical.get("resolution"))
        streams = metadata.get("video_streams") if isinstance(metadata, dict) else []
        if (not width or not height) and isinstance(streams, list) and streams:
            first_stream = streams[0] if isinstance(streams[0], dict) else {}
            try:
                width = width or int(first_stream.get("width") or 0)
                height = height or int(first_stream.get("height") or 0)
            except Exception:
                pass

        scene_visual = {}
        if isinstance(local, dict):
            scene_local = local.get("scene", {})
            if isinstance(scene_local, dict):
                raw_visual = scene_local.get("visual_features", {})
                if isinstance(raw_visual, dict):
                    scene_visual = raw_visual

        def _vf(key: str, default: float) -> float:
            try:
                return float(scene_visual.get(key, default))
            except Exception:
                return default

        brightness_v = _vf("brightness", 0.5)
        saturation_v = _vf("saturation", 0.35)
        edge_v = _vf("edge_density", 0.1)
        motion_v = _vf("motion_score", 0.0)
        face_ratio_v = _vf("face_ratio", 0.0)
        red_ratio_v = _vf("red_ratio", 0.33)
        green_ratio_v = _vf("green_ratio", 0.33)
        blue_ratio_v = _vf("blue_ratio", 0.33)

        if blue_ratio_v >= green_ratio_v and blue_ratio_v >= red_ratio_v:
            dominant_color = "blue_dominant"
        elif green_ratio_v >= red_ratio_v:
            dominant_color = "green_dominant"
        else:
            dominant_color = "red_dominant"

        if brightness_v >= 0.72:
            brightness_level = "bright"
        elif brightness_v <= 0.38:
            brightness_level = "dim"
        else:
            brightness_level = "balanced_brightness"

        if saturation_v >= 0.48:
            saturation_level = "vivid"
        elif saturation_v <= 0.26:
            saturation_level = "desaturated"
        else:
            saturation_level = "neutral_saturation"

        if motion_v >= 24.0:
            motion_level = "fast_motion"
        elif motion_v >= 10.0:
            motion_level = "moderate_motion"
        else:
            motion_level = "static_motion"

        if edge_v >= 0.16:
            texture_complexity = "complex_texture"
        elif edge_v <= 0.07:
            texture_complexity = "simple_texture"
        else:
            texture_complexity = "medium_texture"

        if face_ratio_v >= 0.30:
            face_presence_level = "high_face_presence"
        elif face_ratio_v >= 0.10:
            face_presence_level = "medium_face_presence"
        else:
            face_presence_level = "low_face_presence"

        inferred_arch_tokens = []
        corpus_seed = " ".join(
            [
                filename_text,
                " ".join(filename_tokens),
                " ".join(path_tokens),
                " ".join(metadata_terms),
                scene_text,
                mood_text,
                object_text,
                " ".join(tag_values),
                rec_text,
            ]
        ).lower()
        if self._contains_any(corpus_seed, ["教堂", "church", "cathedral", "chapel", "basilica", "朝圣", "pilgrimage", "圣地", "holy"]):
            inferred_arch_tokens.extend(["church", "architecture", "religious"])
        if self._contains_any(corpus_seed, ["哥特", "gothic"]):
            inferred_arch_tokens.extend(["gothic", "architecture"])
        if self._contains_any(corpus_seed, ["铁桥", "钢桥", "桥", "bridge", "viaduct", "overpass", "大桥", "拱桥"]):
            inferred_arch_tokens.extend(["bridge", "architecture"])
        if self._contains_any(corpus_seed, ["城堡", "castle", "fortress"]):
            inferred_arch_tokens.extend(["castle", "architecture"])
        if self._contains_any(corpus_seed, ["寺庙", "temple", "shrine", "修道院", "monastery"]):
            inferred_arch_tokens.extend(["temple", "religious", "architecture"])
        if inferred_arch_tokens:
            object_list = self._dedupe_list(object_list + inferred_arch_tokens)
            object_text = " ".join(object_list)

        corpus = " ".join(
            [
                filename_text,
                " ".join(filename_tokens),
                " ".join(path_tokens),
                " ".join(metadata_terms),
                scene_text,
                mood_text,
                object_text,
                " ".join(tag_values),
                rec_text,
                dominant_color,
                brightness_level,
                saturation_level,
                motion_level,
                texture_complexity,
            ]
        ).lower()

        location_mapping = {
            "mountain": ["mountain", "alpine", "hill", "雪山", "高山", "山脉"],
            "beach": ["beach", "sea", "ocean", "coast", "沙滩", "海边", "海岸"],
            "city": ["city", "street", "urban", "building", "城市", "街头", "城区"],
            "indoor": ["indoor", "room", "studio", "kitchen", "室内", "房间", "客厅", "厨房"],
            "forest": ["forest", "tree", "woods", "树林", "森林"],
            "snow": ["snow", "ice", "winter", "滑雪", "雪地", "冰川"],
            "waterfall": ["waterfall", "river", "stream", "瀑布", "河流", "溪流"],
            "church": ["church", "cathedral", "chapel", "basilica", "教堂", "大教堂"],
            "bridge": ["bridge", "iron bridge", "steel bridge", "viaduct", "桥", "铁桥", "钢桥"],
            "castle": ["castle", "fortress", "城堡", "古堡", "要塞"],
            "temple": ["temple", "shrine", "monastery", "abbey", "寺庙", "修道院", "神社"],
        }
        activity_mapping = {
            "walking": ["walk", "walking", "hiking", "徒步", "行走"],
            "sports": ["ski", "snowboard", "surf", "run", "运动", "滑雪", "冲浪", "跑步"],
            "driving": ["drive", "car", "road", "驾驶", "公路", "车"],
            "talking": ["talk", "speak", "vlog", "分享", "解说", "讲解"],
            "food": ["food", "cook", "eat", "餐厅", "美食", "做饭", "吃"],
            "scenic": ["scenic", "landscape", "view", "风景", "观景", "航拍"],
            "architecture_tour": ["architecture", "gothic", "church", "cathedral", "bridge", "landmark", "建筑", "地标", "古建"],
        }
        style_mapping = {
            "vlog": ["vlog", "daily", "日常", "记录"],
            "cinematic": ["cinematic", "film", "大片", "电影感"],
            "documentary": ["documentary", "纪录", "采访", "讲述"],
            "tutorial": ["tutorial", "how to", "教程", "教学", "攻略"],
            "travel": ["travel", "trip", "journey", "旅行", "旅途"],
        }
        movement_mapping = {
            "aerial": ["drone", "aerial", "航拍", "俯拍"],
            "tracking": ["tracking", "follow", "跟拍", "追踪"],
            "pan_tilt": ["pan", "tilt", "横移", "摇镜"],
            "handheld": ["handheld", "手持"],
            "static": ["static", "tripod", "固定机位", "静止"],
        }
        shot_mapping = {
            "close_up": ["close-up", "close up", "特写", "近景", "portrait"],
            "medium": ["medium shot", "中景"],
            "wide": ["wide", "landscape", "远景", "全景", "大景"],
            "macro": ["macro", "微距"],
        }
        perspective_mapping = {
            "first_person": ["first person", "fpv", "第一视角", "主观视角"],
            "third_person": ["third person", "第三视角"],
            "drone_view": ["drone", "aerial", "航拍"],
            "eye_level": ["eye level", "平视"],
        }
        framing_mapping = {
            "subject_centered": ["center", "居中"],
            "rule_of_thirds": ["rule of thirds", "三分法"],
            "symmetry": ["symmetry", "对称"],
            "dynamic": ["dynamic", "动感"],
        }
        color_mapping = {
            "warm": ["warm", "golden", "sunset", "暖色", "金色"],
            "cool": ["cool", "blue", "cold", "冷色", "蓝调"],
            "high_contrast": ["contrast", "高对比", "强烈光影"],
            "natural": ["natural", "neutral", "自然色"],
        }
        weather_mapping = {
            "snow": ["snow", "blizzard", "雪", "冰"],
            "rain": ["rain", "storm", "雨", "暴雨"],
            "fog": ["fog", "mist", "雾", "薄雾"],
            "sunny": ["sunny", "sunlight", "晴天", "阳光"],
            "cloudy": ["cloud", "overcast", "阴天", "多云"],
        }

        setting = self._infer_by_keyword(corpus, location_mapping, default="general")
        activity = self._infer_by_keyword(corpus, activity_mapping, default="general")
        visual_style = self._infer_by_keyword(corpus, style_mapping, default="general")
        camera_movement = self._infer_by_keyword(corpus, movement_mapping, default="unknown")
        shot_type = self._infer_by_keyword(corpus, shot_mapping, default="unknown")
        perspective = self._infer_by_keyword(corpus, perspective_mapping, default="unknown")
        framing = self._infer_by_keyword(corpus, framing_mapping, default="unknown")
        color_tone = self._infer_by_keyword(corpus, color_mapping, default="natural")
        weather = self._infer_by_keyword(corpus, weather_mapping, default="unknown")
        location_type = "indoor" if setting == "indoor" else ("outdoor" if setting != "general" else "unknown")

        if setting == "general":
            if dominant_color == "green_dominant":
                setting = "forest"
            elif dominant_color == "blue_dominant" and "water" in object_list:
                setting = "beach"
            elif texture_complexity == "complex_texture":
                setting = "city"
            elif brightness_level == "dim":
                setting = "indoor"
        if activity == "general":
            if motion_level in {"fast_motion", "moderate_motion"}:
                activity = "walking"
            else:
                activity = "scenic"
        if weather == "unknown":
            if brightness_level == "bright":
                weather = "sunny"
            elif brightness_level == "dim" and saturation_level == "desaturated":
                weather = "cloudy"
        location_type = "indoor" if setting == "indoor" else ("outdoor" if setting != "general" else "unknown")

        creation_time = tags.get("creation_time") if isinstance(tags, dict) else None
        time_of_day = self._infer_time_of_day(str(creation_time) if creation_time else None, corpus)
        season = self._infer_season(corpus)
        lighting_condition = self._infer_lighting(time_of_day, weather, corpus)

        primary_subject = "person" if any(o.lower() == "person" for o in object_list) else (object_list[0] if object_list else "unknown")
        people_presence = "present" if any(o.lower() in {"person", "people", "human"} for o in object_list) else "none"
        if people_presence == "none" and face_presence_level in {"medium_face_presence", "high_face_presence"}:
            people_presence = "present"
            if primary_subject == "unknown":
                primary_subject = "person"
        quality_tier = self._infer_quality_tier(quality_score)
        emotion_intensity = self._infer_emotion_intensity(mood_text, corpus)

        use_cases = []
        if visual_style in {"travel", "vlog", "cinematic"} or setting in {"mountain", "beach", "city", "forest", "snow", "waterfall"}:
            use_cases.append("travel_vlog")
        if activity in {"sports", "driving"} or motion_level == "fast_motion":
            use_cases.append("action_montage")
        if setting in {"church", "bridge", "castle", "temple"} or activity == "architecture_tour":
            use_cases.append("landmark_story")
        if emotion_intensity == "low":
            use_cases.append("atmospheric_broll")
        if quality_tier == "high":
            use_cases.append("hero_shot")
        if activity == "talking":
            use_cases.append("storytelling_clip")
        if not use_cases:
            use_cases.append("general_broll")

        narrative_role = "hook" if 0 < duration_f <= 6 else "broll"
        if activity == "talking":
            narrative_role = "explanation"
        elif activity == "sports":
            narrative_role = "climax"
        elif shot_type == "wide":
            narrative_role = "establishing"

        orientation, aspect_ratio_bucket = self._infer_orientation(width, height)
        duration_bucket = self._infer_duration_bucket(duration_f)
        content_type = self._infer_content_type(activity, people_presence, setting, visual_style)
        action_intensity = self._infer_action_intensity(activity, camera_movement, emotion_intensity)
        stability_level = self._infer_stability_level(camera_movement, action_intensity)
        clip_purpose = self._infer_clip_purpose(narrative_role, use_cases)
        audience_intent = self._infer_audience_intent(content_type, activity, narrative_role)
        camera_platform = "drone" if camera_movement == "aerial" else ("vehicle" if activity == "driving" else ("tripod" if camera_movement == "static" else "handheld"))

        business_tags = []
        for rec in recommendations:
            if not isinstance(rec, dict):
                continue
            rec_type = str(rec.get("type", "")).strip().lower()
            rec_priority = str(rec.get("priority", "")).strip().lower()
            message = f"{rec.get('message', '')} {rec.get('action', '')}".lower()
            if rec_type:
                business_tags.append(rec_type)
            if rec_priority:
                business_tags.append(f"priority_{rec_priority}")
            if any(k in message for k in ["旅行", "travel", "vlog", "冒险"]):
                business_tags.append("travel_content")
            if any(k in message for k in ["教程", "教学", "guide", "攻略"]):
                business_tags.append("tutorial_content")
            if any(k in message for k in ["文化", "heritage", "教育"]):
                business_tags.append("culture_content")
        if not business_tags:
            business_tags = ["general_content"]
        business_tags = self._dedupe_list(business_tags)

        topic_labels = [
            setting,
            activity,
            visual_style,
            mood_text,
            weather,
            time_of_day,
            season,
            narrative_role,
            clip_purpose,
            content_type,
            audience_intent,
            orientation,
            duration_bucket,
            dominant_color,
            brightness_level,
            saturation_level,
            motion_level,
            texture_complexity,
            face_presence_level,
        ]
        topics = self._dedupe_list(object_list + topic_labels + use_cases + business_tags)

        label_keywords = self._expand_label_aliases(
            [
                setting,
                activity,
                visual_style,
                camera_movement,
                shot_type,
                perspective,
                framing,
                color_tone,
                weather,
                time_of_day,
                season,
                narrative_role,
                clip_purpose,
                orientation,
                content_type,
                audience_intent,
                dominant_color,
                brightness_level,
                saturation_level,
                motion_level,
                texture_complexity,
                face_presence_level,
            ]
            + use_cases
        )
        audio_streams = metadata.get("audio_streams") if isinstance(metadata, dict) else []
        audio_cues = []
        if isinstance(audio_streams, list) and audio_streams:
            audio_cues.append("audio present")
            for stream in audio_streams[:2]:
                if isinstance(stream, dict):
                    codec_name = str(stream.get("codec", "")).strip()
                    channels = stream.get("channels")
                    if codec_name:
                        audio_cues.append(codec_name)
                    if channels:
                        audio_cues.append(f"{channels}ch")

        transcript_hint = ""
        for k, v in tags.items():
            key = str(k or "").lower()
            if any(x in key for x in ("comment", "description", "lyrics", "subtitle", "transcript")):
                transcript_hint += f" {v}"
        transcript_hint = transcript_hint.strip()

        evidence_payload = {
            "video_id": str(path),
            "duration_sec": duration_f,
            "keyframes": [
                {"t": 0.0, "caption": scene_text},
                {"t": max(duration_f * 0.45, 0.0), "caption": " ".join(object_list[:8])},
                {"t": max(duration_f * 0.8, 0.0), "caption": " ".join(path_tokens[:10])},
            ],
            "ocr": [{"t": 0.0, "text": t} for t in metadata_terms[:12]],
            "transcript": transcript_hint,
            "audio_cues": audio_cues[:8],
            "objects": object_list,
            "activity": activity,
            "setting": setting,
            "mood": mood_text,
            "visual_style": visual_style,
            "camera_movement": camera_movement,
            "shot_type": shot_type,
            "perspective": perspective,
            "time_of_day": time_of_day,
            "season": season,
            "weather": weather,
            "narrative_role": narrative_role,
            "emotion_intensity": emotion_intensity,
            "use_cases": use_cases,
            "scene_description": scene_text,
            "color_tone": color_tone,
            "evidence_text": corpus,
        }
        draft_tag_schema = self._heuristic_structured_tags(evidence_payload)
        llm_tag_schema = self._llm_structured_tags(path, evidence_payload, draft_tag_schema)
        structured_tag_schema = self._normalize_structured_tags(
            llm_tag_schema if llm_tag_schema else draft_tag_schema,
            corpus,
        )
        orientation_binary = "landscape"
        if width and height and int(height) > int(width):
            orientation_binary = "portrait"
        elif orientation == "portrait":
            orientation_binary = "portrait"
        resolution_text = ""
        if width and height:
            resolution_text = f"{int(width)}x{int(height)}"
        elif resolution and "x" in str(resolution):
            resolution_text = str(resolution)
        if motion_level == "fast_motion":
            motion_level_index = "high"
        elif motion_level == "moderate_motion":
            motion_level_index = "moderate"
        else:
            motion_level_index = "low"
        tech_meta_default = {
            "orientation": orientation_binary,
            "resolution": resolution_text,
            "duration_sec": round(float(duration_f or 0.0), 3),
            "motion_level": motion_level_index,
        }
        landmark_gate = self._landmark_gate(evidence_payload)
        draft_index_layers = self._draft_index_layers_from_structured(
            structured_tags=structured_tag_schema,
            evidence=evidence_payload,
            forced_landmarks=landmark_gate,
            tech_meta_default=tech_meta_default,
        )
        llm_index_layers = self._llm_refine_index_layers(
            evidence=evidence_payload,
            draft_layers=draft_index_layers,
            landmark_gate=landmark_gate,
        )
        index_layers = self._normalize_index_layers(
            raw_layers=llm_index_layers if llm_index_layers else draft_index_layers,
            evidence=evidence_payload,
            forced_landmarks=landmark_gate,
            tech_meta_default=tech_meta_default,
        )
        structured_terms = self._flatten_structured_tag_terms(structured_tag_schema)
        index_layer_terms = self._flatten_index_layer_terms(index_layers)
        search_facets = {}
        tags_node = structured_tag_schema.get("tags", {}) if isinstance(structured_tag_schema, dict) else {}
        for cat in TAG_CATEGORIES:
            node = tags_node.get(cat, {}) if isinstance(tags_node, dict) else {}
            zh_list = node.get("zh", []) if isinstance(node, dict) else []
            en_list = node.get("en", []) if isinstance(node, dict) else []
            facets = []
            if isinstance(zh_list, list):
                facets.extend([str(x).strip() for x in zh_list if str(x).strip()])
            if isinstance(en_list, list):
                facets.extend([str(x).strip().lower() for x in en_list if str(x).strip()])
            search_facets[cat] = self._dedupe_list(facets)[:18]
        core_layer = index_layers.get("core_search_tags", {}) if isinstance(index_layers, dict) else {}
        secondary_layer = index_layers.get("secondary_tags", {}) if isinstance(index_layers, dict) else {}
        core_facets = []
        secondary_facets = []
        if isinstance(core_layer, dict):
            core_facets.extend(core_layer.get("zh", []) if isinstance(core_layer.get("zh"), list) else [])
            core_facets.extend(core_layer.get("en", []) if isinstance(core_layer.get("en"), list) else [])
        if isinstance(secondary_layer, dict):
            secondary_facets.extend(secondary_layer.get("zh", []) if isinstance(secondary_layer.get("zh"), list) else [])
            secondary_facets.extend(secondary_layer.get("en", []) if isinstance(secondary_layer.get("en"), list) else [])
        search_facets["core_search_tags"] = self._dedupe_list([str(x).strip() for x in core_facets if str(x).strip()])[:24]
        search_facets["secondary_tags"] = self._dedupe_list([str(x).strip() for x in secondary_facets if str(x).strip()])[:36]

        searchable_tags = [v for v in (tag_values + metadata_terms) if len(v) <= 72]
        search_keywords = self._dedupe_list(
            topics
            + label_keywords
            + structured_terms
            + index_layer_terms
            + [
                scene_text,
                mood_text,
                filename_text,
                primary_subject,
                location_type,
                camera_platform,
                aspect_ratio_bucket,
                stability_level,
                lighting_condition,
                dominant_color,
                brightness_level,
                saturation_level,
                motion_level,
                texture_complexity,
                face_presence_level,
            ]
            + filename_tokens
            + path_tokens
            + searchable_tags
        )
        semantic_text = " | ".join(search_keywords)

        semantic = {
            "scene_description": scene_text,
            "mood": mood_text,
            "primary_subject": primary_subject,
            "secondary_subjects": self._dedupe_list(object_list),
            "content_type": content_type,
            "activity": activity,
            "action_intensity": action_intensity,
            "setting": setting,
            "location_type": location_type,
            "time_of_day": time_of_day,
            "season": season,
            "weather": weather,
            "camera_movement": camera_movement,
            "camera_platform": camera_platform,
            "shot_type": shot_type,
            "framing": framing,
            "perspective": perspective,
            "visual_style": visual_style,
            "color_tone": color_tone,
            "lighting_condition": lighting_condition,
            "narrative_role": narrative_role,
            "clip_purpose": clip_purpose,
            "emotion_intensity": emotion_intensity,
            "people_presence": people_presence,
            "quality_tier": quality_tier,
            "duration_bucket": duration_bucket,
            "aspect_ratio_bucket": aspect_ratio_bucket,
            "orientation": orientation,
            "stability_level": stability_level,
            "dominant_color": dominant_color,
            "brightness_level": brightness_level,
            "saturation_level": saturation_level,
            "motion_level": motion_level,
            "texture_complexity": texture_complexity,
            "face_presence_level": face_presence_level,
            "use_cases": use_cases,
            "audience_intent": audience_intent,
            "business_tags": business_tags,
            "topics": topics,
            "structured_tags": structured_tag_schema,
            "index_layers": index_layers,
            "search_facets": search_facets,
            "search_keywords": search_keywords,
        }

        # v0.6: Add _meta for version tracking
        semantic["_meta"] = {
            "semantic_version": SEMANTIC_SCHEMA_VERSION,
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "extraction_time": self._now(),
            "tag_library_version": "chatgpt_v1_2124",
        }
        # Model/prompt version injected by _llm_structured_tags if LLM was used.
        # v0.19 L6: also classify into stable provider tag for M1 badge UI.
        if structured_tag_schema and isinstance(structured_tag_schema, dict):
            model_version = structured_tag_schema.get("_model", "heuristic_only")
            semantic["_meta"]["model_version"] = model_version
            semantic["_meta"]["provider"] = self._classify_provider(model_version)
            semantic["_meta"]["prompt_version"] = "v3.0_25cat"
        else:
            # Defensive default for edge cases (no structured tag schema at all)
            semantic["_meta"]["model_version"] = "heuristic_only"
            semantic["_meta"]["provider"] = "heuristic"
            semantic["_meta"]["prompt_version"] = "v3.0_25cat"

        return {
            "semantic": semantic,
            "semantic_text": semantic_text,
            "search_keywords": search_keywords,
        }

    def _semantic_from_saved_analysis(self, path: Path, analysis: Dict, fallback_mood: str, fallback_scene: str, fallback_objects: List[str], quality_score):
        scene_text = fallback_scene
        mood_text = fallback_mood
        objects = list(fallback_objects or [])
        if isinstance(analysis, dict):
            local = analysis.get("local_analysis", {})
            scene = local.get("scene", {}) if isinstance(local, dict) else {}
            obj = local.get("objects", {}) if isinstance(local, dict) else {}
            scene_text = scene.get("description") or scene_text
            mood_text = scene.get("mood") or mood_text
            detected = obj.get("detected_objects") if isinstance(obj, dict) else None
            if isinstance(detected, list) and detected:
                objects = detected
        return self._build_semantic_bundle(path, analysis or {}, scene_text, mood_text, objects, quality_score)

    def _analyze_video(self, path: Path) -> Dict:
        _av_t0 = time.perf_counter()
        toolkit = self._toolkit_instance()
        analysis = toolkit.analyze_single_video(path)

        metadata = analysis.get("metadata", {})
        local = analysis.get("local_analysis", {})
        technical = local.get("technical", {})
        scene = local.get("scene", {})
        objects = local.get("objects", {})

        duration = None
        try:
            duration = float(metadata.get("duration")) if metadata.get("duration") else None
        except Exception:
            duration = None

        size_bytes = None
        try:
            size_bytes = int(metadata.get("size")) if metadata.get("size") else path.stat().st_size
        except Exception:
            size_bytes = None

        resolution = technical.get("resolution")
        width, height = self._parse_resolution(resolution)
        if width is None or height is None:
            streams = metadata.get("video_streams") or []
            if streams:
                try:
                    width = int(streams[0].get("width")) if streams[0].get("width") else None
                    height = int(streams[0].get("height")) if streams[0].get("height") else None
                    if width and height:
                        resolution = f"{width}x{height}"
                except Exception:
                    width, height = None, None

        streams = metadata.get("video_streams") or []
        fps_raw = technical.get("fps")
        codec = technical.get("codec")
        if streams:
            fps_raw = fps_raw or streams[0].get("fps")
            codec = codec or streams[0].get("codec")

        scene_description = scene.get("description")
        mood_text = scene.get("mood")
        detected_objects = objects.get("detected_objects") or []
        generic_scene = not str(scene_description or "").strip() or "mixed environment scene" in str(scene_description).lower()
        generic_objects = len(detected_objects) <= 3
        vision_enrich = {}
        if generic_scene or generic_objects:
            vision_enrich = self._vision_enrich_tags(path)
            vision_scene = str(vision_enrich.get("scene", "") or "").strip()
            vision_keywords = vision_enrich.get("keywords") or []
            if not isinstance(vision_keywords, list):
                vision_keywords = []
            landmarks = vision_enrich.get("landmarks") or []
            if not isinstance(landmarks, list):
                landmarks = []
            arch_styles = vision_enrich.get("architecture_style") or []
            if not isinstance(arch_styles, list):
                arch_styles = []

            merged_terms = [
                str(x).strip()
                for x in (vision_keywords + landmarks + arch_styles)
                if str(x).strip()
            ]
            if vision_scene:
                if scene_description:
                    scene_description = f"{scene_description}; {vision_scene}"
                else:
                    scene_description = vision_scene
            if merged_terms:
                detected_objects = self._dedupe_list([str(x) for x in detected_objects] + merged_terms[:14])
            if vision_enrich:
                analysis["vision_enrich"] = {
                    "scene": vision_scene,
                    "keywords": merged_terms[:16],
                }
        quality_score = technical.get("overall_quality")
        semantic_bundle = self._build_semantic_bundle(
            path=path,
            analysis=analysis,
            scene_description=scene_description,
            mood=mood_text,
            objects=detected_objects,
            quality_score=quality_score,
        )

        # GPS extraction from metadata
        gps = metadata.get("gps")
        gps_latitude = gps["latitude"] if isinstance(gps, dict) and gps.get("latitude") is not None else None
        gps_longitude = gps["longitude"] if isinstance(gps, dict) and gps.get("longitude") is not None else None

        # ---- 综合可用性评分 ----
        _usability_result = None
        if _score_asset is not None:
            try:
                _vs = toolkit._get_visual_stats(path) if hasattr(toolkit, '_get_visual_stats') else {}
                _ai = analysis.get("audio_quality") or None
                if isinstance(_ai, dict) and not _ai:
                    _ai = None
                _usability_result = _score_asset(
                    asset_row={
                        "uid": sha256 if 'sha256' in dir() else "",
                        "duration": duration,
                        "width": width,
                        "height": height,
                        "fps": self._parse_fps(fps_raw),
                        "codec": codec,
                        "quality_score": quality_score,
                        "phash": None,
                    },
                    visual_stats=_vs,
                    audio_info=_ai,
                    analysis_json={
                        "asr_text": analysis.get("transcription", {}).get("text", ""),
                        "ocr_text": "",
                        "objects": detected_objects,
                        "semantic": semantic_bundle.get("semantic", {}),
                        "gps": {"lat": gps_latitude, "lon": gps_longitude} if gps_latitude else None,
                        "tags": [],
                    },
                    tag_results=[],
                    library_stats=None,
                )
            except Exception as e:
                _gml_logger.warning("usability scoring failed for %s: %s", path.name, e)
                _usability_result = None

        _av_elapsed = (time.perf_counter() - _av_t0) * 1000
        _gml_logger.info("[perf] analyze_video: %.1fms path=%s", _av_elapsed, path.name)
        try:
            from modules.app_api.services.perf_log import record as _perf_rec
            _perf_rec("analyze_video", _av_elapsed, {"path": str(path.name)})
        except Exception:
            pass

        _result = {
            "analysis": analysis,
            "duration": duration,
            "size_bytes": size_bytes,
            "resolution": resolution,
            "width": width,
            "height": height,
            "fps": self._parse_fps(fps_raw),
            "codec": codec,
            "quality_score": quality_score,
            "scene_description": scene_description,
            "mood": mood_text,
            "objects": detected_objects,
            "semantic_json": semantic_bundle["semantic"],
            "semantic_text": semantic_bundle["semantic_text"],
            "search_keywords": semantic_bundle["search_keywords"],
            "semantic_version": SEMANTIC_SCHEMA_VERSION,
            "gps_latitude": gps_latitude,
            "gps_longitude": gps_longitude,
        }
        if _usability_result:
            _result["quality_assessment"] = _usability_result
        return _result

    def _analyze_image(self, path: Path) -> Dict:
        if cv2 is None or np is None:
            raise RuntimeError("缺少图像分析依赖（opencv-python / numpy）")

        img = cv2.imread(str(path))
        if img is None:
            raise RuntimeError(f"无法读取图片: {path}")

        height, width = img.shape[:2]
        resolution = f"{int(width)}x{int(height)}" if width and height else ""

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        brightness = float(np.mean(gray) / 255.0)
        saturation = float(np.mean(hsv[:, :, 1]) / 255.0)
        edges = cv2.Canny(gray, 70, 160)
        edge_density = float(np.mean(edges > 0))

        b_mean = float(np.mean(img[:, :, 0]))
        g_mean = float(np.mean(img[:, :, 1]))
        r_mean = float(np.mean(img[:, :, 2]))
        rgb_sum = max(r_mean + g_mean + b_mean, 1e-6)
        red_ratio = r_mean / rgb_sum
        green_ratio = g_mean / rgb_sum
        blue_ratio = b_mean / rgb_sum

        # 静态图片没有真实 motion/face score，保留 0 以避免误导。
        motion_score = 0.0
        face_ratio = 0.0

        try:
            size_bytes = int(path.stat().st_size)
        except Exception:
            size_bytes = None

        file_mtime_iso = ""
        try:
            file_mtime_iso = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
        except Exception:
            file_mtime_iso = ""

        orientation, _ = self._infer_orientation(width, height)
        megapixels = float(width * height) / 1_000_000.0 if width and height else 0.0
        if megapixels >= 12:
            quality_score = 0.94
        elif megapixels >= 6:
            quality_score = 0.88
        elif megapixels >= 3:
            quality_score = 0.80
        else:
            quality_score = 0.72

        scene_parts: List[str] = []
        if orientation == "portrait":
            scene_parts.append("portrait photo")
        elif orientation == "landscape":
            scene_parts.append("landscape photo")
        if brightness >= 0.72:
            scene_parts.append("bright daylight")
        elif brightness <= 0.34:
            scene_parts.append("low light")
        if saturation >= 0.50:
            scene_parts.append("vivid color")
        elif saturation <= 0.25:
            scene_parts.append("muted color")
        scene_description = "; ".join(scene_parts) if scene_parts else "still image"

        if brightness >= 0.72 and saturation >= 0.45:
            mood_text = "bright energetic"
        elif brightness <= 0.34:
            mood_text = "moody calm"
        else:
            mood_text = "natural"

        objects: List[str] = []
        filename_tokens = self._split_filename_tokens(path.stem)
        for token in filename_tokens:
            key = self._normalize_tag_to_key(token)
            if not key:
                continue
            entry = self._entry_from_key(key)
            if not entry:
                continue
            if entry.get("en"):
                objects.append(entry["en"])
            if entry.get("zh"):
                objects.append(entry["zh"])

        vision_enrich = self._vision_enrich_tags(path)
        vision_scene = str(vision_enrich.get("scene", "") or "").strip()
        vision_keywords = vision_enrich.get("keywords") or []
        landmarks = vision_enrich.get("landmarks") or []
        arch_styles = vision_enrich.get("architecture_style") or []
        if not isinstance(vision_keywords, list):
            vision_keywords = []
        if not isinstance(landmarks, list):
            landmarks = []
        if not isinstance(arch_styles, list):
            arch_styles = []
        if vision_scene:
            scene_description = f"{scene_description}; {vision_scene}" if scene_description else vision_scene
        objects = self._dedupe_list(
            objects + [str(x).strip() for x in (vision_keywords + landmarks + arch_styles) if str(x).strip()]
        )

        if not objects:
            if orientation == "portrait":
                objects.extend(["person", "portrait"])
            else:
                objects.extend(["landscape", "city"])

        analysis = {
            "metadata": {
                "duration": "0",
                "size": str(size_bytes or 0),
                "video_streams": [],
                "audio_streams": [],
                "tags": {
                    "creation_time": file_mtime_iso,
                    "file_name": path.name,
                    "parent_folder": path.parent.name,
                    "media_type": "image",
                },
            },
            "local_analysis": {
                "technical": {
                    "resolution": resolution,
                    "fps": None,
                    "codec": "image",
                    "overall_quality": quality_score,
                },
                "scene": {
                    "description": scene_description,
                    "mood": mood_text,
                    "method": "image_heuristic",
                    "visual_features": {
                        "brightness": brightness,
                        "saturation": saturation,
                        "edge_density": edge_density,
                        "motion_score": motion_score,
                        "face_ratio": face_ratio,
                        "red_ratio": red_ratio,
                        "green_ratio": green_ratio,
                        "blue_ratio": blue_ratio,
                    },
                },
                "objects": {
                    "detected_objects": objects,
                    "confidence": 0.66 if vision_enrich else 0.52,
                    "method": "image_vision_enrich" if vision_enrich else "image_heuristic",
                },
            },
            "recommendations": [],
        }
        if vision_enrich:
            analysis["vision_enrich"] = {
                "scene": vision_scene,
                "keywords": self._dedupe_list(
                    [str(x).strip() for x in (vision_keywords + landmarks + arch_styles) if str(x).strip()]
                )[:16],
            }

        semantic_bundle = self._build_semantic_bundle(
            path=path,
            analysis=analysis,
            scene_description=scene_description,
            mood=mood_text,
            objects=objects,
            quality_score=quality_score,
        )

        return {
            "analysis": analysis,
            "duration": None,
            "size_bytes": size_bytes,
            "resolution": resolution,
            "width": int(width) if width else None,
            "height": int(height) if height else None,
            "fps": None,
            "codec": "image",
            "quality_score": quality_score,
            "scene_description": scene_description,
            "mood": mood_text,
            "objects": objects,
            "semantic_json": semantic_bundle["semantic"],
            "semantic_text": semantic_bundle["semantic_text"],
            "search_keywords": semantic_bundle["search_keywords"],
            "semantic_version": SEMANTIC_SCHEMA_VERSION,
        }

    @staticmethod
    def _choose_primary_path(current_path: Optional[str], current_source: Optional[str], new_path: str, new_source: str) -> str:
        # Keep local path as primary when available; otherwise latest wins.
        if current_path and current_source == "local" and new_source != "local" and Path(current_path).exists():
            return current_path
        return new_path

    def _upsert_location(self, conn: sqlite3.Connection, uid: str, path: str, source_type: str, source_ref: Optional[str]):
        now = self._now()
        conn.execute(
            """
            INSERT INTO asset_locations (uid, path, source_type, source_ref, is_available, last_seen_at)
            VALUES (?, ?, ?, ?, 1, ?)
            ON CONFLICT(path) DO UPDATE SET
                uid=excluded.uid,
                source_type=excluded.source_type,
                source_ref=excluded.source_ref,
                is_available=1,
                last_seen_at=excluded.last_seen_at
            """,
            (uid, path, source_type, source_ref, now),
        )

    # _find_similar_by_phash → DuplicateDetectionMixin
    def _ingest_video_file(self, conn: sqlite3.Connection, path: Path, source_type: str, source_ref: Optional[str]) -> Dict:
        sha256 = self._compute_sha256(path)
        now = self._now()

        existing = conn.execute(
            """
            SELECT uid, primary_path, source_type, phash, resolution, duration,
                   mood, scene_description, objects_json, quality_score,
                   analysis_json, semantic_json, semantic_text, keywords_json, semantic_version
            FROM assets
            WHERE sha256 = ?
            """,
            (sha256,),
        ).fetchone()

        uid = existing["uid"] if existing else sha256
        prev_path = existing["primary_path"] if existing else None
        prev_source = existing["source_type"] if existing else None
        primary_path = self._choose_primary_path(prev_path, prev_source, str(path), source_type)

        if existing:
            asset_source = prev_source if (prev_source == "local" and source_type != "local") else source_type
            semantic_json = self._safe_json_loads(existing["semantic_json"], {})
            search_keywords = self._safe_json_loads(existing["keywords_json"], [])
            semantic_text = existing["semantic_text"] or ""
            semantic_version = existing["semantic_version"]
            analysis_from_db = self._safe_json_loads(existing["analysis_json"], {})
            fallback_objects = self._safe_json_loads(existing["objects_json"], [])
            refreshed_bundle = None

            needs_semantic_upgrade = (
                semantic_version != SEMANTIC_SCHEMA_VERSION
                or not isinstance(semantic_json, dict)
                or not semantic_json
            )

            scene_legacy = str(existing["scene_description"] or "").strip().lower()
            mood_legacy = str(existing["mood"] or "").strip().lower()
            local = analysis_from_db.get("local_analysis", {}) if isinstance(analysis_from_db, dict) else {}
            scene_method = str((local.get("scene", {}) or {}).get("method", "")).lower() if isinstance(local, dict) else ""
            obj_method = str((local.get("objects", {}) or {}).get("method", "")).lower() if isinstance(local, dict) else ""
            looks_legacy = (
                "模拟" in scene_method
                or "simulation" in scene_method
                or "模拟" in obj_method
                or "simulation" in obj_method
                or scene_legacy in {"scenic landscape or urban environment", ""}
                or mood_legacy in {"varied", ""}
            )
            needs_refresh_analysis = needs_semantic_upgrade or looks_legacy

            if needs_refresh_analysis and path.exists():
                try:
                    refreshed_bundle = self._analyze_video(path)
                    semantic_json = refreshed_bundle["semantic_json"]
                    semantic_text = refreshed_bundle["semantic_text"]
                    search_keywords = refreshed_bundle["search_keywords"]
                    semantic_version = refreshed_bundle["semantic_version"]
                except Exception:
                    refreshed_bundle = None

            if refreshed_bundle is None and needs_semantic_upgrade:
                semantic_bundle = self._semantic_from_saved_analysis(
                    path=path,
                    analysis=analysis_from_db,
                    fallback_mood=existing["mood"] or "",
                    fallback_scene=existing["scene_description"] or "",
                    fallback_objects=fallback_objects if isinstance(fallback_objects, list) else [],
                    quality_score=existing["quality_score"],
                )
                semantic_json = semantic_bundle["semantic"]
                semantic_text = semantic_bundle["semantic_text"]
                search_keywords = semantic_bundle["search_keywords"]
                semantic_version = SEMANTIC_SCHEMA_VERSION

            if refreshed_bundle is not None:
                # Extract usability results from refreshed analysis
                _ref_usability = refreshed_bundle.get("quality_assessment")
                _ref_u_score = _ref_usability["usability_score"] if _ref_usability else None
                _ref_u_tier = _ref_usability["usability_tier"] if _ref_usability else None
                _ref_u_mtype = _ref_usability["material_type"] if _ref_usability else None
                _ref_u_trash = _ref_usability["trash_evaluation"]["trash_level"] if _ref_usability else "none"

                conn.execute(
                    """
                    UPDATE assets
                    SET filename=?, primary_path=?, source_type=?,
                        duration=?, size_bytes=?, resolution=?, width=?, height=?, fps=?, codec=?,
                        quality_score=?, scene_description=?, mood=?, objects_json=?,
                        analysis_json=?, semantic_json=?, semantic_text=?, keywords_json=?, semantic_version=?,
                        gps_latitude=?, gps_longitude=?,
                        usability_score=?, usability_tier=?, material_type=?, trash_level=?,
                        updated_at=?
                    WHERE uid=?
                    """,
                    (
                        path.name,
                        primary_path,
                        asset_source,
                        refreshed_bundle["duration"],
                        refreshed_bundle["size_bytes"],
                        refreshed_bundle["resolution"],
                        refreshed_bundle["width"],
                        refreshed_bundle["height"],
                        refreshed_bundle["fps"],
                        refreshed_bundle["codec"],
                        refreshed_bundle["quality_score"],
                        refreshed_bundle["scene_description"],
                        refreshed_bundle["mood"],
                        json.dumps(refreshed_bundle["objects"], ensure_ascii=False),
                        json.dumps(refreshed_bundle["analysis"], ensure_ascii=False),
                        json.dumps(semantic_json, ensure_ascii=False),
                        semantic_text,
                        json.dumps(search_keywords, ensure_ascii=False),
                        semantic_version,
                        refreshed_bundle.get("gps_latitude"),
                        refreshed_bundle.get("gps_longitude"),
                        _ref_u_score,
                        _ref_u_tier,
                        _ref_u_mtype,
                        _ref_u_trash,
                        now,
                        uid,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE assets
                    SET filename=?, primary_path=?, source_type=?,
                        semantic_json=?, semantic_text=?, keywords_json=?, semantic_version=?,
                        updated_at=?
                    WHERE uid=?
                    """,
                    (
                        path.name,
                        primary_path,
                        asset_source,
                        json.dumps(semantic_json, ensure_ascii=False),
                        semantic_text,
                        json.dumps(search_keywords, ensure_ascii=False),
                        semantic_version,
                        now,
                        uid,
                    ),
                )
            self._upsert_location(conn, uid, str(path), source_type, source_ref)
            self._upsert_embedding_for_asset(
                conn=conn,
                uid=uid,
                filename=path.name,
                semantic_text=semantic_text,
                keywords_json=search_keywords,
                semantic_json=semantic_json,
            )
            try:
                sj = semantic_json if isinstance(semantic_json, dict) else self._safe_json_loads(semantic_json, {})
                self._persist_evidence_and_tags(uid, sj, conn)
            except Exception:
                pass
            return {
                "uid": uid,
                "filename": path.name,
                "path": str(path),
                "sha256": sha256,
                "phash": existing["phash"],
                "dedup_hit": True,
                "similar_uid": uid if existing["phash"] else None,
                "phash_distance": 0 if existing["phash"] else None,
                "resolution": refreshed_bundle["resolution"] if refreshed_bundle else existing["resolution"],
                "duration": refreshed_bundle["duration"] if refreshed_bundle else existing["duration"],
                "semantic_dimensions_count": len((semantic_json or {}).keys()) if isinstance(semantic_json, dict) else 0,
                "semantic_refreshed": bool(refreshed_bundle is not None),
            }

        analysis_bundle = self._analyze_video(path)
        phash = self._compute_phash(path)
        similar_uid, similar_distance = self._find_similar_by_phash(conn, phash)

        # v0.7 fingerprint computation
        content_fp = self._compute_content_fingerprint(path, "video")
        thumb_hash = self._compute_thumbnail_hash(path, "video")

        created_at = now

        # Extract usability scoring results from analysis_bundle
        _usability = analysis_bundle.get("quality_assessment")
        _u_score = _usability["usability_score"] if _usability else None
        _u_tier = _usability["usability_tier"] if _usability else None
        _u_mtype = _usability["material_type"] if _usability else None
        _u_trash = _usability["trash_evaluation"]["trash_level"] if _usability else "none"

        conn.execute(
            """
            INSERT INTO assets (
                uid, sha256, phash, filename, primary_path, source_type,
                duration, size_bytes, resolution, width, height, fps, codec,
                quality_score, scene_description, mood, objects_json,
                analysis_json, semantic_json, semantic_text, keywords_json, semantic_version,
                gps_latitude, gps_longitude,
                content_fingerprint, thumbnail_hash, fingerprint_version,
                usability_score, usability_tier, material_type, trash_level,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(uid) DO UPDATE SET
                sha256=excluded.sha256,
                phash=COALESCE(excluded.phash, assets.phash),
                filename=excluded.filename,
                primary_path=excluded.primary_path,
                source_type=excluded.source_type,
                duration=excluded.duration,
                size_bytes=excluded.size_bytes,
                resolution=excluded.resolution,
                width=excluded.width,
                height=excluded.height,
                fps=excluded.fps,
                codec=excluded.codec,
                quality_score=excluded.quality_score,
                scene_description=excluded.scene_description,
                mood=excluded.mood,
                objects_json=excluded.objects_json,
                analysis_json=excluded.analysis_json,
                semantic_json=excluded.semantic_json,
                semantic_text=excluded.semantic_text,
                keywords_json=excluded.keywords_json,
                semantic_version=excluded.semantic_version,
                gps_latitude=excluded.gps_latitude,
                gps_longitude=excluded.gps_longitude,
                content_fingerprint=COALESCE(excluded.content_fingerprint, assets.content_fingerprint),
                thumbnail_hash=COALESCE(excluded.thumbnail_hash, assets.thumbnail_hash),
                fingerprint_version=excluded.fingerprint_version,
                usability_score=excluded.usability_score,
                usability_tier=excluded.usability_tier,
                material_type=excluded.material_type,
                trash_level=excluded.trash_level,
                updated_at=excluded.updated_at
            """,
            (
                uid,
                sha256,
                phash,
                path.name,
                primary_path,
                source_type,
                analysis_bundle["duration"],
                analysis_bundle["size_bytes"],
                analysis_bundle["resolution"],
                analysis_bundle["width"],
                analysis_bundle["height"],
                analysis_bundle["fps"],
                analysis_bundle["codec"],
                analysis_bundle["quality_score"],
                analysis_bundle["scene_description"],
                analysis_bundle["mood"],
                json.dumps(analysis_bundle["objects"], ensure_ascii=False),
                json.dumps(analysis_bundle["analysis"], ensure_ascii=False),
                json.dumps(analysis_bundle["semantic_json"], ensure_ascii=False),
                analysis_bundle["semantic_text"],
                json.dumps(analysis_bundle["search_keywords"], ensure_ascii=False),
                analysis_bundle["semantic_version"],
                analysis_bundle.get("gps_latitude"),
                analysis_bundle.get("gps_longitude"),
                content_fp,
                thumb_hash,
                self.FINGERPRINT_VERSION,
                _u_score,
                _u_tier,
                _u_mtype,
                _u_trash,
                created_at,
                now,
            ),
        )

        self._upsert_location(conn, uid, str(path), source_type, source_ref)
        self._upsert_embedding_for_asset(
            conn=conn,
            uid=uid,
            filename=path.name,
            semantic_text=analysis_bundle["semantic_text"],
            keywords_json=analysis_bundle["search_keywords"],
            semantic_json=analysis_bundle["semantic_json"],
        )
        try:
            self._persist_evidence_and_tags(uid, analysis_bundle["semantic_json"], conn)
        except Exception:
            pass
        self._generate_thumbnail(uid, path, "video")

        return {
            "uid": uid,
            "filename": path.name,
            "path": str(path),
            "sha256": sha256,
            "phash": phash,
            "content_fingerprint": content_fp,
            "thumbnail_hash": thumb_hash,
            "dedup_hit": bool(existing),
            "similar_uid": similar_uid,
            "phash_distance": similar_distance,
            "resolution": analysis_bundle["resolution"],
            "duration": analysis_bundle["duration"],
            "semantic_dimensions_count": len((analysis_bundle.get("semantic_json") or {}).keys()),
        }

    def _ingest_image_file(self, conn: sqlite3.Connection, path: Path, source_type: str, source_ref: Optional[str]) -> Dict:
        sha256 = self._compute_sha256(path)
        now = self._now()

        existing = conn.execute(
            """
            SELECT uid, primary_path, source_type, phash, resolution, duration,
                   mood, scene_description, objects_json, quality_score,
                   analysis_json, semantic_json, semantic_text, keywords_json, semantic_version
            FROM assets
            WHERE sha256 = ?
            """,
            (sha256,),
        ).fetchone()

        uid = existing["uid"] if existing else sha256
        prev_path = existing["primary_path"] if existing else None
        prev_source = existing["source_type"] if existing else None
        primary_path = self._choose_primary_path(prev_path, prev_source, str(path), source_type)

        if existing:
            asset_source = prev_source if (prev_source == "local" and source_type != "local") else source_type
            semantic_json = self._safe_json_loads(existing["semantic_json"], {})
            search_keywords = self._safe_json_loads(existing["keywords_json"], [])
            semantic_text = existing["semantic_text"] or ""
            semantic_version = existing["semantic_version"]
            analysis_from_db = self._safe_json_loads(existing["analysis_json"], {})
            fallback_objects = self._safe_json_loads(existing["objects_json"], [])
            refreshed_bundle = None

            needs_semantic_upgrade = (
                semantic_version != SEMANTIC_SCHEMA_VERSION
                or not isinstance(semantic_json, dict)
                or not semantic_json
            )
            needs_refresh_analysis = needs_semantic_upgrade

            if needs_refresh_analysis and path.exists():
                try:
                    refreshed_bundle = self._analyze_image(path)
                    semantic_json = refreshed_bundle["semantic_json"]
                    semantic_text = refreshed_bundle["semantic_text"]
                    search_keywords = refreshed_bundle["search_keywords"]
                    semantic_version = refreshed_bundle["semantic_version"]
                except Exception:
                    refreshed_bundle = None

            if refreshed_bundle is None and needs_semantic_upgrade:
                semantic_bundle = self._semantic_from_saved_analysis(
                    path=path,
                    analysis=analysis_from_db,
                    fallback_mood=existing["mood"] or "",
                    fallback_scene=existing["scene_description"] or "",
                    fallback_objects=fallback_objects if isinstance(fallback_objects, list) else [],
                    quality_score=existing["quality_score"],
                )
                semantic_json = semantic_bundle["semantic"]
                semantic_text = semantic_bundle["semantic_text"]
                search_keywords = semantic_bundle["search_keywords"]
                semantic_version = SEMANTIC_SCHEMA_VERSION

            if refreshed_bundle is not None:
                conn.execute(
                    """
                    UPDATE assets
                    SET filename=?, primary_path=?, source_type=?,
                        duration=?, size_bytes=?, resolution=?, width=?, height=?, fps=?, codec=?,
                        quality_score=?, scene_description=?, mood=?, objects_json=?,
                        analysis_json=?, semantic_json=?, semantic_text=?, keywords_json=?, semantic_version=?,
                        gps_latitude=?, gps_longitude=?,
                        updated_at=?
                    WHERE uid=?
                    """,
                    (
                        path.name,
                        primary_path,
                        asset_source,
                        refreshed_bundle["duration"],
                        refreshed_bundle["size_bytes"],
                        refreshed_bundle["resolution"],
                        refreshed_bundle["width"],
                        refreshed_bundle["height"],
                        refreshed_bundle["fps"],
                        refreshed_bundle["codec"],
                        refreshed_bundle["quality_score"],
                        refreshed_bundle["scene_description"],
                        refreshed_bundle["mood"],
                        json.dumps(refreshed_bundle["objects"], ensure_ascii=False),
                        json.dumps(refreshed_bundle["analysis"], ensure_ascii=False),
                        json.dumps(semantic_json, ensure_ascii=False),
                        semantic_text,
                        json.dumps(search_keywords, ensure_ascii=False),
                        semantic_version,
                        refreshed_bundle.get("gps_latitude"),
                        refreshed_bundle.get("gps_longitude"),
                        now,
                        uid,
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE assets
                    SET filename=?, primary_path=?, source_type=?,
                        semantic_json=?, semantic_text=?, keywords_json=?, semantic_version=?,
                        updated_at=?
                    WHERE uid=?
                    """,
                    (
                        path.name,
                        primary_path,
                        asset_source,
                        json.dumps(semantic_json, ensure_ascii=False),
                        semantic_text,
                        json.dumps(search_keywords, ensure_ascii=False),
                        semantic_version,
                        now,
                        uid,
                    ),
                )
            self._upsert_location(conn, uid, str(path), source_type, source_ref)
            self._upsert_embedding_for_asset(
                conn=conn,
                uid=uid,
                filename=path.name,
                semantic_text=semantic_text,
                keywords_json=search_keywords,
                semantic_json=semantic_json,
            )
            try:
                sj = semantic_json if isinstance(semantic_json, dict) else self._safe_json_loads(semantic_json, {})
                self._persist_evidence_and_tags(uid, sj, conn)
            except Exception:
                pass
            return {
                "uid": uid,
                "filename": path.name,
                "path": str(path),
                "sha256": sha256,
                "phash": existing["phash"],
                "dedup_hit": True,
                "similar_uid": uid if existing["phash"] else None,
                "phash_distance": 0 if existing["phash"] else None,
                "resolution": refreshed_bundle["resolution"] if refreshed_bundle else existing["resolution"],
                "duration": refreshed_bundle["duration"] if refreshed_bundle else existing["duration"],
                "semantic_dimensions_count": len((semantic_json or {}).keys()) if isinstance(semantic_json, dict) else 0,
                "semantic_refreshed": bool(refreshed_bundle is not None),
            }

        analysis_bundle = self._analyze_image(path)
        phash = self._compute_image_phash(path)
        similar_uid, similar_distance = self._find_similar_by_phash(conn, phash)

        # v0.7 fingerprint computation (image)
        content_fp = self._compute_content_fingerprint(path, "image")
        thumb_hash = self._compute_thumbnail_hash(path, "image")

        created_at = now

        conn.execute(
            """
            INSERT INTO assets (
                uid, sha256, phash, filename, primary_path, source_type,
                duration, size_bytes, resolution, width, height, fps, codec,
                quality_score, scene_description, mood, objects_json,
                analysis_json, semantic_json, semantic_text, keywords_json, semantic_version,
                gps_latitude, gps_longitude,
                content_fingerprint, thumbnail_hash, fingerprint_version,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(uid) DO UPDATE SET
                sha256=excluded.sha256,
                phash=COALESCE(excluded.phash, assets.phash),
                filename=excluded.filename,
                primary_path=excluded.primary_path,
                source_type=excluded.source_type,
                duration=excluded.duration,
                size_bytes=excluded.size_bytes,
                resolution=excluded.resolution,
                width=excluded.width,
                height=excluded.height,
                fps=excluded.fps,
                codec=excluded.codec,
                quality_score=excluded.quality_score,
                scene_description=excluded.scene_description,
                mood=excluded.mood,
                objects_json=excluded.objects_json,
                analysis_json=excluded.analysis_json,
                semantic_json=excluded.semantic_json,
                semantic_text=excluded.semantic_text,
                keywords_json=excluded.keywords_json,
                semantic_version=excluded.semantic_version,
                gps_latitude=excluded.gps_latitude,
                gps_longitude=excluded.gps_longitude,
                content_fingerprint=COALESCE(excluded.content_fingerprint, assets.content_fingerprint),
                thumbnail_hash=COALESCE(excluded.thumbnail_hash, assets.thumbnail_hash),
                fingerprint_version=excluded.fingerprint_version,
                updated_at=excluded.updated_at
            """,
            (
                uid,
                sha256,
                phash,
                path.name,
                primary_path,
                source_type,
                analysis_bundle["duration"],
                analysis_bundle["size_bytes"],
                analysis_bundle["resolution"],
                analysis_bundle["width"],
                analysis_bundle["height"],
                analysis_bundle["fps"],
                analysis_bundle["codec"],
                analysis_bundle["quality_score"],
                analysis_bundle["scene_description"],
                analysis_bundle["mood"],
                json.dumps(analysis_bundle["objects"], ensure_ascii=False),
                json.dumps(analysis_bundle["analysis"], ensure_ascii=False),
                json.dumps(analysis_bundle["semantic_json"], ensure_ascii=False),
                analysis_bundle["semantic_text"],
                json.dumps(analysis_bundle["search_keywords"], ensure_ascii=False),
                analysis_bundle["semantic_version"],
                analysis_bundle.get("gps_latitude"),
                analysis_bundle.get("gps_longitude"),
                content_fp,
                thumb_hash,
                self.FINGERPRINT_VERSION,
                created_at,
                now,
            ),
        )

        self._upsert_location(conn, uid, str(path), source_type, source_ref)
        self._upsert_embedding_for_asset(
            conn=conn,
            uid=uid,
            filename=path.name,
            semantic_text=analysis_bundle["semantic_text"],
            keywords_json=analysis_bundle["search_keywords"],
            semantic_json=analysis_bundle["semantic_json"],
        )
        try:
            self._persist_evidence_and_tags(uid, analysis_bundle["semantic_json"], conn)
        except Exception:
            pass
        self._generate_thumbnail(uid, path, "image")

        return {
            "uid": uid,
            "filename": path.name,
            "path": str(path),
            "sha256": sha256,
            "phash": phash,
            "content_fingerprint": content_fp,
            "thumbnail_hash": thumb_hash,
            "dedup_hit": bool(existing),
            "similar_uid": similar_uid,
            "phash_distance": similar_distance,
            "resolution": analysis_bundle["resolution"],
            "duration": analysis_bundle["duration"],
            "semantic_dimensions_count": len((analysis_bundle.get("semantic_json") or {}).keys()),
        }

    def _ingest_video_paths(
        self,
        videos: Iterable[Path],
        source_type: str,
        source_ref: Optional[str],
        source_display: Optional[str] = None,
        progress_callback=None,
        should_cancel=None,
    ) -> Dict:
        _ivp_t0 = time.perf_counter()
        video_list = [Path(p).resolve() for p in videos]
        result = {
            "source_type": source_type,
            "source": source_display or source_ref or "",
            "scanned": len(video_list),
            "indexed": 0,
            "dedup_hits": 0,
            "failed": 0,
            "assets": [],
        }
        total = len(video_list)
        done = 0

        with self._connect() as conn:
            for p in video_list:
                if callable(should_cancel):
                    try:
                        if bool(should_cancel()):
                            result["cancelled"] = True
                            result["cancelled_after"] = done
                            break
                    except Exception:
                        result["cancelled"] = True
                        result["cancelled_after"] = done
                        break
                try:
                    item = self._ingest_video_file(conn, p, source_type, source_ref)
                    result["indexed"] += 1
                    if item["dedup_hit"]:
                        result["dedup_hits"] += 1
                    result["assets"].append(item)
                except Exception as exc:
                    result["failed"] += 1
                    result.setdefault("errors", []).append(f"{p.name}: {exc}")
                finally:
                    done += 1
                    # 短事务提交，避免一次大批量入库长时间持有写锁。
                    try:
                        conn.commit()
                    except Exception:
                        pass
                    if callable(progress_callback):
                        try:
                            progress_callback(done, total, str(p))
                        except Exception:
                            pass

            # 持续更新：每轮入库后补齐一批历史缺失 embedding，避免一次性重算阻塞。
            try:
                result["embedding_refreshed"] = self._refresh_embeddings_incremental(
                    conn,
                    max_items=max(6, min(60, result["indexed"] // 2 + 6)),
                )
            except Exception:
                result["embedding_refreshed"] = 0
            try:
                conn.commit()
            except Exception:
                pass

        _ivp_elapsed = (time.perf_counter() - _ivp_t0) * 1000
        _gml_logger.info("[perf] ingest_video_paths: %.1fms scanned=%d indexed=%d",
                         _ivp_elapsed, result["scanned"], result["indexed"])
        try:
            from modules.app_api.services.perf_log import record as _perf_rec
            _perf_rec("ingest_video_paths", _ivp_elapsed,
                      {"scanned": result["scanned"], "indexed": result["indexed"]})
        except Exception:
            pass
        return result

    def _ingest_image_paths(
        self,
        images: Iterable[Path],
        source_type: str,
        source_ref: Optional[str],
        source_display: Optional[str] = None,
        progress_callback=None,
        should_cancel=None,
    ) -> Dict:
        _iip_t0 = time.perf_counter()
        image_list = [Path(p).resolve() for p in images]
        result = {
            "source_type": source_type,
            "source": source_display or source_ref or "",
            "scanned": len(image_list),
            "indexed": 0,
            "dedup_hits": 0,
            "failed": 0,
            "assets": [],
        }
        total = len(image_list)
        done = 0

        with self._connect() as conn:
            for p in image_list:
                if callable(should_cancel):
                    try:
                        if bool(should_cancel()):
                            result["cancelled"] = True
                            result["cancelled_after"] = done
                            break
                    except Exception:
                        result["cancelled"] = True
                        result["cancelled_after"] = done
                        break
                try:
                    item = self._ingest_image_file(conn, p, source_type, source_ref)
                    result["indexed"] += 1
                    if item["dedup_hit"]:
                        result["dedup_hits"] += 1
                    result["assets"].append(item)
                except Exception as exc:
                    result["failed"] += 1
                    result.setdefault("errors", []).append(f"{p.name}: {exc}")
                finally:
                    done += 1
                    try:
                        conn.commit()
                    except Exception:
                        pass
                    if callable(progress_callback):
                        try:
                            progress_callback(done, total, str(p))
                        except Exception:
                            pass

            try:
                result["embedding_refreshed"] = self._refresh_embeddings_incremental(
                    conn,
                    max_items=max(6, min(60, result["indexed"] // 2 + 6)),
                )
            except Exception:
                result["embedding_refreshed"] = 0
            try:
                conn.commit()
            except Exception:
                pass

        _iip_elapsed = (time.perf_counter() - _iip_t0) * 1000
        _gml_logger.info("[perf] ingest_image_paths: %.1fms scanned=%d indexed=%d",
                         _iip_elapsed, result["scanned"], result["indexed"])
        try:
            from modules.app_api.services.perf_log import record as _perf_rec
            _perf_rec("ingest_image_paths", _iip_elapsed,
                      {"scanned": result["scanned"], "indexed": result["indexed"]})
        except Exception:
            pass
        return result

    # ------------------------------------------------------------------
    # Auto visual index after ingest (R3 W-010)

    def _auto_visual_index(self, assets: list) -> bool:
        """Trigger CLIP visual indexing for newly ingested assets in a background thread.

        Returns True if indexing was triggered, False if CLIP unavailable or no assets.
        Call ``_cancel_visual_index()`` to stop a running background indexing job.
        """
        if not assets:
            return False
        if not hasattr(self, "_clip_encoder") or self._clip_encoder is None:
            try:
                from modules.workflow_engine.workflow import _log_degradation
                _log_degradation("auto_visual_index", "CLIP 不可用（需 torch + transformers）", "跳过自动视觉索引")
            except Exception:
                pass
            return False

        uid_path_pairs = []
        for a in assets:
            uid = a.get("uid", "")
            path = a.get("path") or a.get("primary_path", "")
            if uid and path and Path(path).exists():
                uid_path_pairs.append((uid, path))
        if not uid_path_pairs:
            return False

        import threading

        # Cancel any previous running index job
        self._cancel_visual_index()
        stop_event = threading.Event()
        self._visual_index_stop = stop_event

        def _index_worker():
            for uid, path in uid_path_pairs:
                if stop_event.is_set():
                    _gml_logger.info("auto visual index cancelled (%d remaining)", len(uid_path_pairs))
                    break
                try:
                    self.index_asset_visual(uid, path)
                except Exception:
                    _gml_logger.warning("auto visual index failed for %s", uid, exc_info=True)

        t = threading.Thread(target=_index_worker, daemon=True, name="auto_visual_index")
        t.start()
        return True

    def _cancel_visual_index(self) -> None:
        """Signal the background visual index thread to stop."""
        stop = getattr(self, "_visual_index_stop", None)
        if stop is not None:
            stop.set()

    # ------------------------------------------------------------------
    # Public ingest APIs

    def ingest_local_path(self, source_path: str, max_videos: int = 600, progress_callback=None, should_cancel=None) -> Dict:
        root = Path(source_path).expanduser().resolve()
        if not root.exists():
            raise FileNotFoundError(f"路径不存在: {root}")

        videos = self._discover_videos(root)
        total_candidates = len(videos)
        try:
            max_videos = int(max_videos)
        except Exception:
            max_videos = 600
        if max_videos <= 0:
            max_videos = 600
        max_videos = min(max_videos, 5000)

        selected = videos[:max_videos]
        result = self._ingest_video_paths(
            selected,
            source_type="local",
            source_ref=str(root),
            source_display=str(root),
            progress_callback=progress_callback,
            should_cancel=should_cancel,
        )
        result["total_candidates"] = total_candidates
        result["max_videos"] = max_videos
        result["truncated"] = total_candidates > len(selected)
        result["visual_index_triggered"] = self._auto_visual_index(result.get("assets", []))
        return result

    def ingest_local_images(self, source_path: str, max_images: int = 1200, progress_callback=None, should_cancel=None) -> Dict:
        root = Path(source_path).expanduser().resolve()
        if not root.exists():
            raise FileNotFoundError(f"路径不存在: {root}")

        images = self._discover_images(root)
        total_candidates = len(images)
        try:
            max_images = int(max_images)
        except Exception:
            max_images = 1200
        if max_images <= 0:
            max_images = 1200
        max_images = min(max_images, 8000)

        selected = images[:max_images]
        result = self._ingest_image_paths(
            selected,
            source_type="local",
            source_ref=str(root),
            source_display=str(root),
            progress_callback=progress_callback,
            should_cancel=should_cancel,
        )
        result["total_candidates"] = total_candidates
        result["max_images"] = max_images
        result["truncated"] = total_candidates > len(selected)
        result["visual_index_triggered"] = self._auto_visual_index(result.get("assets", []))
        return result

    # GDrive methods → GDriveMixin (integrations/gdrive.py)    # ------------------------------------------------------------------
    # Query APIs

    # _candidate_local_roots, _try_relocate_asset, _best_existing_path → PathRelinkMixin    # ── Phase 3: structured tag recall ──

    def _tag_recall(
        self,
        conn: sqlite3.Connection,
        query: str,
        top_k: int = 500,
    ) -> Tuple[Dict[str, float], Dict[str, Dict], str]:
        """Three-path tag recall: resolve tokens → expand via tag_relation → score assets.

        Returns (tag_scores, tag_match_info, query_type).
        tag_scores: {uid: normalized_score}
        tag_match_info: {uid: {matched_tags, matched_aliases, expanded_tags, hit_details, query_type, has_custom_tag}}
        query_type: exact_tag | alias_tag | composed_query | abstract_intent
        """
        tokens = self._tokenize_query(query)
        if not tokens:
            return {}, {}, "abstract_intent"

        # Extract original query tokens (before synonym expansion) for classification.
        # _tokenize_query adds synonyms; classification should reflect user intent, not expansions.
        _orig_raw = re.split(r"[\s,，;；|/]+", query.strip().lower())
        original_tokens = {p.strip() for p in _orig_raw if len(p.strip()) >= 2}

        tag_cache: Dict[str, Optional[int]] = {}
        resolved_tags: Dict[str, int] = {}      # token → tag_id (all tokens)
        resolution_info: Dict[str, Dict] = {}   # token → {tag_id, hit_type, tag_name}
        unresolved_terms: List[str] = []

        # For classification: only count original user tokens
        orig_resolved: Dict[str, int] = {}
        orig_info: Dict[str, Dict] = {}

        # Step 2: resolve tokens
        for token in tokens:
            tag_id = self._resolve_tag_id(token, conn, _cache=tag_cache, context="search")
            if tag_id == self._STOPWORD_SENTINEL:
                continue
            if tag_id is not None and tag_id > 0:
                hit_type = self._classify_resolution(token, tag_id, conn)
                tag_name = self._get_tag_name_cached(tag_id, conn)
                resolved_tags[token] = tag_id
                info_entry = {
                    "tag_id": tag_id,
                    "hit_type": hit_type,
                    "tag_name": tag_name,
                    "original_term": token,
                }
                resolution_info[token] = info_entry
                # Track original-only resolutions for query classification
                if token in original_tokens:
                    orig_resolved[token] = tag_id
                    orig_info[token] = info_entry
            elif tag_id is None:
                unresolved_terms.append(token)

        # Step 3: classify query type (based on original user tokens only)
        query_type = self._classify_query(query, orig_resolved, orig_info, conn)

        if not resolved_tags:
            return {}, {}, query_type

        # Step 4: expand via tag_relation only
        # expanded_tags: tag_id → (hit_strength, relation_type, from_tag_id)
        expanded_tags: Dict[int, Tuple[float, str, int]] = {}
        direct_tag_ids = set(resolved_tags.values())

        for tag_id in direct_tag_ids:
            # Direct hit gets the strength from how it was resolved
            best_strength = 0.0
            for info in resolution_info.values():
                if info["tag_id"] == tag_id:
                    s = TAG_HIT_STRENGTH.get(info["hit_type"], 1.0)
                    if s > best_strength:
                        best_strength = s
            expanded_tags[tag_id] = (best_strength, "direct", tag_id)

        # Expand synonyms and parent→child via tag_relation
        if direct_tag_ids:
            placeholders = ",".join("?" for _ in direct_tag_ids)
            tag_id_list = list(direct_tag_ids)

            # synonym expansion
            syn_rows = conn.execute(
                f"""SELECT from_tag_id, to_tag_id FROM tag_relation
                    WHERE relation_type = 'synonym'
                    AND (from_tag_id IN ({placeholders}) OR to_tag_id IN ({placeholders}))""",
                tag_id_list + tag_id_list,
            ).fetchall()
            for sr in syn_rows:
                peer = sr[1] if sr[0] in direct_tag_ids else sr[0]
                if peer not in expanded_tags:
                    expanded_tags[peer] = (TAG_HIT_STRENGTH["synonym"], "synonym", sr[0] if sr[0] in direct_tag_ids else sr[1])

            # parent → child expansion
            child_rows = conn.execute(
                f"""SELECT from_tag_id, to_tag_id FROM tag_relation
                    WHERE relation_type IN ('parent_child', 'parent')
                    AND from_tag_id IN ({placeholders})""",
                tag_id_list,
            ).fetchall()
            for cr in child_rows:
                child_id = cr[1]
                if child_id not in expanded_tags:
                    expanded_tags[child_id] = (TAG_HIT_STRENGTH["parent_child"], "parent_child", cr[0])

        if not expanded_tags:
            return {}, {}, query_type

        # Step 5: query asset_tag_result
        all_tag_ids = list(expanded_tags.keys())
        placeholders = ",".join("?" for _ in all_tag_ids)
        atr_rows = conn.execute(
            f"""SELECT asset_id, tag_id, effective_score, source_summary
                FROM asset_tag_result
                WHERE tag_id IN ({placeholders})
                AND result_scope = 'asset'
                AND is_displayed = 1""",
            all_tag_ids,
        ).fetchall()

        # Step 6: aggregate per-asset scores
        asset_scores: Dict[str, float] = {}       # uid → total_score
        asset_details: Dict[str, List[Dict]] = {}  # uid → [hit_detail, ...]

        for atr in atr_rows:
            uid = str(atr[0])  # asset_id stores assets.uid (TEXT)
            tag_id = atr[1]
            eff_score = float(atr[2]) if atr[2] is not None else 0.5
            hit_strength, relation_type, source_tag_id = expanded_tags.get(tag_id, (0.5, "unknown", tag_id))
            weighted = eff_score * hit_strength

            asset_scores[uid] = asset_scores.get(uid, 0.0) + weighted

            tag_name = self._get_tag_name_cached(tag_id, conn)
            detail = {
                "tag_id": tag_id,
                "tag_name": tag_name,
                "hit_strength": hit_strength,
                "relation_type": relation_type,
                "effective_score": eff_score,
                "weighted_score": weighted,
            }
            if relation_type != "direct":
                detail["source_tag_name"] = self._get_tag_name_cached(source_tag_id, conn)
            asset_details.setdefault(uid, []).append(detail)

        if not asset_scores:
            return {}, {}, query_type

        # Step 7: normalize to [0, 1]
        max_score = max(asset_scores.values())
        if max_score > 0:
            tag_scores = {uid: score / max_score for uid, score in asset_scores.items()}
        else:
            tag_scores = dict(asset_scores)

        # Sort and truncate to top_k
        sorted_uids = sorted(tag_scores.keys(), key=lambda u: tag_scores[u], reverse=True)[:top_k]
        tag_scores = {uid: tag_scores[uid] for uid in sorted_uids}

        # Build match_info per uid
        has_custom_tag = any(
            info.get("hit_type") == "custom" for info in resolution_info.values()
        )
        matched_tags = [info["tag_name"] for info in resolution_info.values()]
        matched_aliases = [
            info["original_term"]
            for info in resolution_info.values()
            if info["hit_type"] in ("alias", "custom")
        ]
        expanded_tag_names = [
            self._get_tag_name_cached(tid, conn)
            for tid, (_, rtype, _) in expanded_tags.items()
            if rtype != "direct"
        ]

        tag_match_info: Dict[str, Dict] = {}
        for uid in sorted_uids:
            tag_match_info[uid] = {
                "matched_tags": matched_tags,
                "matched_aliases": matched_aliases,
                "expanded_tags": expanded_tag_names,
                "hit_details": asset_details.get(uid, []),
                "query_type": query_type,
                "has_custom_tag": has_custom_tag,
            }

        return tag_scores, tag_match_info, query_type

    def _score_asset(self, row: sqlite3.Row, keywords: List[str]) -> int:
        filename = (row["filename"] or "").lower()
        path_text = (row["primary_path"] or "").lower()
        scene = (row["scene_description"] or "").lower()
        mood = (row["mood"] or "").lower()
        resolution = (row["resolution"] or "").lower()
        objects = (row["objects_json"] or "").lower()
        semantic_text = (row["semantic_text"] or "").lower()
        semantic_json_text = (row["semantic_json"] or "").lower()
        keywords_text = (row["keywords_json"] or "").lower()

        score = 0
        for kw in keywords:
            if kw in filename:
                score += 10
            if kw in path_text:
                score += 11
            if kw in scene:
                score += 8
            if kw in objects:
                score += 6
            if kw in mood:
                score += 4
            if kw in resolution:
                score += 3
            if kw in semantic_text:
                score += 7
            if kw in keywords_text:
                score += 9
            if f"core:{kw}" in keywords_text:
                score += 13
            if f"secondary:{kw}" in keywords_text:
                score += 4
            if kw in semantic_json_text:
                score += 6
        return score

    def _fetch_assets_by_uids(self, conn: sqlite3.Connection, uids: List[str]) -> List[sqlite3.Row]:
        if not uids:
            return []
        ordered = [u for u in uids if u]
        placeholders = ",".join("?" for _ in ordered)
        return conn.execute(
            f"""
            SELECT uid, filename, sha256, size_bytes, primary_path, source_type, duration, resolution,
                   quality_score, scene_description, mood, objects_json,
                   semantic_json, semantic_text, keywords_json, updated_at,
                   gps_latitude, gps_longitude
            FROM assets
            WHERE uid IN ({placeholders})
            """,
            tuple(ordered),
        ).fetchall()

    # ── Phase 3: shared candidate builder ──

    def _build_search_candidates(
        self,
        conn: sqlite3.Connection,
        q: str,
        keywords: List[str],
        mode: str,
        media: str,
    ) -> Tuple[List[sqlite3.Row], Dict[str, float], Dict[str, float], Dict[str, Dict], str]:
        """Build unified candidate set from FTS5 + vector + tag recall.

        Ensures search_assets() and count_matching_assets() use the same candidate pool.
        Returns (rows, vector_scores, tag_scores, tag_match_info, query_type).
        """
        where_clause = self._media_type_where_sql(media, alias="")

        # FTS5 recall
        fts_uids: set = set()
        if mode in {"keyword", "hybrid"} and keywords:
            try:
                fts_query = " OR ".join(f'"{kw}"' for kw in keywords if kw)
                if fts_query:
                    fts_rows = conn.execute(
                        "SELECT uid FROM assets_fts WHERE semantic_text MATCH ? LIMIT 2000",
                        (fts_query,),
                    ).fetchall()
                    fts_uids = {r["uid"] for r in fts_rows}
            except Exception:
                fts_uids = set()

        # Base rows
        sql = """
            SELECT uid, filename, sha256, size_bytes, primary_path, source_type, duration, resolution,
                   quality_score, scene_description, mood, objects_json,
                   semantic_json, semantic_text, keywords_json, updated_at,
                   gps_latitude, gps_longitude
            FROM assets
        """
        if where_clause:
            sql += f" WHERE {where_clause}"
        sql += " ORDER BY updated_at DESC LIMIT 4000"
        rows = list(conn.execute(sql).fetchall())
        existing_uids = {str(r["uid"]) for r in rows}

        # Merge FTS hits
        if fts_uids:
            fts_missing = [uid for uid in fts_uids if uid not in existing_uids][:500]
            if fts_missing:
                fts_fetched = self._fetch_assets_by_uids(conn, fts_missing)
                if media != "all":
                    fts_fetched = [
                        r for r in fts_fetched
                        if self._infer_asset_kind(r["filename"], r["primary_path"]) == media
                    ]
                rows.extend(fts_fetched)
                existing_uids.update(str(r["uid"]) for r in fts_fetched)

        # Vector recall
        vector_scores: Dict[str, float] = {}
        if q and mode in {"hybrid", "vector"}:
            vector_scores = self._vector_search(conn, q, top_k=1400)
            if vector_scores:
                vec_missing = [uid for uid in vector_scores if uid not in existing_uids][:1200]
                if vec_missing:
                    vec_fetched = self._fetch_assets_by_uids(conn, vec_missing)
                    if media != "all":
                        vec_fetched = [
                            r for r in vec_fetched
                            if self._infer_asset_kind(r["filename"], r["primary_path"]) == media
                        ]
                    rows.extend(vec_fetched)
                    existing_uids.update(str(r["uid"]) for r in vec_fetched)

        # Tag recall
        tag_scores: Dict[str, float] = {}
        tag_match_info: Dict[str, Dict] = {}
        query_type = "composed_query"
        if q and mode in {"keyword", "hybrid"}:
            tag_scores, tag_match_info, query_type = self._tag_recall(conn, q, top_k=500)
            if tag_scores:
                tag_missing = [uid for uid in tag_scores if uid not in existing_uids][:500]
                if tag_missing:
                    tag_fetched = self._fetch_assets_by_uids(conn, tag_missing)
                    if media != "all":
                        tag_fetched = [
                            r for r in tag_fetched
                            if self._infer_asset_kind(r["filename"], r["primary_path"]) == media
                        ]
                    rows.extend(tag_fetched)
                    existing_uids.update(str(r["uid"]) for r in tag_fetched)

        return rows, vector_scores, tag_scores, tag_match_info, query_type

    def _hybrid_rank_candidates(
        self,
        conn: sqlite3.Connection,
        rows: List[sqlite3.Row],
        query: str,
        keywords: List[str],
        retrieval_mode: str = "hybrid",
        vector_scores: Optional[Dict[str, float]] = None,
        tag_scores: Optional[Dict[str, float]] = None,
        tag_match_info: Optional[Dict[str, Dict]] = None,
        query_type: str = "composed_query",
    ) -> List[Dict[str, Any]]:
        if not rows:
            return []
        mode = str(retrieval_mode or "hybrid").strip().lower()
        if mode not in {"hybrid", "keyword", "vector"}:
            mode = "hybrid"

        if tag_scores is None:
            tag_scores = {}
        if tag_match_info is None:
            tag_match_info = {}

        row_by_uid: Dict[str, sqlite3.Row] = {}
        for row in rows:
            uid = str(row["uid"])
            if uid not in row_by_uid:
                row_by_uid[uid] = row

        # FTS scoring
        lexical_scores: Dict[str, int] = {}
        if mode in {"hybrid", "keyword"}:
            for uid, row in row_by_uid.items():
                score = self._score_asset(row, keywords) if keywords else 0
                if score > 0:
                    lexical_scores[uid] = score
            if keywords and not lexical_scores:
                relaxed_keywords = self._relaxed_query_tokens(keywords)
                if relaxed_keywords and relaxed_keywords != keywords:
                    for uid, row in row_by_uid.items():
                        score = self._score_asset(row, relaxed_keywords)
                        if score > 0:
                            lexical_scores[uid] = score

        # Vector scores
        if mode in {"hybrid", "vector"}:
            if vector_scores is None:
                vector_scores = self._vector_search(conn, query, top_k=1400)
            else:
                vector_scores = dict(vector_scores)
        else:
            vector_scores = {}

        # Dynamic weights by query_type
        weights = QUERY_TYPE_WEIGHTS.get(query_type, QUERY_TYPE_WEIGHTS["composed_query"])

        # Normalize each path to [0, 1]
        max_tag = max(tag_scores.values()) if tag_scores else 0.0
        max_fts = max(lexical_scores.values()) if lexical_scores else 0

        # Collect all candidate uids that have at least one non-zero signal
        all_candidate_uids: Set[str] = set()
        for uid in tag_scores:
            if uid in row_by_uid:
                all_candidate_uids.add(uid)
        for uid in lexical_scores:
            if uid in row_by_uid:
                all_candidate_uids.add(uid)
        for uid, vs in vector_scores.items():
            if uid in row_by_uid and float(vs) >= 0.08:
                all_candidate_uids.add(uid)

        if not all_candidate_uids:
            return []

        # Weighted fusion
        combined_scores: Dict[str, float] = {}
        for uid in all_candidate_uids:
            tag_norm = (tag_scores.get(uid, 0.0) / max_tag) if max_tag > 0 else 0.0
            fts_norm = (float(lexical_scores.get(uid, 0)) / float(max_fts)) if max_fts > 0 else 0.0
            raw_vec = float(vector_scores.get(uid, -1.0))
            vec_norm = max(0.0, min(1.0, (raw_vec + 1.0) / 2.0))

            score = (
                weights["tag"] * tag_norm
                + weights["fts"] * fts_norm
                + weights["embedding"] * vec_norm
            )

            # custom_tag boost
            uid_info = tag_match_info.get(uid, {})
            if uid_info.get("has_custom_tag"):
                score += SEARCH_WEIGHTS.get("custom_tag_boost", 0.10)

            combined_scores[uid] = score

        ranked_uids = sorted(
            combined_scores.keys(),
            key=lambda u: (
                combined_scores.get(u, 0.0),
                tag_scores.get(u, 0.0),
                float(lexical_scores.get(u, 0)),
                float(vector_scores.get(u, -1.0)),
                str(row_by_uid[u]["updated_at"] or ""),
            ),
            reverse=True,
        )

        # Build match_sources list
        ranked: List[Dict[str, Any]] = []
        for uid in ranked_uids:
            sources = []
            if uid in tag_scores and tag_scores[uid] > 0:
                sources.append("tag")
            if uid in lexical_scores and lexical_scores[uid] > 0:
                sources.append("fts")
            if uid in vector_scores and float(vector_scores[uid]) >= 0.08:
                sources.append("embedding")

            uid_info = tag_match_info.get(uid, {})
            match_info = {
                "match_sources": sources,
                "combined_score": round(combined_scores.get(uid, 0.0), 4),
                "tag_score": round(tag_scores.get(uid, 0.0), 4),
                "fts_score": int(lexical_scores.get(uid, 0)),
                "embedding_score": round(float(vector_scores.get(uid, 0.0)), 4),
                "query_type": query_type,
                "weights_used": weights,
                "matched_tags": uid_info.get("matched_tags", []),
                "matched_aliases": uid_info.get("matched_aliases", []),
                "expanded_tags": uid_info.get("expanded_tags", []),
                "hit_details": uid_info.get("hit_details", []),
            }
            ranked.append({
                "row": row_by_uid[uid],
                "uid": uid,
                "match_score": float(combined_scores.get(uid, 0.0)),
                "keyword_score": int(lexical_scores.get(uid, 0)),
                "vector_score": float(vector_scores.get(uid, 0.0)),
                "tag_score": round(tag_scores.get(uid, 0.0), 4),
                "match_info": match_info,
            })
        return ranked

    def count_matching_assets(self, query: str = "", retrieval_mode: str = "hybrid", media_type: str = "all") -> int:
        q = (query or "").strip().lower()
        keywords = self._tokenize_query(q) if q else []
        mode = str(retrieval_mode or "hybrid").strip().lower()
        if mode not in {"hybrid", "keyword", "vector", "visual", "fusion"}:
            mode = "hybrid"
        # Visual count shortcut
        if mode == "visual" and q:
            visual_scores = self.visual_search(q, top_k=500) if hasattr(self, "visual_search") else {}
            return len(visual_scores)
        # Fusion count: union of hybrid + visual
        if mode == "fusion" and q:
            hybrid_count = self.count_matching_assets(query=q, retrieval_mode="hybrid", media_type=media_type)
            visual_scores = self.visual_search(q, top_k=500) if hasattr(self, "visual_search") else {}
            # Approximate: union is at most sum, but likely overlapping
            return max(hybrid_count, len(visual_scores))
        media = self._normalize_media_type(media_type)
        with self._connect() as conn:
            if not q:
                where_clause = self._media_type_where_sql(media, alias="")
                sql = "SELECT COUNT(*) FROM assets"
                if where_clause:
                    sql += f" WHERE {where_clause}"
                return int(conn.execute(sql).fetchone()[0])

            rows, vector_scores, tag_scores, tag_match_info, query_type = (
                self._build_search_candidates(conn, q, keywords, mode, media)
            )
            ranked = self._hybrid_rank_candidates(
                conn=conn,
                rows=rows,
                query=q,
                keywords=keywords,
                retrieval_mode=mode,
                vector_scores=vector_scores,
                tag_scores=tag_scores,
                tag_match_info=tag_match_info,
                query_type=query_type,
            )
            return len(ranked)

    def search_assets(
        self,
        query: str = "",
        limit: int = 100,
        offset: int = 0,
        retrieval_mode: str = "hybrid",
        media_type: str = "all",
    ) -> List[Dict]:
        import time as _time_mod
        _search_t0 = _time_mod.monotonic()
        q = (query or "").strip().lower()
        keywords = self._tokenize_query(q) if q else []
        mode = str(retrieval_mode or "hybrid").strip().lower()
        if mode not in {"hybrid", "keyword", "vector", "visual", "fusion"}:
            mode = "hybrid"
        media = self._normalize_media_type(media_type)
        try:
            limit = max(1, int(limit))
        except Exception:
            limit = 100
        # Visual search shortcut — delegates to VisionMixin
        if mode == "visual" and q:
            visual_scores = self.visual_search(q, top_k=limit) if hasattr(self, "visual_search") else {}
            if visual_scores:
                visual_uids = list(visual_scores.keys())[:limit]
                assets = self.get_assets(visual_uids) if hasattr(self, "get_assets") else []
                for asset in assets:
                    asset["vector_score"] = visual_scores.get(asset.get("uid", ""), 0.0)
                    asset["keyword_score"] = 0.0
                    asset["tag_score"] = 0.0
                return assets
            return []
        # Fusion: combine hybrid text results with visual results via RRF
        if mode == "fusion" and q:
            hybrid_results = self.search_assets(
                query=q, limit=limit * 2, offset=0,
                retrieval_mode="hybrid", media_type=media_type,
            )
            visual_scores = self.visual_search(q, top_k=limit * 2) if hasattr(self, "visual_search") else {}
            uid_scores: Dict[str, float] = {}
            for rank, asset in enumerate(hybrid_results):
                uid = asset.get("uid", "")
                if uid:
                    uid_scores[uid] = uid_scores.get(uid, 0.0) + 1.0 / (60 + rank)
            for rank, (uid, _vs) in enumerate(sorted(visual_scores.items(), key=lambda x: -x[1])):
                uid_scores[uid] = uid_scores.get(uid, 0.0) + 1.0 / (60 + rank)
            sorted_uids = sorted(uid_scores.keys(), key=lambda u: -uid_scores[u])
            page_uids = sorted_uids[offset:offset + limit]
            if not page_uids:
                return []
            assets = self.get_assets(page_uids) if hasattr(self, "get_assets") else []
            hybrid_by_uid = {a.get("uid"): a for a in hybrid_results}
            for asset in assets:
                uid = asset.get("uid", "")
                asset["match_score"] = uid_scores.get(uid, 0.0)
                h = hybrid_by_uid.get(uid, {})
                asset["keyword_score"] = h.get("keyword_score", 0.0)
                asset["vector_score"] = h.get("vector_score", 0.0)
                asset["visual_score"] = visual_scores.get(uid, 0.0)
                asset["tag_score"] = h.get("tag_score", 0.0)
            assets.sort(key=lambda a: -a.get("match_score", 0.0))
            return assets
        try:
            offset = max(0, int(offset))
        except Exception:
            offset = 0

        with self._connect() as conn:
            if not q:
                where_clause = self._media_type_where_sql(media, alias="a")
                sql = """
                    SELECT a.uid, a.filename, a.sha256, a.size_bytes, a.primary_path, a.source_type,
                           a.duration, a.resolution, a.quality_score, a.scene_description, a.mood,
                           a.objects_json, a.semantic_json, a.keywords_json, a.updated_at,
                           a.gps_latitude, a.gps_longitude,
                           COALESCE(
                               (
                                   SELECT l.path
                                   FROM asset_locations l
                                   WHERE l.uid = a.uid AND l.is_available = 1
                                   ORDER BY CASE WHEN l.source_type='local' THEN 0 ELSE 1 END, l.id DESC
                                   LIMIT 1
                               ),
                               a.primary_path
                           ) AS best_path,
                           CASE WHEN EXISTS (
                               SELECT 1 FROM asset_locations l2
                               WHERE l2.uid = a.uid AND l2.is_available = 1
                           ) THEN 1 ELSE 0 END AS available_hint
                    FROM assets a
                """
                if where_clause:
                    sql += f" WHERE {where_clause}"
                sql += """
                    ORDER BY a.updated_at DESC
                    LIMIT ? OFFSET ?
                """
                rows = conn.execute(
                    sql,
                    (limit, offset),
                ).fetchall()
                results = []
                for row in rows:
                    objects = self._safe_json_loads(row["objects_json"], [])
                    if not isinstance(objects, list):
                        objects = []
                    semantic = self._safe_json_loads(row["semantic_json"], {})
                    semantic_keywords = self._safe_json_loads(row["keywords_json"], [])
                    if not isinstance(semantic_keywords, list):
                        semantic_keywords = []
                    _uid = row["uid"]
                    results.append(
                        {
                            "uid": _uid,
                            "filename": row["filename"],
                            "path": row["best_path"],
                            "asset_kind": self._infer_asset_kind(row["filename"], row["best_path"] or row["primary_path"]),
                            "available": bool(row["available_hint"]),
                            "source_type": row["source_type"],
                            "duration": row["duration"],
                            "resolution": row["resolution"],
                            "quality_score": row["quality_score"],
                            "scene_description": row["scene_description"],
                            "mood": row["mood"],
                            "objects": objects,
                            "semantic": semantic if isinstance(semantic, dict) else {},
                            "semantic_keywords": semantic_keywords,
                            "semantic_dimensions_count": len(semantic.keys()) if isinstance(semantic, dict) else 0,
                            "semantic_dimension_names": list(semantic.keys()) if isinstance(semantic, dict) else [],
                            "updated_at": row["updated_at"],
                            "gps_latitude": row["gps_latitude"],
                            "gps_longitude": row["gps_longitude"],
                            "thumbnail_url": f"/api/library/thumbnail/{_uid}" if self.thumbnail_path(_uid) else None,
                            "match_score": 1,
                            "keyword_score": 0,
                            "vector_score": 0.0,
                        }
                    )
                return results

            rows, vector_scores, tag_scores, tag_match_info, query_type = (
                self._build_search_candidates(conn, q, keywords, mode, media)
            )
            ranked = self._hybrid_rank_candidates(
                conn=conn,
                rows=rows,
                query=q,
                keywords=keywords,
                retrieval_mode=mode,
                vector_scores=vector_scores,
                tag_scores=tag_scores,
                tag_match_info=tag_match_info,
                query_type=query_type,
            )

            # Record search signal (best-effort, before returning)
            _elapsed_ms = int((_time_mod.monotonic() - _search_t0) * 1000)
            try:
                self._record_search_signal(
                    conn=conn, query=q, query_type=query_type,
                    retrieval_mode=mode, result_count=len(ranked),
                    tag_match_info=tag_match_info, tag_scores=tag_scores,
                    vector_scores=vector_scores, ranked_count=len(ranked),
                    search_duration_ms=_elapsed_ms,
                )
                conn.commit()
            except Exception:
                pass
            try:
                from modules.app_api.services.perf_log import record as _perf_rec
                _perf_rec("search_assets", _elapsed_ms, {"query": q, "results": len(ranked), "mode": mode})
            except Exception:
                pass

            if not ranked:
                return []

            paged = ranked[offset: offset + limit]
            if not paged:
                return []

            results = []
            for cand in paged:
                row = cand["row"]
                best_path = self._best_existing_path(
                    conn,
                    row["uid"],
                    row["primary_path"],
                    filename=row["filename"],
                    sha256=row["sha256"],
                    size_bytes=row["size_bytes"],
                    allow_relocate=False,
                    update_availability=False,
                )
                objects = []
                try:
                    objects = json.loads(row["objects_json"] or "[]")
                except Exception:
                    objects = []
                semantic = self._safe_json_loads(row["semantic_json"], {})
                semantic_keywords = self._safe_json_loads(row["keywords_json"], [])

                _uid = row["uid"]
                results.append(
                    {
                        "uid": _uid,
                        "filename": row["filename"],
                        "path": best_path,
                        "asset_kind": self._infer_asset_kind(row["filename"], best_path or row["primary_path"]),
                        "available": bool(best_path and Path(best_path).exists()),
                        "source_type": row["source_type"],
                        "duration": row["duration"],
                        "resolution": row["resolution"],
                        "quality_score": row["quality_score"],
                        "scene_description": row["scene_description"],
                        "mood": row["mood"],
                        "objects": objects,
                        "semantic": semantic,
                        "semantic_keywords": semantic_keywords,
                        "semantic_dimensions_count": len(semantic.keys()) if isinstance(semantic, dict) else 0,
                        "semantic_dimension_names": list(semantic.keys()) if isinstance(semantic, dict) else [],
                        "updated_at": row["updated_at"],
                        "gps_latitude": row["gps_latitude"],
                        "gps_longitude": row["gps_longitude"],
                        "thumbnail_url": f"/api/library/thumbnail/{_uid}" if self.thumbnail_path(_uid) else None,
                        "match_score": cand["match_score"],
                        "keyword_score": cand["keyword_score"],
                        "vector_score": cand["vector_score"],
                        "tag_score": cand.get("tag_score", 0.0),
                        "match_info": cand.get("match_info", {}),
                    }
                )
            return results

    # ── Search signal learning loop ──

    def _record_search_signal(
        self,
        conn: sqlite3.Connection,
        query: str,
        query_type: str,
        retrieval_mode: str,
        result_count: int,
        tag_match_info: Dict[str, Dict],
        tag_scores: Dict[str, float],
        vector_scores: Dict[str, float],
        ranked_count: int,
        search_duration_ms: int = 0,
    ) -> None:
        """Record a search event to search_log and write unresolved search terms to learning_candidate.

        Called at the end of search_assets() for every non-empty query.
        Writes are best-effort — failures are silently ignored.
        """
        if not query or not query.strip():
            return

        normalized = query.strip().lower()

        # Gather resolved / unresolved info from tag_match_info
        resolved_tags_set: set = set()
        for uid_info in tag_match_info.values():
            for t in uid_info.get("matched_tags", []):
                resolved_tags_set.add(t)
            break  # All uids share the same matched_tags

        # Count hits per path
        tag_hit_count = sum(1 for v in tag_scores.values() if v > 0)
        vector_hit_count = sum(1 for v in vector_scores.values() if float(v) >= 0.08)
        # fts_hit_count is not directly available here; use ranked_count - tag - vector overlap estimate
        fts_hit_count = max(0, ranked_count - tag_hit_count)  # approximation

        is_zero_hit = 1 if ranked_count == 0 else 0

        # Resolve only original user tokens (not n-gram sub-tokens) to avoid
        # flooding learning_candidate with noise like "选词", "词管" etc.
        _orig_parts = re.split(r"[\s,，;；|/]+", normalized)
        original_tokens = [p.strip() for p in _orig_parts if len(p.strip()) >= 2]
        tag_cache: Dict[str, Optional[int]] = {}
        unresolved_terms: List[str] = []
        for token in original_tokens:
            tag_id = self._resolve_tag_id(token, conn, _cache=tag_cache, context="search")
            if tag_id is None:
                unresolved_terms.append(token)

        # Write to search_log
        try:
            conn.execute(
                """INSERT INTO search_log
                   (query_text, normalized_query, query_type, retrieval_mode,
                    result_count, tag_hit_count, fts_hit_count, vector_hit_count,
                    resolved_tags, unresolved_terms, is_zero_hit,
                    search_duration_ms)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (query.strip(), normalized, query_type, retrieval_mode,
                 ranked_count, tag_hit_count, fts_hit_count, vector_hit_count,
                 json.dumps(list(resolved_tags_set), ensure_ascii=False) if resolved_tags_set else None,
                 json.dumps(unresolved_terms, ensure_ascii=False) if unresolved_terms else None,
                 is_zero_hit, search_duration_ms),
            )
        except Exception:
            pass

        # Write unresolved search terms to learning_candidate (source_kind='search_query')
        for term in unresolved_terms:
            norm_term = term.lower().strip()
            if len(norm_term) < 2:
                continue
            try:
                conn.execute(
                    """INSERT INTO learning_candidate
                       (candidate_text, normalized_text, category_hint, source_kind,
                        occurrence_count, asset_count)
                       VALUES (?, ?, 'search', 'search_query', 1, 0)
                       ON CONFLICT(normalized_text, source_kind) DO UPDATE SET
                           occurrence_count = occurrence_count + 1""",
                    (term, norm_term),
                )
            except Exception:
                pass

    # ── Search analytics methods ──

    def get_search_analytics(self, days: int = 30, limit: int = 50) -> Dict:
        """Return search analytics: popular queries, zero-hit queries, unresolved terms.

        Args:
            days: Look back N days.
            limit: Max entries per category.
        """
        with self._connect() as conn:
            cutoff = f"datetime('now', '-{int(days)} days')"

            # Popular queries (by frequency)
            popular = conn.execute(
                f"""SELECT normalized_query, COUNT(*) as search_count,
                           SUM(result_count) as total_results,
                           AVG(result_count) as avg_results,
                           MAX(created_at) as last_searched
                    FROM search_log
                    WHERE created_at >= {cutoff}
                    GROUP BY normalized_query
                    ORDER BY search_count DESC
                    LIMIT ?""",
                (limit,),
            ).fetchall()

            # Zero-hit queries (unique queries that returned 0 results)
            zero_hits = conn.execute(
                f"""SELECT normalized_query, COUNT(*) as occurrence_count,
                           MAX(created_at) as last_searched
                    FROM search_log
                    WHERE is_zero_hit = 1 AND created_at >= {cutoff}
                    GROUP BY normalized_query
                    ORDER BY occurrence_count DESC
                    LIMIT ?""",
                (limit,),
            ).fetchall()

            # Unresolved search terms from learning_candidate
            unresolved = conn.execute(
                """SELECT candidate_text, normalized_text, occurrence_count,
                          review_status, suggested_action, created_at
                   FROM learning_candidate
                   WHERE source_kind = 'search_query'
                   ORDER BY occurrence_count DESC
                   LIMIT ?""",
                (limit,),
            ).fetchall()

            # Summary stats
            total_searches = conn.execute(
                f"SELECT COUNT(*) FROM search_log WHERE created_at >= {cutoff}",
            ).fetchone()[0]
            zero_hit_total = conn.execute(
                f"SELECT COUNT(*) FROM search_log WHERE is_zero_hit = 1 AND created_at >= {cutoff}",
            ).fetchone()[0]
            unique_queries = conn.execute(
                f"SELECT COUNT(DISTINCT normalized_query) FROM search_log WHERE created_at >= {cutoff}",
            ).fetchone()[0]
            _agg = conn.execute(
                f"""SELECT AVG(result_count), AVG(search_duration_ms)
                    FROM search_log WHERE created_at >= {cutoff}""",
            ).fetchone()
            avg_results = round(_agg[0], 1) if _agg and _agg[0] is not None else None
            avg_duration = int(_agg[1]) if _agg and _agg[1] is not None else None

            return {
                "summary": {
                    "total_searches": total_searches,
                    "unique_queries": unique_queries,
                    "zero_hit_count": zero_hit_total,
                    "zero_hit_rate": round(zero_hit_total / max(total_searches, 1), 3),
                    "avg_results": avg_results,
                    "avg_duration_ms": avg_duration,
                    "days": days,
                },
                "popular_queries": [
                    {
                        "query": r[0],
                        "search_count": r[1],
                        "total_results": r[2],
                        "avg_results": round(r[3], 1) if r[3] else 0,
                        "last_searched": r[4],
                    }
                    for r in popular
                ],
                "zero_hit_queries": [
                    {
                        "query": r[0],
                        "occurrence_count": r[1],
                        "last_searched": r[2],
                    }
                    for r in zero_hits
                ],
                "unresolved_search_terms": [
                    {
                        "term": r[0],
                        "normalized": r[1],
                        "occurrence_count": r[2],
                        "review_status": r[3],
                        "suggested_action": r[4],
                        "first_seen": r[5],
                    }
                    for r in unresolved
                ],
            }

    def get_zero_hit_queries(self, days: int = 30, limit: int = 50) -> List[Dict]:
        """Return queries that produced zero results, ordered by frequency."""
        with self._connect() as conn:
            cutoff = f"datetime('now', '-{int(days)} days')"
            rows = conn.execute(
                f"""SELECT normalized_query, COUNT(*) as cnt,
                           MAX(created_at) as last_at
                    FROM search_log
                    WHERE is_zero_hit = 1 AND created_at >= {cutoff}
                    GROUP BY normalized_query
                    ORDER BY cnt DESC
                    LIMIT ?""",
                (limit,),
            ).fetchall()
            return [{"query": r[0], "count": r[1], "last_searched": r[2]} for r in rows]

    def get_popular_searches(self, days: int = 30, limit: int = 20) -> List[Dict]:
        """Return most frequently searched queries."""
        with self._connect() as conn:
            cutoff = f"datetime('now', '-{int(days)} days')"
            rows = conn.execute(
                f"""SELECT normalized_query, COUNT(*) as cnt,
                           AVG(result_count) as avg_res,
                           MAX(created_at) as last_at
                    FROM search_log
                    WHERE created_at >= {cutoff}
                    GROUP BY normalized_query
                    ORDER BY cnt DESC
                    LIMIT ?""",
                (limit,),
            ).fetchall()
            return [
                {"query": r[0], "count": r[1], "avg_results": round(r[2], 1) if r[2] else 0, "last_searched": r[3]}
                for r in rows
            ]

