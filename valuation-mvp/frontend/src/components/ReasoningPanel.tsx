import { ReasoningStep } from "../types";

interface Props {
  steps: ReasoningStep[];
}

export function ReasoningPanel({ steps }: Props) {
  if (!steps || steps.length === 0) return null;

  return (
    <div className="space-y-4">
      <h3 className="uppercase" style={{ fontSize: "11px", color: "#B0AA9E", letterSpacing: "2px" }}>
        SÅ RÄKNADE VI
      </h3>
      <div className="space-y-4">
        {steps.map((step, i) => (
          <div key={i} style={{ borderLeft: "2px solid #D5D0C5", paddingLeft: "16px" }}>
            <p
              className="uppercase mb-1"
              style={{ fontSize: "11px", color: "#8A8578", letterSpacing: "1px", fontWeight: 600 }}
            >
              {step.step}
            </p>
            <p style={{ fontSize: "14px", color: "#5C5850", lineHeight: "1.65", maxWidth: "65ch" }}>
              {step.description}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}
