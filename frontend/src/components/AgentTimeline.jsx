import React from 'react';
import { 
  Activity, 
  Cpu, 
  Clock, 
  CheckCircle2, 
  AlertTriangle, 
  ShieldCheck, 
  Terminal,
  ArrowRight
} from 'lucide-react';

export default function AgentTimeline({ events }) {
  if (!events || events.length === 0) {
    return (
      <div className="p-12 text-center border border-dashed border-slate-800 rounded-xl">
        <p className="text-slate-400 text-sm">No agent events logged yet. Trigger an Agent Cycle to view execution telemetry.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      
      {/* Telemetry Header */}
      <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 flex items-center justify-between">
        <div className="flex items-center space-x-2.5">
          <Terminal className="w-5 h-5 text-emerald-400" />
          <div>
            <h3 className="text-sm font-bold text-white font-mono uppercase tracking-wider">
              Agent Execution &amp; State Audit Trail
            </h3>
            <p className="text-xs text-slate-400">
              Immutable structured record of all autonomous decisions, tool invocations, and state transitions
            </p>
          </div>
        </div>
        <span className="px-2.5 py-1 rounded bg-emerald-950/60 text-emerald-400 border border-emerald-800 text-xs font-mono">
          {events.length} Events Captured
        </span>
      </div>

      {/* Events List */}
      <div className="space-y-2.5 font-mono text-xs">
        {events.map((evt) => (
          <div
            key={evt.id}
            className="p-3.5 rounded-xl bg-slate-900/90 border border-slate-800/80 hover:border-slate-700 transition space-y-1.5"
          >
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-[11px] text-slate-400">
              <div className="flex items-center space-x-2">
                <span className="text-slate-500 font-semibold">
                  {new Date(evt.timestamp).toLocaleTimeString()}
                </span>
                <span className="text-slate-600">•</span>
                <span className="px-1.5 py-0.2 rounded bg-blue-950 text-blue-400 border border-blue-900">
                  {evt.agent_name}
                </span>
                {evt.tool_name && (
                  <span className="px-1.5 py-0.2 rounded bg-purple-950 text-purple-400 border border-purple-900">
                    tool: {evt.tool_name}
                  </span>
                )}
              </div>

              {evt.commitment_id && (
                <span className="text-slate-400 font-mono text-[10px]">
                  ref: {evt.commitment_id}
                </span>
              )}
            </div>

            <div className="text-slate-200 font-sans text-xs font-medium">
              {evt.summary}
            </div>

            {evt.rationale && (
              <div className="text-slate-400 text-[11px] font-sans italic bg-slate-950/60 p-2 rounded border border-slate-900">
                Rationale: {evt.rationale}
              </div>
            )}

            {(evt.previous_state || evt.new_state) && (
              <div className="flex items-center space-x-2 text-[10px] text-amber-400/90 pt-0.5">
                <span>Transition:</span>
                <span className="font-semibold">{evt.previous_state || 'NONE'}</span>
                <ArrowRight className="w-3 h-3 text-slate-500" />
                <span className="font-semibold">{evt.new_state}</span>
              </div>
            )}
          </div>
        ))}
      </div>

    </div>
  );
}
