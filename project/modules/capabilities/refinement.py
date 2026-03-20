"""Refinement strategy for premium edit quality."""

from dataclasses import asdict, dataclass
from typing import Dict


@dataclass
class RefinePlan:
    """Final polish plan for renderer or external NLE."""

    editor: str
    transition_style: str
    color_profile: str
    skin_smooth_strength: float
    notes: str


def build_refine_plan(
    style: str = "travel_story",
    editor: str = "internal_ffmpeg",
    quality: str = "high",
) -> RefinePlan:
    """Build a deterministic refinement plan."""
    style_key = str(style or "travel_story").strip().lower()
    editor_key = str(editor or "internal_ffmpeg").strip().lower()
    quality_key = str(quality or "high").strip().lower()

    styles = {
        "travel_story": ("fade", "warm_film", 0.45),
        "cinematic": ("smoothleft", "teal_orange", 0.30),
        "clean_vlog": ("fadeblack", "neutral_clean", 0.25),
    }
    transition, color_profile, skin = styles.get(style_key, styles["travel_story"])
    if quality_key == "draft":
        transition = "none"
        skin = min(skin, 0.2)
    elif quality_key == "premium":
        skin = max(skin, 0.55)

    if editor_key not in {"internal_ffmpeg", "davinci", "finalcut", "premiere", "jianying"}:
        editor_key = "internal_ffmpeg"

    notes = "Render internally with FFmpeg stage pipeline."
    if editor_key != "internal_ffmpeg":
        notes = (
            f"Hand off timeline to {editor_key}. "
            "Use FCPXML/EDL export from internal rough timeline, then re-import final master."
        )

    return RefinePlan(
        editor=editor_key,
        transition_style=transition,
        color_profile=color_profile,
        skin_smooth_strength=round(skin, 2),
        notes=notes,
    )


def build_refine_payload(style: str = "travel_story", editor: str = "internal_ffmpeg", quality: str = "high") -> Dict:
    """Return dict payload for workflow or API layers."""
    return asdict(build_refine_plan(style=style, editor=editor, quality=quality))
