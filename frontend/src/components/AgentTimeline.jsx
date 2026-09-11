import React, { useState } from 'react';
import { 
  Activity, 
  Cpu, 
  Clock, 
  CheckCircle2, 
  AlertTriangle, 
  ShieldCheck, 
  Terminal,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Radio
} from 'lucide-react';

export default function AgentTimeline({ events }) {
  const [expandedGroups, setExpandedGroups] = useState({});

  if (!events || events.length === 0) {
    return (
      <div className="p-12 text-center border border-dashed border-slate-800 rounded-xl">
        <p className="text-slate-400 text-sm">No agent events logged yet. Trigger an Agent Cycle to view execution telemetry.</p>
      </div>
    );
  }

  // Group consecutive autonomous verification monitoring checks
  const timelineBlocks = [];
  let currentMonGroup = null;

  for (const evt of events) {
    const isMonCheck = 
      evt.action_name === 'VERIFY_RESOLUTION' || 
      evt.tool_name === 'verify_commitment' ||
      (evt.summary && evt.summary.includes('Verification check #') && evt.summary.includes('Awaiting counterparty response'));

    if (isMonCheck) {
      if (!currentMonGroup) {
        currentMonGroup = {
          type: 'MONITORING_GROUP',
          id: `mon_grp_${evt.id || Math.random()}`,
          events: [evt],
        };
        timelineBlocks.push(currentMonGroup);
      } else {
        currentMonGroup.events.push(evt);
      }
    } else {
      currentMonGroup = null;
      timelineBlocks.push({
        type: 'SINGLE_EVENT',
        id: evt.id,
        event: evt,
      });
    }
  }

  const toggleGroup = (groupId) => {
    setExpandedGroups(prev => ({
      ...prev,
      [groupId]: !prev[groupId],
    }));
  };

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
        {timelineBlocks.map((block) => {
          if (block.type === 'MONITORING_GROUP' && block.events.length > 1) {
            const count = block.events.length;
            const recent = block.events.slice(0, 3);
            const older = block.events.slice(3);
            const isExpanded = !!expandedGroups[block.id];
            const firstEvt = block.events[0];

            return (
              <div
                key={block.id}
                className="p-3.5 rounded-xl bg-slate-900/90 border border-cyan-900/50 hover:border-cyan-800/70 transition space-y-2.5"
              >
                {/* Group Summary Header */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1 text-[11px]">
                  <div className="flex items-center space-x-2">
                    <Radio className="w-3.5 h-3.5 text-cyan-400 animate-pulse shrink-0" />
                    <span className="font-bold text-cyan-300 uppercase tracking-wider">
                      VERIFICATION MONITORING
                    </span>
                    <span className="text-slate-500">•</span>
                    <span className="text-slate-400">
                      Bounded Autonomous Cycle (10s interval)
                    </span>
                  </div>
                  <span className="px-2 py-0.5 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800 text-[10px] font-mono">
                    {count} checks • Awaiting counterparty response
                  </span>
                </div>

                <div className="text-[11px] text-slate-400 font-sans">
                  Active monitoring loop actively polling independent external documentary proof against the VerificationGate (<span className="font-mono text-slate-300">T_proof &gt; T_exec</span>). Bounded monitoring, not uncontrolled looping.
                </div>

                {/* Latest Attempts */}
                <div className="space-y-1.5 pl-3 border-l-2 border-cyan-900/60 text-[11px]">
                  {recent.map((evt, idx) => (
                    <div key={evt.id} className="flex flex-col sm:flex-row sm:items-center justify-between text-slate-300 gap-1">
                      <div className="flex items-center space-x-2">
                        <span className={`text-[10px] px-1.5 py-0.2 rounded font-semibold ${
                          idx === 0 
                            ? 'bg-cyan-900/80 text-cyan-200 border border-cyan-700' 
                            : 'bg-slate-800 text-slate-400'
                        }`}>
                          {idx === 0 ? 'Latest' : 'Previous'}
                        </span>
                        <span className="text-slate-200 font-sans">{evt.summary}</span>
                      </div>
                      <span className="text-slate-500 text-[10px] shrink-0 font-mono">
                        {new Date(evt.timestamp).toLocaleTimeString()}
                      </span>
                    </div>
                  ))}
                </div>

                {/* Collapsible Older Checks */}
                {older.length > 0 && (
                  <div className="pt-1">
                    <button
                      onClick={() => toggleGroup(block.id)}
                      className="text-[11px] text-cyan-400 hover:text-cyan-300 font-mono flex items-center space-x-1.5 transition cursor-pointer"
                    >
                      {isExpanded ? (
                        <>
                          <ChevronUp className="w-3.5 h-3.5" />
                          <span>Hide earlier monitoring history</span>
                        </>
                      ) : (
                        <>
                          <ChevronDown className="w-3.5 h-3.5" />
                          <span>+{older.length} earlier verification checks recorded (Show monitoring history)</span>
                        </>
                      )}
                    </button>

                    {isExpanded && (
                      <div className="mt-2 space-y-1 pl-3 border-l-2 border-slate-800 max-h-48 overflow-y-auto text-[10px] font-mono text-slate-400">
                        {older.map((evt) => (
                          <div key={evt.id} className="flex items-center justify-between py-0.5 border-b border-slate-900/60">
                            <span className="truncate pr-2">{evt.summary}</span>
                            <span className="text-slate-600 shrink-0">{new Date(evt.timestamp).toLocaleTimeString()}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          }

          // Single Event Rendering
          const evt = block.type === 'MONITORING_GROUP' ? block.events[0] : block.event;
          return (
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
          );
        })}
      </div>

    </div>
  );
}
