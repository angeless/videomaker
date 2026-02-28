"""Capability registry for the split feature architecture."""

from typing import Dict, List, Optional

from .types import CapabilitySpec


CAPABILITY_SPECS: List[CapabilitySpec] = [
    CapabilitySpec(
        capability_id="topic_library",
        name="Topic Library",
        goal="Store reusable topic templates and strategy metadata as a database module.",
        inputs=["topic template", "category", "audience", "tags"],
        outputs=["searchable topic records"],
        status="prototype",
        references=["Airtable", "Notion database"],
    ),
    CapabilitySpec(
        capability_id="topic_copy",
        name="Topic + Copy",
        goal="Generate hooks, outline, and short-form copy by combining topic records with material semantics.",
        inputs=["topic record", "material semantic tags", "target duration"],
        outputs=["copy brief", "script skeleton"],
        depends_on=["topic_library"],
        status="prototype",
        references=["Lumen5", "Canva Magic Write"],
    ),
    CapabilitySpec(
        capability_id="text_rough_cut",
        name="Text Rough Cut",
        goal="Perform transcript-driven rough cutting using text-level keep/delete decisions.",
        inputs=["ASR transcript spans", "remove phrases", "target duration"],
        outputs=["rough-cut timeline plan"],
        status="prototype",
        references=["Wondershare Filmora", "Descript"],
    ),
    CapabilitySpec(
        capability_id="short_clip",
        name="Short Video Quick Cut",
        goal="Pick highlights from long video and produce short-form clip timelines.",
        inputs=["highlight candidates", "duration budget"],
        outputs=["ordered highlight timeline"],
        status="prototype",
        references=["Wisecut", "Clipchamp"],
    ),
    CapabilitySpec(
        capability_id="refinement",
        name="Refinement",
        goal="Apply aesthetic strategy and optional external NLE handoff for premium quality edit.",
        inputs=["matched script", "render style", "editor target"],
        outputs=["refine plan", "stage render config"],
        depends_on=["short_clip"],
        status="prototype",
        references=["DaVinci Resolve", "Final Cut Pro", "Adobe Premiere Pro", "Jianying"],
    ),
    CapabilitySpec(
        capability_id="social_export",
        name="Social Export",
        goal="Export platform-specific deliverables with strict specs and quality presets.",
        inputs=["master video", "platform profile"],
        outputs=["platform-ready files"],
        depends_on=["refinement"],
        status="prototype",
        references=["FlexClip", "CapCut Export Presets"],
    ),
    CapabilitySpec(
        capability_id="publish_prep",
        name="Publish Preparation",
        goal="Prepare platform-ready publish title, body, and keyword package from script and voiceover copy.",
        inputs=["script", "voiceover", "platform prompt profile"],
        outputs=["platform publish copy package"],
        status="prototype",
        references=["Platform content ops templates"],
    ),
    CapabilitySpec(
        capability_id="subtitle_calibration",
        name="Subtitle Calibration",
        goal="Calibrate bilingual subtitles with optional timeline alignment and translation refinement.",
        inputs=["subtitles", "mode", "translation", "source_audio(optional)"],
        outputs=["calibrated subtitles", "timeline change report", "quality report"],
        status="prototype",
        references=["Descript", "Filmora"],
    ),
    CapabilitySpec(
        capability_id="image_semantic",
        name="Image Semantic",
        goal="Analyze image semantics and provide searchable semantic signals for downstream planning.",
        inputs=["image paths", "semantic query", "analysis options"],
        outputs=["semantic analysis result", "search hits"],
        status="prototype",
        references=["Vision tagging", "semantic retrieval"],
    ),
    CapabilitySpec(
        capability_id="article_expand",
        name="Article Expansion",
        goal="Expand source notes into WeChat article-ready structures with title, lead, body, and CTA.",
        inputs=["source text", "key points", "tone", "length target"],
        outputs=["article draft", "title candidates", "keywords"],
        status="prototype",
        references=["WeChat content ops templates"],
    ),
    CapabilitySpec(
        capability_id="audio_voice",
        name="Music + Voice",
        goal="Plan voiceover and soundtrack layers, including voice clone and mood-driven BGM strategy.",
        inputs=["subtitles", "style", "mood"],
        outputs=["voiceover segments", "music plan"],
        status="prototype",
        references=["ElevenLabs", "AIVA"],
    ),
    CapabilitySpec(
        capability_id="content_publish",
        name="Content Publish",
        goal="Build multi-platform publish plans and execute optional live publishing with reusable session state.",
        inputs=["publish package", "platform list", "session", "dry_run"],
        outputs=["publish plan", "publish execution result", "publish history"],
        status="prototype",
        references=["Social media publisher tools"],
    ),
]


_SPEC_BY_ID: Dict[str, CapabilitySpec] = {spec.capability_id: spec for spec in CAPABILITY_SPECS}


def list_capabilities() -> List[CapabilitySpec]:
    """Return registered capability specs in declared order."""
    return list(CAPABILITY_SPECS)


def get_capability(capability_id: str) -> Optional[CapabilitySpec]:
    """Get a capability spec by id."""
    return _SPEC_BY_ID.get(capability_id)


def legacy_step_mapping() -> Dict[int, str]:
    """
    Map current 7-step pipeline to capability names.

    This is a transition map so old workflow code can coexist with the split design.
    """
    return {
        1: "topic_library",
        2: "topic_copy",
        3: "topic_copy",
        4: "topic_copy",
        5: "text_rough_cut",
        6: "short_clip",
        7: "refinement",
    }
