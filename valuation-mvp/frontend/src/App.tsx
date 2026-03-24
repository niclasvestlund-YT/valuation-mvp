import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { LandingScreen } from "./components/LandingScreen";
import { ScanningScreen } from "./components/ScanningScreen";
import { ValuationResult } from "./components/ValuationResult";
import { valuateImages, revaluateByName } from "./api/valuate";
import { ValuationResponse, ScanEntry } from "./types";

type Screen = "landing" | "scanning" | "result";

const fadeSlide = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -6 },
  transition: { duration: 0.22 },
};

export default function App() {
  const [screen, setScreen] = useState<Screen>("landing");
  const [result, setResult] = useState<ValuationResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [thumbnailUrl, setThumbnailUrl] = useState<string | null>(null);
  const [history, setHistory] = useState<ScanEntry[]>([]);
  const [scanProgress, setScanProgress] = useState(0);
  const [isCorrected, setIsCorrected] = useState(false);
  const [previousValue, setPreviousValue] = useState<number | null>(null);

  const handleAnalyze = async (files: File[]) => {
    // Create thumbnail from first file
    if (thumbnailUrl) URL.revokeObjectURL(thumbnailUrl);
    const thumb = files[0] ? URL.createObjectURL(files[0]) : null;
    setThumbnailUrl(thumb);

    setResult(null);
    setError(null);
    setScanProgress(0);
    setScreen("scanning");

    // Advance steps based on realistic timing — steps snap to done when API returns
    const t1 = setTimeout(() => setScanProgress((p) => Math.max(p, 1)), 2800);
    const t2 = setTimeout(() => setScanProgress((p) => Math.max(p, 2)), 6000);

    try {
      const response = await valuateImages(files);
      clearTimeout(t1);
      clearTimeout(t2);

      // Complete all steps, brief pause so user sees the done state
      setScanProgress(3);
      setResult(response);

      setHistory((prev) =>
        [
          {
            product_name: response.product_name,
            estimated_value: response.estimated_value,
            thumbnailUrl: thumb,
            timestamp: new Date(),
            result: response,
          },
          ...prev,
        ].slice(0, 3),
      );

      setTimeout(() => setScreen("result"), 500);
    } catch (e) {
      clearTimeout(t1);
      clearTimeout(t2);
      setError(e instanceof Error ? e.message : "Något gick fel. Försök igen.");
      setScreen("landing");
    }
  };

  const handleCorrect = async (productName: string) => {
    const oldValue = result?.estimated_value ?? null;
    setPreviousValue(oldValue);
    setIsCorrected(true);
    setError(null);
    setScanProgress(1); // step 0 already "done" — product is known
    setScreen("scanning");

    const t1 = setTimeout(() => setScanProgress((p) => Math.max(p, 2)), 1500);

    try {
      const response = await revaluateByName(productName);
      clearTimeout(t1);
      setScanProgress(3);
      setResult(response);

      setHistory((prev) =>
        [
          {
            product_name: response.product_name,
            estimated_value: response.estimated_value,
            thumbnailUrl,
            timestamp: new Date(),
            result: response,
          },
          ...prev,
        ].slice(0, 3),
      );

      setTimeout(() => setScreen("result"), 400);
    } catch (e) {
      clearTimeout(t1);
      setError(e instanceof Error ? e.message : "Något gick fel. Försök igen.");
      setScreen("landing");
    }
  };

  const handleReset = () => {
    setResult(null);
    setError(null);
    setIsCorrected(false);
    setPreviousValue(null);
    setScreen("landing");
  };

  const handleOpenHistory = (entry: ScanEntry) => {
    setResult(entry.result);
    setThumbnailUrl(entry.thumbnailUrl);
    setIsCorrected(false);
    setPreviousValue(null);
    setScreen("result");
  };

  return (
    <div className="min-h-screen bg-[#F7F5F0] text-[#2C2A25]">
      <div className="relative max-w-[520px] mx-auto px-4 py-8">

        {/* Header — always visible */}
        <motion.h1
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="text-center font-bold text-[#2C2A25] mb-6"
          style={{ fontSize: "1.875rem", letterSpacing: "-0.5px" }}
        >
          VÄRDEKOLL
        </motion.h1>

        {/* Error banner */}
        <AnimatePresence>
          {error && (
            <motion.div
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="mb-4 p-3 rounded-xl border text-sm"
              style={{
                background: "rgba(196,67,42,0.08)",
                borderColor: "rgba(196,67,42,0.25)",
                color: "#c4432a",
              }}
            >
              {error}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Screen router */}
        <AnimatePresence mode="wait">
          {screen === "landing" && (
            <motion.div key="landing" {...fadeSlide}>
              <LandingScreen
                onAnalyze={handleAnalyze}
                history={history}
                onOpenHistory={handleOpenHistory}
              />
            </motion.div>
          )}

          {screen === "scanning" && (
            <motion.div key="scanning" {...fadeSlide}>
              <ScanningScreen thumbnailUrl={thumbnailUrl} progress={scanProgress} />
            </motion.div>
          )}

          {screen === "result" && result && (
            <motion.div key="result" {...fadeSlide}>
              <ValuationResult
                result={result}
                thumbnailUrl={thumbnailUrl}
                onReset={handleReset}
                onCorrect={handleCorrect}
                isCorrected={isCorrected}
                previousValue={previousValue}
              />
            </motion.div>
          )}
        </AnimatePresence>

      </div>
    </div>
  );
}
