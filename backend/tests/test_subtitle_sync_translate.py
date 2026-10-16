"""Tests: subtitle remap to recap timeline + translation to subtitle_language."""
import json


def test_remap_transcript_to_recap_timeline():
    from backend.agents.agent07_rendering import RenderingAgent

    agent = RenderingAgent("/tmp")
    highlights = [{"start": 10, "end": 20}, {"start": 30, "end": 35}]
    transcript = [
        {"start": 0, "end": 5, "text": "before all"},       # dropped
        {"start": 12, "end": 14, "text": "inside clip 1"},
        {"start": 18, "end": 32, "text": "spans gap"},       # split in two
        {"start": 40, "end": 42, "text": "after all"},       # dropped
    ]
    # intro on (2s) -> clip1 at recap [2,12), clip2 at recap [12,17)
    out = agent._remap_transcript(transcript, highlights, True, True)
    assert [(c["start"], c["end"], c["text"]) for c in out] == [
        (2 + 2, 2 + 4, "inside clip 1"),       # 12-14 -> recap 4-6
        (2 + 8, 2 + 10, "spans gap"),           # 18-20 -> recap 10-12
        (12 + 0, 12 + 2, "spans gap"),          # 30-32 -> recap 12-14
    ]


def test_remap_no_intro_shifts_to_zero():
    from backend.agents.agent07_rendering import RenderingAgent

    agent = RenderingAgent("/tmp")
    out = agent._remap_transcript(
        [{"start": 5, "end": 7, "text": "hi"}],
        [{"start": 0, "end": 10}], False, False)
    assert [(c["start"], c["end"]) for c in out] == [(5.0, 7.0)]


def test_translate_segments_to_myanmar(monkeypatch):
    import asyncio

    import backend.celery_app.tasks as tasks

    class _Manager:
        def __init__(self, settings):
            pass

        async def complete(self, task, prompt, **kw):
            assert "Myanmar" in prompt
            data = json.loads(prompt.split("\nInput:\n", 1)[1])
            assert len(data) == 2
            return (json.dumps({"segments": [
                {"text": "မင်္ဂလာပါ"}, {"text": "ကျေးဇူးတင်ပါတယ်"}]}), "gemini")

    monkeypatch.setattr("backend.ai_provider.manager.ProviderManager", _Manager)
    segments = [{"start": 0, "end": 2, "text": "Hello"},
                {"start": 2, "end": 4, "text": "Thank you"}]
    out = tasks._translate_segments(object(), segments, "my", "en")
    assert [s["text"] for s in out] == ["မင်္ဂလာပါ", "ကျေးဇူးတင်ပါတယ်"]
    assert [s["start"] for s in out] == [0, 2]  # timestamps preserved


def test_translate_segments_skips_same_language():
    import backend.celery_app.tasks as tasks

    segments = [{"start": 0, "end": 2, "text": "မင်္ဂလာပါ"}]
    # No provider call must happen: same language -> returned as-is.
    assert tasks._translate_segments(object(), segments, "my", "my") == segments


def test_translate_segments_falls_back_on_bad_json(monkeypatch):
    import backend.celery_app.tasks as tasks

    class _Manager:
        def __init__(self, settings):
            pass

        async def complete(self, task, prompt, **kw):
            return ("not json at all", "gemini")

    monkeypatch.setattr("backend.ai_provider.manager.ProviderManager", _Manager)
    segments = [{"start": 0, "end": 2, "text": "Hello"}]
    assert tasks._translate_segments(object(), segments, "my", "en") == segments
