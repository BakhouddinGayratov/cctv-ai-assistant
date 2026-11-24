import { Camera as CameraIcon, CircleStop, Expand, History, ImageDown, Play, Radio, VideoOff } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useEffectEvent, useRef, useState } from "react";
import { useLightbox } from "@/components/lightbox";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { api, snapshotUrl, streamUrl } from "@/lib/api";
import type { Camera } from "@/lib/types";
import { channelLabel, cn } from "@/lib/utils";
import { PtzPad } from "./ptz-pad";

type PlayerState = "idle" | "connecting" | "live" | "error";

/**
 * Sahifadan chiqilganda yoki tab yashirilganda NVR oqimi darhol yopiladi.
 * Kamera almashtirishda "stop" yuborilmaydi — server bitta-oqim qoidasini o'zi boshqaradi
 * (aks holda kechikkan stop yangi oqimni uzib qo'yishi mumkin).
 */
function useStreamLifecycle(playing: boolean, onHidden: () => void) {
  const hidden = useEffectEvent(onHidden);
  const playingRef = useRef(playing);
  playingRef.current = playing;

  useEffect(() => {
    const stop = () => navigator.sendBeacon?.("/api/stream/stop");
    const onVis = () => {
      if (document.hidden && playingRef.current) {
        stop();
        hidden();
      }
    };
    window.addEventListener("pagehide", stop);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.removeEventListener("pagehide", stop);
      document.removeEventListener("visibilitychange", onVis);
      if (playingRef.current) void api.stopStream().catch(() => undefined);
    };
  }, []);
}

