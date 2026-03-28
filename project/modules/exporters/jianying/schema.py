"""Jianying Professional v5.x draft schema constants (community reverse-engineered)."""

DRAFT_CONTENT_VERSION = 360000
PLATFORM_VERSION = "5.9.0"
APP_ID = 3704
CANVAS_WIDTH = 1080
CANVAS_HEIGHT = 1920

TRACK_TYPE_VIDEO = "video"
TRACK_TYPE_AUDIO = "audio"
TRACK_TYPE_TEXT = "text"

MATERIAL_TYPE_VIDEO = "video"
MATERIAL_TYPE_AUDIO = "audio"
MATERIAL_TYPE_TEXT = "text"


def make_draft_meta(name: str, width: int = CANVAS_WIDTH, height: int = CANVAS_HEIGHT) -> dict:
    """Generate draft_meta_info.json content."""
    return {
        "draft_fold_path": "",
        "draft_id": "",
        "draft_name": name,
        "draft_resolution": f"{width}*{height}",
        "draft_root_path": "",
        "tm_draft_create": "",
        "tm_draft_modified": "",
    }


def make_empty_draft_content(duration_us: int, width: int = CANVAS_WIDTH, height: int = CANVAS_HEIGHT) -> dict:
    """Generate the skeleton of draft_content.json."""
    return {
        "canvas_config": {
            "height": height,
            "ratio": "original",
            "width": width,
        },
        "color_space": 0,
        "config": {"adjust_max_index": 1, "attachment_info": []},
        "cover": "",
        "duration": duration_us,
        "extra_info": "",
        "fps": 30.0,
        "free_render_index_mode_on": False,
        "id": "",
        "keyframes": {"adjusts": [], "audios": [], "effects": [], "filters": [], "handwrites": [], "stickers": [], "texts": [], "videos": []},
        "materials": {
            "audios": [],
            "effects": [],
            "material_animations": [],
            "material_datas": [],
            "texts": [],
            "video_effects": [],
            "videos": [],
        },
        "mutable_config": None,
        "name": "",
        "new_version": str(DRAFT_CONTENT_VERSION),
        "platform": {"app_id": APP_ID, "app_source": "", "app_version": PLATFORM_VERSION, "device_id": "", "hard_disk_id": "", "mac_address": "", "os": "mac", "os_version": ""},
        "relationships": [],
        "render_index_track_mode_on": False,
        "retouch_cover": None,
        "source": "default",
        "static_cover_image_path": "",
        "tracks": [],
        "update_time": "",
        "version": DRAFT_CONTENT_VERSION,
    }
