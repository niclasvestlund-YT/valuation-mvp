import { Check } from "lucide-react";

const STEPS = [
  { label: "Analyserar bild", active: "Identifierar produkt med bildanalys...", done: "Produkt identifierad" },
  { label: "Söker marknadsdata", active: "Hämtar priser från Tradera och Google...", done: "Marknadsdata hämtad" },
  { label: "Beräknar värde", active: "Väger samman data och estimerar värde...", done: "Estimat klart" },
];

function StepIcon({ state }: { state: "done" | "active" | "waiting" }) {
  if (state === "done") {
    return (
      <div
        className="flex items-center justify-center shrink-0"
        style={{ width: 24, height: 24, borderRadius: "50%", background: "#2C2A25" }}
      >
        <Check style={{ width: 13, height: 13, color: "#F7F5F0", strokeWidth: 2.5 }} />
      </div>
    );
  }
  if (state === "active") {
    return (
      <div
        className="flex items-center justify-center shrink-0"
        style={{ width: 24, height: 24, borderRadius: "50%", border: "2px solid #2C2A25" }}
      >
        <div style={{ width: 7, height: 7, borderRadius: "50%", background: "#2C2A25" }} />
      </div>
    );
  }
  return (
    <div
      className="shrink-0"
      style={{ width: 24, height: 24, borderRadius: "50%", border: "2px solid #D5D0C5" }}
    />
  );
}

interface Props {
  thumbnailUrl: string | null;
  /** 0 = step 1 active · 1 = step 2 active · 2 = step 3 active · 3 = all done */
  progress: number;
}

export function ScanningScreen({ thumbnailUrl, progress }: Props) {
  const steps = STEPS.map((s, i) => ({
    ...s,
    state: (progress > i ? "done" : progress === i ? "active" : "waiting") as "done" | "active" | "waiting",
  }));

  return (
    <div className="space-y-6">
      {/* Photo */}
      <div className="relative overflow-hidden" style={{ borderRadius: 16, height: 220 }}>
        {thumbnailUrl ? (
          <img src={thumbnailUrl} alt="Ditt foto" className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full" style={{ background: "#EDEAE3" }} />
        )}
        {/* label overlay — intentional on-image gradient per spec */}
        <div
          className="absolute inset-x-0 bottom-0 flex items-end"
          style={{
            height: 64,
            background: "linear-gradient(transparent, rgba(44,42,37,0.55))",
            paddingLeft: 12,
            paddingBottom: 10,
          }}
        >
          <p style={{ fontSize: "11px", color: "rgba(247,245,240,0.85)", fontWeight: 500 }}>Ditt foto</p>
        </div>
      </div>

      {/* Steps */}
      <div className="space-y-4">
        {steps.map((step, i) => (
          <div key={i} className="flex items-start gap-3">
            <div style={{ marginTop: 1 }}>
              <StepIcon state={step.state} />
            </div>
            <div>
              <p
                style={{
                  fontSize: "14px",
                  fontWeight: 500,
                  color: step.state === "waiting" ? "#B0AA9E" : "#2C2A25",
                }}
              >
                {step.label}
              </p>
              {step.state !== "waiting" && (
                <p style={{ fontSize: "12px", color: "#8A8578", marginTop: 2 }}>
                  {step.state === "done" ? step.done : step.active}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
