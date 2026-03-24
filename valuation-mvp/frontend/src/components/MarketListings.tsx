import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { MarketListing } from "../types";

interface Props {
  listings: MarketListing[];
}

const SOURCE_LABELS: Record<string, string> = {
  tradera: "Tradera",
  blocket: "Blocket",
  facebook_marketplace: "Facebook",
  google_shopping: "Google Shopping",
  prisjakt: "Prisjakt",
};

function formatSEK(value: number) {
  return new Intl.NumberFormat("sv-SE", { style: "currency", currency: "SEK", maximumFractionDigits: 0 }).format(value);
}

function formatDate(dateStr: string): string {
  try {
    const date = new Date(dateStr);
    const diff = Math.floor((Date.now() - date.getTime()) / 86400000);
    if (diff <= 0) return "idag";
    if (diff === 1) return "igår";
    if (diff < 7) return `${diff} dagar sedan`;
    if (diff < 30) return `${Math.floor(diff / 7)} veckor sedan`;
    if (diff < 365) return `${Math.floor(diff / 30)} mån sedan`;
    return `${Math.floor(diff / 365)} år sedan`;
  } catch {
    return dateStr;
  }
}

function getConditionTag(title: string): string | null {
  const t = title.toLowerCase();
  if (t.includes("nyskick") || t.includes("oöppnad") || t.includes("obruten")) return "Nyskick";
  if (t.includes("fint skick") || t.includes("gott skick") || t.includes("bra skick")) return "Fint skick";
  if (t.includes("begagnad") || t.includes("använd")) return "Begagnad";
  return null;
}

function RelevanceDot({ score }: { score: number }) {
  if (score >= 0.7) return <span style={{ fontSize: "10px", color: "#34a873" }}>● hög relevans</span>;
  if (score >= 0.4) return <span style={{ fontSize: "10px", color: "#d4a017" }}>● medium</span>;
  return null;
}

export function MarketListings({ listings }: Props) {
  const [showAll, setShowAll] = useState(false);

  if (!listings || listings.length === 0) return null;

  const sorted = [...listings].sort((a, b) => b.relevance_score - a.relevance_score);
  const displayed = showAll ? sorted : sorted.slice(0, 5);
  const hasMore = sorted.length > 5;

  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <h3 className="uppercase" style={{ fontSize: "11px", color: "#B0AA9E", letterSpacing: "2px" }}>
          SENASTE FÖRSÄLJNINGAR
        </h3>
        <span style={{ fontSize: "11px", color: "#B0AA9E" }}>Sorterat efter relevans</span>
      </div>

      <div className="rounded-xl overflow-hidden" style={{ border: "1px solid #E8E4DB" }}>
        {displayed.map((listing, i) => {
          const condition = getConditionTag(listing.title);
          const sourceLabel = SOURCE_LABELS[listing.source] ?? listing.source;
          const timeAgo = listing.date ? formatDate(listing.date) : null;

          return (
            <div
              key={i}
              className="flex items-center gap-3 px-3"
              style={{
                minHeight: "52px",
                paddingTop: "10px",
                paddingBottom: "10px",
                background: "#FFFFFF",
                borderBottom: i < displayed.length - 1 ? "1px solid #E8E4DB" : undefined,
              }}
            >
              <div className="flex-1 min-w-0">
                <p className="truncate" style={{ fontSize: "14px", color: "#2C2A25", fontWeight: 500 }}>
                  {listing.title}
                </p>
                <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                  <span style={{ fontSize: "11px", color: "#B0AA9E" }}>{sourceLabel}</span>
                  {timeAgo && <span style={{ fontSize: "11px", color: "#B0AA9E" }}>· {timeAgo}</span>}
                  {condition && (
                    <span
                      className="rounded"
                      style={{
                        fontSize: "11px",
                        color: "#8A8578",
                        background: "#EDEAE3",
                        border: "1px solid #E8E4DB",
                        padding: "0 4px",
                        borderRadius: "4px",
                      }}
                    >
                      {condition}
                    </span>
                  )}
                  <RelevanceDot score={listing.relevance_score} />
                </div>
              </div>
              <div className="flex items-center gap-2 shrink-0">
                <span style={{ fontSize: "14px", fontWeight: 600, color: "#2C2A25", fontVariantNumeric: "tabular-nums" }}>
                  {formatSEK(listing.price)}
                </span>
                {listing.url && (
                  <a href={listing.url} target="_blank" rel="noopener noreferrer" style={{ color: "#B0AA9E" }}>
                    <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {hasMore && !showAll && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-2 underline"
          style={{ fontSize: "12px", color: "#8A8578" }}
        >
          Visa alla {sorted.length} objekt →
        </button>
      )}
    </div>
  );
}
