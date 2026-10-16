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
               outro_text: str | None = None) -> RenderResult:
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
            intro = self._title_card(workdir, intro_text or title, "intro", has_audio=has_audio) if intro_text or title else None
            outro = self._title_card(workdir, outro_text or "Thanks for watching", "outro", has_audio=has_audio) if outro_text else None
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

            # 3) subtitles
            srt_path = workdir / "subtitles.srt"
            self._write_srt(srt_path, transcript or [])
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
