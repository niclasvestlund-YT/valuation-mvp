import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronRight } from "lucide-react";

interface Suggestion {
  name: string;
  context: string;
}

function getSuggestions(productName: string): Suggestion[] {
  // Find the last digit sequence in the name and suggest adjacent models
  const re = /(\d+)/g;
  let match: RegExpExecArray | null;
  let lastMatch: RegExpExecArray | null = null;
  while ((match = re.exec(productName)) !== null) {
    lastMatch = match;
  }
  if (!lastMatch) return [];

  const num = parseInt(lastMatch[1], 10);
  const before = productName.slice(0, lastMatch.index);
  const after = productName.slice(lastMatch.index + lastMatch[1].length);

  const suggestions: Suggestion[] = [];
  if (num > 1) suggestions.push({ name: `${before}${num - 1}${after}`, context: "Äldre modell" });
  suggestions.push({ name: `${before}${num + 1}${after}`, context: "Nyare modell" });
  if (suggestions.length < 3) suggestions.push({ name: `${before}${num + 2}${after}`, context: "Nyare modell" });
  return suggestions.slice(0, 3);
}

interface Props {
  open: boolean;
  productName: string;
  onSelect: (name: string) => void;
  onClose: () => void;
}

export function CorrectionSheet({ open, productName, onSelect, onClose }: Props) {
  const [inputValue, setInputValue] = useState("");
  const suggestions = getSuggestions(productName);

  const handleSubmitManual = () => {
    const name = inputValue.trim();
    if (!name) return;
    onSelect(name);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") handleSubmitManual();
  };

  return (
    <AnimatePresence>
      {open && (
        <>
          {/* Overlay */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(44,42,37,0.5)",
              zIndex: 50,
            }}
          />

          {/* Sheet */}
          <motion.div
            initial={{ y: "100%" }}
            animate={{ y: 0 }}
            exit={{ y: "100%" }}
            transition={{ type: "spring", damping: 32, stiffness: 320 }}
            style={{
              position: "fixed",
              bottom: 0,
              left: 0,
              right: 0,
              zIndex: 51,
              background: "#FFFFFF",
              borderRadius: "20px 20px 0 0",
              boxShadow: "0 -4px 24px rgba(0,0,0,0.08)",
              padding: "0 16px 40px",
              maxWidth: 520,
              margin: "0 auto",
            }}
          >
            {/* Handle */}
            <div style={{ display: "flex", justifyContent: "center", paddingTop: 12, paddingBottom: 20 }}>
              <div style={{ width: 36, height: 4, borderRadius: 2, background: "#E8E4DB" }} />
            </div>

            {/* Header */}
            <p style={{ fontSize: "1.25rem", fontWeight: 600, color: "#2C2A25", marginBottom: 4 }}>
              Rätta produkt
            </p>
            <p style={{ fontSize: "13px", color: "#8A8578", marginBottom: 24 }}>
              Vi identifierade: {productName}
            </p>

            {/* Suggestions */}
            {suggestions.length > 0 && (
              <div style={{ marginBottom: 24 }}>
                <p
                  className="uppercase"
                  style={{ fontSize: "11px", color: "#B0AA9E", letterSpacing: "2px", marginBottom: 8 }}
                >
                  MENADE DU KANSKE
                </p>
                <div className="rounded-xl overflow-hidden" style={{ border: "1px solid #E8E4DB" }}>
                  {suggestions.map((s, i) => (
                    <button
                      key={s.name}
                      onClick={() => onSelect(s.name)}
                      className="flex items-center justify-between w-full px-4 py-3"
                      style={{
                        background: "#FFFFFF",
                        borderBottom: i < suggestions.length - 1 ? "1px solid #E8E4DB" : undefined,
                        textAlign: "left",
                      }}
                    >
                      <div>
                        <p style={{ fontSize: "14px", color: "#2C2A25", fontWeight: 500 }}>{s.name}</p>
                        <p style={{ fontSize: "12px", color: "#8A8578", marginTop: 1 }}>{s.context}</p>
                      </div>
                      <ChevronRight style={{ width: 16, height: 16, color: "#B0AA9E", flexShrink: 0 }} />
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Manual input */}
            <div style={{ marginBottom: 20 }}>
              <p
                className="uppercase"
                style={{ fontSize: "11px", color: "#B0AA9E", letterSpacing: "2px", marginBottom: 8 }}
              >
                ELLER SKRIV SJÄLV
              </p>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={inputValue}
                  onChange={(e) => setInputValue(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={`T.ex. "${suggestions[0]?.name ?? "Sony WH-1000XM5"}"`}
                  style={{
                    flex: 1,
                    height: 44,
                    borderRadius: 12,
                    border: "1px solid #D5D0C5",
                    background: "#F7F5F0",
                    padding: "0 12px",
                    fontSize: "14px",
                    color: "#2C2A25",
                    outline: "none",
                  }}
                />
                <button
                  onClick={handleSubmitManual}
                  disabled={!inputValue.trim()}
                  style={{
                    height: 44,
                    paddingLeft: 16,
                    paddingRight: 16,
                    borderRadius: 12,
                    background: inputValue.trim() ? "#2C2A25" : "#D5D0C5",
                    color: "#F7F5F0",
                    fontSize: "14px",
                    fontWeight: 600,
                    flexShrink: 0,
                    transition: "background 0.15s",
                  }}
                >
                  Värdera
                </button>
              </div>
            </div>

            {/* Cancel */}
            <p className="text-center">
              <button
                onClick={onClose}
                className="underline"
                style={{ fontSize: "13px", color: "#8A8578" }}
              >
                Avbryt
              </button>
            </p>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
