"""Regression tests for three live 2026-10-16 bugs.

1. process_video double-retry: the inner self.retry() raised Retry, the
   outer except caught it, retried AGAIN (second task message) and fell
   through to _fail_job. Two workers then ran the same job seconds
   apart, both writing normalized.mp4, and every normalize failed with
   0 frames.
2. Recap with no audio: the intro/outro title cards were video-only, and
   ffmpeg concat takes its stream layout from the FIRST segment, so the
   clips' audio was silently dropped from every recap.
3. SupabaseStorage.delete passed json= to httpx.delete(), which takes no
   body kwargs -> TypeError on every cleanup delete.
"""
import shutil
import subprocess

import pytest

from backend.agents.agent07_rendering import RenderingAgent

FFMPEG = shutil.which("ffmpeg")
FFPROBE = shutil.which("ffprobe")
needs_ffmpeg = pytest.mark.skipif(not (FFMPEG and FFPROBE),
                                  reason="ffmpeg/ffprobe not installed")


def _probe_streams(path):
    proc = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=30, check=False)
    return set((proc.stdout or "").split())


def _duration(path):
    proc = subprocess.run(
        [FFPROBE, "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, timeout=30, check=False)
    return float((proc.stdout or "0").strip() or 0)


def _make_source(path, with_audio: bool, dur: int = 4):
    cmd = [FFMPEG, "-y", "-f", "lavfi", "-i",
           f"color=c=0x1a2b4a:s=640x360:d={dur}:r=30"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:d={dur}"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
    if with_audio:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
    cmd += [str(path)]
    subprocess.run(cmd, capture_output=True, timeout=60, check=True)


@needs_ffmpeg
def test_title_card_carries_silent_audio(tmp_path):
    agent = RenderingAgent(tmp_path / "results")
    card = agent._title_card(tmp_path, "Hello", "intro", has_audio=True)
    assert card is not None and card.exists()
    assert "audio" in _probe_streams(card)


@needs_ffmpeg
def test_title_card_video_only_when_source_has_no_audio(tmp_path):
    agent = RenderingAgent(tmp_path / "results")
    card = agent._title_card(tmp_path, "Hello", "intro", has_audio=False)
    assert card is not None and card.exists()
    assert "audio" not in _probe_streams(card)


@needs_ffmpeg
def test_render_keeps_audio(tmp_path):
    src = tmp_path / "src.mp4"
    _make_source(src, with_audio=True)
    agent = RenderingAgent(tmp_path / "results")
    res = agent.render(src, [{"start": 0, "end": 2}], [{"start": 0, "end": 2, "text": "hi"}],
                       "T", "j1", intro_text="Intro", outro_text="Thanks")
    assert res.ok, res.errors
    assert "audio" in _probe_streams(res.video_path)


@needs_ffmpeg
def test_render_video_only_source_still_succeeds(tmp_path):
    # Previously every clip cut failed (-c:a aac with no audio stream),
    # so render failed outright for no-audio originals.
    src = tmp_path / "src.mp4"
    _make_source(src, with_audio=False)
    agent = RenderingAgent(tmp_path / "results")
    res = agent.render(src, [{"start": 0, "end": 2}], [],
                       "T", "j1", intro_text="Intro", outro_text="Thanks")
    assert res.ok, res.errors
    assert "audio" not in _probe_streams(res.video_path)


def test_process_video_retry_not_doubled(monkeypatch):
    from celery.exceptions import Retry

    import backend.celery_app.tasks as tasks

    class _Q:
        def __init__(self, row):
            self._row = row

        def filter_by(self, **kw):
            return self

        def one_or_none(self):
            return self._row

    class _Job:
        video_id = "v1"
        user_id = "u1"
        result = {}

    class _Video:
        id = "v1"
        storage_path = "uploads/v1/original.mp4"

    class _DB:
        def query(self, model):
            name = getattr(model, "__name__", "")
            return _Q(_Job() if name == "Job" else _Video())

        def close(self):
            pass

    class _Result:
        ok = False
        errors = ["normalize failed: boom"]

    class _Agent:
        def __init__(self, *a, **k):
            pass

        def process(self, *a, **k):
            return _Result()

    class _Req:
        retries = 0

    class _Self:
        max_retries = 2
        request = _Req()
        retry_calls = 0

        def retry(self, exc=None, countdown=None):
            type(self).retry_calls += 1
            raise Retry("Retry in 60s")

    failed = []
    monkeypatch.setattr(tasks, "_db", lambda: _DB())
    monkeypatch.setattr(tasks, "set_job_progress", lambda *a, **k: None)
    monkeypatch.setattr(tasks, "_fail_job", lambda *a, **k: failed.append(a))
    monkeypatch.setattr("backend.storage.ensure_local",
                        lambda *a, **k: "/tmp/x.mp4")
    monkeypatch.setattr("backend.agents.agent02_processing.ProcessingAgent",
                        _Agent)
    monkeypatch.setattr("backend.config.get_settings",
                        lambda: type("S", (), {"STORAGE_ROOT": "/tmp"})())

    fake = _Self()
    with pytest.raises(Retry):
        # run is a bound method (self = real task); __func__ lets us
        # drive the plain function with a fake self whose retry() only
        # records + raises, never touching the broker.
        tasks.process_video.run.__func__(fake, "j1")
    assert fake.retry_calls == 1
    assert failed == []


def test_supabase_delete_uses_request_not_delete_kwarg(monkeypatch):
    import httpx

    from backend.storage.supabase_store import SupabaseStorage

    calls = {}

    class _Resp:
        def raise_for_status(self):
            pass

    def _request(method, url, **kwargs):
        calls["method"] = method
        calls["json"] = kwargs.get("json")
        return _Resp()

    monkeypatch.setattr(httpx, "request", _request)
    store = SupabaseStorage("https://ref.supabase.co", "svc-key", "recap-results")
    store.delete("results/j1/recap_final.mp4")
    assert calls["method"] == "DELETE"
    assert calls["json"] == {"prefixes": ["results/j1/recap_final.mp4"]}


@needs_ffmpeg
def test_render_intro_outro_toggles(tmp_path):
    # Intro/outro are individually switchable: disabling one drops only
    # that card. Duration check: intro+outro = 2s + clips + 2s; with both
    # off the output is just the clips (2s for the single highlight).
    src = tmp_path / "src.mp4"
    _make_source(src, with_audio=True)
    agent = RenderingAgent(tmp_path / "results")
    hl = [{"start": 0, "end": 2}]
    tr = [{"start": 0, "end": 2, "text": "hi"}]
    both = agent.render(src, hl, tr, "T", "j1", intro_text="Intro",
                        outro_text="Thanks", intro_enabled=True,
                        outro_enabled=True)
    assert both.ok, both.errors
    assert _duration(both.video_path) == pytest.approx(6.0, abs=0.6)
    none = agent.render(src, hl, tr, "T", "j2", intro_text="Intro",
                        outro_text="Thanks", intro_enabled=False,
                        outro_enabled=False)
    assert none.ok, none.errors
    assert _duration(none.video_path) == pytest.approx(2.0, abs=0.6)
    intro_only = agent.render(src, hl, tr, "T", "j3", intro_text="Intro",
                              outro_text="Thanks", intro_enabled=True,
                              outro_enabled=False)
    assert intro_only.ok, intro_only.errors
    assert _duration(intro_only.video_path) == pytest.approx(4.0, abs=0.6)


def test_persist_ingestion_stores_intro_outro_flags():
    from backend.agents.agent01_ingestion import IngestionResult, persist_ingestion
    from backend.database import Job, Video

    # persist_ingestion needs a DB session; reuse the sqlite helper shape
    # from the fair-use tests via an in-memory engine.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from backend.database import Base

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(__import__("backend.database", fromlist=["User"]).User(
        id="u1", email="u1@dev.local"))
    db.commit()
    res = IngestionResult(
        ok=True, job_id="j1", video_id="v1", container="mp4",
        metadata={"original_name": "a.mp4", "duration_sec": 10.0,
                  "size_bytes": 100, "sha256_prefix": "ab"})
    persist_ingestion(db, res, user_id="u1",
                      storage_path="uploads/v1/original.mp4",
                      intro_enabled=False, outro_enabled=True)
    db.commit()
    video = db.query(Video).filter_by(id="v1").one()
    assert video.meta["intro_enabled"] is False
    assert video.meta["outro_enabled"] is True
