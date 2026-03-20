# Capability Modules

This package introduces a product-oriented split for editing features.

Capabilities:

- `topic_library`: topic templates as database records.
- `topic_copy`: topic + semantic signal to copy draft.
- `text_rough_cut`: transcript-based rough cut planning.
- `short_clip`: long-to-short highlight selection.
- `refinement`: final polish strategy and external NLE handoff plan.
- `social_export`: platform-specific export profiles and batch export jobs.
- `publish_prep`: multi-platform publish title/body/keyword preparation with prompt profiles.
- `audio_voice`: voiceover synthesis, BGM auto-pick, and master mix orchestration.
- `nle_handoff`: FCPXML/EDL handoff package generation.

This layer does not replace current `step1~step7` runtime immediately.
It provides stable boundaries so legacy workflow and new UI can migrate incrementally.
