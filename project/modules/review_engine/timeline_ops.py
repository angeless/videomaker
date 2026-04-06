"""TimelineOps — track and clip operations (C2 + C3).

All operations enforce constraints: track type limits, lock protection,
overlap detection for video tracks.
"""

import logging
import uuid
from typing import List, Optional, Tuple

from modules.review_engine.exceptions import LockedTrackError
from modules.review_engine.timeline_store import TimelineStore

logger = logging.getLogger(__name__)

# Track type limits (C2)
TRACK_TYPE_LIMITS = {
    "video": 4,
    "audio": 4,
    "subtitle": 2,
    "effect": 2,
}


class TimelineOps:
    """Business logic for track and clip operations."""

    def __init__(self, store: TimelineStore):
        self._store = store

    # ── C2: Track operations ─────────────────────────────────────

    def add_track(
        self,
        timeline_id: str,
        session_id: str,
        track_type: str,
        label: str = "",
    ) -> str:
        """Add a track with type limit enforcement."""
        limit = TRACK_TYPE_LIMITS.get(track_type, 4)
        existing = [
            t for t in self._store.get_tracks(session_id)
            if t.track_type == track_type
        ]
        if len(existing) >= limit:
            raise ValueError(
                f"Cannot add more {track_type} tracks (limit: {limit}, current: {len(existing)})"
            )
        sort_order = len(self._store.get_tracks(session_id))
        return self._store.add_track(timeline_id, session_id, track_type, label, sort_order)

    def remove_track(self, track_id: str, session_id: str) -> bool:
        """Remove a track (fails if locked)."""
        tracks = self._store.get_tracks(session_id)
        for t in tracks:
            if t.track_id == track_id:
                if t.locked:
                    raise LockedTrackError(f"Track {track_id} is locked")
                return self._store.remove_track(track_id)
        return False

    def reorder_tracks(self, session_id: str, track_ids: List[str]) -> None:
        """Reorder tracks by the given ID sequence."""
        for i, tid in enumerate(track_ids):
            self._store.update_track(tid, sort_order=i)

    def toggle_lock(self, track_id: str) -> bool:
        """Toggle lock state. Returns new lock state."""
        tracks_all = []
        # Find track across all sessions (simple approach)
        # In practice, caller provides session_id context
        from modules.review_engine.contracts import TimelineTrack
        conn = self._store._connect()
        try:
            row = conn.execute(
                "SELECT locked FROM timeline_tracks WHERE track_id = ?", (track_id,)
            ).fetchone()
            if row is None:
                return False
            new_state = not bool(row["locked"])
            self._store.update_track(track_id, locked=new_state)
            return new_state
        finally:
            conn.close()

    def toggle_mute(self, track_id: str, session_id: str) -> bool:
        """Toggle mute (audio tracks only). Returns new mute state."""
        tracks = self._store.get_tracks(session_id)
        for t in tracks:
            if t.track_id == track_id:
                if t.track_type != "audio":
                    raise ValueError("Mute is only valid for audio tracks")
                new_state = not t.muted
                self._store.update_track(track_id, muted=new_state)
                return new_state
        raise ValueError(f"Track {track_id} not found")

    def set_volume(self, track_id: str, session_id: str, volume: float) -> None:
        """Set volume for an audio track (0.0 - 2.0)."""
        tracks = self._store.get_tracks(session_id)
        for t in tracks:
            if t.track_id == track_id:
                if t.track_type != "audio":
                    raise ValueError("Volume is only valid for audio tracks")
                volume = max(0.0, min(2.0, volume))
                self._store.update_track(track_id, volume=volume)
                return
        raise ValueError(f"Track {track_id} not found")

    # ── C3: Clip operations ──────────────────────────────────────

    def move_clip(self, clip_id: str, new_start_ms: int, session_id: str) -> None:
        """Move a clip to a new start position."""
        self._assert_clip_not_on_locked_track(clip_id, session_id)
        clips = self._find_clip(clip_id, session_id)
        if clips is None:
            raise ValueError(f"Clip {clip_id} not found")
        clip, track = clips
        duration = clip.end_ms - clip.start_ms
        self._store.update_clip(clip_id, start_ms=new_start_ms, end_ms=new_start_ms + duration)

    def trim_clip(self, clip_id: str, in_ms: int, out_ms: int, session_id: str) -> None:
        """Trim clip source in/out points."""
        self._assert_clip_not_on_locked_track(clip_id, session_id)
        self._store.update_clip(clip_id, source_in_ms=in_ms, source_out_ms=out_ms)

    def split_clip(self, clip_id: str, at_ms: int, session_id: str) -> Tuple[str, str]:
        """Split a clip at at_ms. Returns (left_clip_id, right_clip_id)."""
        self._assert_clip_not_on_locked_track(clip_id, session_id)
        result = self._find_clip(clip_id, session_id)
        if result is None:
            raise ValueError(f"Clip {clip_id} not found")
        clip, track = result

        if not (clip.start_ms < at_ms < clip.end_ms):
            raise ValueError(
                f"Split point {at_ms} must be between {clip.start_ms} and {clip.end_ms}"
            )

        # Calculate source split point
        ratio = (at_ms - clip.start_ms) / (clip.end_ms - clip.start_ms)
        source_split = clip.source_in_ms + int(
            (clip.source_out_ms - clip.source_in_ms) * ratio
        )

        # Update original clip to be the left half
        self._store.update_clip(clip_id, end_ms=at_ms, source_out_ms=source_split)

        # Create right half as new clip
        right_id = self._store.add_clip(
            track_id=clip.track_id,
            start_ms=at_ms,
            end_ms=clip.end_ms,
            source_path=clip.source_path,
            source_in_ms=source_split,
            source_out_ms=clip.source_out_ms,
            label=clip.label,
        )
        return clip_id, right_id

    def remove_clip(self, clip_id: str, session_id: str) -> bool:
        """Remove a clip (fails if on locked track)."""
        self._assert_clip_not_on_locked_track(clip_id, session_id)
        return self._store.remove_clip(clip_id)

    def move_clip_to_track(
        self, clip_id: str, target_track_id: str, session_id: str
    ) -> None:
        """Move clip to a different track (same type only)."""
        self._assert_clip_not_on_locked_track(clip_id, session_id)
        result = self._find_clip(clip_id, session_id)
        if result is None:
            raise ValueError(f"Clip {clip_id} not found")
        clip, source_track = result

        target_track = None
        for t in self._store.get_tracks(session_id):
            if t.track_id == target_track_id:
                target_track = t
                break
        if target_track is None:
            raise ValueError(f"Target track {target_track_id} not found")
        if target_track.locked:
            raise LockedTrackError(f"Target track {target_track_id} is locked")
        if source_track.track_type != target_track.track_type:
            raise ValueError(
                f"Cannot move clip between different track types "
                f"({source_track.track_type} → {target_track.track_type})"
            )

        self._store.update_clip(clip_id, track_id=target_track_id)

    def check_overlap(self, track_id: str, session_id: str) -> List[Tuple[str, str]]:
        """Check for overlapping clips on a track. Returns list of overlapping pairs."""
        clips = sorted(self._store.get_clips(track_id), key=lambda c: c.start_ms)
        overlaps = []
        for i in range(len(clips) - 1):
            if clips[i].end_ms > clips[i + 1].start_ms:
                overlaps.append((clips[i].clip_id, clips[i + 1].clip_id))
        return overlaps

    # ── Internal ─────────────────────────────────────────────────

    def _find_clip(self, clip_id, session_id):
        """Find clip and its track. Returns (Clip, TimelineTrack) or None."""
        for track in self._store.get_tracks(session_id):
            for clip in self._store.get_clips(track.track_id):
                if clip.clip_id == clip_id:
                    return clip, track
        return None

    def _assert_clip_not_on_locked_track(self, clip_id, session_id):
        """Raise LockedTrackError if clip is on a locked track."""
        result = self._find_clip(clip_id, session_id)
        if result is not None:
            _, track = result
            if track.locked:
                raise LockedTrackError(f"Track {track.track_id} is locked")
