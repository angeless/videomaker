import os
from pathlib import Path
import json
import sys
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.capabilities.audio_voice import (
    build_audio_capability_payload,
    build_elevenlabs_tts_payload,
    build_voiceover_timeline,
    mix_voiceover_to_video,
    pick_bgm,
    pick_bgm_track,
    synthesize_voiceover_segments,
)
from modules.capabilities.article_expand import generate_article_expansion
from modules.capabilities.content_publish import (
    bootstrap_publish_session,
    build_publish_plan,
    list_publish_platforms,
    run_publish_plan,
)
from modules.capabilities.nle_handoff import (
    build_nle_launch_command,
    collect_nle_master_video,
    create_nle_handoff,
    find_latest_video_candidate,
    launch_nle_handoff,
)
from modules.capabilities.short_clip import HighlightCandidate, pick_highlights
from modules.capabilities.social_export import (
    build_export_plan,
    build_ffmpeg_export_cmd,
    list_export_profiles,
    list_export_specs,
    validate_source_for_export,
)
from modules.capabilities.text_rough_cut import (
    TranscriptSpan,
    build_text_rough_cut_plan,
    parse_span_index_expr,
)
from modules.capabilities.topic_library import TopicTemplate, search_topics, upsert_topic


def test_topic_library_upsert_and_search(tmp_path):
    db_path = tmp_path / "topics.db"
    upsert_topic(
        str(db_path),
        TopicTemplate(
            slug="winter-trip",
            title="Winter Trip",
            category="travel",
            tags=["snow", "vlog"],
        ),
    )
    results = search_topics(str(db_path), query="winter")
    assert len(results) == 1
    assert results[0]["slug"] == "winter-trip"


def test_text_rough_cut_plan_with_trim_and_filter():
    spans = [
        TranscriptSpan(start=0.0, end=1.0, text="hello everyone"),
        TranscriptSpan(start=1.02, end=2.0, text="uh today"),
        TranscriptSpan(start=3.0, end=4.0, text="let us go"),
    ]
    plan = build_text_rough_cut_plan(
        spans,
        removed_phrases=["uh"],
        target_duration_s=1.5,
    )
    assert plan["duration_s"] <= 1.5
    assert len(plan["segments"]) >= 1


def test_text_rough_cut_parse_span_index_expr():
    parsed = parse_span_index_expr("1, 2,5-7,7-6,abc,0,-1, 20", max_index=10)
    assert parsed == [1, 2, 5, 6, 7]


def test_text_rough_cut_plan_with_keep_and_drop_indexes():
    spans = [
        TranscriptSpan(start=0.0, end=1.0, text="a"),
        TranscriptSpan(start=1.2, end=2.0, text="b"),
        TranscriptSpan(start=2.1, end=3.0, text="c"),
        TranscriptSpan(start=3.1, end=4.0, text="d"),
    ]
    plan = build_text_rough_cut_plan(
        spans,
        removed_phrases=[],
        keep_span_indexes=[1, 2, 4],
        drop_span_indexes=[2],
        apply_removed_phrases=True,
    )
    kept_texts = [item["text"] for item in plan["kept_spans"]]
    assert kept_texts == ["a", "d"]
    assert plan["total_span_count"] == 4
    assert plan["kept_span_count"] == 2
    assert plan["removed_by_selection_count"] >= 1


def test_text_rough_cut_plan_can_disable_phrase_filter():
    spans = [
        TranscriptSpan(start=0.0, end=1.0, text="uh hello"),
        TranscriptSpan(start=1.2, end=2.0, text="normal"),
    ]
    plan = build_text_rough_cut_plan(
        spans,
        removed_phrases=["uh"],
        apply_removed_phrases=False,
    )
    assert plan["kept_span_count"] == 2
    assert plan["removed_by_phrase_count"] == 0


