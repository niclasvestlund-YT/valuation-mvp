import { useRef, useState, DragEvent, ChangeEvent } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Camera, Upload, X } from "lucide-react";

interface Props {
  onAnalyze: (files: File[]) => void;
  loading: boolean;
  loadingStep: string;
}

export function ImageUpload({ onAnalyze, loading, loadingStep }: Props) {
  const [files, setFiles] = useState<File[]>([]);
  const [previews, setPreviews] = useState<string[]>([]);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const cameraInputRef = useRef<HTMLInputElement>(null);

  const addFiles = (newFiles: FileList | File[]) => {
    const arr = Array.from(newFiles);
    const combined = [...files, ...arr].slice(0, 5);
    setFiles(combined);
    setPreviews((prev) => [...prev, ...arr.map((f) => URL.createObjectURL(f))].slice(0, 5));
  };

  const removeFile = (i: number) => {
    URL.revokeObjectURL(previews[i]);
    setFiles((p) => p.filter((_, j) => j !== i));
    setPreviews((p) => p.filter((_, j) => j !== i));
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files) addFiles(e.dataTransfer.files);
  };

  const onFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) addFiles(e.target.files);
    e.target.value = "";
  };

  return (
    <div className="space-y-4">
      {/* Drop zone */}
      <motion.div
        onClick={() => !loading && fileInputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        animate={{ borderColor: dragging ? "#8A8578" : "#D5D0C5" }}
        className="relative border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-colors"
        style={{ background: dragging ? "rgba(213,208,197,0.25)" : "#F7F5F0" }}
      >
        <div className="flex flex-col items-center gap-3">
          <div className="p-4 rounded-full bg-[#EDEAE3]">
            <Camera className="w-8 h-8 text-[#8A8578]" />
          </div>
          <div>
            <p className="text-[#2C2A25] font-medium">Ta ett foto</p>
            <p className="text-[#8A8578] text-sm mt-1">eller välj från biblioteket</p>
          </div>
          <p className="text-[#B0AA9E] text-xs">JPG, PNG, WebP · Max 10MB · Upp till 5 bilder</p>
        </div>
        <input ref={fileInputRef} type="file" accept="image/jpeg,image/png,image/webp" multiple className="hidden" onChange={onFileChange} />
      </motion.div>

      {/* Camera button */}
      <button
        onClick={() => cameraInputRef.current?.click()}
        disabled={loading}
        className="w-full flex items-center justify-center gap-2 py-3 rounded-xl border border-[#D5D0C5] bg-[#EDEAE3] hover:bg-[#E8E4DB] disabled:opacity-50 text-[#5C5850] transition-colors"
      >
        <Camera className="w-5 h-5 text-[#8A8578]" />
        Ta foto med kamera
      </button>
      <input ref={cameraInputRef} type="file" accept="image/*" capture="environment" className="hidden" onChange={onFileChange} />

      {/* Previews */}
      <AnimatePresence>
        {previews.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex gap-3 flex-wrap"
          >
            {previews.map((src, i) => (
              <motion.div key={src} initial={{ opacity: 0, scale: 0.8 }} animate={{ opacity: 1, scale: 1 }} className="relative group">
                <img src={src} alt="" className="w-20 h-20 object-cover rounded-xl border border-[#E8E4DB]" />
                <button
                  onClick={() => removeFile(i)}
                  className="absolute -top-2 -right-2 p-0.5 rounded-full bg-white border border-[#E8E4DB] text-[#8A8578] hover:text-[#c4432a] opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </motion.div>
            ))}
            {previews.length < 5 && (
              <button
                onClick={() => fileInputRef.current?.click()}
                className="w-20 h-20 flex items-center justify-center rounded-xl border-2 border-dashed border-[#D5D0C5] hover:border-[#8A8578] text-[#B0AA9E] transition-colors"
              >
                <Upload className="w-5 h-5" />
              </button>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Analyze button */}
      <button
        onClick={() => files.length > 0 && onAnalyze(files)}
        disabled={files.length === 0 || loading}
        className="w-full py-4 rounded-xl font-semibold text-lg transition-all duration-200 flex items-center justify-center gap-3"
        style={{
          background: files.length === 0 || loading ? "#EDEAE3" : "#2C2A25",
          color: files.length === 0 || loading ? "#B0AA9E" : "#F7F5F0",
        }}
      >
        {loading ? (
          <>
            <div className="w-5 h-5 border-2 rounded-full animate-spin" style={{ borderColor: "rgba(247,245,240,0.3)", borderTopColor: "#F7F5F0" }} />
            <span>{loadingStep}</span>
          </>
        ) : (
          "Värdera produkt"
        )}
      </button>
    </div>
  );
}
