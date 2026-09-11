import React from 'react';
import { 
  ArrowDownLeft, 
  ArrowUpRight, 
  Clock, 
  AlertTriangle, 
  CheckCircle2, 
  User, 
  Building2,
  ChevronRight,
  FileCheck
} from 'lucide-react';

export default function TheyOweWeOwe({ commitments, onSelectCommitment }) {
  const theyOwe = commitments.filter(c => c.obligation_direction === 'THEY_OWE_US');
  const weOwe = commitments.filter(c => c.obligation_direction === 'WE_OWE_THEM');

  return (
    <div className="space-y-6">
      
      {/* Overview Dual Columns */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        
        {/* Column 1: They Owe Northstar Studio */}
        <div className="space-y-4">
          <div className="p-4 rounded-xl bg-gradient-to-br from-blue-950/40 via-slate-900 to-slate-900 border border-blue-800/40 shadow-sm flex items-center justify-between">
            <div className="flex items-center space-x-3.5">
              <div className="w-10 h-10 rounded-lg bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-400 shrink-0">
                <ArrowDownLeft className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider font-mono flex items-center space-x-2">
                  <span>THEY OWE US ({theyOwe.length})</span>
                  <span className="px-2 py-0.2 rounded text-[10px] bg-blue-500/20 text-blue-300 font-mono">Inbound Promises</span>
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  External promises and deliverables owed by clients and vendors to Northstar Studio
                </p>
              </div>
            </div>
            <span className="text-2xl font-bold font-mono text-blue-400">
              {theyOwe.length}
            </span>
          </div>

          <div className="space-y-3">
            {theyOwe.map(c => (
              <div
                key={c.id}
                onClick={() => onSelectCommitment(c)}
                className="p-4 sm:p-5 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-blue-500/60 transition cursor-pointer group shadow-sm"
              >
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div>
                    <div className="flex items-center space-x-2 text-xs font-mono">
                      <span className="text-blue-400 font-semibold">{c.promisor.name}</span>
                      {c.promisor.organization && (
                        <span className="text-slate-400 font-normal">({c.promisor.organization})</span>
                      )}
                    </div>
                    <h4 className="text-sm font-bold text-slate-200 group-hover:text-blue-300 transition mt-0.5 leading-snug">
                      {c.title}
                    </h4>
                  </div>

                  <div className="flex items-center space-x-2 shrink-0 font-mono text-[10px]">
                    <span className={`px-2 py-0.5 rounded uppercase font-bold border ${
                      c.risk === 'HIGH' || c.risk === 'CRITICAL' 
                        ? 'bg-rose-950/80 text-rose-300 border-rose-800' 
                        : 'bg-slate-950 text-slate-400 border border-slate-800'
                    }`}>
                      {c.risk}
                    </span>
                    <span className={`px-2.5 py-0.5 rounded uppercase font-bold border ${
                      c.status === 'OVERDUE' 
                        ? 'bg-rose-950/80 text-rose-300 border-rose-800' 
                        : c.status === 'RESOLVED'
                        ? 'bg-emerald-950/80 text-emerald-300 border-emerald-800'
                        : 'bg-slate-950 text-slate-400 border-slate-800'
                    }`}>
                      {c.status}
                    </span>
                  </div>
                </div>

                <p className="text-xs text-slate-400 line-clamp-2 mb-3 leading-relaxed">
                  {c.description}
                </p>

                <div className="flex items-center justify-between text-xs text-slate-400 font-mono border-t border-slate-800/70 pt-2.5">
                  <div className="flex items-center space-x-3">
                    <span className="flex items-center space-x-1.5">
                      <Clock className="w-3.5 h-3.5 text-slate-500" />
                      <span>Due: {c.due_date ? new Date(c.due_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A'}</span>
                    </span>
                    <span className="text-slate-600">•</span>
                    <span className="flex items-center space-x-1 text-blue-400/90">
                      <FileCheck className="w-3 h-3" />
                      <span>{c.evidence_references?.length || 0} Sources</span>
                    </span>
                  </div>

                  <span className="text-slate-400 group-hover:text-blue-400 transition flex items-center space-x-0.5 font-sans font-medium">
                    <span>Inspect Trace</span>
                    <ChevronRight className="w-4 h-4" />
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Column 2: Northstar Studio Owes Others */}
        <div className="space-y-4">
          <div className="p-4 rounded-xl bg-gradient-to-br from-indigo-950/40 via-slate-900 to-slate-900 border border-indigo-800/40 shadow-sm flex items-center justify-between">
            <div className="flex items-center space-x-3.5">
              <div className="w-10 h-10 rounded-lg bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-indigo-400 shrink-0">
                <ArrowUpRight className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider font-mono flex items-center space-x-2">
                  <span>WE OWE THEM ({weOwe.length})</span>
                  <span className="px-2 py-0.2 rounded text-[10px] bg-indigo-500/20 text-indigo-300 font-mono">Outbound Obligations</span>
                </h3>
                <p className="text-xs text-slate-400 mt-0.5">
                  Promises made by Northstar Studio to clients, vendors, and regulatory partners
                </p>
              </div>
            </div>
            <span className="text-2xl font-bold font-mono text-indigo-400">
              {weOwe.length}
            </span>
          </div>

          <div className="space-y-3">
            {weOwe.map(c => (
              <div
                key={c.id}
                onClick={() => onSelectCommitment(c)}
                className="p-4 sm:p-5 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-indigo-500/60 transition cursor-pointer group shadow-sm"
              >
                <div className="flex items-start justify-between gap-3 mb-2">
                  <div>
                    <div className="flex items-center space-x-2 text-xs font-mono">
                      <span className="text-indigo-400 font-semibold">Owed to: {c.promisee.name}</span>
                      {c.promisee.organization && (
                        <span className="text-slate-400 font-normal">({c.promisee.organization})</span>
                      )}
                    </div>
                    <h4 className="text-sm font-bold text-slate-200 group-hover:text-indigo-300 transition mt-0.5 leading-snug">
                      {c.title}
                    </h4>
                  </div>

                  <div className="flex items-center space-x-2 shrink-0 font-mono text-[10px]">
                    <span className="px-2 py-0.5 rounded uppercase font-bold bg-slate-950 text-slate-400 border border-slate-800">
                      {c.risk}
                    </span>
                    <span className="px-2.5 py-0.5 rounded uppercase font-bold bg-slate-950 text-slate-400 border border-slate-800">
                      {c.status}
                    </span>
                  </div>
                </div>

                <p className="text-xs text-slate-400 line-clamp-2 mb-3 leading-relaxed">
                  {c.description}
                </p>

                <div className="flex items-center justify-between text-xs text-slate-400 font-mono border-t border-slate-800/70 pt-2.5">
                  <div className="flex items-center space-x-3">
                    <span className="flex items-center space-x-1.5">
                      <Clock className="w-3.5 h-3.5 text-slate-500" />
                      <span>Due: {c.due_date ? new Date(c.due_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A'}</span>
                    </span>
                    <span className="text-slate-600">•</span>
                    <span className="flex items-center space-x-1 text-indigo-400/90">
                      <FileCheck className="w-3 h-3" />
                      <span>{c.evidence_references?.length || 0} Sources</span>
                    </span>
                  </div>

                  <span className="text-slate-400 group-hover:text-indigo-400 transition flex items-center space-x-0.5 font-sans font-medium">
                    <span>Inspect Trace</span>
                    <ChevronRight className="w-4 h-4" />
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
