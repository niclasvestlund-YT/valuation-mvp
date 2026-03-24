import { useRef } from "react";
import { Camera } from "lucide-react";
import { ValuationResponse } from "../types";

interface Props {
  result: ValuationResponse;
  thumbnailUrl: string | null;
  onReset: () => void;
  onForceShow: () => void;
}

export function AmbiguousModelState({ result, thumbnailUrl, onReset, onForceShow }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleMorePhotos = (_fileList: FileList | null) => {
    // Reset to landing so user can start a new, better-lit scan
    onReset();
  };

  return (
    <div className="space-y-5">
      {/* Photo with badge */}
      <div className="relative overflow-hidden" style={{ borderRadius: 16, height: 200 }}>
        {thumbnailUrl ? (
          <img src={thumbnailUrl} alt="" className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full" style={{ background: "#EDEAE3" }} />
        )}
        <span
          className="absolute top-3 right-3"
          style={{
            fontSize: "11px",
            fontWeight: 600,
            color: "#FFFFFF",
            background: "rgba(44,42,37,0.72)",
            padding: "3px 8px",
            borderRadius: 6,
          }}
        >
          Otydlig bild
        </span>
      </div>

      {/* Identity */}
      <div>
        <p className="uppercase mb-1" style={{ fontSize: "11px", color: "#B0AA9E", letterSpacing: "2px" }}>
          MÖJLIG MATCHNING
        </p>
        <p style={{ fontSize: "1.25rem", fontWeight: 600, color: "#2C2A25", lineHeight: 1.4 }}>
          {result.product_name ?? "Okänd produkt"}
        </p>
      </div>

      {/* Explanation */}
      {result.warnings.length > 0 && (
        <p style={{ fontSize: "14px", color: "#5C5850", lineHeight: 1.65 }}>
          {result.warnings[0]}
        </p>
      )}

      {/* Photo request slots */}
      <div className="rounded-[14px] p-4 space-y-3" style={{ background: "#EDEAE3" }}>
        <p style={{ fontSize: "13px", fontWeight: 500, color: "#2C2A25" }}>
          Lägg till fler bilder för bättre estimat
        </p>
        <div className="grid grid-cols-3 gap-2">
          {["Sidan", "Modellnr.", "Etikett"].map((label) => (
            <button
              key={label}
              onClick={() => fileInputRef.current?.click()}
              className="flex flex-col items-center justify-center gap-1 rounded-xl border-2 border-dashed"
              style={{
                height: 80,
                background: "#F7F5F0",
                borderColor: "#D5D0C5",
                fontSize: "11px",
                color: "#8A8578",
              }}
            >
              <Camera style={{ width: 18, height: 18, color: "#B0AA9E" }} />
              {label}
            </button>
          ))}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={(e) => handleMorePhotos(e.target.files)}
        />
      </div>

      {/* Blockquote suggestion */}
      <div style={{ borderLeft: "2px solid #D5D0C5", paddingLeft: 16 }}>
        <p style={{ fontSize: "14px", color: "#5C5850", lineHeight: 1.65 }}>
          Olika modeller i samma serie kan skilja sig mycket i pris. En tydligare bild av
          modellnumret hjälper oss ge ett träffsäkert estimat.
        </p>
      </div>

      {/* CTA */}
      <button
        onClick={onReset}
        className="w-full flex items-center justify-center"
        style={{
          height: 48,
          borderRadius: 14,
          background: "#2C2A25",
          color: "#F7F5F0",
          fontSize: "14px",
          fontWeight: 600,
        }}
      >
        Ta fler bilder
      </button>

      {/* Escape — only shown when a fallback estimate actually exists */}
      {result.estimated_value !== null && (
        <p className="text-center">
          <button
            onClick={onForceShow}
            className="underline"
            style={{ fontSize: "13px", color: "#8A8578" }}
          >
            Visa ungefärligt estimat ändå
          </button>
        </p>
      )}
    </div>
  );
}
