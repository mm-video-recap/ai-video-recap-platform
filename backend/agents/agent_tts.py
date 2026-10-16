"""TTS narration for recaps: Edge TTS (Thiha/Nilar) + Gemini TTS.

The platform originally had NO voiceover at all — recaps always kept
the original audio. When the user picks TTS narration, the recap's
audio track is replaced with a synthesized reading of the recap
summary (in the recap language), fitted to the recap video duration.

Edge TTS needs no key (Microsoft's free Edge TTS service). Gemini TTS
uses the owner's Gemini key. TTS failure NEVER fails a render — the
original audio is kept and a warning is recorded.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import re
import shutil
import subprocess
import wave
from pathlib import Path

log = logging.getLogger(__name__)

EDGE_VOICES = {
    "thiha": "my-MM-ThihaNeural",   # Myanmar, male
    "nilar": "my-MM-NilarNeural",  # Myanmar, female
}
GEMINI_VOICES = ["Kore", "Charon", "Zephyr", "Puck",
                 "Leda", "Fenrir", "Callirrhoe", "Autonoe"]
GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
GEMINI_TTS_SAMPLE_RATE = 24000

# Edge TTS accepts one long SSML document, but very long texts fail
# mid-stream — chunk by sentence so one bad chunk can't kill the rest.
_CHUNK_CHARS = 800


def validate_tts_prefs(provider: str, voice: str, rate: float, pitch: int) -> None:
    """Raise ValueError on an invalid TTS preference set."""
    if provider not in ("edge", "gemini"):
        raise ValueError(f"unknown tts_provider: {provider!r}")
    if provider == "edge" and voice not in EDGE_VOICES:
        raise ValueError(f"edge voice must be one of {sorted(EDGE_VOICES)}")
    if provider == "gemini" and voice not in GEMINI_VOICES:
        raise ValueError(f"gemini voice must be one of {GEMINI_VOICES}")
    if not 0.5 <= rate <= 2.0:
        raise ValueError("tts_rate must be between 0.5 and 2.0")
    if not -20 <= pitch <= 20:
        raise ValueError("tts_pitch must be between -20 and +20 Hz")


def split_text(text: str) -> list[str]:
    """Split narration into sentence chunks of at most _CHUNK_CHARS."""
    sentences = re.split(r"(?<=[.!?။\n])\s+", text.strip())
    chunks: list[str] = []
    buf = ""
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if len(buf) + len(sent) + 1 > _CHUNK_CHARS and buf:
            chunks.append(buf)
            buf = sent
        else:
            buf = f"{buf} {sent}".strip() if buf else sent
    if buf:
        chunks.append(buf)
    return chunks or [text.strip()]


def _ffprobe_duration(path: Path, ffprobe: str) -> float | None:
    try:
        proc = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, timeout=30, check=False)
        return float((proc.stdout or "").strip())
    except Exception:
        return None


async def _synthesize_edge(text: str, voice: str, rate: float, pitch: int,
                           out_path: Path) -> None:
    import edge_tts  # noqa: PLC0415

    # edge-tts rate/pitch take SSML strings: "+10%", "-5Hz".
    rate_s = f"{int(round((rate - 1.0) * 100)):+d}%"
    pitch_s = f"{int(pitch):+d}Hz"
    communicate = edge_tts.Communicate(text, EDGE_VOICES[voice],
                                       rate=rate_s, pitch=pitch_s)
    await communicate.save(str(out_path))


async def _synthesize_gemini(text: str, voice: str, settings, out_path: Path) -> None:
    import httpx  # noqa: PLC0415

    keys = getattr(settings, "gemini_keys", None) or []
    if not keys:
        raise RuntimeError("no Gemini key configured for Gemini TTS")
    tts_model = getattr(settings, "GEMINI_TTS_MODEL", None) or GEMINI_TTS_MODEL
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{tts_model}:generateContent")
    body = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}},
        },
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(url, params={"key": keys[0]}, json=body)
        resp.raise_for_status()
        data = resp.json()
    try:
        b64 = data["candidates"][0]["content"]["parts"][0]["inlineData"]["data"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Gemini TTS returned no audio: {exc}") from exc
    pcm = base64.b64decode(b64)
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(GEMINI_TTS_SAMPLE_RATE)
        wf.writeframes(pcm)


def synthesize_narration(text: str, provider: str, voice: str, rate: float,
                         pitch: int, workdir: Path, settings=None) -> Path | None:
    """Synthesize narration text to a single merged WAV. None on failure."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        log.warning("tts: ffmpeg missing, cannot merge narration")
        return None
    text = (text or "").strip()
    if not text:
        return None
    workdir.mkdir(parents=True, exist_ok=True)
    chunks = split_text(text)
    parts: list[Path] = []
    try:
        for i, chunk in enumerate(chunks):
            part = workdir / f"tts_{i:03d}"
            if provider == "edge":
                part = part.with_suffix(".mp3")
                asyncio.run(_synthesize_edge(chunk, voice, rate, pitch, part))
            else:
                part = part.with_suffix(".wav")
                asyncio.run(_synthesize_gemini(chunk, voice, settings, part))
            if not part.exists() or part.stat().st_size == 0:
                raise RuntimeError(f"TTS chunk {i} produced no audio")
            parts.append(part)
        merged = workdir / "narration.wav"
        concat = workdir / "tts_concat.txt"
        concat.write_text("".join(f"file '{p}'\n" for p in parts))
        proc = subprocess.run(
            [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
             "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2", str(merged)],
            capture_output=True, text=True, timeout=300, check=False)
        if proc.returncode != 0 or not merged.exists():
            raise RuntimeError(f"TTS merge failed: {proc.stderr[-300:]}")
        log.info("tts ok provider=%s voice=%s chunks=%d",
                 provider, voice, len(chunks))
        return merged
    except Exception as exc:
        log.warning("tts synthesis failed (%s): %s", provider, exc)
        return None


