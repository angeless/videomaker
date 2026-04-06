"""Unit tests for TimelineStore (C1)."""

import os
import tempfile

import pytest

from modules.review_engine.timeline_store import TimelineStore


@pytest.fixture
def store(tmp_path):
    """Fresh TimelineStore with temp DB."""
    db_path = str(tmp_path / "test_timeline.db")
    return TimelineStore(db_path)


# ── T1: create_timeline ─────────────────────────────────────────

def test_create_timeline(store):
    tid = store.create_timeline("session_1")
    assert isinstance(tid, str)
    assert len(tid) > 0


# ── T2: add_track ───────────────────────────────────────────────

def test_add_track(store):
    tid = store.create_timeline("s1")
    track_id = store.add_track(tid, "s1", "video", label="V1")
    assert isinstance(track_id, str)

    tracks = store.get_tracks("s1")
    assert len(tracks) == 1
    assert tracks[0].track_type == "video"
    assert tracks[0].label == "V1"


# ── T3: add_clip ────────────────────────────────────────────────

def test_add_clip(store):
    tid = store.create_timeline("s1")
    track_id = store.add_track(tid, "s1", "video")
    clip_id = store.add_clip(track_id, start_ms=0, end_ms=5000,
                             source_path="/v/clip1.mp4", source_in_ms=0, source_out_ms=5000)
    assert isinstance(clip_id, str)

    clips = store.get_clips(track_id)
    assert len(clips) == 1
    assert clips[0].start_ms == 0
    assert clips[0].end_ms == 5000
    assert clips[0].source_path == "/v/clip1.mp4"


# ── T4: update_clip ─────────────────────────────────────────────

def test_update_clip(store):
    tid = store.create_timeline("s1")
    track_id = store.add_track(tid, "s1", "video")
    clip_id = store.add_clip(track_id, start_ms=0, end_ms=5000)

    store.update_clip(clip_id, start_ms=1000, end_ms=6000)

    clips = store.get_clips(track_id)
    assert clips[0].start_ms == 1000
    assert clips[0].end_ms == 6000


# ── T5: remove track + clips ────────────────────────────────────

def test_remove_track(store):
    tid = store.create_timeline("s1")
    track_id = store.add_track(tid, "s1", "audio")
    store.add_clip(track_id, start_ms=0, end_ms=3000)

    removed = store.remove_track(track_id)
    assert removed is True

    clips = store.get_clips(track_id)
    assert clips == []

    tracks = store.get_tracks("s1")
    assert tracks == []


# ── T6: auto migration (tables created on init) ─────────────────

def test_migration(tmp_path):
    db_path = str(tmp_path / "fresh.db")
    store = TimelineStore(db_path)
    # If we got here without error, tables were created
    tid = store.create_timeline("s1")
    track_id = store.add_track(tid, "s1", "subtitle")
    assert track_id is not None


# ── T7: get_timeline returns full nested structure ───────────────

def test_get_timeline(store):
    tid = store.create_timeline("s1")
    t1 = store.add_track(tid, "s1", "video", label="V1", sort_order=0)
    t2 = store.add_track(tid, "s1", "audio", label="A1", sort_order=1)
    store.add_clip(t1, start_ms=0, end_ms=5000, source_path="/v/a.mp4")
    store.add_clip(t2, start_ms=0, end_ms=5000, source_path="/a/bgm.mp3")

    tl = store.get_timeline("s1")
    assert tl is not None
    assert tl.session_id == "s1"
    assert len(tl.tracks) == 2
    assert len(tl.tracks[0].clips) == 1
    assert tl.duration_ms == 5000
