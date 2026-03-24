import { MarketListing } from "../types";

interface Props {
  listings: MarketListing[];
  estimate: number | null;
}

function formatK(v: number) {
  return v >= 1000 ? `${(Math.round(v / 100) / 10).toFixed(1).replace(".0", "")}k` : `${Math.round(v)}`;
}

export function PriceDistributionPlot({ listings, estimate }: Props) {
  if (listings.length < 3) return null;

  const prices = listings.map((l) => l.price);
  const min = Math.min(...prices);
  const max = Math.max(...prices);
  if (max === min) return null;

  const sorted = [...prices].sort((a, b) => a - b);
  const q1 = sorted[Math.floor(sorted.length * 0.25)];
  const q3 = sorted[Math.floor(sorted.length * 0.75)];

  const W = 300;
  const PAD = 24;
  const INNER = W - PAD * 2;
  const xOf = (p: number) => PAD + ((p - min) / (max - min)) * INNER;

  const estimateInRange = estimate !== null && estimate >= min && estimate <= max;

  return (
    <div>
      <h3
        className="uppercase mb-3"
        style={{ fontSize: "11px", color: "#B0AA9E", letterSpacing: "2px" }}
      >
        PRISFÖRDELNING BLAND JÄMFÖRELSEOBJEKT
      </h3>
      <div className="rounded-xl p-4" style={{ background: "#EDEAE3", border: "1px solid #E8E4DB" }}>
        <svg viewBox={`0 0 ${W} 58`} className="w-full" style={{ overflow: "visible" }}>
          {/* Axis line */}
          <line
            x1={PAD} y1={28} x2={W - PAD} y2={28}
            stroke="#D5D0C5" strokeWidth="3" strokeLinecap="round"
          />

          {/* IQR band */}
          <rect
            x={xOf(q1)}
            y={22}
            width={Math.max(xOf(q3) - xOf(q1), 6)}
            height={12}
            rx={3}
            fill="#B0AA9E"
            opacity={0.5}
          />

          {/* Dots — all listings */}
          {listings.map((l, i) => {
            const inIQR = l.price >= q1 && l.price <= q3;
            return (
              <circle
                key={i}
                cx={xOf(l.price)}
                cy={28}
                r={3.5}
                fill={inIQR ? "#8A8578" : "#B0AA9E"}
              />
            );
          })}

          {/* Estimate marker */}
          {estimateInRange && (
            <>
              <line
                x1={xOf(estimate!)}
                y1={8}
                x2={xOf(estimate!)}
                y2={50}
                stroke="#2C2A25"
                strokeWidth="2"
                strokeLinecap="round"
              />
              <text
                x={xOf(estimate!)}
                y={6}
                textAnchor="middle"
                fill="#2C2A25"
                fontSize="9"
                fontWeight="600"
                dominantBaseline="auto"
              >
                {formatK(estimate!)}
              </text>
            </>
          )}

          {/* Min label */}
          <text x={PAD} y={52} fill="#B0AA9E" fontSize="9" textAnchor="middle">
            {formatK(min)}
          </text>

          {/* Max label */}
          <text x={W - PAD} y={52} fill="#B0AA9E" fontSize="9" textAnchor="middle">
            {formatK(max)}
          </text>
        </svg>
        <p className="text-center mt-1" style={{ fontSize: "11px", color: "#B0AA9E" }}>
          ● i mitten = vanligast
        </p>
      </div>
    </div>
  );
}
