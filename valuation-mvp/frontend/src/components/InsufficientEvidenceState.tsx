import { AlertCircle } from "lucide-react";
import { ValuationResponse } from "../types";

const SOURCE_LABELS: Record<string, string> = {
  tradera: "Tradera",
  blocket: "Blocket",
  facebook_marketplace: "Facebook",
  google_shopping: "Google Shopping",
  prisjakt: "Prisjakt",
};

function formatSEK(v: number) {
  return new Intl.NumberFormat("sv-SE", { style: "currency", currency: "SEK", maximumFractionDigits: 0 }).format(v);
}

interface Props {
  result: ValuationResponse;
  thumbnailUrl: string | null;
  onReset: () => void;
  onForceShow: () => void;
}

export function InsufficientEvidenceState({ result, thumbnailUrl, onReset, onForceShow }: Props) {
  const sourceCounts = result.market_listings.reduce<Record<string, number>>((acc, l) => {
    acc[l.source] = (acc[l.source] ?? 0) + 1;
    return acc;
  }, {});

  const traderaUrl = `https://www.tradera.com/search?q=${encodeURIComponent(result.product_name ?? "")}`;
  const blocketUrl = `https://www.blocket.se/annonser/hela_sverige?q=${encodeURIComponent(result.product_name ?? "")}`;

  return (
    <div className="space-y-5">
      {/* Identity row */}
      <div className="flex items-center gap-3">
        {thumbnailUrl ? (
          <img
            src={thumbnailUrl}
            alt=""
            className="object-cover shrink-0"
            style={{ width: 52, height: 52, borderRadius: 12, border: "1px solid #E8E4DB" }}
          />
        ) : (
          <div style={{ width: 52, height: 52, borderRadius: 12, background: "#EDEAE3", flexShrink: 0 }} />
        )}
        <div>
          <p style={{ fontSize: "18px", fontWeight: 600, color: "#2C2A25" }}>
            {result.product_name ?? "Okänd produkt"}
          </p>
          <p style={{ fontSize: "11px", color: "#B0AA9E", marginTop: 2 }}>Identifierad ✓</p>
        </div>
      </div>

      {/* Empty state */}
      <div className="flex flex-col items-center text-center py-4 space-y-3">
        <div
          className="flex items-center justify-center rounded-full"
          style={{ width: 48, height: 48, background: "#EDEAE3" }}
        >
          <AlertCircle style={{ width: 22, height: 22, color: "#8A8578" }} />
        </div>
        <div>
          <p style={{ fontSize: "1.25rem", fontWeight: 600, color: "#2C2A25" }}>
            Inte tillräckligt med data
          </p>
          <p style={{ fontSize: "14px", color: "#8A8578", marginTop: 4 }}>
            Vi hittade {result.product_name ?? "produkten"} men bara{" "}
            {result.comparables_used} relevanta{" "}
            {result.comparables_used === 1 ? "annons" : "annonser"}.
          </p>
        </div>
      </div>

      {/* DET VI HITTADE */}
      {(Object.keys(sourceCounts).length > 0 || result.new_price) && (
        <div>
          <p className="uppercase mb-2" style={{ fontSize: "11px", color: "#B0AA9E", letterSpacing: "2px" }}>
            DET VI HITTADE
          </p>
          <div className="rounded-xl overflow-hidden" style={{ border: "1px solid #E8E4DB" }}>
            {Object.entries(sourceCounts).map(([source, count], i, arr) => (
              <div
                key={source}
                className="flex items-center justify-between px-4 py-2.5"
                style={{
                  background: "#FFFFFF",
                  borderBottom: (i < arr.length - 1 || result.new_price) ? "1px solid #E8E4DB" : undefined,
                  fontSize: "14px",
                }}
              >
                <span style={{ color: "#5C5850" }}>{SOURCE_LABELS[source] ?? source}</span>
                <span style={{ color: "#8A8578" }}>
                  {count} {count === 1 ? "annons" : "annonser"}
                </span>
              </div>
            ))}
            {result.new_price && (
              <div className="flex items-center justify-between px-4 py-2.5" style={{ background: "#FFFFFF", fontSize: "14px" }}>
                <span style={{ color: "#5C5850" }}>Nypris</span>
                <span style={{ color: "#8A8578" }}>{formatSEK(result.new_price)}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Blockquote suggestion */}
      <div style={{ borderLeft: "2px solid #D5D0C5", paddingLeft: 16 }}>
        <p style={{ fontSize: "14px", color: "#5C5850", lineHeight: 1.65 }}>
          Prova igen om ett par dagar — nya annonser dyker upp hela tiden. Du kan också söka
          manuellt på{" "}
          <a href={traderaUrl} target="_blank" rel="noopener noreferrer" className="underline" style={{ color: "#2C2A25" }}>
            Tradera
          </a>{" "}
          eller{" "}
          <a href={blocketUrl} target="_blank" rel="noopener noreferrer" className="underline" style={{ color: "#2C2A25" }}>
            Blocket
          </a>
          .
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
        Värdera en annan produkt
      </button>

      {/* Escape — only shown when a fallback estimate actually exists */}
      {result.estimated_value !== null && (
        <p className="text-center">
          <button
            onClick={onForceShow}
            className="underline"
            style={{ fontSize: "13px", color: "#8A8578" }}
          >
            Visa grov uppskattning ändå
          </button>
        </p>
      )}
    </div>
  );
}
