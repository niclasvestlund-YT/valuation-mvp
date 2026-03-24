import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { AlertTriangle, CheckCircle, XCircle, AlertCircle, Pencil, ChevronRight } from "lucide-react";
import { ValuationResponse } from "../types";
import { MarketListings } from "./MarketListings";
import { ReasoningPanel } from "./ReasoningPanel";
import { ValueRetentionBar } from "./ValueRetentionBar";
import { PriceDistributionPlot } from "./PriceDistributionPlot";
import { SourceBadge } from "./SourceBadge";
import { AmbiguousModelState } from "./AmbiguousModelState";
import { InsufficientEvidenceState } from "./InsufficientEvidenceState";
import { CorrectionSheet } from "./CorrectionSheet";

// ── helpers ──────────────────────────────────────────────────────────────────

function roundToNearest50(v: number) {
  return Math.round(v / 50) * 50;
}

function formatSEK(v: number) {
  return new Intl.NumberFormat("sv-SE", { style: "currency", currency: "SEK", maximumFractionDigits: 0 }).format(v);
}

function formatKr(v: number) {
  return new Intl.NumberFormat("sv-SE").format(Math.round(v));
}

function confidenceLabel(c: number): string {
  if (c >= 0.7) return "Hög konfidens";
  if (c >= 0.4) return "Medium konfidens";
  return "Låg konfidens";
}

function formatTimestamp(): string {
  return new Date().toLocaleDateString("sv-SE", { day: "numeric", month: "long", year: "numeric" });
}

// ── status config ─────────────────────────────────────────────────────────────

const STATUS_CONFIG = {
  ok: { label: "Tillförlitlig", style: { background: "rgba(52,168,115,0.1)", color: "#34a873", borderColor: "rgba(52,168,115,0.3)" }, icon: CheckCircle },
  ambiguous_model: { label: "Oklar modell", style: { background: "rgba(212,160,23,0.1)", color: "#d4a017", borderColor: "rgba(212,160,23,0.3)" }, icon: AlertTriangle },
  insufficient_evidence: { label: "Otillräcklig data", style: { background: "rgba(196,67,42,0.1)", color: "#c4432a", borderColor: "rgba(196,67,42,0.3)" }, icon: XCircle },
  estimated_from_depreciation: { label: "Modellbaserat estimat", style: { background: "rgba(212,160,23,0.1)", color: "#d4a017", borderColor: "rgba(212,160,23,0.3)" }, icon: AlertCircle },
  degraded: { label: "Begränsad data", style: { background: "rgba(212,160,23,0.1)", color: "#d4a017", borderColor: "rgba(212,160,23,0.3)" }, icon: AlertCircle },
  error: { label: "Fel", style: { background: "rgba(196,67,42,0.1)", color: "#c4432a", borderColor: "rgba(196,67,42,0.3)" }, icon: XCircle },
};

// ── component ─────────────────────────────────────────────────────────────────

interface Props {
  result: ValuationResponse;
  thumbnailUrl: string | null;
  onReset: () => void;
  onCorrect: (productName: string) => void;
  isCorrected: boolean;
  previousValue: number | null;
}

