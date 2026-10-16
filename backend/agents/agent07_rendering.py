"""
Agent 07 — Rendering Agent.

Builds the final recap MP4 with ffmpeg:
1. Cuts highlight clips from the normalized video, concatenates them.
2. Subtitles: burn-in via libass when a usable font is present; otherwise
   writes a sidecar .srt and muxes soft subtitles (mov_text).
3. Optional intro/outro title cards (2s color clips with drawtext).
4. Exports H.264 + AAC MP4 with faststart.

Never raises — returns ok=False with errors instead.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

log = logging.getLogger("agents.rendering")


@dataclass
class RenderResult:
    ok: bool
    job_id: str
    video_path: str | None = None
    subtitle_path: str | None = None
    subtitle_mode: str = "none"  # burned_in | soft | sidecar | none
    duration_sec: float | None = None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoSansMyanmar-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


class RenderingAgent:
    def __init__(self, results_root: str | Path):
        self.root = Path(results_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ffmpeg = shutil.which("ffmpeg")

    # -- helpers -------------------------------------------------------------
    def _run(self, cmd: list[str], timeout: int = 900) -> subprocess.CompletedProcess:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, check=False)

    def _find_font(self) -> Path | None:
        for cand in _FONT_CANDIDATES:
            if Path(cand).exists():
                return Path(cand)
        # fall back to fc-list scan
        fc = shutil.which("fc-list")
        if fc:
            try:
                out = subprocess.run([fc, ":style=Regular", "file"],
                                     capture_output=True, text=True, timeout=15)
                for line in (out.stdout or "").splitlines():
                    p = line.split(":")[0].strip()
                    if p.endswith(".ttf") and Path(p).exists():
                        return Path(p)
            except Exception:
                pass
        return None

    def _remap_transcript(self, transcript: list[dict], highlights: list[dict],
                         intro_enabled: bool, outro_enabled: bool) -> list[dict]:
        """Remap subtitle cues from ORIGINAL-video time to RECAP time.

        The SRT is burned onto the JOINED video (intro + concatenated
        highlight clips + outro), whose timeline is NOT the original
        timeline. Writing original timestamps onto it put every cue at
        the wrong moment (live 2026-10-16: subtitles out of sync). Each
        cue is clipped to the highlight(s) it overlaps and shifted to
        that clip's position in the recap; cues outside all highlights
        are dropped.
        """
        layout: list[tuple[float, float, float]] = []  # (recap_start, orig_start, orig_end)
        t = 2.0 if intro_enabled else 0.0  # title cards are exactly 2s
        for hl in highlights or []:
            try:
                s, e = float(hl["start"]), float(hl["end"])
            except (TypeError, ValueError, KeyError):
                continue
            if e > s:
                layout.append((t, s, e))
                t += e - s
        remapped: list[dict] = []
        for seg in transcript or []:
            try:
                s = float(seg.get("start", 0) or 0)
                e = float(seg.get("end", s) or s)
            except (TypeError, ValueError):
                continue
            text = (seg.get("text") or "").strip()
            if not text or e <= s:
                continue
            for (rt, os_, oe) in layout:
                lo, hi = max(s, os_), min(e, oe)
                if hi > lo:
                    remapped.append({"start": rt + (lo - os_),
                                     "end": rt + (hi - os_), "text": text})
        remapped.sort(key=lambda c: c["start"])
        return remapped

    def _write_srt(self, path: Path, transcript: list[dict]) -> None:
        def ts(sec: float) -> str:
            ms = int(sec * 1000)
            return f"{ms//3600000:02d}:{(ms//60000)%60:02d}:{(ms//1000)%60:02d},{ms%1000:03d}"
        with open(path, "w", encoding="utf-8") as fh:
            for i, seg in enumerate(transcript, 1):
                start = float(seg.get("start", 0) or 0)
                end = float(seg.get("end", start + 2) or start + 2)
                text = (seg.get("text") or "").strip().replace("\n", " ")
                if not text:
                    continue
                fh.write(f"{i}\n{ts(start)} --> {ts(end)}\n{text}\n\n")

    def _has_audio(self, path: Path) -> bool:
        """True when the file has an audio stream (ffprobe). Defaults to
        True when ffprobe is unavailable — preserve current behavior."""
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return True
        try:
            proc = subprocess.run(
                [ffprobe, "-v", "error", "-select_streams", "a",
                 "-show_entries", "stream=index", "-of", "csv=p=0", str(path)],
                capture_output=True, text=True, timeout=30, check=False)
            return bool((proc.stdout or "").strip())
        except Exception:
            return True

    def _duration(self, path: Path) -> float | None:
        """Media duration in seconds via ffprobe; None when unavailable."""
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return None
        try:
            proc = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", str(path)],
                capture_output=True, text=True, timeout=30, check=False)
            return float((proc.stdout or "").strip())
        except Exception:
            return None

    def _title_card(self, workdir: Path, text: str, name: str,
                    w: int = 1280, h: int = 720, has_audio: bool = True) -> Path | None:
        """2-second title card; returns path or None if drawtext unavailable.

        When has_audio, the card carries a SILENT audio stream. The
        concat step takes its stream layout from the FIRST segment —
        a video-only intro card silently dropped the clips' audio from
        every recap (live 2026-10-16: recaps came out with no sound).
        When the source has no audio, all parts stay video-only so the
        concat layouts still match.
        """
        out = workdir / f"{name}.mp4"
        safe = text.replace("'", "").replace(":", " ")[:80]
        cmd = [self.ffmpeg, "-y", "-f", "lavfi",
               "-i", f"color=c=0x1a2b4a:s={w}x{h}:d=2:r=30"]
        if has_audio:
            cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
        cmd += ["-vf", f"drawtext=text='{safe}':fontsize=56:fontcolor=white:"
                      f"x=(w-text_w)/2:y=(h-text_h)/2",
               "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
        if has_audio:
            cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
        cmd += [str(out)]
        p = self._run(cmd, timeout=120)
        return out if p.returncode == 0 and out.exists() else None

    # -- main -----------------------------------------------------------------
    def render(self, normalized_path: str | Path, highlights: list[dict],
               transcript: list[dict], title: str, job_id: str,
               intro_text: str | None = None,
               outro_text: str | None = None,
               intro_enabled: bool = True,
               outro_enabled: bool = True,
               narration_text: str | None = None,
               tts_provider: str = "edge",
               tts_voice: str = "thiha",
               tts_rate: float = 1.0,
               tts_pitch: int = 0,
               settings=None) -> RenderResult:
        res = RenderResult(ok=False, job_id=job_id)
        src = Path(normalized_path)
        try:
            if not self.ffmpeg:
                res.errors.append("ffmpeg is not installed; cannot render")
                return res
            if not src.exists():
                res.errors.append(f"normalized video not found: {normalized_path}")
                return res
            if not highlights:
                res.errors.append("no highlights to render")
                return res

            workdir = self.root / job_id
            workdir.mkdir(parents=True, exist_ok=True)

            # All concat parts must share one stream layout: detect once
            # whether the source has audio, and build every part to match.
            has_audio = self._has_audio(src)

            # 1) cut clips
            clips: list[Path] = []
            for i, hl in enumerate(highlights):
                clip = workdir / f"clip_{i:02d}.mp4"
                cmd = [self.ffmpeg, "-y",
                       "-ss", str(hl["start"]), "-to", str(hl["end"]),
                       "-i", str(src),
                       "-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
                if has_audio:
                    cmd += ["-c:a", "aac", "-b:a", "128k"]
                cmd += [str(clip)]
                p = self._run(cmd, timeout=600)
                if p.returncode == 0 and clip.exists():
                    clips.append(clip)
                else:
                    res.warnings.append(f"clip {i} cut failed, skipped")
            if not clips:
                res.errors.append("all highlight clips failed to cut")
                return res

            # 2) concat (+ optional title cards)
            parts: list[Path] = []
            intro = self._title_card(workdir, intro_text or title, "intro", has_audio=has_audio) if (intro_enabled and (intro_text or title)) else None
            outro = self._title_card(workdir, outro_text or "Thanks for watching", "outro", has_audio=has_audio) if (outro_enabled and outro_text) else None
            if intro:
                parts.append(intro)
            parts.extend(clips)
            if outro:
                parts.append(outro)

            concat_list = workdir / "concat.txt"
            concat_list.write_text("".join(f"file '{p}'\n" for p in parts))
            joined = workdir / "joined.mp4"
            p = self._run([self.ffmpeg, "-y", "-f", "concat", "-safe", "0",
                           "-i", str(concat_list), "-c", "copy", str(joined)])
            if p.returncode != 0 or not joined.exists():
                res.errors.append(f"concat failed: {p.stderr[-300:]}")
                return res

            # 2b) TTS narration (optional): replace the audio track with a
            # synthesized reading of the recap summary, fitted to the
            # recap duration. TTS failure NEVER fails the render — the
            # original audio is kept and a warning is recorded.
            if narration_text and narration_text.strip():
                try:
                    from backend.agents.agent_tts import (  # noqa: PLC0415
                        fit_narration_to_duration, replace_audio,
                        synthesize_narration, validate_tts_prefs)
                    validate_tts_prefs(tts_provider, tts_voice, tts_rate, tts_pitch)
                    narrated = synthesize_narration(
                        narration_text, tts_provider, tts_voice, tts_rate,
                        tts_pitch, workdir, settings=settings)
                    # Edge TTS is network-fragile (its endpoint can be
                    # unreachable from a datacenter). Fall back to Gemini
                    # TTS — the Gemini API is already proven reachable —
                    # rather than silently keeping the original audio.
                    if narrated is None and tts_provider == "edge":
                        gemini_voice = "Charon" if tts_voice == "thiha" else "Kore"
                        narrated = synthesize_narration(
                            narration_text, "gemini", gemini_voice,
                            tts_rate, 0, workdir, settings=settings)
                        if narrated is not None:
                            res.warnings.append(
                                "edge TTS unavailable; used Gemini voice "
                                f"{gemini_voice} instead")
                    if narrated is not None:
                        target = self._duration(joined)
                        fitted = fit_narration_to_duration(narrated, target, workdir) if target else None
                        narrated_video = workdir / "joined_narrated.mp4"
                        if replace_audio(joined, fitted or narrated, narrated_video):
                            joined = narrated_video
                            res.warnings.append(
                                f"narration: {tts_provider}/{tts_voice}")
                        else:
                            res.warnings.append("narration audio replace failed; kept original audio")
                    else:
                        res.warnings.append("narration synthesis failed; kept original audio")
                except Exception as exc:
                    log.warning("tts narration skipped job=%s: %s", job_id, exc)
                    res.warnings.append(f"narration skipped: {exc}")

            # 3) subtitles — remapped to the recap timeline (intro + clips
            # + outro), NOT the original timeline.
            srt_path = workdir / "subtitles.srt"
            self._write_srt(srt_path, self._remap_transcript(
                transcript or [], highlights, intro_enabled, outro_enabled))
            res.subtitle_path = str(srt_path)
            final = workdir / "recap_final.mp4"
            font = self._find_font()
            if font and srt_path.stat().st_size > 0:
                vf = f"subtitles={srt_path}:fontsdir={font.parent}"
                p = self._run([self.ffmpeg, "-y", "-i", str(joined),
                               "-vf", vf, "-c:v", "libx264", "-preset", "veryfast",
                               "-crf", "23", "-c:a", "copy",
                               "-movflags", "+faststart", str(final)])
                res.subtitle_mode = "burned_in" if p.returncode == 0 else "sidecar"
            if res.subtitle_mode != "burned_in":
                # soft subtitles (muxed mov_text) + sidecar file
                if srt_path.stat().st_size > 0:
                    p = self._run([self.ffmpeg, "-y", "-i", str(joined),
                                   "-i", str(srt_path),
                                   "-c:v", "copy", "-c:a", "copy",
                                   "-c:s", "mov_text", "-movflags", "+faststart",
                                   str(final)])
                    res.subtitle_mode = "soft" if p.returncode == 0 else "sidecar"
                    if p.returncode != 0:
                        shutil.copyfile(joined, final)
                else:
                    shutil.copyfile(joined, final)
                    res.subtitle_mode = "none"
                    res.warnings.append("no subtitle text; exported without captions")

            if not final.exists():
                res.errors.append("final render output missing")
                return res
            res.video_path = str(final)
            res.ok = True
            log.info("render ok job=%s mode=%s clips=%d", job_id,
                     res.subtitle_mode, len(clips))
        except subprocess.TimeoutExpired:
            res.errors.append("ffmpeg timed out during render")
        except Exception as exc:
            log.exception("render job=%s failed", job_id)
            res.errors.append(f"render crashed: {exc}")
        return res
