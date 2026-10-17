"""Tests: quota-exhaustion flag + warning plumbing.

When a job's AI output is incomplete because provider quota ran out
(HTTP 429 / 'quota' / 'keys exhausted'), render_recap persists
quota_exhausted=True on the job result and GET /api/results returns it,
so the result page can show a quota warning banner (when the user
enabled that option in Settings) instead of silently empty output.
"""
import backend.celery_app.tasks as tasks


def test_is_quota_error_text():
    assert tasks._is_quota_error_text("all 11 keys exhausted: {...}") is True
    assert tasks._is_quota_error_text("gemini HTTP 429: quota exceeded") is True
    assert tasks._is_quota_error_text("You exceeded your current quota") is True
    assert tasks._is_quota_error_text("API key not valid") is False
    assert tasks._is_quota_error_text("LLM did not return JSON") is False
    assert tasks._is_quota_error_text("") is False
    assert tasks._is_quota_error_text(None) is False


def test_job_hit_quota():
    assert tasks._job_hit_quota({}) is False
    assert tasks._job_hit_quota(
        {"summary": {"error": "all providers failed: gemini: all 11 keys exhausted"}}
    ) is True
    assert tasks._job_hit_quota(
        {"speech": {"error": "gemini transcription HTTP 429"}}
    ) is True
    assert tasks._job_hit_quota(
        {"vision": {"frames": [{"error": "gemini vision: quota exceeded"}]}}
    ) is True
    assert tasks._job_hit_quota(
        {"summary": {"error": "API key not valid"}}
    ) is False
    assert tasks._job_hit_quota(
        {"summary": {"error": "LLM did not return JSON"}}
    ) is False


def _complete_job(job_id, quota_exhausted):
    from backend.database import Job, Output, get_session_factory

    db = get_session_factory()()
    try:
        job = db.query(Job).filter_by(id=job_id).one()
        job.status = "completed"
        job.result = {
            "summary": {"title": "T", "description": "", "summary_short": "",
                        "summary_long": "", "key_points": [], "timeline": []},
            "speech": {"transcript": []},
            "highlights": [],
            "render": {"warnings": []},
            "quota_exhausted": quota_exhausted,
        }
        db.add(Output(job_id=job_id, kind="recap_video",
                      storage_path=f"results/{job_id}/recap_final.mp4",
                      size_bytes=123))
        db.commit()
    finally:
        db.close()


def test_results_returns_quota_exhausted_true(client, uploaded):
    _complete_job(uploaded["job_id"], True)
    r = client.get(f"/api/results/{uploaded['job_id']}",
                   headers=uploaded["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["quota_exhausted"] is True


def test_results_returns_quota_exhausted_false(client, uploaded):
    _complete_job(uploaded["job_id"], False)
    r = client.get(f"/api/results/{uploaded['job_id']}",
                   headers=uploaded["headers"])
    assert r.status_code == 200, r.text
    assert r.json()["quota_exhausted"] is False
