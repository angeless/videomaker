"""JianyingExportBuilder — converts three-track timeline to Jianying Pro v5.x draft."""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.exporters.jianying.schema import (
    MATERIAL_TYPE_AUDIO,
    MATERIAL_TYPE_TEXT,
    MATERIAL_TYPE_VIDEO,
    TRACK_TYPE_AUDIO,
    TRACK_TYPE_TEXT,
    TRACK_TYPE_VIDEO,
    make_draft_meta,
    make_empty_draft_content,
)

_log = logging.getLogger(__name__)


class JianyingExportBuilder:
    """Build a Jianying Professional draft package from timeline tracks."""

    def __init__(self, project_name: str, tracks: Dict[str, List[Dict]], *,
                 width: int = 1080, height: int = 1920):
        self._name = project_name
        self._tracks = tracks
        self._width = width
        self._height = height

    def build(self, output_dir: str) -> Dict[str, Any]:
        """Write draft_content.json + draft_meta_info.json to *output_dir*/{name}/."""
        out = Path(output_dir).expanduser().resolve()
        draft_dir = out / self._name
        draft_dir.mkdir(parents=True, exist_ok=True)

        total_ms = self._total_duration_ms()
        duration_us = total_ms * 1000  # microseconds

        content = make_empty_draft_content(duration_us, self._width, self._height)
        content["id"] = str(uuid.uuid4())
        content["name"] = self._name
        content["update_time"] = datetime.now().isoformat()

        # Build materials + tracks
        materials_videos: List[Dict] = []
        materials_audios: List[Dict] = []
        materials_texts: List[Dict] = []
        tracks_out: List[Dict] = []

        # Video track
        video_items = self._tracks.get("video", [])
        if video_items:
            segments = []
            for clip in video_items:
                mat_id = str(uuid.uuid4())
                uid = clip.get("uid", "")
                path = clip.get("path", "") or clip.get("absolute_path", "")
                materials_videos.append({
                    "id": mat_id,
                    "type": MATERIAL_TYPE_VIDEO,
                    "path": str(path),
                    "duration": (clip.get("end_ms", 0) - clip.get("start_ms", 0)) * 1000,
                })
                segments.append({
                    "id": str(uuid.uuid4()),
                    "material_id": mat_id,
                    "source_timerange": {
                        "start": 0,
                        "duration": (clip.get("end_ms", 0) - clip.get("start_ms", 0)) * 1000,
                    },
                    "target_timerange": {
                        "start": clip.get("start_ms", 0) * 1000,
                        "duration": (clip.get("end_ms", 0) - clip.get("start_ms", 0)) * 1000,
                    },
                    "extra_material_refs": [],
                    "visible": True,
                })
            tracks_out.append({
                "id": str(uuid.uuid4()),
                "type": TRACK_TYPE_VIDEO,
                "segments": segments,
            })

        # Subtitle track → text track
        sub_items = self._tracks.get("subtitle", [])
        if sub_items:
            segments = []
            for sub in sub_items:
                mat_id = str(uuid.uuid4())
                text = sub.get("text", "")
                materials_texts.append({
                    "id": mat_id,
                    "type": MATERIAL_TYPE_TEXT,
                    "content": text,
                })
                segments.append({
                    "id": str(uuid.uuid4()),
                    "material_id": mat_id,
                    "source_timerange": {
                        "start": 0,
                        "duration": (sub.get("end_ms", 0) - sub.get("start_ms", 0)) * 1000,
                    },
                    "target_timerange": {
                        "start": sub.get("start_ms", 0) * 1000,
                        "duration": (sub.get("end_ms", 0) - sub.get("start_ms", 0)) * 1000,
                    },
                    "extra_material_refs": [],
                    "visible": True,
                })
            tracks_out.append({
                "id": str(uuid.uuid4()),
                "type": TRACK_TYPE_TEXT,
                "segments": segments,
            })

        # Audio track
        audio_items = self._tracks.get("audio", [])
        if audio_items:
            segments = []
            for aud in audio_items:
                mat_id = str(uuid.uuid4())
                materials_audios.append({
                    "id": mat_id,
                    "type": MATERIAL_TYPE_AUDIO,
                    "path": "",
                    "duration": (aud.get("end_ms", 0) - aud.get("start_ms", 0)) * 1000,
                })
                segments.append({
                    "id": str(uuid.uuid4()),
                    "material_id": mat_id,
                    "source_timerange": {
                        "start": 0,
                        "duration": (aud.get("end_ms", 0) - aud.get("start_ms", 0)) * 1000,
                    },
                    "target_timerange": {
                        "start": aud.get("start_ms", 0) * 1000,
                        "duration": (aud.get("end_ms", 0) - aud.get("start_ms", 0)) * 1000,
                    },
                    "extra_material_refs": [],
                    "visible": True,
                })
            tracks_out.append({
                "id": str(uuid.uuid4()),
                "type": TRACK_TYPE_AUDIO,
                "segments": segments,
            })

        content["materials"]["videos"] = materials_videos
        content["materials"]["audios"] = materials_audios
        content["materials"]["texts"] = materials_texts
        content["tracks"] = tracks_out

        # Round-15: atomic writes — crash mid-export used to corrupt the
        # draft package, forcing the user to restart Jianying. Atomicity
        # via tempfile + os.replace in the shared helper.
        from modules.app_api.param_utils import atomic_write_json
        content_path = draft_dir / "draft_content.json"
        atomic_write_json(content_path, content)

        meta = make_draft_meta(self._name, self._width, self._height)
        meta["draft_id"] = content["id"]
        meta["draft_root_path"] = str(draft_dir)
        meta["tm_draft_create"] = content["update_time"]
        meta["tm_draft_modified"] = content["update_time"]
        meta_path = draft_dir / "draft_meta_info.json"
        atomic_write_json(meta_path, meta)

        _log.info("Jianying draft exported to %s", draft_dir)
        return {
            "draft_path": str(draft_dir),
            "content_file": str(content_path),
            "meta_file": str(meta_path),
            "tracks_count": len(tracks_out),
            "duration_ms": total_ms,
        }

    def _total_duration_ms(self) -> int:
        max_ms = 0
        for track_name in ("video", "subtitle", "audio"):
            for item in self._tracks.get(track_name, []):
                end = int(item.get("end_ms", 0) or 0)
                if end > max_ms:
                    max_ms = end
        return max_ms
