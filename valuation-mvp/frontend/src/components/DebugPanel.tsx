import { useState } from "react";
import { ChevronDown, ChevronRight, Bug } from "lucide-react";

interface Props {
  data: Record<string, unknown>;
}

export function DebugPanel({ data }: Props) {
  const [open, setOpen] = useState(false);

  return (
    <div className="rounded-xl border border-slate-700 overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center gap-2 px-4 py-3 bg-slate-800 hover:bg-slate-750 text-slate-400 text-sm transition-colors"
      >
        <Bug className="w-4 h-4" />
        <span className="flex-1 text-left font-medium">Debug info</span>
        {open ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
      </button>
      {open && (
        <div className="bg-slate-900 p-4 overflow-auto max-h-96">
          <pre className="text-xs text-slate-300 whitespace-pre-wrap break-all font-mono">
            {JSON.stringify(data, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}
