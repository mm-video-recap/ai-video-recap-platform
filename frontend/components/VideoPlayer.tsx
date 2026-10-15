"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useT } from "@/lib/i18n";
import { formatDuration, parseSrt, type ParsedCue } from "@/lib/utils";
import type { Highlight, TimelineChapter } from "@/lib/types";

interface VideoPlayerProps {
  src: string;
  title?: string;
  chapters?: TimelineChapter[];
  highlights?: Highlight[];
  subtitleUrl?: string | null;
  autoPlay?: boolean;
}

/** Custom video player: play/seek, chapter + highlight markers, SRT subtitle overlay. */
export default function VideoPlayer({
  src,
  title,
  chapters = [],
  highlights = [],
  subtitleUrl,
  autoPlay,
}: VideoPlayerProps) {
  const { t } = useT();
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [playing, setPlaying] = useState(false);
  const [current, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(1);
  const [muted, setMuted] = useState(false);
  const [rate, setRate] = useState(1);
  const [showSubs, setShowSubs] = useState(true);
  const [cues, setCues] = useState<ParsedCue[]>([]);

  useEffect(() => {
    if (!subtitleUrl) {
      setCues([]);
      return;
    }
    let cancelled = false;
    fetch(subtitleUrl)
      .then((r) => (r.ok ? r.text() : ""))
      .then((text) => {
        if (!cancelled && text) setCues(parseSrt(text));
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [subtitleUrl]);

  const activeCue = useMemo(() => {
    if (!showSubs) return null;
    return cues.find((c) => current >= c.start && current <= c.end) ?? null;
  }, [cues, current, showSubs]);

  const toggle = () => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) void v.play();
    else v.pause();
  };

  const seekBy = (delta: number) => {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = Math.max(0, Math.min(v.duration || 0, v.currentTime + delta));
  };

  const toggleFullscreen = () => {
    const el = containerRef.current;
    if (!el) return;
    if (document.fullscreenElement) void document.exitFullscreen();
    else void el.requestFullscreen();
  };

  const cycleRate = () => {
    const rates = [1, 1.25, 1.5, 2, 0.5];
    const next = rates[(rates.indexOf(rate) + 1) % rates.length];
    setRate(next);
    if (videoRef.current) videoRef.current.playbackRate = next;
  };

  const seekTo = (time: number) => {
    const v = videoRef.current;
    if (v) v.currentTime = time;
  };

  const sliderFill = duration > 0 ? (current / duration) * 100 : 0;

  const marker = (start: number, color: string, label: string, key: string) => {
    if (!duration) return null;
    const left = Math.min(100, Math.max(0, (start / duration) * 100));
    return (
      <button
        key={key}
        onClick={() => seekTo(start)}
        title={label}
        aria-label={t("result.jumpTo", { time: formatDuration(start) })}
        className={`absolute top-1/2 h-3 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full ${color} transition-transform hover:scale-150`}
        style={{ left: `${left}%` }}
      />
    );
  };

  return (
    <div
      ref={containerRef}
      className="group relative overflow-hidden rounded-2xl bg-black shadow-card"
      onKeyDown={(e) => {
        if (e.key === " " && e.target === e.currentTarget) {
          e.preventDefault();
          toggle();
        }
      }}
      tabIndex={0}
      aria-label={title ?? t("player.play")}
    >
      <video
        ref={videoRef}
        src={src}
        autoPlay={autoPlay}
        playsInline
        preload="metadata"
        className="aspect-video w-full"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onTimeUpdate={(e) => setCurrent(e.currentTarget.currentTime)}
        onLoadedMetadata={(e) => setDuration(e.currentTarget.duration || 0)}
        onVolumeChange={(e) => {
          setVolume(e.currentTarget.volume);
          setMuted(e.currentTarget.muted);
        }}
        onClick={toggle}
      />
      {activeCue && (
        <div className="cue-overlay" aria-hidden>
          <span>{activeCue.text}</span>
        </div>
      )}

      {/* Controls */}
      <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/40 to-transparent px-3 pb-2 pt-8 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
        {/* Seek bar with markers */}
        <div className="relative mb-2 px-1">
          <input
            type="range"
            min={0}
            max={duration || 0}
            step={0.1}
            value={current}
            onChange={(e) => seekTo(Number(e.target.value))}
            aria-label={title ?? "Seek"}
            className="slider relative z-10 w-full"
            style={{ ["--fill" as string]: `${sliderFill}%` }}
          />
          <div aria-hidden className="pointer-events-none absolute inset-x-1 top-1/2 h-1.5 -translate-y-1/2">
            {chapters.map((c, i) =>
              marker(c.start, "bg-indigo-400", c.label, `ch-${i}`)
            )}
            {highlights.map((h, i) =>
              marker(h.start, "bg-amber-400", `${t("result.highlights")} ${i + 1}`, `hl-${i}`)
            )}
          </div>
        </div>

        <div className="flex items-center gap-1.5 text-white">
          <button onClick={() => seekBy(-10)} aria-label={t("player.seekBack")} className="rounded-lg p-2 hover:bg-white/15" title={t("player.seekBack")}>⏪</button>
          <button onClick={toggle} aria-label={playing ? t("player.pause") : t("player.play")} className="rounded-lg p-2 text-xl hover:bg-white/15" title={playing ? t("player.pause") : t("player.play")}>
            {playing ? "⏸" : "▶"}
          </button>
          <button onClick={() => seekBy(10)} aria-label={t("player.seekForward")} className="rounded-lg p-2 hover:bg-white/15" title={t("player.seekForward")}>⏩</button>
          <button
            onClick={() => {
              const v = videoRef.current;
              if (v) v.muted = !v.muted;
            }}
            aria-label={muted ? t("player.unmute") : t("player.mute")}
            className="rounded-lg p-2 hover:bg-white/15"
            title={muted ? t("player.unmute") : t("player.mute")}
          >
            {muted || volume === 0 ? "🔇" : "🔊"}
          </button>
          <span className="ml-1 text-xs tabular-nums text-white/80">
            {formatDuration(current)} / {formatDuration(duration)}
          </span>
          <div className="ml-auto flex items-center gap-1.5">
            <button onClick={cycleRate} aria-label={t("player.playbackRate")} title={t("player.playbackRate")} className="rounded-lg px-2 py-2 text-xs font-bold tabular-nums hover:bg-white/15">
              {rate}×
            </button>
            {subtitleUrl && (
              <button
                onClick={() => setShowSubs((s) => !s)}
                aria-label={t("player.subtitles")}
                aria-pressed={showSubs}
                title={t("player.subtitles")}
                className={`rounded-lg p-2 ${showSubs ? "bg-white/20" : "hover:bg-white/15"}`}
              >
                💬
              </button>
            )}
            <button onClick={toggleFullscreen} aria-label={t("player.fullscreen")} title={t("player.fullscreen")} className="rounded-lg p-2 hover:bg-white/15">⛶</button>
          </div>
        </div>
      </div>

      {/* Big center play button when paused at start */}
      {!playing && current === 0 && (
        <button
          onClick={toggle}
          aria-label={t("player.play")}
          className="absolute inset-0 flex items-center justify-center bg-black/30"
        >
          <span aria-hidden className="flex h-20 w-20 items-center justify-center rounded-full bg-white/90 text-3xl text-black shadow-glow-lg transition-transform hover:scale-105">
            ▶
          </span>
        </button>
      )}
    </div>
  );
}
