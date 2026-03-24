function formatSEK(v: number) {
  return new Intl.NumberFormat("sv-SE", { style: "currency", currency: "SEK", maximumFractionDigits: 0 }).format(v);
}

interface Props {
  newPrice: number;
  estimatedValue: number;
  newPriceSource: string | null;
}

export function ValueRetentionBar({ newPrice, estimatedValue, newPriceSource }: Props) {
  const retainedPct = Math.min(Math.round((estimatedValue / newPrice) * 100), 100);

  return (
    <div className="rounded-[14px]" style={{ background: "#EDEAE3", padding: "14px 16px" }}>
      <div className="flex items-center justify-between mb-2">
        <span style={{ fontSize: "14px", color: "#8A8578" }}>
          Nypris {newPriceSource ? `(${newPriceSource}) ` : ""}{formatSEK(newPrice)} → behåller
        </span>
        <span style={{ fontSize: "15px", fontWeight: 600, color: "#2C2A25" }}>{retainedPct}%</span>
      </div>
      <div className="rounded-full overflow-hidden flex" style={{ height: "6px", background: "#E8E4DB" }}>
        <div
          className="h-full rounded-full"
          style={{ width: `${retainedPct}%`, background: "#2C2A25" }}
        />
      </div>
    </div>
  );
}