def test_short_clip_selection_budget_and_overlap():
    picks = pick_highlights(
        [
            HighlightCandidate(0.0, 3.0, 0.9, "hook"),
            HighlightCandidate(2.8, 6.0, 0.8, "overlap"),
            HighlightCandidate(7.0, 11.0, 0.95, "peak"),
        ],
        target_duration_s=5.0,
        max_clips=3,
    )
    total = sum(x.end - x.start for x in picks)
    assert total <= 5.01
    assert len(picks) >= 1


def test_social_export_cmd_builds_profile_args():
    cmd = build_ffmpeg_export_cmd("in.mp4", "out.mp4", "douyin")
    assert cmd[0] == "ffmpeg"
    assert any("scale=1080:1920" in part for part in cmd)
    assert cmd[-1] == "out.mp4"


def test_social_export_build_plan(tmp_path):
    in_video = tmp_path / "in.mp4"
    in_video.write_bytes(b"fake")
    out_dir = tmp_path / "exports"
    plan = build_export_plan(
        input_video=str(in_video),
        output_dir=str(out_dir),
        platform_ids=["douyin", "tiktok"],
        quality="high",
    )
    assert len(plan["jobs"]) == 2
    assert plan["jobs"][0]["platform_id"] == "douyin"
    assert "command" in plan["jobs"][0]


def test_social_export_build_plan_supports_cn_alias(tmp_path):
    in_video = tmp_path / "in.mp4"
    in_video.write_bytes(b"fake")
    out_dir = tmp_path / "exports"
    plan = build_export_plan(
        input_video=str(in_video),
        output_dir=str(out_dir),
        platform_ids=["微信短视频", "微信公众号", "b站视频", "YouTube视频"],
        quality="high",
    )
    pids = [job["platform_id"] for job in plan["jobs"]]
    assert pids == ["wechat_short", "wechat_mp", "bilibili", "youtube"]


def test_social_export_profiles_include_required_base_templates():
    profiles = list_export_profiles()
    ids = {item["platform_id"] for item in profiles}
    assert {"tiktok", "wechat_short", "douyin", "xiaohongshu", "wechat_mp", "bilibili", "youtube"}.issubset(ids)
    assert {"ixigua", "wechat_channels", "instagram", "twitter", "threads", "facebook", "blog"}.issubset(ids)


def test_social_export_profiles_merge_custom_templates():
    profiles = list_export_profiles(
        profile_overrides={
            "travel_square": {
                "platform_id": "travel_square",
                "name": "旅行方屏 1:1",
                "width": 1080,
                "height": 1080,
                "fps": 30,
                "video_bitrate": "8M",
                "audio_bitrate": "192k",
                "max_duration_s": 120,
            }
        }
    )
    lookup = {item["platform_id"]: item for item in profiles}
    assert lookup["travel_square"]["width"] == 1080
    assert lookup["travel_square"]["height"] == 1080


def test_social_export_specs_include_codec_and_aliases():
    specs = list_export_specs()
    lookup = {item["platform_id"]: item for item in specs}
    douyin = lookup["douyin"]
    assert douyin["container"] == "mp4"
    assert douyin["video_codec"] == "h264"
    assert douyin["audio_codec"] == "aac"
    assert douyin["pixel_format"] == "yuv420p"
    assert "抖音短视频" in douyin["aliases"]
    assert douyin["aspect_ratio_label"] == "9:16"


def test_social_export_build_plan_strict_duration_limit(tmp_path, monkeypatch):
    in_video = tmp_path / "in.mp4"
    in_video.write_bytes(b"fake")
    out_dir = tmp_path / "exports"
    monkeypatch.setattr("modules.capabilities.social_export.probe_video_duration", lambda *_args, **_kwargs: 240.0)

    strict_plan = build_export_plan(
        input_video=str(in_video),
        output_dir=str(out_dir),
        platform_ids=["douyin"],
        quality="high",
        strict_duration_limit=True,
    )
    strict_job = strict_plan["jobs"][0]
    assert strict_job["trim_applied"] is True
    assert strict_job["effective_duration_s"] == 180.0
    assert "-t" in strict_job["command"]

    loose_plan = build_export_plan(
        input_video=str(in_video),
        output_dir=str(out_dir),
        platform_ids=["douyin"],
        quality="high",
        strict_duration_limit=False,
    )
    loose_job = loose_plan["jobs"][0]
    assert loose_job["trim_applied"] is False
    assert loose_job["effective_duration_s"] == 240.0
    assert "-t" not in loose_job["command"]