export function ValuationResult({ result, thumbnailUrl, onReset, onCorrect, isCorrected, previousValue }: Props) {
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [feedback, setFeedback] = useState<"yes" | "no" | null>(null);
  const [shared, setShared] = useState(false);
  const [forceShowEstimate, setForceShowEstimate] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);

  // ── Delegate to error-state screens ─────────────────────────────────────
  if (!forceShowEstimate) {
    if (result.status === "ambiguous_model") {
      return (
        <AmbiguousModelState
          result={result}
          thumbnailUrl={thumbnailUrl}
          onReset={onReset}
          onForceShow={() => setForceShowEstimate(true)}
        />
      );
    }
    if (result.status === "insufficient_evidence") {
      return (
        <InsufficientEvidenceState
          result={result}
          thumbnailUrl={thumbnailUrl}
          onReset={onReset}
          onForceShow={() => setForceShowEstimate(true)}
        />
      );
    }
  }

  const handleCorrectSelect = (name: string) => {
    setSheetOpen(false);
    onCorrect(name);
  };

  const cfg = STATUS_CONFIG[result.status];
  const StatusIcon = cfg.icon;

  const hasEstimate = result.estimated_value !== null;
  const hasRetentionBar = hasEstimate && result.new_price !== null && result.new_price > 0;

  // Combined info line parts
  const infoParts: string[] = [];
  if (result.value_range) {
    infoParts.push(`${formatKr(result.value_range[0])} – ${formatKr(result.value_range[1])} kr`);
  }
  if (result.confidence !== null) {
    infoParts.push(confidenceLabel(result.confidence));
  }
  if (result.comparables_used > 0) {
    infoParts.push(`${result.comparables_used} ${result.comparables_used === 1 ? "källa" : "källor"}`);
  }
  const infoLine = infoParts.join(" · ");

  // Source counts for chips
  const sourceCounts = result.market_listings.reduce<Record<string, number>>((acc, l) => {
    acc[l.source] = (acc[l.source] ?? 0) + 1;
    return acc;
  }, {});

  const traderaUrl = `https://www.tradera.com/search?q=${encodeURIComponent(result.product_name ?? "")}`;
  const blocketUrl = `https://www.blocket.se/annonser/hela_sverige?q=${encodeURIComponent(result.product_name ?? "")}`;

  const handleShare = async () => {
    const name = result.product_name ?? "Produkten";
    const value = hasEstimate ? formatSEK(roundToNearest50(result.estimated_value!)) : "okänt värde";
    const text = `${name} är värd ca ${value} i andrahand (Värdekoll)`;
    try {
      if (navigator.share) {
        await navigator.share({ text });
      } else {
        await navigator.clipboard.writeText(text);
        setShared(true);
        setTimeout(() => setShared(false), 2000);
      }
    } catch { /* ignore */ }
  };

  return (
    <div className="space-y-5">

      {/* ── Warnings ──────────────────────────────────────────────────────── */}
      {result.warnings.length > 0 && (
        <div className="space-y-2">
          {result.warnings.map((w, i) => (
            <div
              key={i}
              className="flex items-start gap-2 p-3 rounded-xl border"
              style={{ background: "rgba(212,160,23,0.08)", borderColor: "rgba(212,160,23,0.25)" }}
            >
              <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" style={{ color: "#d4a017" }} />
              <p style={{ fontSize: "13px", color: "#5C5850" }}>{w}</p>
            </div>
          ))}
        </div>
      )}

      {/* ── Product row ───────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        {thumbnailUrl ? (
          <img
            src={thumbnailUrl}
            alt=""
            className="object-cover shrink-0"
            style={{ width: 52, height: 52, borderRadius: 12, border: "1px solid #E8E4DB" }}
          />
        ) : (
          <div
            className="shrink-0 flex items-center justify-center"
            style={{ width: 52, height: 52, borderRadius: 12, background: "#EDEAE3", border: "1px solid #E8E4DB" }}
          >
            <span style={{ fontSize: "11px", color: "#B0AA9E" }}>foto</span>
          </div>
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p style={{ fontSize: "18px", fontWeight: 600, color: "#2C2A25", lineHeight: "1.375" }}>
              {result.product_name ?? "Okänd produkt"}
            </p>
            {isCorrected && (
              <span
                style={{
                  fontSize: "11px",
                  fontWeight: 500,
                  color: "#5C5850",
                  background: "#EDEAE3",
                  padding: "2px 7px",
                  borderRadius: 6,
                  whiteSpace: "nowrap",
                }}
              >
                Rättad
              </span>
            )}
          </div>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span
              className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium border"
              style={cfg.style}
            >
              <StatusIcon className="w-3 h-3" />
              {cfg.label}
            </span>
            <span style={{ fontSize: "11px", color: "#B0AA9E" }}>Identifierad ✓</span>
          </div>
        </div>
        <button
          onClick={() => setSheetOpen(true)}
          className="shrink-0 p-1.5"
          style={{ color: "#B0AA9E" }}
          aria-label="Rätta produkt"
        >
          <Pencil className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* ── Change indicator (after correction) ───────────────────────────── */}
      {isCorrected && previousValue !== null && hasEstimate && (
        <div className="flex items-center justify-center gap-2">
          <span style={{ fontSize: "13px", color: "#B0AA9E", textDecoration: "line-through" }}>
            {formatSEK(roundToNearest50(previousValue))}
          </span>
          <span style={{ fontSize: "13px", color: "#B0AA9E" }}>→</span>
          <span style={{ fontSize: "13px", fontWeight: 600, color: "#2C2A25" }}>
            {formatSEK(roundToNearest50(result.estimated_value!))}
          </span>
          {(() => {
            const delta = result.estimated_value! - previousValue;
            const sign = delta >= 0 ? "+" : "";
            const color = delta >= 0 ? "#34a873" : "#c4432a";
            return (
              <span
                style={{
                  fontSize: "12px",
                  fontWeight: 500,
                  color,
                  background: delta >= 0 ? "rgba(52,168,115,0.1)" : "rgba(196,67,42,0.1)",
                  padding: "2px 8px",
                  borderRadius: 20,
                }}
              >
                {sign}{formatKr(Math.round(delta / 50) * 50)} kr
              </span>
            );
          })()}
        </div>
      )}

      {/* ── Correction sheet ──────────────────────────────────────────────── */}
      <CorrectionSheet
        open={sheetOpen}
        productName={result.product_name ?? ""}
        onSelect={handleCorrectSelect}
        onClose={() => setSheetOpen(false)}
      />

      {/* ── Estimate (hero — no card) ──────────────────────────────────────── */}
      {hasEstimate ? (
        <div>
          <p className="uppercase mb-1" style={{ fontSize: "11px", color: "#B0AA9E", letterSpacing: "2px" }}>
            BEGAGNAT MARKNADSVÄRDE
          </p>
          <p style={{ fontSize: "3.25rem", fontWeight: 700, color: "#2C2A25", lineHeight: 1, letterSpacing: "-2px" }}>
            {formatSEK(roundToNearest50(result.estimated_value!))}
          </p>
          {infoLine && (
            <p className="mt-2" style={{ fontSize: "14px", color: "#8A8578" }}>
              <strong style={{ color: "#5C5850" }}>{infoParts[0]}</strong>
              {infoParts.length > 1 && ` · ${infoParts.slice(1).join(" · ")}`}
            </p>
          )}
        </div>
      ) : (
        <div className="py-4 rounded-xl text-center" style={{ background: "#EDEAE3" }}>
          <p style={{ fontSize: "14px", color: "#8A8578" }}>
            {result.status === "ambiguous_model"
              ? "Produkten kunde inte identifieras tillräckligt säkert. Försök med en tydligare bild."
              : "Tillräcklig data saknas för att ge ett estimat."}
          </p>
        </div>
      )}

      {/* ── Value retention bar ───────────────────────────────────────────── */}
      {hasRetentionBar && (
        <ValueRetentionBar
          newPrice={result.new_price!}
          estimatedValue={result.estimated_value!}
          newPriceSource={result.new_price_source}
        />
      )}

      {/* ── Action buttons ────────────────────────────────────────────────── */}
      <div className="flex gap-3">
        <button
          onClick={onReset}
          className="flex-1 flex items-center justify-center"
          style={{
            height: 48,
            borderRadius: 14,
            background: "#2C2A25",
            color: "#F7F5F0",
            fontSize: "14px",
            fontWeight: 600,
          }}
        >
          Scanna ny
        </button>
        <button
          onClick={() => setShowAdvanced((v) => !v)}
          className="flex-1 flex items-center justify-center border"
          style={{
            height: 48,
            borderRadius: 14,
            borderColor: "#D5D0C5",
            color: "#5C5850",
            fontSize: "14px",
            fontWeight: 500,
          }}
        >
          {showAdvanced ? "Dölj detaljer" : "Se detaljer"}
        </button>
      </div>

      {/* ── Quick links ───────────────────────────────────────────────────── */}
      <div className="flex items-center justify-center gap-3">
        <a
          href={traderaUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="underline"
          style={{ fontSize: "11px", color: "#8A8578" }}
        >
          Sälj på Tradera
        </a>
        <span style={{ fontSize: "11px", color: "#B0AA9E" }}>·</span>
        <button
          onClick={handleShare}
          className="underline"
          style={{ fontSize: "11px", color: "#8A8578" }}
        >
          {shared ? "Kopierat!" : "Dela estimat"}
        </button>
      </div>

      {/* ── Timestamp ─────────────────────────────────────────────────────── */}
      <p className="text-center" style={{ fontSize: "11px", color: "#B0AA9E" }}>
        Estimerat idag {formatTimestamp()}
      </p>

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* ── Advanced View ─────────────────────────────────────────────────── */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      <AnimatePresence>
        {showAdvanced && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
            style={{ overflow: "hidden" }}
          >
            <div className="space-y-6 pt-2">
              <div style={{ height: 1, background: "#E8E4DB" }} />

              {/* Source chips */}
              {Object.keys(sourceCounts).length > 0 && (
                <div>
                  <h3 className="uppercase mb-2" style={{ fontSize: "11px", color: "#B0AA9E", letterSpacing: "2px" }}>
                    KÄLLOR
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(sourceCounts).map(([source, count]) => (
                      <SourceBadge key={source} source={source} count={count} />
                    ))}
                  </div>
                </div>
              )}

              {/* Price distribution dot plot */}
              <PriceDistributionPlot
                listings={result.market_listings}
                estimate={result.estimated_value}
              />

              {/* Comparable listings */}
              {result.market_listings.length > 0 && (
                <MarketListings listings={result.market_listings} />
              )}

              {/* Reasoning blockquote */}
              {result.reasoning.length > 0 && (
                <ReasoningPanel steps={result.reasoning} />
              )}

              {/* Feedback */}
              <div className="rounded-xl p-4" style={{ background: "#EDEAE3" }}>
                {feedback ? (
                  <p style={{ fontSize: "14px", color: "#8A8578" }}>Tack för din feedback!</p>
                ) : (
                  <>
                    <p style={{ fontSize: "13px", fontWeight: 500, color: "#2C2A25" }}>
                      Identifierade vi rätt produkt?
                    </p>
                    <div className="flex gap-2 mt-3">
                      <button
                        onClick={() => setFeedback("yes")}
                        className="flex-1 py-2 rounded-xl border"
                        style={{ fontSize: "13px", color: "#5C5850", borderColor: "#D5D0C5", background: "#FFFFFF" }}
                      >
                        Ja, stämmer
                      </button>
                      <button
                        onClick={() => setSheetOpen(true)}
                        className="flex-1 py-2 rounded-xl border"
                        style={{ fontSize: "13px", color: "#5C5850", borderColor: "#D5D0C5", background: "#FFFFFF" }}
                      >
                        Nej, fel modell
                      </button>
                    </div>
                  </>
                )}
              </div>

              {/* Next steps */}
              <div>
                <h3 className="uppercase mb-2" style={{ fontSize: "11px", color: "#B0AA9E", letterSpacing: "2px" }}>
                  NÄSTA STEG
                </h3>
                <div className="rounded-xl overflow-hidden" style={{ border: "1px solid #E8E4DB" }}>
                  {[
                    { label: "Sälj på Tradera", url: traderaUrl },
                    { label: "Lägg upp på Blocket", url: blocketUrl },
                  ].map((item, i, arr) => (
                    <a
                      key={item.label}
                      href={item.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center justify-between px-4 py-3"
                      style={{
                        background: "#FFFFFF",
                        borderBottom: i < arr.length - 1 ? "1px solid #E8E4DB" : undefined,
                        color: "#2C2A25",
                        fontSize: "14px",
                      }}
                    >
                      {item.label}
                      <ChevronRight className="w-4 h-4" style={{ color: "#B0AA9E" }} />
                    </a>
                  ))}
                  <button
                    onClick={handleShare}
                    className="flex items-center justify-between px-4 py-3 w-full"
                    style={{ background: "#FFFFFF", color: "#2C2A25", fontSize: "14px" }}
                  >
                    Dela estimat
                    <ChevronRight className="w-4 h-4" style={{ color: "#B0AA9E" }} />
                  </button>
                </div>
              </div>

            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
