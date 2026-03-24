import { useRef } from "react";
import { Camera, Tag, Sun } from "lucide-react";
import { ScanEntry } from "../types";

const TIPS = [
  { Icon: Camera, title: "Hela produkten synlig", sub: "Fota hela enheten" },
  { Icon: Tag, title: "Modellnr om möjligt", sub: "Etikett eller box" },
  { Icon: Sun, title: "Bra ljus, ingen blixt", sub: "Naturligt ljus" },
] as const;

function formatSEK(v: number) {
  return new Intl.NumberFormat("sv-SE", { style: "currency", currency: "SEK", maximumFractionDigits: 0 }).format(
    Math.round(v / 50) * 50,
  );
}

function formatRelativeTime(date: Date): string {
  const diff = Math.floor((Date.now() - date.getTime()) / 60000);
  if (diff < 1) return "Just nu";
  if (diff < 60) return `${diff} min sedan`;
  const h = Math.floor(diff / 60);
  if (h < 24) return `${h} tim sedan`;
  return `${Math.floor(h / 24)} dag${Math.floor(h / 24) > 1 ? "ar" : ""} sedan`;
}

interface Props {
  onAnalyze: (files: File[]) => void;
  history: ScanEntry[];
  onOpenHistory: (entry: ScanEntry) => void;
}

export function LandingScreen({ onAnalyze, history, onOpenHistory }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  const handleFiles = (fileList: FileList | null) => {
    if (fileList && fileList.length > 0) {
      onAnalyze(Array.from(fileList).slice(0, 5));
    }
  };

  return (
    <div className="space-y-6">
      {/* Hero */}
      <div className="text-center space-y-1 pt-2">
        <h2 style={{ fontSize: "1.25rem", fontWeight: 700, color: "#2C2A25", lineHeight: 1.5 }}>
          Vad är din pryl värd idag?
        </h2>
        <p style={{ fontSize: "15px", color: "#8A8578" }}>
          Fota en teknikprodukt. Vi kollar vad den säljs för.
        </p>
      </div>

      {/* Upload area */}
      <div
        role="button"
        tabIndex={0}
        className="flex flex-col items-center justify-center rounded-[20px] cursor-pointer"
        style={{
          minHeight: 180,
          background: "#EDEAE3",
          border: "2px dashed #D5D0C5",
          padding: "28px 20px",
          gap: 12,
        }}
        onClick={() => fileInputRef.current?.click()}
        onKeyDown={(e) => e.key === "Enter" && fileInputRef.current?.click()}
      >
        <div
          className="flex items-center justify-center rounded-full"
          style={{ width: 56, height: 56, background: "#F7F5F0" }}
        >
          <Camera style={{ width: 28, height: 28, color: "#8A8578" }} />
        </div>
        <div className="text-center">
          <p style={{ fontSize: "15px", fontWeight: 500, color: "#2C2A25" }}>Ta ett foto</p>
          <p style={{ fontSize: "13px", color: "#8A8578", marginTop: 2 }}>eller välj från biblioteket</p>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
      </div>

      {/* Camera shortcut */}
      <button
        onClick={() => cameraInputRef.current?.click()}
        className="w-full flex items-center justify-center gap-2 rounded-xl border"
        style={{
          height: 44,
          fontSize: "14px",
          color: "#5C5850",
          borderColor: "#D5D0C5",
          background: "#EDEAE3",
        }}
      >
        <Camera style={{ width: 16, height: 16, color: "#8A8578" }} />
        Öppna kamera
      </button>
      <input
        ref={cameraInputRef}
        type="file"
        accept="image/*"
        capture="environment"
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />

      {/* Tips row */}
      <div>
        <p className="uppercase mb-3" style={{ fontSize: "11px", color: "#B0AA9E", letterSpacing: "2px" }}>
          TIPS FÖR BÄSTA RESULTAT
        </p>
        <div className="grid grid-cols-3 gap-2">
          {TIPS.map(({ Icon, title, sub }) => (
            <div
              key={title}
              className="flex flex-col items-center text-center rounded-xl gap-2"
              style={{ background: "#EDEAE3", padding: "12px 8px" }}
            >
              <Icon style={{ width: 24, height: 24, color: "#8A8578" }} />
              <div>
                <p style={{ fontSize: "11px", fontWeight: 500, color: "#5C5850", lineHeight: 1.35 }}>{title}</p>
                <p style={{ fontSize: "10px", color: "#B0AA9E", marginTop: 2, lineHeight: 1.35 }}>{sub}</p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Recent scans */}
      {history.length > 0 && (
        <div>
          <p className="uppercase mb-3" style={{ fontSize: "11px", color: "#B0AA9E", letterSpacing: "2px" }}>
            SENASTE VÄRDERINGAR
          </p>
          <div className="rounded-xl overflow-hidden" style={{ border: "1px solid #E8E4DB" }}>
            {history.map((entry, i) => (
              <button
                key={i}
                onClick={() => onOpenHistory(entry)}
                className="w-full flex items-center gap-3 px-3 text-left"
                style={{
                  paddingTop: 10,
                  paddingBottom: 10,
                  background: "#FFFFFF",
                  borderBottom: i < history.length - 1 ? "1px solid #E8E4DB" : undefined,
                }}
              >
                {entry.thumbnailUrl ? (
                  <img
                    src={entry.thumbnailUrl}
                    alt=""
                    className="object-cover shrink-0"
                    style={{ width: 36, height: 36, borderRadius: 8, border: "1px solid #E8E4DB" }}
                  />
                ) : (
                  <div style={{ width: 36, height: 36, borderRadius: 8, background: "#EDEAE3", flexShrink: 0 }} />
                )}
                <div className="flex-1 min-w-0">
                  <p className="truncate" style={{ fontSize: "13px", color: "#2C2A25", fontWeight: 500 }}>
                    {entry.product_name ?? "Okänd produkt"}
                  </p>
                  <p style={{ fontSize: "11px", color: "#B0AA9E" }}>{formatRelativeTime(entry.timestamp)}</p>
                </div>
                {entry.estimated_value !== null && (
                  <span style={{ fontSize: "13px", fontWeight: 600, color: "#2C2A25", flexShrink: 0 }}>
                    {formatSEK(entry.estimated_value)}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