def test_social_export_build_plan_supports_custom_profile_override(tmp_path):
    in_video = tmp_path / "in.mp4"
    in_video.write_bytes(b"fake")
    out_dir = tmp_path / "exports"
    plan = build_export_plan(
        input_video=str(in_video),
        output_dir=str(out_dir),
        platform_ids=["travel_square"],
        quality="high",
        profile_overrides={
            "travel_square": {
                "platform_id": "travel_square",
                "name": "旅行方屏 1:1",
                "width": 1080,
                "height": 1080,
                "fps": 30,
                "video_bitrate": "8M",
                "audio_bitrate": "192k",
                "max_duration_s": 120,
            }
        },
    )
    job = plan["jobs"][0]
    assert job["platform_id"] == "travel_square"
    assert "scale=1080:1080" in "".join(job["command"])


def test_social_export_validate_source_detects_transforms(monkeypatch):
    monkeypatch.setattr(
        "modules.capabilities.social_export.probe_video_meta",
        lambda *_args, **_kwargs: {
            "duration_s": 240.0,
            "width": 720,
            "height": 1280,
            "fps": 25.0,
            "aspect_ratio": 0.5625,
            "aspect_ratio_label": "9:16",
            "has_audio_stream": True,
            "audio_streams": 1,
        },
    )
    report = validate_source_for_export(
        input_video="in.mp4",
        platform_ids=["抖音短视频", "b站视频"],
        strict_duration_limit=True,
    )
    checks = {item["platform_id"]: item for item in report["checks"]}
    douyin = checks["douyin"]
    bilibili = checks["bilibili"]
    assert douyin["trim_required"] is True
    assert douyin["upscale_required"] is True
    assert douyin["aspect_transform_required"] is False
    assert bilibili["trim_required"] is False
    assert bilibili["upscale_required"] is True
    assert bilibili["aspect_transform_required"] is True
    assert report["summary"]["strict_trim_required_platforms"] == 1
    assert report["summary"]["transform_required_platforms"] == 2


def test_social_export_validate_source_can_disable_trim(monkeypatch):
    monkeypatch.setattr(
        "modules.capabilities.social_export.probe_video_meta",
        lambda *_args, **_kwargs: {
            "duration_s": 240.0,
            "width": 1080,
            "height": 1920,
            "fps": 30.0,
            "aspect_ratio": 0.5625,
            "aspect_ratio_label": "9:16",
            "has_audio_stream": True,
            "audio_streams": 1,
        },
    )
    report = validate_source_for_export(
        input_video="in.mp4",
        platform_ids=["douyin"],
        strict_duration_limit=False,
    )
    check = report["checks"][0]
    assert check["duration_exceeded"] is True
    assert check["trim_required"] is False
    assert any("未启用严格时长截断" in msg for msg in check["warnings"])


def test_article_expand_generate_basics():
    result = generate_article_expansion(
        source_text="这是公众号扩写输入文本，包含拍摄与发布复盘。",
        key_points=["拍摄", "剪辑", "发布"],
    )
    assert result["platform_id"] == "wechat_mp"
    assert len(result["title_candidates"]) >= 1
    assert len(result["sections"]) >= 3


def test_content_publish_plan_and_run_with_session():
    session = bootstrap_publish_session(authenticated=True, expires_in_minutes=30)
    platforms = list_publish_platforms()["groups"]["domestic"]
    plan = build_publish_plan(
        content={"title": "发布标题", "description": "发布描述", "keywords": ["旅行"]},
        platform_ids=platforms[:2],
        dry_run=False,
        session=session,
    )
    result = run_publish_plan(plan=plan, session=session, dry_run=False)
    assert result["status"] == "posted"
    assert result["summary"]["posted"] == 2


