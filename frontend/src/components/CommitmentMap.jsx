import React, { useState } from 'react';
import { 
  ArrowRight, 
  Clock, 
  FileText, 
  Mail, 
  Briefcase, 
  CheckCircle, 
  AlertTriangle, 
  Sparkles,
  ChevronRight,
  ShieldCheck,
  Search,
  Activity,
  HeartPulse,
  Send,
  HelpCircle,
  ArrowDownLeft,
  ArrowUpRight,
  Layers,
  FileCheck
} from 'lucide-react';

const STATUS_THEMES = {
  DISCOVERED: 'bg-slate-800 text-slate-300 border-slate-700',
  ACTIVE: 'bg-blue-950/60 text-blue-300 border-blue-800',
  WAITING: 'bg-indigo-950/60 text-indigo-300 border-indigo-800',
  DUE: 'bg-cyan-950/60 text-cyan-300 border-cyan-800',
  OVERDUE: 'bg-rose-950/70 text-rose-300 border-rose-700 font-semibold',
  INVESTIGATING: 'bg-purple-950/60 text-purple-300 border-purple-700',
  ACTION_READY: 'bg-amber-950/60 text-amber-300 border-amber-700',
  AWAITING_APPROVAL: 'bg-amber-900/80 text-amber-200 border-amber-500 ring-1 ring-amber-500/50 font-bold',
  EXECUTING: 'bg-blue-900/80 text-blue-200 border-blue-600',
  VERIFYING: 'bg-teal-950/60 text-teal-300 border-teal-700 font-bold',
  RESOLVED: 'bg-emerald-950/80 text-emerald-300 border-emerald-600 font-bold',
  BLOCKED: 'bg-red-950/60 text-red-300 border-red-800',
  CANCELLED: 'bg-slate-900 text-slate-400 border-slate-800',
  REJECTED: 'bg-rose-950 text-rose-400 border-rose-900',
  ESCALATED: 'bg-orange-950 text-orange-300 border-orange-700',
};

const HEALTH_CONFIG = {
  STABLE: {
    label: 'STABLE',
    classes: 'bg-emerald-950/50 text-emerald-300 border-emerald-700/60',
    dot: 'bg-emerald-400',
    desc: 'On track with expectations',
  },
  DRIFTING: {
    label: 'DRIFTING',
    classes: 'bg-amber-950/60 text-amber-300 border-amber-600/70',
    dot: 'bg-amber-400 animate-pulse',
    desc: 'Noticeable schedule divergence detected',
  },
  AT_RISK: {
    label: 'AT RISK',
    classes: 'bg-orange-950/70 text-orange-300 border-orange-600',
    dot: 'bg-orange-400 animate-ping',
    desc: 'Downstream milestones threatened',
  },
  OVERDUE: {
    label: 'OVERDUE',
    classes: 'bg-rose-950/80 text-rose-300 border-rose-600 font-bold',
    dot: 'bg-rose-400 animate-bounce',
    desc: 'Promise deadline breached',
  },
  RECOVERING: {
    label: 'RECOVERY IN PROGRESS',
    classes: 'bg-cyan-950/60 text-cyan-300 border-cyan-600',
    dot: 'bg-cyan-400 animate-pulse',
    desc: 'Action dispatched; awaiting counterparty response',
  },
  VERIFIED: {
    label: 'VERIFIED',
    classes: 'bg-emerald-900/80 text-emerald-200 border-emerald-500 font-bold',
    dot: 'bg-emerald-300',
    desc: 'Independent outcome confirmed & resolved',
  },
};

