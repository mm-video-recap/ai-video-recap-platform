"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useT } from "@/lib/i18n";

export type PreviewBlurRegion = {
  x: number;
  y: number;
  w: number;
  h: number;
  intensity: number;
};

export type PreviewSettings = {
  regions: PreviewBlurRegion[];
  /** 0 = top, 1 = bottom — fraction of video height */
  subtitleY: number;
  /** font size as fraction of video height */
  subtitleSize: number;
};

type Box = { id: number; x: number; y: number; w: number; h: number };

const round4 = (n: number) => Math.round(n * 10000) / 10000;
const clamp01 = (n: number) => Math.min(1, Math.max(0, n));

/**
 * Preview editor: the main canvas where the user draws blur boxes
 * (drag to move, corner handle to resize, x to remove — like the
 * reference screenshot) and positions the subtitle line (drag up/down
 * + size slider). Everything is stored as fractions of the video
 * size, so the backend burns it into the final video exactly as
 * edited, at any render resolution.
 */
export default function PreviewEditor({
  file,
  initial,
  onDone,
}: {
  file: File;
  initial?: PreviewSettings;
  onDone: (s: PreviewSettings) => void;
}) {
  const { t } = useT();
  const [url, setUrl] = useState<string | null>(null);
  const [boxes, setBoxes] = useState<Box[]>(() =>
    (initial?.regions ?? []).map((r, i) => ({
      id: i,
      x: clamp01(r.x),
      y: clamp01(r.y),
      w: clamp01(r.w),
      h: clamp01(r.h),
    }))
  );
  const [intensity, setIntensity] = useState(
    initial?.regions?.[0]?.intensity ?? 22
  );
  const [subY, setSubY] = useState(initial?.subtitleY ?? 0.96);
  const [subPx, setSubPx] = useState(24);
  const [subTouched, setSubTouched] = useState(false);
  const [nextId, setNextId] = useState((initial?.regions ?? []).length);
  const [selected, setSelected] = useState<number | null>(null);

  const stageRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<null | {
    id: number;
    mode: "move" | "resize";
    startX: number;
    startY: number;
    orig: Box;
  }>(null);
  const subDragRef = useRef<null | { startY: number; origY: number }>(null);

  useEffect(() => {
    const u = URL.createObjectURL(file);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);

  const stageSize = useCallback(() => {
    const el = stageRef.current;
    if (!el) return { w: 1, h: 1 };
    const r = el.getBoundingClientRect();
    return { w: Math.max(1, r.width), h: Math.max(1, r.height) };
  }, []);

  // ---- box drag / resize (window-level move so it survives fast touches) ----
  const onDragMove = useCallback(
    (e: PointerEvent) => {
      const d = dragRef.current;
      if (!d) return;
      const { w, h } = stageSize();
      const dx = (e.clientX - d.startX) / w;
      const dy = (e.clientY - d.startY) / h;
      setBoxes((prev) =>
        prev.map((b) => {
          if (b.id !== d.id) return b;
          if (d.mode === "move") {
            return {
              ...b,
              x: clamp01(Math.min(1 - b.w, Math.max(0, d.orig.x + dx))),
              y: clamp01(Math.min(1 - b.h, Math.max(0, d.orig.y + dy))),
            };
          }
          return {
            ...b,
            w: clamp01(Math.min(1 - d.orig.x, Math.max(0.05, d.orig.w + dx))),
            h: clamp01(Math.min(1 - d.orig.y, Math.max(0.05, d.orig.h + dy))),
          };
        })
      );
    },
    [stageSize]
  );

  const onDragEnd = useCallback(() => {
    dragRef.current = null;
    window.removeEventListener("pointermove", onDragMove);
  }, [onDragMove]);

  const onBoxPointerDown = (
    e: React.PointerEvent,
    id: number,
    mode: "move" | "resize"
  ) => {
    e.stopPropagation();
    e.preventDefault();
    const box = boxes.find((b) => b.id === id);
    if (!box) return;
    setSelected(id);
    dragRef.current = {
      id,
      mode,
      startX: e.clientX,
      startY: e.clientY,
      orig: { ...box },
    };
    window.addEventListener("pointermove", onDragMove);
    window.addEventListener("pointerup", onDragEnd, { once: true });
  };

  // ---- subtitle vertical drag ----
  const onSubDragMove = useCallback(
    (e: PointerEvent) => {
      const d = subDragRef.current;
      if (!d) return;
      const { h } = stageSize();
      const dy = (e.clientY - d.startY) / h;
      setSubY(Math.min(0.98, Math.max(0.02, d.origY + dy)));
    },
    [stageSize]
  );

  const onSubDragEnd = useCallback(() => {
    subDragRef.current = null;
    window.removeEventListener("pointermove", onSubDragMove);
  }, [onSubDragMove]);

  const onSubPointerDown = (e: React.PointerEvent) => {
    e.stopPropagation();
    e.preventDefault();
    subDragRef.current = { startY: e.clientY, origY: subY };
    window.addEventListener("pointermove", onSubDragMove);
    window.addEventListener("pointerup", onSubDragEnd, { once: true });
  };

  const addBox = () => {
    const id = nextId;
    setNextId(id + 1);
    setBoxes((prev) => [
      ...prev,
      { id, x: 0.2, y: 0.42, w: 0.6, h: 0.16 },
    ]);
    setSelected(id);
  };

  const removeBox = (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    setBoxes((prev) => prev.filter((b) => b.id !== id));
    setSelected((s) => (s === id ? null : s));
  };

  const handleDone = () => {
    const { h } = stageSize();
    onDone({
      regions: boxes.map((b) => ({
        x: round4(b.x),
        y: round4(b.y),
        w: round4(b.w),
        h: round4(b.h),
        intensity,
      })),
      subtitleY: round4(subY),
      subtitleSize: round4(subPx / h),
    });
  };

  return (
    <div>
      <div
        ref={stageRef}
        className="relative w-full select-none overflow-hidden rounded-2xl bg-black"
        style={{ touchAction: "none" }}
        onPointerDown={() => setSelected(null)}
      >
        {url && (
          <video
            src={url}
            className="block w-full"
            muted
            loop
            playsInline
            autoPlay
            preload="metadata"
            onLoadedMetadata={(e) => {
              if (!subTouched) {
                const h = e.currentTarget.clientHeight || 360;
                setSubPx(Math.round(h * (initial?.subtitleSize ?? 0.033)));
              }
            }}
            onClick={(e) => {
              const v = e.currentTarget;
              if (v.paused) v.play();
              else v.pause();
            }}
          />
        )}

        {/* blur boxes */}
        {boxes.map((b) => (
          <div
            key={b.id}
            onPointerDown={(e) => onBoxPointerDown(e, b.id, "move")}
            className={`absolute rounded-xl border-2 transition-colors ${
              selected === b.id
                ? "border-white shadow-[0_0_0_2px_rgba(59,130,246,0.8)]"
                : "border-white/80"
            }`}
            style={{
              left: `${b.x * 100}%`,
              top: `${b.y * 100}%`,
              width: `${b.w * 100}%`,
              height: `${b.h * 100}%`,
              backdropFilter: `blur(${Math.round(intensity * 0.55)}px)`,
              WebkitBackdropFilter: `blur(${Math.round(intensity * 0.55)}px)`,
              background: "rgba(255,255,255,0.08)",
              cursor: "move",
            }}
          >
            <button
              type="button"
              aria-label={t("preview.removeBlur")}
              onClick={(e) => removeBox(e, b.id)}
              className="absolute -right-3 -top-3 flex h-7 w-7 items-center justify-center rounded-full bg-black/70 text-sm font-bold text-white shadow"
            >
              ×
            </button>
            <span
              aria-hidden
              onPointerDown={(e) => onBoxPointerDown(e, b.id, "resize")}
              className="absolute -bottom-2 -right-2 h-6 w-6 rounded-full border-2 border-indigo-500 bg-white shadow"
              style={{ cursor: "nwse-resize", touchAction: "none" }}
            />
          </div>
        ))}

        {/* draggable subtitle preview */}
        <div
          onPointerDown={onSubPointerDown}
          className="absolute left-1/2 -translate-x-1/2 -translate-y-1/2 cursor-grab whitespace-nowrap rounded-full border-2 border-white/90 bg-black/45 px-4 py-1 font-bold text-white shadow-lg active:cursor-grabbing"
          style={{
            top: `${subY * 100}%`,
            fontSize: subPx,
            touchAction: "none",
          }}
        >
          {t("preview.subtitleSample")}
        </div>

        {/* overlay buttons like the reference */}
        <button
          type="button"
          onClick={addBox}
          className="absolute left-3 top-3 rounded-full bg-black/55 px-5 py-2.5 text-sm font-bold text-white shadow-lg backdrop-blur"
        >
          + {t("preview.addBlur")}
        </button>
        <button
          type="button"
          onClick={handleDone}
          className="absolute right-3 top-3 rounded-full bg-black/55 px-5 py-2.5 text-sm font-bold text-white shadow-lg backdrop-blur"
        >
          ✓ {t("preview.done")}
        </button>
      </div>

      <div className="mt-4 space-y-3">
        <div>
          <div className="mb-1 flex items-center justify-between text-sm">
            <span className="font-semibold">{t("preview.blurStrength")}</span>
            <span className="rounded-full bg-[var(--surface)] px-3 py-0.5 text-xs font-bold">
              {intensity}
            </span>
          </div>
          <input
            type="range"
            min={1}
            max={50}
            value={intensity}
            onChange={(e) => setIntensity(Number(e.target.value))}
            className="w-full"
            aria-label={t("preview.blurStrength")}
          />
        </div>
        <div>
          <div className="mb-1 flex items-center justify-between text-sm">
            <span className="font-semibold">{t("preview.subtitleSize")}</span>
            <span className="rounded-full bg-[var(--surface)] px-3 py-0.5 text-xs font-bold">
              {subPx}px
            </span>
          </div>
          <input
            type="range"
            min={12}
            max={72}
            value={subPx}
            onChange={(e) => {
              setSubPx(Number(e.target.value));
              setSubTouched(true);
            }}
            className="w-full"
            aria-label={t("preview.subtitleSize")}
          />
        </div>
        <p className="text-xs text-[var(--muted)]">{t("preview.hint")}</p>
      </div>
    </div>
  );
}