def test_audio_voice_payload_contains_plan():
    payload = build_audio_capability_payload(
        {
            "clips": [{"duration": 2.0}, {"duration": 3.0}],
            "subtitles": [{"cn_text": "你好世界", "start_time": 0.0, "end_time": 1.5}],
        }
    )
    assert payload["music_plan"]["duration_s"] == 5.0
    assert len(payload["voiceover_segments"]) == 1


def test_audio_voice_build_elevenlabs_payload():
    payload = build_elevenlabs_tts_payload("你好世界", model_id="eleven_multilingual_v2")
    assert payload["text"] == "你好世界"
    assert payload["model_id"] == "eleven_multilingual_v2"
    assert "voice_settings" in payload


def test_audio_voice_synthesize_dry_run(tmp_path):
    result = synthesize_voiceover_segments(
        [{"start": 0.0, "end": 1.2, "text": "你好，欢迎来到冰岛"}],
        output_dir=str(tmp_path / "voice"),
        provider="elevenlabs",
        voice_id="voice_abc",
        dry_run=True,
    )
    assert result["dry_run"] is True
    assert result["total_segments"] == 1
    assert result["segments"][0]["status"] == "planned"
    assert result["segments"][0]["output_audio"].endswith(".mp3")


def test_audio_voice_synthesize_requires_api_key_when_not_dry(tmp_path):
    with pytest.raises(ValueError):
        synthesize_voiceover_segments(
            [{"start": 0.0, "end": 1.2, "text": "hello"}],
            output_dir=str(tmp_path / "voice"),
            provider="elevenlabs",
            voice_id="voice_abc",
            api_key="",
            dry_run=False,
        )


def test_audio_voice_build_timeline_dry_run(tmp_path):
    clip1 = tmp_path / "seg1.mp3"
    clip2 = tmp_path / "seg2.mp3"
    clip1.write_bytes(b"a")
    clip2.write_bytes(b"b")
    ret = build_voiceover_timeline(
        [
            {"output_audio": str(clip2), "start": 2.0, "text": "b"},
            {"output_audio": str(clip1), "start": 0.5, "text": "a"},
        ],
        output_audio=str(tmp_path / "narration.m4a"),
        dry_run=True,
    )
    assert ret["status"] == "planned"
    assert ret["total_segments"] == 2
    assert "adelay=500|500" in " ".join(ret["command"])


def test_audio_voice_mix_master_dry_run(tmp_path, monkeypatch):
    video = tmp_path / "in.mp4"
    nar = tmp_path / "nar.m4a"
    bgm = tmp_path / "bgm.mp3"
    video.write_bytes(b"v")
    nar.write_bytes(b"n")
    bgm.write_bytes(b"b")
    monkeypatch.setattr("modules.capabilities.audio_voice._probe_has_audio_stream", lambda *_args, **_kwargs: True)
    ret = mix_voiceover_to_video(
        input_video=str(video),
        output_video=str(tmp_path / "out.mp4"),
        narration_audio=str(nar),
        bgm_audio=str(bgm),
        dry_run=True,
    )
    assert ret["status"] == "planned"
    assert ret["has_origin_audio"] is True
    assert "amix=inputs=3" in " ".join(ret["command"])


def test_audio_voice_mix_master_dry_run_without_ducking(tmp_path, monkeypatch):
    video = tmp_path / "in.mp4"
    nar = tmp_path / "nar.m4a"
    bgm = tmp_path / "bgm.mp3"
    video.write_bytes(b"v")
    nar.write_bytes(b"n")
    bgm.write_bytes(b"b")
    monkeypatch.setattr("modules.capabilities.audio_voice._probe_has_audio_stream", lambda *_args, **_kwargs: True)
    ret = mix_voiceover_to_video(
        input_video=str(video),
        output_video=str(tmp_path / "out.mp4"),
        narration_audio=str(nar),
        bgm_audio=str(bgm),
        enable_ducking=False,
        dry_run=True,
    )
    cmd = " ".join(ret["command"])
    assert ret["status"] == "planned"
    assert "sidechaincompress" not in cmd


