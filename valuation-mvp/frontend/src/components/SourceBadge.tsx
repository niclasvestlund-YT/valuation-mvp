const SOURCE_LABELS: Record<string, string> = {
  tradera: "Tradera",
  blocket: "Blocket",
  facebook_marketplace: "Facebook",
  google_shopping: "Google Shopping",
  prisjakt: "Prisjakt",
};

interface Props {
  source: string;
  count?: number;
}

export function SourceBadge({ source, count }: Props) {
  const label = SOURCE_LABELS[source] ?? source;
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border"
      style={{ background: "#EDEAE3", color: "#5C5850", borderColor: "#E8E4DB" }}
    >
      {label}
      {count !== undefined && <span style={{ color: "#8A8578" }}>×{count}</span>}
    </span>
  );
}
