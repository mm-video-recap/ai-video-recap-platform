/** Format bytes into a human-readable string. */
export function formatBytes(bytes: number): string {
  if (!bytes || bytes <= 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1
  );
  const v = bytes / Math.pow(1024, i);
  return `${v >= 100 ? Math.round(v) : v.toFixed(1)} ${units[i]}`;
}

/** Format seconds as m:ss or h:mm:ss. */
export function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

/** Format an ISO date string for display. */
export function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

/** Format seconds as SRT timestamp 00:00:00,000. */
export function toSrtTime(seconds: number): string {
  const ms = Math.floor((seconds % 1) * 1000);
  const s = Math.floor(seconds) % 60;
  const m = Math.floor(seconds / 60) % 60;
  const h = Math.floor(seconds / 3600);
  const p = (n: number, l = 2) => String(n).padStart(l, "0");
  return `${p(h)}:${p(m)}:${p(s)},${p(ms, 3)}`;
}

/** Minimal SRT parser for client-side subtitle overlay. */
export interface ParsedCue {
  start: number;
  end: number;
  text: string;
}

function srtTimeToSec(t: string): number {
  const m = t.trim().match(/(\d+):(\d+):(\d+)[,.](\d+)/);
  if (!m) return 0;
  return (
    parseInt(m[1], 10) * 3600 +
    parseInt(m[2], 10) * 60 +
    parseInt(m[3], 10) +
    parseInt(m[4].padEnd(3, "0").slice(0, 3), 10) / 1000
  );
}

export function parseSrt(srt: string): ParsedCue[] {
  const cues: ParsedCue[] = [];
  const blocks = srt.replace(/\r\n/g, "\n").split(/\n\s*\n/);
  for (const block of blocks) {
    const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
    if (lines.length < 2) continue;
    const timeLine = lines.find((l) => l.includes("-->"));
    if (!timeLine) continue;
    const [startRaw, endRaw] = timeLine.split("-->").map((s) => s.trim());
    const text = lines
      .filter((l) => l !== timeLine && !/^\d+$/.test(l))
      .join("\n");
    if (!text) continue;
    cues.push({
      start: srtTimeToSec(startRaw),
      end: srtTimeToSec(endRaw),
      text,
    });
  }
  return cues.sort((a, b) => a.start - b.start);
}

/** Load recap preferences from localStorage. */
export function loadPreferences(): { summaryStyle: string; defaultLanguage: string } {
  try {
    const raw = window.localStorage.getItem("recap_prefs");
    if (raw) {
      const p = JSON.parse(raw);
      return {
        summaryStyle: p.summaryStyle || "detailed",
        defaultLanguage: p.defaultLanguage || "my",
      };
    }
  } catch {
    /* ignore */
  }
  return { summaryStyle: "detailed", defaultLanguage: "my" };
}

/** Transcription (BYOK) preferences: provider + the user's own key.
 * Stored in localStorage only. The key is sent with each upload as a
 * form field (never a query param) and stored encrypted server-side. */
export type TranscriptionProvider = "auto" | "gemini" | "groq";

export function loadTranscriptionPrefs(): { provider: TranscriptionProvider; key: string } {
  try {
    const raw = window.localStorage.getItem("recap_transcription");
    if (raw) {
      const p = JSON.parse(raw);
      const provider = p.provider === "gemini" || p.provider === "groq" ? p.provider : "auto";
      return { provider, key: typeof p.key === "string" ? p.key : "" };
    }
  } catch {
    /* ignore */
  }
  return { provider: "auto", key: "" };
}

export function saveTranscriptionPrefs(provider: TranscriptionProvider, key: string) {
  window.localStorage.setItem("recap_transcription", JSON.stringify({ provider, key }));
}

/** Voiceover (TTS narration) preferences, stored in localStorage only. */
export type VoiceMode = "original" | "tts";
export type TtsProvider = "edge" | "gemini";

export interface VoicePrefs {
  voiceMode: VoiceMode;
  ttsProvider: TtsProvider;
  ttsVoice: string;
  ttsRate: number;
  ttsPitch: number;
}

export function loadVoicePrefs(): VoicePrefs {
  const defaults: VoicePrefs = {
    voiceMode: "original",
    ttsProvider: "edge",
    ttsVoice: "thiha",
    ttsRate: 1.0,
    ttsPitch: 0,
  };
  try {
    const raw = window.localStorage.getItem("recap_voice");
    if (raw) {
      const p = JSON.parse(raw);
      return {
        voiceMode: p.voiceMode === "tts" ? "tts" : "original",
        ttsProvider: p.ttsProvider === "gemini" ? "gemini" : "edge",
        ttsVoice: typeof p.ttsVoice === "string" && p.ttsVoice ? p.ttsVoice : "thiha",
        ttsRate: typeof p.ttsRate === "number" && p.ttsRate >= 0.5 && p.ttsRate <= 2 ? p.ttsRate : 1.0,
        ttsPitch: typeof p.ttsPitch === "number" && p.ttsPitch >= -20 && p.ttsPitch <= 20 ? p.ttsPitch : 0,
      };
    }
  } catch {
    /* ignore */
  }
  return defaults;
}

export function saveVoicePrefs(prefs: VoicePrefs) {
  window.localStorage.setItem("recap_voice", JSON.stringify(prefs));
}

/** Canonical processing stage keys, in pipeline order. */
export const STAGE_ORDER = [
  "upload",
  "audio",
  "speech",
  "analysis",
  "summary",
  "highlights",
  "rendering",
  "completed",
] as const;

export type StageKey = (typeof STAGE_ORDER)[number];

/** Normalize backend stage strings to canonical stage keys. */
export function normalizeStage(stage: string): StageKey {
  const s = stage.toLowerCase().trim();
  const map: [RegExp, StageKey][] = [
    [/^(upload|uploading|uploaded|ingest|ingestion)$/, "upload"],
    [/audio|extract/, "audio"],
    [/speech|transcri|whisper|stt/, "speech"],
    [/analy|vision/, "analysis"],
    [/summar/, "summary"],
    [/highlight|select/, "highlights"],
    [/render|export|assembl/, "rendering"],
    [/complet|done|finish|success/, "completed"],
  ];
  for (const [re, key] of map) {
    if (re.test(s)) return key;
  }
  return "analysis";
}

/** Estimate processing minutes from video duration seconds (heuristic). */
export function estimateMinutes(durationSec: number): number {
  if (!durationSec || durationSec <= 0) return 2;
  return Math.max(1, Math.ceil(durationSec / 60 / 4));
}

export const ACCEPTED_VIDEO_TYPES = ["mp4", "mov", "webm", "mkv"];
export const MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024; // 2 GB

export function getExtension(name: string): string {
  const parts = name.split(".");
  return parts.length > 1 ? parts.pop()!.toLowerCase() : "";
}