def fit_narration_to_duration(narration: Path, target_sec: float,
                             workdir: Path) -> Path | None:
    """Fit narration audio to target_sec: speed up (max 2x) + trim if
    longer, pad with silence if shorter. Returns fitted WAV or None."""
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe or target_sec <= 0:
        return None
    dur = _ffprobe_duration(narration, ffprobe)
    if dur is None or dur <= 0:
        return None
    out = workdir / "narration_fitted.wav"
    try:
        if dur > target_sec:
            factor = min(dur / target_sec, 2.0)
            # atempo only accepts 0.5-100; chain if needed (factor <= 2).
            proc = subprocess.run(
                [ffmpeg, "-y", "-i", str(narration),
                 "-af", f"atempo={factor:.3f}", "-t", str(target_sec),
                 "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2", str(out)],
                capture_output=True, text=True, timeout=300, check=False)
        elif dur < target_sec - 0.05:
            proc = subprocess.run(
                [ffmpeg, "-y", "-i", str(narration),
                 "-af", f"apad=whole_dur={target_sec:.3f}",
                 "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2", str(out)],
                capture_output=True, text=True, timeout=300, check=False)
        else:
            return narration
        if proc.returncode != 0 or not out.exists():
            log.warning("tts fit failed: %s", proc.stderr[-300:])
            return None
        return out
    except Exception as exc:
        log.warning("tts fit crashed: %s", exc)
        return None


def replace_audio(video: Path, narration: Path, out_path: Path) -> bool:
    """Replace a video's audio track with the narration. Video is copied."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    proc = subprocess.run(
        [ffmpeg, "-y", "-i", str(video), "-i", str(narration),
         "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac",
         "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(out_path)],
        capture_output=True, text=True, timeout=600, check=False)
    if proc.returncode != 0 or not out_path.exists():
        log.warning("tts audio replace failed: %s", proc.stderr[-300:])
        return False
    return True