def test_audio_voice_mix_master_bgm_loop_and_fade(tmp_path, monkeypatch):
    video = tmp_path / "in.mp4"
    nar = tmp_path / "nar.m4a"
    bgm = tmp_path / "bgm.mp3"
    video.write_bytes(b"v")
    nar.write_bytes(b"n")
    bgm.write_bytes(b"b")
    monkeypatch.setattr("modules.capabilities.audio_voice._probe_has_audio_stream", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("modules.capabilities.audio_voice._probe_media_duration", lambda *_args, **_kwargs: 35.0)
    ret = mix_voiceover_to_video(
        input_video=str(video),
        output_video=str(tmp_path / "out.mp4"),
        narration_audio=str(nar),
        bgm_audio=str(bgm),
        bgm_loop=True,
        bgm_fade_out_s=2.5,
        enable_ducking=False,
        dry_run=True,
    )
    cmd_text = " ".join(ret["command"])
    assert ret["status"] == "planned"
    assert "-stream_loop -1" in cmd_text
    assert "atrim=duration=35.000" in cmd_text
    assert "afade=t=out:st=32.500:d=2.500" in cmd_text


def test_audio_voice_mix_master_bgm_no_loop(tmp_path, monkeypatch):
    video = tmp_path / "in.mp4"
    nar = tmp_path / "nar.m4a"
    bgm = tmp_path / "bgm.mp3"
    video.write_bytes(b"v")
    nar.write_bytes(b"n")
    bgm.write_bytes(b"b")
    monkeypatch.setattr("modules.capabilities.audio_voice._probe_has_audio_stream", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("modules.capabilities.audio_voice._probe_media_duration", lambda *_args, **_kwargs: 40.0)
    ret = mix_voiceover_to_video(
        input_video=str(video),
        output_video=str(tmp_path / "out.mp4"),
        narration_audio=str(nar),
        bgm_audio=str(bgm),
        bgm_loop=False,
        enable_ducking=False,
        dry_run=True,
    )
    cmd_text = " ".join(ret["command"])
    assert ret["status"] == "planned"
    assert "-stream_loop -1" not in cmd_text
    assert "atrim=duration=" not in cmd_text
    assert "afade=t=out" not in cmd_text


def test_audio_voice_mix_master_remote_bgm_url(tmp_path, monkeypatch):
    video = tmp_path / "in.mp4"
    nar = tmp_path / "nar.m4a"
    video.write_bytes(b"v")
    nar.write_bytes(b"n")
    monkeypatch.setattr("modules.capabilities.audio_voice._probe_has_audio_stream", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("modules.capabilities.audio_voice._probe_media_duration", lambda *_args, **_kwargs: 30.0)
    ret = mix_voiceover_to_video(
        input_video=str(video),
        output_video=str(tmp_path / "out.mp4"),
        narration_audio=str(nar),
        bgm_audio="https://cdn.example.com/audio/theme.mp3",
        bgm_loop=True,
        enable_ducking=False,
        dry_run=True,
    )
    cmd_text = " ".join(ret["command"])
    assert ret["status"] == "planned"
    assert ret["bgm_is_remote"] is True
    assert ret["bgm_audio"] == "https://cdn.example.com/audio/theme.mp3"
    assert ret["bgm_loop_applied"] is False
    assert "远端 BGM URL" in ret["bgm_loop_fallback_reason"]
    assert "https://cdn.example.com/audio/theme.mp3" in cmd_text
    assert "-stream_loop -1" not in cmd_text


def test_audio_voice_mix_master_ducking_fallback_when_filter_missing(tmp_path, monkeypatch):
    video = tmp_path / "in.mp4"
    nar = tmp_path / "nar.m4a"
    bgm = tmp_path / "bgm.mp3"
    video.write_bytes(b"v")
    nar.write_bytes(b"n")
    bgm.write_bytes(b"b")
    monkeypatch.setattr("modules.capabilities.audio_voice._probe_has_audio_stream", lambda *_args, **_kwargs: True)
    monkeypatch.setattr("modules.capabilities.audio_voice._ffmpeg_supports_filter", lambda *_args, **_kwargs: False)
    ret = mix_voiceover_to_video(
        input_video=str(video),
        output_video=str(tmp_path / "out.mp4"),
        narration_audio=str(nar),
        bgm_audio=str(bgm),
        enable_ducking=True,
        dry_run=True,
    )
    cmd = " ".join(ret["command"])
    assert ret["status"] == "planned"
    assert ret["ducking_applied"] is False
    assert "sidechaincompress" not in cmd
    assert "降级" in ret["ducking_fallback_reason"]


def test_audio_voice_pick_bgm_track_selects_best_candidate(tmp_path, monkeypatch):
    music_dir = tmp_path / "bgm"
    music_dir.mkdir(parents=True)
    travel = music_dir / "travel_story_theme.mp3"
    generic = music_dir / "random_loop.mp3"
    travel.write_bytes(b"a")
    generic.write_bytes(b"b")

    durations = {
        str(travel): 170.0,
        str(generic): 80.0,
    }
    monkeypatch.setattr(
        "modules.capabilities.audio_voice._probe_media_duration",
        lambda path, ffprobe_bin="ffprobe": durations.get(str(path)),
    )
    pick = pick_bgm_track(
        mood="travel_story",
        target_duration_s=120,
        library_dirs=[str(music_dir)],
    )
    assert pick["status"] == "selected"
    assert pick["selected_track"] == str(travel)
    assert pick["total_tracks"] == 2


def test_audio_voice_pick_bgm_track_empty_dirs():
    pick = pick_bgm_track(
        mood="travel_story",
        target_duration_s=60,
        library_dirs=[],
    )
    assert pick["status"] == "empty_library"
    assert pick["selected_track"] == ""


def test_audio_voice_pick_bgm_wrapper_local(tmp_path, monkeypatch):
    music_dir = tmp_path / "bgm"
    music_dir.mkdir(parents=True)
    t1 = music_dir / "travel_theme.mp3"
    t1.write_bytes(b"a")
    monkeypatch.setattr("modules.capabilities.audio_voice._probe_media_duration", lambda *_args, **_kwargs: 120.0)
    pick = pick_bgm(
        provider="local_library",
        mood="travel_story",
        target_duration_s=90,
        library_dirs=[str(music_dir)],
    )
    assert pick["provider"] == "local_library"
    assert pick["status"] == "selected"
    assert pick["selected_track"] == str(t1)


def test_audio_voice_pick_bgm_remote_download(tmp_path, monkeypatch):
    out_dir = tmp_path / "remote_bgm"
    req_urls = []

    class _Resp:
        def __init__(self, body: bytes):
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req, timeout=0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        req_urls.append(url)
        if url.endswith("/pick"):
            payload = {
                "tracks": [
                    {
                        "title": "Coastal Drive",
                        "audio_url": "https://cdn.example.com/music/coastal_drive.mp3",
                        "duration_s": 140.0,
                        "score": 0.92,
                    }
                ]
            }
            return _Resp(json.dumps(payload).encode("utf-8"))
        return _Resp(b"FAKE_MP3_BYTES")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    pick = pick_bgm(
        provider="elevencreative_compatible",
        mood="travel_story",
        target_duration_s=120,
        endpoint="https://api.example.com/pick",
        api_key="sk_demo",
        output_dir=str(out_dir),
        download_audio=True,
    )
    assert pick["provider"] == "elevencreative_compatible"
    assert pick["status"] == "selected"
    assert pick["selected_track"].endswith(".mp3")
    assert Path(pick["selected_track"]).exists()
    assert any(url.endswith("/pick") for url in req_urls)
    assert any("cdn.example.com/music/coastal_drive.mp3" in url for url in req_urls)


def test_audio_voice_pick_bgm_remote_download_cache_hit(tmp_path, monkeypatch):
    out_dir = tmp_path / "remote_bgm_cache"
    download_calls = {"n": 0}

    class _Resp:
        def __init__(self, body: bytes):
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req, timeout=0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url.endswith("/pick"):
            payload = {
                "tracks": [
                    {
                        "title": "Ocean Breeze",
                        "audio_url": "https://cdn.example.com/music/ocean_breeze.mp3",
                        "duration_s": 128.0,
                        "score": 0.88,
                    }
                ]
            }
            return _Resp(json.dumps(payload).encode("utf-8"))
        download_calls["n"] += 1
        return _Resp(b"FAKE_MP3_BYTES")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    first = pick_bgm(
        provider="elevencreative_compatible",
        mood="travel_story",
        target_duration_s=110,
        endpoint="https://api.example.com/pick",
        api_key="sk_demo",
        output_dir=str(out_dir),
        download_audio=True,
        cache_enabled=True,
    )
    second = pick_bgm(
        provider="elevencreative_compatible",
        mood="travel_story",
        target_duration_s=110,
        endpoint="https://api.example.com/pick",
        api_key="sk_demo",
        output_dir=str(out_dir),
        download_audio=True,
        cache_enabled=True,
    )
    assert first["status"] == "selected"
    assert second["status"] == "selected"
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert first["selected_track"] == second["selected_track"]
    assert download_calls["n"] == 1


def test_audio_voice_pick_bgm_remote_force_refresh(tmp_path, monkeypatch):
    out_dir = tmp_path / "remote_bgm_force"
    download_calls = {"n": 0}

    class _Resp:
        def __init__(self, body: bytes):
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req, timeout=0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url.endswith("/pick"):
            payload = {
                "tracks": [
                    {
                        "title": "Night Ride",
                        "audio_url": "https://cdn.example.com/music/night_ride.mp3",
                        "duration_s": 100.0,
                        "score": 0.81,
                    }
                ]
            }
            return _Resp(json.dumps(payload).encode("utf-8"))
        download_calls["n"] += 1
        return _Resp(b"FAKE_MP3_BYTES")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    _ = pick_bgm(
        provider="elevencreative_compatible",
        mood="travel_story",
        endpoint="https://api.example.com/pick",
        api_key="sk_demo",
        output_dir=str(out_dir),
        download_audio=True,
        cache_enabled=True,
        force_refresh=False,
    )
    second = pick_bgm(
        provider="elevencreative_compatible",
        mood="travel_story",
        endpoint="https://api.example.com/pick",
        api_key="sk_demo",
        output_dir=str(out_dir),
        download_audio=True,
        cache_enabled=True,
        force_refresh=True,
    )
    assert second["status"] == "selected"
    assert second["force_refresh"] is True
    assert second["download_applied"] is True
    assert download_calls["n"] == 2


def test_audio_voice_pick_bgm_remote_cache_ttl_expired(tmp_path, monkeypatch):
    out_dir = tmp_path / "remote_bgm_ttl"
    download_calls = {"n": 0}

    class _Resp:
        def __init__(self, body: bytes):
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req, timeout=0):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        if url.endswith("/pick"):
            payload = {
                "tracks": [
                    {
                        "title": "Sunset Trail",
                        "audio_url": "https://cdn.example.com/music/sunset_trail.mp3",
                        "duration_s": 118.0,
                        "score": 0.86,
                    }
                ]
            }
            return _Resp(json.dumps(payload).encode("utf-8"))
        download_calls["n"] += 1
        return _Resp(b"FAKE_MP3_BYTES")

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    first = pick_bgm(
        provider="elevencreative_compatible",
        mood="travel_story",
        endpoint="https://api.example.com/pick",
        api_key="sk_demo",
        output_dir=str(out_dir),
        download_audio=True,
        cache_enabled=True,
        cache_max_age_seconds=60.0,
    )
    cache_file = Path(first["selected_track"])
    assert cache_file.exists()
    # Push file mtime to older than ttl.
    old_time = cache_file.stat().st_mtime - 120.0
    os.utime(cache_file, (old_time, old_time))

    second = pick_bgm(
        provider="elevencreative_compatible",
        mood="travel_story",
        endpoint="https://api.example.com/pick",
        api_key="sk_demo",
        output_dir=str(out_dir),
        download_audio=True,
        cache_enabled=True,
        cache_max_age_seconds=60.0,
    )
    assert second["status"] == "selected"
    assert second["cache_expired"] is True
    assert second["download_applied"] is True
    assert download_calls["n"] == 2


def test_audio_voice_pick_bgm_remote_strict_schema_rejects_invalid(tmp_path, monkeypatch):
    class _Resp:
        def __init__(self, body: bytes):
            self._body = body

        def read(self):
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(req, timeout=0):
        _ = timeout
        # Missing tracks[] in strict mode.
        return _Resp(json.dumps({"candidates": [{"url": "https://cdn.example.com/a.mp3"}]}).encode("utf-8"))

    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)
    with pytest.raises(RuntimeError):
        pick_bgm(
            provider="elevencreative_compatible",
            mood="travel_story",
            endpoint="https://api.example.com/pick",
            api_key="sk_demo",
            output_dir=str(tmp_path / "strict"),
            download_audio=False,
            strict_schema=True,
        )


def test_nle_handoff_generates_exchange_files(tmp_path):
    v1 = tmp_path / "a.mp4"
    v2 = tmp_path / "b.mp4"
    v1.write_bytes(b"x")
    v2.write_bytes(b"y")
    script = {
        "clips": [
            {"video_id": "clip_a", "source_start": 0, "source_end": 3, "scene_description": "a"},
            {"video_id": "clip_b", "source_start": 1, "source_end": 4, "scene_description": "b"},
        ]
    }
    materials = {
        "clip_a": {"path": str(v1)},
        "clip_b": {"path": str(v2)},
    }
    ret = create_nle_handoff(
        script=script,
        materials=materials,
        output_dir=str(tmp_path / "handoff"),
        editor="davinci",
        title="Demo",
        fps=30,
    )
    assert ret["editor"] == "davinci"
    assert ret["clip_count"] == 2
    assert any(p.endswith(".fcpxml") for p in ret["files"])
    assert any(p.endswith(".edl") for p in ret["files"])


def test_nle_launch_command_uses_default_mac_app(tmp_path):
    target = tmp_path / "timeline.fcpxml"
    target.write_text("<fcpxml/>", encoding="utf-8")
    launch = build_nle_launch_command(
        editor="finalcut",
        target_file=str(target),
        platform_key="darwin",
    )
    assert launch["platform"] == "darwin"
    assert launch["app_name"] == "Final Cut Pro"
    assert launch["command"][:3] == ["open", "-a", "Final Cut Pro"]
    assert launch["command"][-1] == str(target.resolve())


def test_nle_launch_handoff_dry_run_prefers_editor_format(tmp_path):
    fcpx = tmp_path / "timeline.fcpxml"
    edl = tmp_path / "timeline.edl"
    fcpx.write_text("<fcpxml/>", encoding="utf-8")
    edl.write_text("TITLE: TEST\n", encoding="utf-8")
    ret = launch_nle_handoff(
        {"editor": "premiere", "files": [str(fcpx), str(edl)]},
        dry_run=True,
        platform_key="darwin",
    )
    assert ret["status"] == "planned"
    assert ret["target_file"].endswith(".edl")


def test_nle_find_latest_video_candidate(tmp_path):
    a = tmp_path / "a.mp4"
    b = tmp_path / "b.mov"
    a.write_bytes(b"a")
    b.write_bytes(b"b")
    a.touch()
    b.touch()
    latest = find_latest_video_candidate([str(tmp_path)])
    assert latest == str(b.resolve())


def test_nle_collect_master_video_copy(tmp_path):
    src = tmp_path / "source.mp4"
    src.write_bytes(b"video")
    out_dir = tmp_path / "output"
    ret = collect_nle_master_video(
        source_video=str(src),
        output_dir=str(out_dir),
        output_name="final.mp4",
        copy_mode="copy",
    )
    assert ret["status"] == "done"
    assert ret["mode"] == "copy"
    assert ret["output_video"].endswith("final.mp4")
    assert (out_dir / "final.mp4").exists()
