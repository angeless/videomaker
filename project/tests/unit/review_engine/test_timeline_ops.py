"""Unit tests for TimelineOps — track operations (C2) + clip operations (C3)."""

import pytest

from modules.review_engine.exceptions import LockedTrackError
from modules.review_engine.timeline_store import TimelineStore
from modules.review_engine.timeline_ops import TimelineOps


@pytest.fixture
def ops(tmp_path):
    store = TimelineStore(str(tmp_path / "test.db"))
    return TimelineOps(store), store


def _setup(ops_store):
    ops, store = ops_store
    tid = store.create_timeline("s1")
    return ops, store, tid


# ═══ C2: Track operations ════════════════════════════════════════


def test_add_track(ops):
    o, store, tid = _setup(ops)
    track_id = o.add_track(tid, "s1", "video", "V1")
    tracks = store.get_tracks("s1")
    assert len(tracks) == 1
    assert tracks[0].track_type == "video"


def test_track_type_limit(ops):
    o, store, tid = _setup(ops)
    for i in range(4):
        o.add_track(tid, "s1", "video", f"V{i}")
    with pytest.raises(ValueError, match="limit"):
        o.add_track(tid, "s1", "video", "V5")


def test_remove_track(ops):
    o, store, tid = _setup(ops)
    track_id = o.add_track(tid, "s1", "audio", "A1")
    assert o.remove_track(track_id, "s1") is True
    assert len(store.get_tracks("s1")) == 0


def test_lock_prevents_removal(ops):
    o, store, tid = _setup(ops)
    track_id = o.add_track(tid, "s1", "video", "V1")
    store.update_track(track_id, locked=True)
    with pytest.raises(LockedTrackError):
        o.remove_track(track_id, "s1")


def test_toggle_mute(ops):
    o, store, tid = _setup(ops)
    track_id = o.add_track(tid, "s1", "audio", "A1")
    new_state = o.toggle_mute(track_id, "s1")
    assert new_state is True


def test_set_volume(ops):
    o, store, tid = _setup(ops)
    track_id = o.add_track(tid, "s1", "audio", "A1")
    o.set_volume(track_id, "s1", 0.5)
    tracks = store.get_tracks("s1")
    assert tracks[0].volume == 0.5


# ═══ C3: Clip operations ═════════════════════════════════════════


def test_move_clip(ops):
    o, store, tid = _setup(ops)
    track_id = o.add_track(tid, "s1", "video")
    clip_id = store.add_clip(track_id, 0, 5000, "/v/a.mp4")
    o.move_clip(clip_id, 2000, "s1")
    clips = store.get_clips(track_id)
    assert clips[0].start_ms == 2000
    assert clips[0].end_ms == 7000


def test_move_clip_rejects_overlap_on_video_track(ops):
    """Moving a video clip into an existing clip's range must raise OverlapError."""
    from modules.review_engine.exceptions import OverlapError
    o, store, tid = _setup(ops)
    track_id = o.add_track(tid, "s1", "video")
    clip_a = store.add_clip(track_id, 0, 5000, "/v/a.mp4")
    clip_b = store.add_clip(track_id, 10000, 15000, "/v/b.mp4")
    # Move clip_b so it would overlap clip_a (start=3000, end=8000 → overlaps [0, 5000))
    with pytest.raises(OverlapError):
        o.move_clip(clip_b, 3000, "s1")
    # State must be unchanged
    clips = sorted(store.get_clips(track_id), key=lambda c: c.start_ms)
    assert clips[1].start_ms == 10000


def test_add_clip_rejects_overlap_on_video_track(ops):
    """add_clip on a video track must raise OverlapError when ranges collide."""
    from modules.review_engine.exceptions import OverlapError
    o, store, tid = _setup(ops)
    track_id = o.add_track(tid, "s1", "video")
    o.add_clip(track_id, "s1", start_ms=0, end_ms=5000, source_path="/v/a.mp4")
    # Second clip overlaps [0, 5000) → must reject
    with pytest.raises(OverlapError):
        o.add_clip(track_id, "s1", start_ms=3000, end_ms=8000, source_path="/v/b.mp4")
    # Only the first clip should be present
    assert len(store.get_clips(track_id)) == 1


def test_add_clip_allows_overlap_on_audio_track(ops):
    """Audio tracks legitimately allow stacked clips (e.g. layered ambience)."""
    o, store, tid = _setup(ops)
    track_id = o.add_track(tid, "s1", "audio")
    o.add_clip(track_id, "s1", start_ms=0, end_ms=5000)
    # Overlap is allowed on audio — should not raise
    o.add_clip(track_id, "s1", start_ms=2000, end_ms=7000)
    assert len(store.get_clips(track_id)) == 2


def test_add_clip_rejects_locked_track(ops):
    """add_clip on a locked track must raise LockedTrackError."""
    o, store, tid = _setup(ops)
    track_id = o.add_track(tid, "s1", "video")
    store.update_track(track_id, locked=True)
    with pytest.raises(LockedTrackError):
        o.add_clip(track_id, "s1", start_ms=0, end_ms=5000)


def test_trim_clip(ops):
    o, store, tid = _setup(ops)
    track_id = o.add_track(tid, "s1", "video")
    clip_id = store.add_clip(track_id, 0, 5000, "/v/a.mp4", 0, 5000)
    o.trim_clip(clip_id, 1000, 4000, "s1")
    clips = store.get_clips(track_id)
    assert clips[0].source_in_ms == 1000
    assert clips[0].source_out_ms == 4000


def test_split_clip(ops):
    o, store, tid = _setup(ops)
    track_id = o.add_track(tid, "s1", "video")
    clip_id = store.add_clip(track_id, 0, 10000, "/v/a.mp4", 0, 10000)
    left_id, right_id = o.split_clip(clip_id, 5000, "s1")
    clips = sorted(store.get_clips(track_id), key=lambda c: c.start_ms)
    assert len(clips) == 2
    assert clips[0].end_ms == 5000
    assert clips[1].start_ms == 5000


def test_remove_clip(ops):
    o, store, tid = _setup(ops)
    track_id = o.add_track(tid, "s1", "video")
    clip_id = store.add_clip(track_id, 0, 5000)
    assert o.remove_clip(clip_id, "s1") is True
    assert store.get_clips(track_id) == []


def test_cross_track_move(ops):
    o, store, tid = _setup(ops)
    t1 = o.add_track(tid, "s1", "video", "V1")
    t2 = o.add_track(tid, "s1", "video", "V2")
    clip_id = store.add_clip(t1, 0, 5000)
    o.move_clip_to_track(clip_id, t2, "s1")
    assert len(store.get_clips(t1)) == 0
    assert len(store.get_clips(t2)) == 1


def test_overlap_detection(ops):
    o, store, tid = _setup(ops)
    track_id = o.add_track(tid, "s1", "video")
    store.add_clip(track_id, 0, 5000)
    store.add_clip(track_id, 3000, 8000)  # overlaps
    overlaps = o.check_overlap(track_id, "s1")
    assert len(overlaps) == 1


def test_locked_track_protects_clips(ops):
    o, store, tid = _setup(ops)
    track_id = o.add_track(tid, "s1", "video")
    clip_id = store.add_clip(track_id, 0, 5000)
    store.update_track(track_id, locked=True)
    with pytest.raises(LockedTrackError):
        o.remove_clip(clip_id, "s1")
