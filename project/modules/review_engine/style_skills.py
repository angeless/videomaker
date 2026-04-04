"""StyleSkill — YAML-based style configuration for video projects.

Defines reusable style presets (color grade, font, transitions, audio,
pacing) that can be saved/loaded and auto-extracted from projects.
"""

import logging
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

try:
    import yaml
except ImportError:
    yaml = None

from .exceptions import ReviewEngineError

logger = logging.getLogger(__name__)


@dataclass
class StyleConfig:
    """A complete style configuration."""
    name: str
    color_grade: str = "natural"
    font: str = "PingFang SC"
    transition: str = "cross_dissolve"
    audio_preset: str = "voice"  # "voice" | "music" | "flat"
    pacing: str = "medium"  # "slow" | "medium" | "fast"
    bgm_volume_db: float = -12.0
    subtitle_style: Dict = field(default_factory=lambda: {
        "color": "white",
        "outline_color": "black",
        "outline_width": 2,
        "position": "bottom",
    })


def _check_yaml():
    if yaml is None:
        raise ReviewEngineError("pyyaml is required for style skills: pip install pyyaml")


def save_style(style: StyleConfig, styles_dir: str) -> str:
    """Save a style config to YAML.

    Returns the file path.
    """
    _check_yaml()
    os.makedirs(styles_dir, exist_ok=True)
    safe_name = style.name.replace(" ", "_").replace("/", "_")
    path = os.path.join(styles_dir, f"{safe_name}.yaml")

    data = {
        "name": style.name,
        "color_grade": style.color_grade,
        "font": style.font,
        "transition": style.transition,
        "audio_preset": style.audio_preset,
        "pacing": style.pacing,
        "bgm_volume_db": style.bgm_volume_db,
        "subtitle_style": style.subtitle_style,
    }

    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

    return path


def load_style(path: str) -> StyleConfig:
    """Load a style config from YAML."""
    _check_yaml()
    if not os.path.isfile(path):
        raise ReviewEngineError(f"Style file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    return StyleConfig(
        name=data.get("name", "unnamed"),
        color_grade=data.get("color_grade", "natural"),
        font=data.get("font", "PingFang SC"),
        transition=data.get("transition", "cross_dissolve"),
        audio_preset=data.get("audio_preset", "voice"),
        pacing=data.get("pacing", "medium"),
        bgm_volume_db=data.get("bgm_volume_db", -12.0),
        subtitle_style=data.get("subtitle_style", {}),
    )


def list_styles(styles_dir: str) -> List[StyleConfig]:
    """List all saved styles."""
    if not os.path.isdir(styles_dir):
        return []

    styles = []
    for fname in sorted(os.listdir(styles_dir)):
        if fname.endswith(".yaml") or fname.endswith(".yml"):
            try:
                styles.append(load_style(os.path.join(styles_dir, fname)))
            except Exception as e:
                logger.warning("Failed to load style %s: %s", fname, e)
    return styles


def auto_extract_style(project_data: Dict) -> StyleConfig:
    """Extract style parameters from a completed project.

    Inspects render settings, subtitle config, transition choices, etc.
    """
    name = project_data.get("project_name", "extracted_style")

    # Extract from render settings
    render = project_data.get("render_settings", {})
    audio = project_data.get("audio_settings", {})
    subtitle = project_data.get("subtitle_settings", {})

    return StyleConfig(
        name=name,
        color_grade=render.get("color_grade", "natural"),
        font=subtitle.get("font", "PingFang SC"),
        transition=render.get("default_transition", "cross_dissolve"),
        audio_preset=audio.get("preset", "voice"),
        pacing=render.get("pacing", "medium"),
        bgm_volume_db=audio.get("bgm_volume_db", -12.0),
        subtitle_style=subtitle.get("style", {}),
    )
