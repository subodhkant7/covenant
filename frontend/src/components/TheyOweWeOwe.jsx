import React from 'react';
import { 
  ArrowDownLeft, 
  ArrowUpRight, 
  Clock, 
  AlertTriangle, 
  CheckCircle2, 
  User, 
  Building2,
  ChevronRight
} from 'lucide-react';

export default function TheyOweWeOwe({ commitments, onSelectCommitment }) {
  const theyOwe = commitments.filter(c => c.obligation_direction === 'THEY_OWE_US');
  const weOwe = commitments.filter(c => c.obligation_direction === 'WE_OWE_THEM');

  return (
    <div className="space-y-6">
      
      {/* Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        
        {/* Column 1: They Owe Northstar Studio */}
        <div className="space-y-4">
          <div className="p-4 rounded-xl bg-gradient-to-br from-blue-950/40 via-slate-900 to-slate-900 border border-blue-800/40 shadow-sm flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 rounded-lg bg-blue-500/10 border border-blue-500/30 flex items-center justify-center text-blue-400">
                <ArrowDownLeft className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
                  THEY OWE US ({theyOwe.length})
                </h3>
                <p className="text-xs text-slate-400">
                  External promises made to Northstar Studio
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
                className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-blue-500/60 transition cursor-pointer group"
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div>
                    <span className="text-[11px] font-mono text-blue-400 font-semibold">
                      {c.promisor.name} ({c.promisor.organization || 'Client'})
                    </span>
                    <h4 className="text-xs font-bold text-slate-200 group-hover:text-blue-300 transition mt-0.5">
                      {c.title}
                    </h4>
                  </div>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-mono uppercase ${
                    c.status === 'OVERDUE' ? 'bg-rose-950/80 text-rose-300 border border-rose-800' : 'bg-slate-950 text-slate-400 border border-slate-800'
                  }`}>
                    {c.status}
                  </span>
                </div>

                <p className="text-xs text-slate-400 line-clamp-2 mb-3">
                  {c.description}
                </p>

                <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono border-t border-slate-800/60 pt-2">
                  <span className="flex items-center space-x-1">
                    <Clock className="w-3 h-3 text-slate-500" />
                    <span>Due: {c.due_date ? new Date(c.due_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : 'N/A'}</span>
                  </span>
                  <span className="text-slate-400 group-hover:text-blue-400 transition flex items-center space-x-0.5">
                    <span>Inspect</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Column 2: Northstar Studio Owes Others */}
        <div className="space-y-4">
          <div className="p-4 rounded-xl bg-gradient-to-br from-indigo-950/40 via-slate-900 to-slate-900 border border-indigo-800/40 shadow-sm flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 rounded-lg bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-indigo-400">
                <ArrowUpRight className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
                  WE OWE THEM ({weOwe.length})
                </h3>
                <p className="text-xs text-slate-400">
                  Promises made by Northstar Studio to clients &amp; partners
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
                className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 hover:border-indigo-500/60 transition cursor-pointer group"
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <div>
                    <span className="text-[11px] font-mono text-indigo-400 font-semibold">
                      Owed to: {c.promisee.name} ({c.promisee.organization || 'Client'})
                    </span>
                    <h4 className="text-xs font-bold text-slate-200 group-hover:text-indigo-300 transition mt-0.5">
                      {c.title}
                    </h4>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-slate-950 text-slate-400 border border-slate-800">
                    {c.status}
                  </span>
                </div>

                <p className="text-xs text-slate-400 line-clamp-2 mb-3">
                  {c.description}
                </p>

                <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono border-t border-slate-800/60 pt-2">
                  <span className="flex items-center space-x-1">
                    <Clock className="w-3 h-3 text-slate-500" />
                    <span>Due: {c.due_date ? new Date(c.due_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : 'N/A'}</span>
                  </span>
                  <span className="text-slate-400 group-hover:text-indigo-400 transition flex items-center space-x-0.5">
                    <span>Inspect</span>
                    <ChevronRight className="w-3.5 h-3.5" />
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