export function LivePlayer({
  camera,
  playing,
  onPlayingChange,
  onOpenArchive,
  nvrOnline,
}: {
  camera: Camera | null;
  playing: boolean;
  onPlayingChange: (v: boolean) => void;
  onOpenArchive: () => void;
  nvrOnline: boolean | undefined;
}) {
  const [state, setState] = useState<PlayerState>("idle");
  const [src, setSrc] = useState<string | null>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const lightbox = useLightbox();
  const channel = camera?.channel ?? null;

  useStreamLifecycle(playing, () => onPlayingChange(false));

  function stop() {
    onPlayingChange(false);
    void api.stopStream().catch(() => undefined);
  }

  useEffect(() => {
    if (channel == null || !playing) {
      setSrc(null);
      setState("idle");
      return;
    }
    setState("connecting");
    setSrc(streamUrl(channel));
    // Chrome MJPEG (multipart) oqimida onLoad'ni ishonchli chiqarmaydi — 2.5 s dan keyin tasvirni ko'rsatamiz
    // (NVR oflayn bo'lsa server o'zi "ulanmagan" kadrini yuboradi).
    const t = window.setTimeout(() => setState((s) => (s === "connecting" ? "live" : s)), 2500);
    return () => window.clearTimeout(t);
  }, [channel, playing]);

  function fullscreen() {
    void frameRef.current?.requestFullscreen?.();
  }

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center gap-3 px-4 pt-4 pb-3 sm:px-5">
        <div className="flex min-w-0 items-center gap-3">
          <span className="grid size-9 place-items-center rounded-lg bg-brand-soft text-brand">
            <CameraIcon className="size-[18px]" />
          </span>
          <div className="min-w-0">
            <h2 className="truncate text-[15px] font-semibold tracking-tight">{camera ? camera.name : "Kamera tanlanmagan"}</h2>
            <p className="text-xs text-fg-muted">
              {camera ? `${channelLabel(camera.channel)} · sub-stream MJPEG · faqat bitta oqim` : "Pastdagi ro'yxatdan yoki 3D xaritadan kamera tanlang"}
            </p>
          </div>
        </div>
        <div className="ml-auto flex items-center gap-1.5">
          <Tooltip content="NVR arxividan lavha">
            <Button size="sm" onClick={onOpenArchive} aria-label="NVR arxiv">
              <History /> <span className="hidden sm:inline">Arxiv</span>
            </Button>
          </Tooltip>
          <Tooltip content="Yuqori sifatli kadr">
            <Button
              size="icon-sm"
              variant="ghost"
              disabled={channel == null}
              aria-label="Kadr olish"
              onClick={() => channel != null && lightbox.open([snapshotUrl(channel, true)], 0, camera?.name)}
            >
              <ImageDown />
            </Button>
          </Tooltip>
          <Tooltip content="To'liq ekran">
            <Button size="icon-sm" variant="ghost" disabled={state !== "live"} aria-label="To'liq ekran" onClick={fullscreen}>
              <Expand />
            </Button>
          </Tooltip>
          {playing ? (
            <Button size="sm" variant="danger" onClick={stop}>
              <CircleStop /> To'xtatish
            </Button>
          ) : (
            <Button size="sm" variant="primary" disabled={channel == null} onClick={() => onPlayingChange(true)}>
              <Play /> Jonli
            </Button>
          )}
        </div>
      </div>

      <div ref={frameRef} className="relative mx-4 mb-4 aspect-video overflow-hidden rounded-xl bg-[#05070d] ring-1 ring-line sm:mx-5 sm:mb-5">
        {src ? (
          <img
            key={src}
            src={src}
            alt={camera ? `${camera.name} jonli oqimi` : "Jonli oqim"}
            className={cn("absolute inset-0 size-full object-contain transition-opacity duration-500", state === "live" ? "opacity-100" : "opacity-0")}
            onLoad={() => setState("live")}
            onError={() => setState("error")}
          />
        ) : null}

        <AnimatePresence>
          {state !== "live" ? (
            <motion.div
              key={state}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="absolute inset-0 grid place-items-center"
            >
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,oklch(40%_0.12_285/35%),transparent_60%)]" />
              <div className="relative flex flex-col items-center gap-3 px-6 text-center text-white/80">
                {state === "connecting" ? (
                  <>
                    <span className="relative grid size-14 place-items-center">
                      <span className="absolute inset-0 animate-ping rounded-full bg-brand/30" />
                      <Radio className="relative size-7 text-white" />
                    </span>
                    <p className="text-sm font-medium">NVR oqimiga ulanmoqda…</p>
                    <p className="text-xs text-white/50">{camera ? channelLabel(camera.channel) : ""}</p>
                  </>
                ) : state === "error" || nvrOnline === false ? (
                  <>
                    <VideoOff className="size-10 text-critical" />
                    <p className="text-sm font-medium">{nvrOnline === false ? "NVR ulanmagan" : "Oqim uzildi"}</p>
                    <p className="max-w-xs text-xs text-white/50">Tarmoqni tekshiring yoki qayta urinib ko'ring.</p>
                  </>
                ) : (
                  <>
                    <CameraIcon className="size-10 text-white/40" />
                    <p className="text-sm font-medium">{camera ? "Jonli ko'rish uchun «Jonli» tugmasini bosing" : "Kamera tanlang"}</p>
                    <p className="max-w-xs text-xs text-white/50">Tizim faqat siz ko'rayotgan bitta kamerani oqimga oladi — NVR ortiqcha yuklanmaydi.</p>
                  </>
                )}
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>

        {state === "live" && camera ? (
          <>
            <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-1/3 animate-scan bg-gradient-to-b from-transparent via-white/[0.035] to-transparent" />
            <div className="absolute top-3 left-3 flex items-center gap-2">
              <Badge tone="critical" className="border-critical/40 bg-black/60 text-white backdrop-blur">
                <span className="size-1.5 animate-pulse rounded-full bg-critical" /> LIVE
              </Badge>
              <Badge className="border-white/10 bg-black/60 font-mono text-white/90 backdrop-blur">{channelLabel(camera.channel)}</Badge>
            </div>
            <PtzPad channel={camera.channel} />
          </>
        ) : null}
      </div>
    </div>
  );
}
