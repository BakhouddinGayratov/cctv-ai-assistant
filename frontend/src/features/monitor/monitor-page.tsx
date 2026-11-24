import { Boxes, Clock3, Grid3x3, Images, LogIn, UserRoundX, UsersRound } from "lucide-react";
import { lazy, Suspense, useCallback, useMemo, useState } from "react";
import { Link } from "react-router";
import { StatTile } from "@/components/stat-tile";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Switch } from "@/components/ui/field";
import { Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { ChatPanel } from "@/features/chat/chat-panel";
import { useAttendance, useConfig, useWorkers } from "@/lib/queries";
import { useMediaQuery } from "@/lib/use-media-query";
import { todayIso } from "@/lib/utils";
import { ArchiveSheet } from "./archive-sheet";
import { CameraGrid, usePreviewStills } from "./camera-grid";
import { LivePlayer } from "./live-player";

const CameraNetwork3D = lazy(() => import("@/features/network3d/camera-network-3d"));

const VIEWS = [
  { value: "grid", label: "Setka", icon: <Grid3x3 /> },
  { value: "3d", label: "3D xarita", icon: <Boxes /> },
] as const;

function readLastChannel(): number | null {
  try {
    const v = Number(localStorage.getItem("cctv-last-channel"));
    return Number.isInteger(v) && v > 0 ? v : null;
  } catch {
    return null;
  }
}

function TodayStrip() {
  const day = todayIso();
  const { data, isLoading } = useAttendance(day);
  const s = data?.summary;
  const inOffice = data?.employees.filter((e) => e.status === "ofisda").length ?? 0;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatTile index={0} loading={isLoading} icon={<UsersRound />} label="Bugun kelganlar" value={s?.present ?? 0} suffix={`/ ${s?.total_employees ?? 0}`} tone="good" hint={<Link to="/attendance" className="hover:text-brand">Davomatni ochish →</Link>} />
      <StatTile index={1} loading={isLoading} icon={<LogIn />} label="Hozir ofisda" value={inOffice} tone="accent" hint="Kirish kameralari bo'yicha" />
      <StatTile index={2} loading={isLoading} icon={<Clock3 />} label="Kechikkanlar" value={s?.late ?? 0} tone="warning" hint="Ish boshlanishidan keyin" />
      <StatTile index={3} loading={isLoading} icon={<UserRoundX />} label="Notanish yuzlar" value={s?.unknown_faces ?? 0} tone="critical" hint={<Link to="/employees" className="hover:text-brand">Biriktirish →</Link>} />
    </div>
  );
}

export function MonitorPage() {
  const config = useConfig();
  const workers = useWorkers();
  const cameras = useMemo(() => config.data?.cameras ?? [], [config.data]);
  const [selected, setSelected] = useState<number | null>(readLastChannel);
  const [playing, setPlaying] = useState(false);
  const [view, setView] = useState<"grid" | "3d">("grid");
  const [previews, setPreviews] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);
  const [chatContext, setChatContext] = useState(true);

  const wide = useMediaQuery("(min-width: 1280px)");
  const clearContext = useCallback(() => setChatContext(false), []);
  const channels = useMemo(() => cameras.map((c) => c.channel), [cameras]);
  const stills = usePreviewStills(channels, previews);
  const camera = cameras.find((c) => c.channel === selected) ?? null;

  const select = useCallback((ch: number) => {
    setSelected(ch);
    setPlaying(true);
    setChatContext(true);
    try {
      localStorage.setItem("cctv-last-channel", String(ch));
    } catch {
      /* ignore */
    }
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, []);

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px] 2xl:grid-cols-[minmax(0,1fr)_460px]">
      <div className="flex min-w-0 flex-col gap-5">
        <TodayStrip />
        <LivePlayer
          camera={camera}
          playing={playing}
          onPlayingChange={setPlaying}
          onOpenArchive={() => setArchiveOpen(true)}
          nvrOnline={workers.data?.nvr_online}
        />

        {wide ? null : <ChatPanel className="h-[640px]" context={chatContext ? camera : null} onClearContext={clearContext} />}

        <Card>
          <CardHeader
            icon={<Grid3x3 />}
            title={`Kameralar (${cameras.length})`}
            description="Kamerani tanlang — jonli oqim ochiladi va AI savollari shu kameraga bog'lanadi"
            actions={
              <>
                {view === "grid" ? <Switch checked={previews} onChange={setPreviews} label={<span className="flex items-center gap-1.5 text-xs"><Images className="size-3.5" /> Kadrlar</span>} /> : null}
                <Segmented ariaLabel="Ko'rinish" value={view} onChange={setView} options={VIEWS} />
              </>
            }
          />
          <CardBody>
            {config.isLoading ? (
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 2xl:grid-cols-6">
                {Array.from({ length: 12 }, (_, i) => (
                  <Skeleton key={i} className="aspect-[16/11]" />
                ))}
              </div>
            ) : view === "grid" ? (
              <CameraGrid cameras={cameras} selected={selected} onSelect={select} stills={stills} />
            ) : (
              <Suspense fallback={<Skeleton className="h-[380px] sm:h-[440px]" />}>
                <CameraNetwork3D cameras={cameras} selected={selected} onSelect={select} />
              </Suspense>
            )}
          </CardBody>
        </Card>
      </div>

      {wide ? (
        <aside>
          <div className="sticky top-[5.25rem] h-[calc(100dvh-6.5rem)]">
            <ChatPanel className="h-full" context={chatContext ? camera : null} onClearContext={clearContext} />
          </div>
        </aside>
      ) : null}

      <ArchiveSheet open={archiveOpen} onOpenChange={setArchiveOpen} cameras={cameras} defaultChannel={selected} />
    </div>
  );
}
