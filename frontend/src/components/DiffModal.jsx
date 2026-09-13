import React, { useState } from 'react';
import { X, ArrowRight, Code2, Columns } from 'lucide-react';

export default function DiffModal({ event, onClose }) {
  const [viewMode, setViewMode] = useState('visual'); // 'visual' | 'json'

  if (!event) return null;

  const isUpdate = event.change_type === 'UPDATE';
  const diffEntries = isUpdate && event.diff_data ? Object.entries(event.diff_data) : [];

  const formatValue = (val) => {
    if (val === null || val === undefined) return <span className="text-slate-500 italic">null</span>;
    if (typeof val === 'object') return JSON.stringify(val);
    if (typeof val === 'number') return val.toLocaleString();
    return String(val);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fadeIn">
      <div className="relative w-full max-w-2xl bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700 bg-slate-800/80">
          <div className="flex items-center space-x-3">
            <span
              className={`px-2.5 py-1 text-xs font-semibold rounded-full uppercase tracking-wider ${
                isUpdate
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                  : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
              }`}
            >
              {event.change_type}
            </span>
            <span className="text-lg font-bold text-white tracking-tight">{event.sku}</span>
            <span className="text-xs px-2 py-0.5 rounded bg-slate-700 text-slate-300">
              Source: {event.source}
            </span>
          </div>

          <div className="flex items-center space-x-2">
            <div className="flex bg-slate-900 rounded-lg p-0.5 border border-slate-700 text-xs">
              <button
                onClick={() => setViewMode('visual')}
                className={`flex items-center space-x-1 px-2.5 py-1 rounded-md transition ${
                  viewMode === 'visual' ? 'bg-blue-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Columns className="w-3.5 h-3.5" />
                <span>Visual</span>
              </button>
              <button
                onClick={() => setViewMode('json')}
                className={`flex items-center space-x-1 px-2.5 py-1 rounded-md transition ${
                  viewMode === 'json' ? 'bg-blue-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Code2 className="w-3.5 h-3.5" />
                <span>Raw JSON</span>
              </button>
            </div>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-700 transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto space-y-4">
          <div className="grid grid-cols-2 gap-4 text-xs text-slate-400 bg-slate-900/50 p-3 rounded-xl border border-slate-750">
            <div>
              <span className="text-slate-500 block">Event ID:</span>
              <span className="font-mono text-slate-200">{event.id}</span>
            </div>
            <div>
              <span className="text-slate-500 block">Ingested At:</span>
              <span className="font-mono text-slate-200">
                {new Date(event.ingested_at).toLocaleString()}
              </span>
            </div>
            <div className="truncate">
              <span className="text-slate-500 block">New SHA-256 Hash:</span>
              <span className="font-mono text-blue-400 text-[11px]">{event.new_hash}</span>
            </div>
            {event.old_hash && (
              <div className="truncate">
                <span className="text-slate-500 block">Old SHA-256 Hash:</span>
                <span className="font-mono text-slate-400 text-[11px]">{event.old_hash}</span>
              </div>
            )}
          </div>

          {viewMode === 'visual' ? (
            isUpdate ? (
              <div className="space-y-3">
                <h4 className="text-sm font-semibold text-slate-200 flex items-center space-x-2">
                  <span>Detected Field Changes</span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-slate-700 text-slate-300">
                    {diffEntries.length} field(s)
                  </span>
                </h4>
                <div className="border border-slate-700 rounded-xl overflow-hidden divide-y divide-slate-700/60 bg-slate-900/40">
                  {diffEntries.map(([field, delta]) => (
                    <div key={field} className="p-3.5 space-y-2">
                      <div className="text-xs font-mono font-bold text-blue-300 uppercase tracking-wider">
                        {field}
                      </div>
                      <div className="grid grid-cols-11 gap-2 items-center text-xs">
                        <div className="col-span-5 p-2 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-300 break-all font-mono line-through">
                          {formatValue(delta.old)}
                        </div>
                        <div className="col-span-1 flex justify-center text-slate-500">
                          <ArrowRight className="w-4 h-4" />
                        </div>
                        <div className="col-span-5 p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 break-all font-mono font-medium">
                          {formatValue(delta.new)}
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <h4 className="text-sm font-semibold text-slate-200">Initial Product Payload (INSERT)</h4>
                <pre className="p-4 rounded-xl bg-slate-900 text-slate-300 text-xs font-mono overflow-x-auto border border-slate-750">
                  {JSON.stringify(event.diff_data, null, 2)}
                </pre>
              </div>
            )
          ) : (
            <pre className="p-4 rounded-xl bg-slate-900 text-slate-300 text-xs font-mono overflow-x-auto border border-slate-750">
              {JSON.stringify(event, null, 2)}
            </pre>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 border-t border-slate-700 bg-slate-800/80 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white text-xs font-semibold rounded-lg transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
