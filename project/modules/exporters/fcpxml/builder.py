"""FCPXMLBuilder — converts three-track timeline to FCPXML 1.9 for Final Cut Pro."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List

from modules.exporters.fcpxml.schema import (
    DEFAULT_FORMAT_NAME,
    FCPXML_DOCTYPE,
    FCPXML_VERSION,
    duration_cmtime,
    ms_to_cmtime,
)

_log = logging.getLogger(__name__)


class FCPXMLBuilder:
    """Build an FCPXML 1.9 file from timeline tracks."""

    def __init__(self, project_name: str, tracks: Dict[str, List[Dict]], *,
                 fps: int = 30, width: int = 1080, height: int = 1920):
        self._name = project_name
        self._tracks = tracks
        self._fps = fps
        self._width = width
        self._height = height

    def build(self, output_path: str) -> Dict[str, Any]:
        """Write .fcpxml file. Returns result dict."""
        out = Path(output_path).expanduser().resolve()
        out.parent.mkdir(parents=True, exist_ok=True)

        root = ET.Element("fcpxml", version=FCPXML_VERSION)

        # Resources
        resources = ET.SubElement(root, "resources")
        format_id = "r1"
        ET.SubElement(resources, "format", id=format_id, name=DEFAULT_FORMAT_NAME,
                      frameDuration=f"1/{self._fps}s",
                      width=str(self._width), height=str(self._height))

        # Asset definitions for video clips
        video_items = self._tracks.get("video", [])
        asset_map: Dict[str, str] = {}
        for i, clip in enumerate(video_items):
            asset_id = f"a{i+1}"
            uid = clip.get("uid", f"clip_{i}")
            path = clip.get("path", "") or clip.get("absolute_path", "")
            dur = duration_cmtime(clip.get("start_ms", 0), clip.get("end_ms", 0))
            src_uri = Path(path).resolve().as_uri() if path else ""
            ET.SubElement(resources, "asset", id=asset_id, name=uid,
                          src=src_uri,
                          duration=dur, format=format_id)
            asset_map[uid] = asset_id

        # Library > Event > Project > Sequence
        library = ET.SubElement(root, "library")
        event = ET.SubElement(library, "event", name=self._name)
        project = ET.SubElement(event, "project", name=self._name)

        total_ms = self._total_duration_ms()
        sequence = ET.SubElement(project, "sequence",
                                 duration=ms_to_cmtime(total_ms),
                                 format=format_id)

        spine = ET.SubElement(sequence, "spine")

        # Video clips → asset-clip elements
        for clip in video_items:
            uid = clip.get("uid", "")
            asset_id = asset_map.get(uid, "")
            start = clip.get("start_ms", 0)
            end = clip.get("end_ms", 0)
            ac = ET.SubElement(spine, "asset-clip",
                               ref=asset_id,
                               name=clip.get("label", uid),
                               offset=ms_to_cmtime(start),
                               duration=duration_cmtime(start, end),
                               format=format_id)

            # Attach subtitles that overlap this clip (clipped to clip range)
            for sub in self._tracks.get("subtitle", []):
                sub_start = sub.get("start_ms", 0)
                sub_end = sub.get("end_ms", 0)
                if sub_start < end and sub_end > start:
                    clipped_start = max(sub_start, start)
                    clipped_end = min(sub_end, end)
                    title = ET.SubElement(ac, "title",
                                         name=sub.get("text", ""),
                                         offset=ms_to_cmtime(clipped_start - start),
                                         duration=duration_cmtime(clipped_start, clipped_end))
                    text_el = ET.SubElement(title, "text")
                    text_style = ET.SubElement(text_el, "text-style")
                    text_style.text = sub.get("text", "")

        # Write XML
        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ")
        xml_str = FCPXML_DOCTYPE + ET.tostring(root, encoding="unicode")

        # Round-15: atomic XML write — crash mid-write used to corrupt the
        # .fcpxml file; FCP / Resolve would refuse to open it and the user
        # had to re-run the whole export. tempfile + fsync + os.replace
        # guarantees either the old file or the new file is visible, never
        # a partial write.
        import os as _os
        import tempfile as _tf
        fd, tmp = _tf.mkstemp(
            dir=str(out.parent), suffix=".fcpxml.tmp", prefix=out.name + "."
        )
        try:
            with _os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(xml_str)
                f.flush()
                _os.fsync(f.fileno())
            _os.replace(tmp, str(out))
        except BaseException:
            try:
                _os.unlink(tmp)
            except OSError:
                pass
            raise

        _log.info("FCPXML exported to %s", out)
        return {
            "fcpxml_path": str(out),
            "duration_ms": total_ms,
            "clip_count": len(video_items),
        }

    def _total_duration_ms(self) -> int:
        max_ms = 0
        for track_name in ("video", "subtitle", "audio"):
            for item in self._tracks.get(track_name, []):
                end = int(item.get("end_ms", 0) or 0)
                if end > max_ms:
                    max_ms = end
        return max_ms