export default function CommitmentMap({ commitments, onSelectCommitment, selectedId }) {
  const [filterQuery, setFilterQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');

  const filtered = commitments.filter(c => {
    const matchesSearch = 
      c.title.toLowerCase().includes(filterQuery.toLowerCase()) ||
      c.promisor.name.toLowerCase().includes(filterQuery.toLowerCase()) ||
      c.description.toLowerCase().includes(filterQuery.toLowerCase()) ||
      (c.promisor.organization && c.promisor.organization.toLowerCase().includes(filterQuery.toLowerCase()));
    
    if (statusFilter === 'ALL') return matchesSearch;
    if (statusFilter === 'OVERDUE') return matchesSearch && (c.status === 'OVERDUE' || c.is_overdue);
    if (statusFilter === 'APPROVAL') return matchesSearch && c.status === 'AWAITING_APPROVAL';
    if (statusFilter === 'RESOLVED') return matchesSearch && c.status === 'RESOLVED';
    return matchesSearch && c.status === statusFilter;
  });

  return (
    <div className="space-y-5">
      
      {/* Visual Operational Statement & Filter Bar */}
      <div className="p-4 rounded-xl bg-gradient-to-r from-slate-900 via-slate-900 to-indigo-950/40 border border-slate-800 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        
        {/* Core Thesis Message */}
        <div className="space-y-1">
          <div className="flex items-center space-x-2 text-xs font-semibold text-blue-400 uppercase tracking-wider font-mono">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Living Operational Relationship Map</span>
          </div>
          <p className="text-xs sm:text-sm text-slate-300 font-medium leading-snug">
            A task tells you what to do. A commitment tells you what the world expects to happen. Covenant watches whether that expectation is actually fulfilled.
          </p>
        </div>

        {/* Filter Toolbar */}
        <div className="flex items-center space-x-3 shrink-0">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
            <input
              type="text"
              placeholder="Filter commitments, parties, orgs..."
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
              className="pl-9 pr-3 py-1.5 rounded-lg bg-slate-950/80 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 w-64 font-sans"
            />
          </div>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 rounded-lg bg-slate-950/80 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-blue-500 font-mono"
          >
            <option value="ALL">All States ({commitments.length})</option>
            <option value="OVERDUE">Overdue Drift</option>
            <option value="APPROVAL">Awaiting Approval</option>
            <option value="ACTIVE">Active</option>
            <option value="INVESTIGATING">Investigating</option>
            <option value="RESOLVED">Resolved</option>
          </select>
        </div>

      </div>

      {/* High-Density Hybrid Table / Card Surface */}
      <div className="space-y-3.5">
        {filtered.map((c) => {
          const isSelected = selectedId === c.id;
          const statusTheme = STATUS_THEMES[c.status] || STATUS_THEMES.DISCOVERED;
          const health = HEALTH_CONFIG[c.health] || HEALTH_CONFIG.STABLE;
          const isTheyOwe = c.obligation_direction === 'THEY_OWE_US';

          return (
            <div
              key={c.id}
              onClick={() => onSelectCommitment(c)}
              className={`group relative rounded-xl border p-5 sm:p-6 lg:p-7 transition-all duration-200 cursor-pointer ${
                isSelected 
                  ? 'bg-slate-900 border-blue-500 ring-1 ring-blue-500/50 shadow-lg shadow-blue-500/10' 
                  : 'bg-slate-900/80 border-slate-800/90 hover:border-slate-700 hover:bg-slate-900 shadow-sm'
              }`}
            >
              
              {/* Row Top Ribbon: Direction, Parties, Health & Risk */}
              <div className="mb-4 pb-3 border-b border-slate-800/70 flex flex-wrap items-center justify-between gap-3 text-xs">
                
                {/* Direction & Relational Parties */}
                <div className="flex flex-wrap items-center gap-2.5">
                  <span className={`inline-flex items-center space-x-1.5 px-3 py-1 rounded-md font-mono text-xs font-bold uppercase tracking-wider border ${
                    isTheyOwe 
                      ? 'bg-blue-950/60 text-blue-300 border-blue-800/80' 
                      : 'bg-indigo-950/60 text-indigo-300 border-indigo-800/80'
                  }`}>
                    {isTheyOwe ? <ArrowDownLeft className="w-3.5 h-3.5 text-blue-400" /> : <ArrowUpRight className="w-3.5 h-3.5 text-indigo-400" />}
                    <span>{isTheyOwe ? 'THEY OWE US' : 'WE OWE THEM'}</span>
                  </span>

                  <div className="flex items-center space-x-2 text-sm font-mono">
                    <span className="text-slate-400">Promisor:</span>
                    <strong className="text-slate-200 font-semibold">{c.promisor.name}</strong>
                    {c.promisor.organization && (
                      <span className="text-slate-400 font-normal">({c.promisor.organization})</span>
                    )}
                    <ArrowRight className="w-4 h-4 text-slate-600" />
                    <span className="text-slate-400">Promisee:</span>
                    <strong className="text-slate-300 font-medium">{c.promisee.name}</strong>
                  </div>

                  {c.category && (
                    <span className="px-2.5 py-1 rounded text-xs font-mono uppercase bg-slate-950 text-slate-400 border border-slate-800">
                      {c.category}
                    </span>
                  )}
                </div>

                {/* Health & Risk Badges */}
                <div className="flex items-center space-x-3 font-mono text-xs">
                  
                  {/* Risk Badge */}
                  <span className={`px-3 py-1 rounded text-xs uppercase font-bold border ${
                    c.risk === 'HIGH' || c.risk === 'CRITICAL'
                      ? 'bg-rose-950/80 text-rose-300 border-rose-800'
                      : c.risk === 'MEDIUM'
                      ? 'bg-amber-950/80 text-amber-300 border-amber-800'
                      : 'bg-slate-950 text-slate-400 border-slate-800'
                  }`}>
                    {c.risk} RISK
                  </span>

                  {/* Health Indicator */}
                  <div className={`px-3 py-1 rounded-md flex items-center space-x-1.5 border text-xs font-mono ${health.classes}`} title={health.desc}>
                    <span className={`w-2 h-2 rounded-full ${health.dot}`}></span>
                    <span>{health.label}</span>
                  </div>

                </div>

              </div>

              {/* Main Content Grid: 4 Dedicated Desktop Columns */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-center">
                
                {/* Col 1: Commitment Identity & Description (lg:col-span-5) */}
                <div className="lg:col-span-5 min-w-0">
                  <h3 className="text-lg sm:text-xl font-bold text-white group-hover:text-blue-300 transition leading-snug">
                    {c.title}
                  </h3>
                  <p className="text-sm text-slate-300 mt-1.5 leading-relaxed font-sans">
                    {c.description}
                  </p>
                </div>

                {/* Col 2: Evidence Trail & Corroboration (lg:col-span-3) */}
                <div className="lg:col-span-3 min-w-0 border-t lg:border-t-0 lg:border-l border-slate-800/80 pt-3 lg:pt-0 lg:pl-6">
                  <div className="text-xs font-mono uppercase tracking-wider text-slate-400 font-semibold mb-2 flex items-center space-x-1.5">
                    <FileCheck className="w-3.5 h-3.5 text-blue-400" />
                    <span>Evidence Trail ({c.evidence_references?.length || 0} Sources)</span>
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    {c.evidence_references?.slice(0, 3).map((ev, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded text-xs bg-slate-950 border border-slate-800/90 text-slate-300 font-sans shadow-sm"
                        title={ev.snippet}
                      >
                        {ev.source_type === 'EMAIL' && <Mail className="w-4 h-4 text-blue-400 shrink-0" />}
                        {ev.source_type === 'CONTRACT' && <FileText className="w-4 h-4 text-indigo-400 shrink-0" />}
                        {ev.source_type === 'PROJECT' && <Briefcase className="w-4 h-4 text-emerald-400 shrink-0" />}
                        <span className="font-mono font-semibold text-xs text-slate-400">[{ev.source_id}]</span>
                        <span className="truncate max-w-[200px] xl:max-w-[280px] font-medium">{ev.title}</span>
                      </span>
                    ))}
                    {c.evidence_references?.length > 3 && (
                      <span className="text-xs text-slate-400 font-mono px-1 font-semibold">
                        +{c.evidence_references.length - 3} more
                      </span>
                    )}
                  </div>
                </div>

                {/* Col 3: Lifecycle State & Next Action (lg:col-span-2) */}
                <div className="lg:col-span-2 min-w-0 border-t lg:border-t-0 lg:border-l border-slate-800/80 pt-3 lg:pt-0 lg:pl-6">
                  <div className="text-xs font-mono uppercase tracking-wider text-slate-400 font-semibold mb-2">
                    Lifecycle State
                  </div>
                  
                  <span className={`inline-block px-3.5 py-1.5 rounded-md text-xs font-mono uppercase tracking-wide border font-bold ${statusTheme}`}>
                    {c.status}
                  </span>

                  {c.next_action && (
                    <div className="mt-2.5 text-xs flex items-start space-x-1.5 text-amber-300 font-medium">
                      <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping shrink-0 mt-1"></span>
                      <span className="text-xs leading-relaxed">{c.next_action.description}</span>
                    </div>
                  )}
                </div>

                {/* Col 4: Timeline, Overdue & Inspect CTA (lg:col-span-2) */}
                <div className="lg:col-span-2 flex flex-col items-start lg:items-end justify-between border-t lg:border-t-0 lg:border-l border-slate-800/80 pt-3 lg:pt-0 lg:pl-6 space-y-2.5">
                  
                  <div className="flex flex-col items-start lg:items-end font-mono">
                    <div className="flex items-center space-x-1.5 text-xs text-slate-300">
                      <Clock className="w-4 h-4 text-slate-400" />
                      <span>Due: {c.due_date ? new Date(c.due_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'No Deadline'}</span>
                    </div>

                    {c.is_overdue && (
                      <span className="mt-1 text-xs text-rose-400 font-bold uppercase bg-rose-950/80 px-2.5 py-1 rounded border border-rose-900">
                        Overdue Drift
                      </span>
                    )}
                  </div>

                  <div className="flex items-center space-x-1.5 text-sm font-semibold text-slate-400 group-hover:text-blue-400 transition">
                    <span>Inspect Trace</span>
                    <ChevronRight className="w-4 h-4" />
                  </div>

                </div>

              </div>

            </div>
          );
        })}

        {filtered.length === 0 && (
          <div className="text-center py-16 border border-dashed border-slate-800 rounded-xl bg-slate-900/30">
            <p className="text-slate-400 text-sm font-medium">No commitments match the selected filter criteria.</p>
          </div>
        )}

        {/* Full-Screen Operational Telemetry Footer Strip */}
        <div className="p-4 rounded-xl bg-slate-950/90 border border-slate-800/80 flex flex-wrap items-center justify-between gap-4 text-xs font-mono text-slate-400">
          <div className="flex items-center space-x-3">
            <span className="flex h-2.5 w-2.5 relative">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
            </span>
            <span className="text-slate-300 font-semibold">Autonomous Lifecycle Engine:</span>
            <span className="text-blue-400 font-bold">ACTIVE (10s Polling Cycle)</span>
          </div>
          <div className="flex items-center space-x-4">
            <span>Deterministic Policy Gate: <strong className="text-emerald-400">ENFORCED</strong></span>
            <span>•</span>
            <span>Zero Self-Attestation: <strong className="text-emerald-400">VERIFIED</strong></span>
            <span>•</span>
            <span>Multi-Source Corroboration: <strong className="text-blue-400">ONLINE</strong></span>
          </div>
        </div>
      </div>

    </div>
  );
}
