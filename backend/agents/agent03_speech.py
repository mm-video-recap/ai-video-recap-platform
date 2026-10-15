"""
Agent 03 — Speech-to-Text Agent.

Pipeline:
1. If faster-whisper is installed -> local transcription (word/segment level).
2. Else -> provider manager speech chain (Groq Whisper -> HF fallback).
3. Else -> degraded result with empty transcript (never crashes).

Output: {"transcript": [{start, end, text}], "language": ..., "confidence": ...}
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

log = logging.getLogger("agents.speech")

try:  # optional heavy dependency
    from faster_whisper import WhisperModel as _WhisperModel
    _FASTER_WHISPER_AVAILABLE = True
except Exception:
    _WhisperModel = None  # type: ignore
    _FASTER_WHISPER_AVAILABLE = False


class SpeechAgent:
    def __init__(self, model_name: str = "base", device: str = "cpu",
                 provider_manager=None):
        self.model_name = model_name
        self.device = device
        self.provider_manager = provider_manager
        self._model = None

    def _local_transcribe(self, audio_path: str) -> dict:
        assert _WhisperModel is not None
        if self._model is None:
            log.info("loading faster-whisper model=%s device=%s", self.model_name, self.device)
            self._model = _WhisperModel(self.model_name, device=self.device,
                                        compute_type="int8")
        segments, info = self._model.transcribe(audio_path, beam_size=5)
        transcript = [
            {"start": round(seg.start, 2), "end": round(seg.end, 2),
             "text": seg.text.strip()}
            for seg in segments if seg.text and seg.text.strip()
        ]
        return {
            "transcript": transcript,
            "language": info.language,
            "language_probability": round(info.language_probability, 3),
            "confidence": round(info.language_probability, 3),
            "engine": "faster-whisper",
        }

    def _provider_transcribe(self, audio_path: str) -> dict:
        assert self.provider_manager is not None
        result, provider = asyncio.run(
            self.provider_manager.transcribe(audio_path))
        result["engine"] = result.get("engine", provider)
        return result

    def transcribe(self, audio_path: str | Path | None, job_id: str) -> dict:
        """Returns the transcript dict; always returns a dict, never raises."""
        out = {"transcript": [], "language": None, "confidence": 0.0,
               "engine": "none", "degraded": True}
        try:
            if not audio_path or not Path(audio_path).exists():
                out["error"] = "no audio available for transcription"
                log.warning("speech job=%s: no audio", job_id)
                return out
            if _FASTER_WHISPER_AVAILABLE:
                log.info("speech job=%s: faster-whisper", job_id)
                out = self._local_transcribe(str(audio_path))
            elif self.provider_manager is not None:
                log.info("speech job=%s: provider chain", job_id)
                out = self._provider_transcribe(str(audio_path))
            else:
                out["error"] = "no transcription backend available"
                log.warning("speech job=%s: no backend", job_id)
                return out
            out["degraded"] = False
            log.info("speech job=%s: %d segments lang=%s",
                     job_id, len(out.get("transcript", [])), out.get("language"))
        except Exception as exc:
            log.exception("speech job=%s failed", job_id)
            out = {"transcript": [], "language": None, "confidence": 0.0,
                   "engine": "none", "degraded": True, "error": str(exc)[:500]}
        return out


def is_faster_whisper_available() -> bool:
    return _FASTER_WHISPER_AVAILABLE
