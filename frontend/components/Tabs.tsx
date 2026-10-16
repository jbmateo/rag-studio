"use client";

import type { ReactNode } from "react";

export interface TabDef {
  id: string;
  label: string;
  panel: ReactNode;
}

export default function Tabs({ tabs, active, onChange }: { tabs: TabDef[]; active: string; onChange: (id: string) => void }) {
  const current = tabs.find((t) => t.id === active) ?? tabs[0];
  function onKeyDown(e: React.KeyboardEvent, i: number) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const next = tabs[(i + (e.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length];
    onChange(next.id);
    document.getElementById(`tab-${next.id}`)?.focus();
  }
  return (
    <div>
      <div role="tablist" aria-label="Workspace" className="flex gap-1 border-b border-slate-200">
        {tabs.map((t, i) => {
          const selected = t.id === current.id;
          return (
            <button key={t.id} id={`tab-${t.id}`} role="tab" type="button" aria-selected={selected}
              aria-controls={`panel-${t.id}`} tabIndex={selected ? 0 : -1}
              onClick={() => onChange(t.id)} onKeyDown={(e) => onKeyDown(e, i)}
              className={`-mb-px border-b-2 px-4 py-2 text-sm font-medium focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 ${
                selected ? "border-indigo-600 text-indigo-600" : "border-transparent text-slate-600 hover:text-slate-900"
              }`}>
              {t.label}
            </button>
          );
        })}
      </div>
      <div role="tabpanel" id={`panel-${current.id}`} aria-labelledby={`tab-${current.id}`} className="pt-6">
        {current.panel}
      </div>
    </div>
  );
}
