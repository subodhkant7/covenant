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
  HelpCircle
} from 'lucide-react';

const STATUS_THEMES = {
  DISCOVERED: 'bg-slate-800 text-slate-300 border-slate-700',
  ACTIVE: 'bg-blue-950/60 text-blue-300 border-blue-800',
  WAITING: 'bg-indigo-950/60 text-indigo-300 border-indigo-800',
  DUE: 'bg-cyan-950/60 text-cyan-300 border-cyan-800',
  OVERDUE: 'bg-rose-950/70 text-rose-300 border-rose-700 font-semibold',
  INVESTIGATING: 'bg-purple-950/60 text-purple-300 border-purple-700',
  ACTION_READY: 'bg-amber-950/60 text-amber-300 border-amber-700',
  AWAITING_APPROVAL: 'bg-amber-900/80 text-amber-200 border-amber-500 ring-1 ring-amber-500/50',
  EXECUTING: 'bg-blue-900/80 text-blue-200 border-blue-600',
  VERIFYING: 'bg-teal-950/60 text-teal-300 border-teal-700',
  RESOLVED: 'bg-emerald-950/60 text-emerald-300 border-emerald-700',
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
      c.description.toLowerCase().includes(filterQuery.toLowerCase());
    
    if (statusFilter === 'ALL') return matchesSearch;
    if (statusFilter === 'OVERDUE') return matchesSearch && (c.status === 'OVERDUE' || c.is_overdue);
    if (statusFilter === 'APPROVAL') return matchesSearch && c.status === 'AWAITING_APPROVAL';
    if (statusFilter === 'RESOLVED') return matchesSearch && c.status === 'RESOLVED';
    return matchesSearch && c.status === statusFilter;
  });

  return (
    <div className="space-y-6">
      
      {/* Visual Operational Statement Banner */}
      <div className="p-4 rounded-xl bg-gradient-to-r from-slate-900 via-slate-900 to-indigo-950/40 border border-slate-800 shadow-sm flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center space-x-2 text-xs font-semibold text-blue-400 uppercase tracking-wider">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Living Operational Relationship Map</span>
          </div>
          <p className="text-sm text-slate-300 font-medium">
            A task tells you what to do. A commitment tells you what the world expects to happen. Covenant watches whether that expectation is actually fulfilled.
          </p>
        </div>

        {/* Filter Toolbar */}
        <div className="flex items-center space-x-3 shrink-0">
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-500" />
            <input
              type="text"
              placeholder="Filter commitments, parties..."
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
              className="pl-9 pr-3 py-1.5 rounded-lg bg-slate-950/80 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 w-56"
            />
          </div>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="px-3 py-1.5 rounded-lg bg-slate-950/80 border border-slate-800 text-xs text-slate-300 focus:outline-none focus:border-blue-500"
          >
            <option value="ALL">All States</option>
            <option value="OVERDUE">Overdue Drift</option>
            <option value="APPROVAL">Awaiting Approval</option>
            <option value="ACTIVE">Active</option>
            <option value="INVESTIGATING">Investigating</option>
            <option value="RESOLVED">Resolved</option>
          </select>
        </div>
      </div>

      {/* Commitment Relationship Flow Graph / Map Surface */}
      <div className="grid grid-cols-1 gap-4">
        {filtered.map((c) => {
          const isSelected = selectedId === c.id;
          const statusTheme = STATUS_THEMES[c.status] || STATUS_THEMES.DISCOVERED;
          const health = HEALTH_CONFIG[c.health] || HEALTH_CONFIG.STABLE;

          return (
            <div
              key={c.id}
              onClick={() => onSelectCommitment(c)}
              className={`group relative rounded-xl border p-5 transition-all duration-200 cursor-pointer ${
                isSelected 
                  ? 'bg-slate-900 border-blue-500 ring-1 ring-blue-500/50 shadow-lg shadow-blue-500/5' 
                  : 'bg-slate-900/70 border-slate-800 hover:border-slate-700 hover:bg-slate-900/90'
              }`}
            >
              
              {/* 7-Step Causality Indicator Ribbon */}
              <div className="mb-3.5 pb-2.5 border-b border-slate-800/60 flex items-center justify-between text-[10px] font-mono text-slate-400 overflow-x-auto">
                <div className="flex items-center space-x-1.5 shrink-0">
                  <span className="text-slate-400">PARTY:</span>
                  <span className="text-slate-200 font-semibold">{c.promisor.name}</span>
                  <ArrowRight className="w-3 h-3 text-slate-600" />
                  <span className="text-slate-400">PROMISE:</span>
                  <span className="text-slate-200 truncate max-w-[140px]">{c.title}</span>
                  <ArrowRight className="w-3 h-3 text-slate-600" />
                  <span className="text-slate-400">DEADLINE:</span>
                  <span className={c.is_overdue ? "text-rose-400 font-bold" : "text-slate-300"}>
                    {c.due_date ? new Date(c.due_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : 'N/A'}
                  </span>
                  <ArrowRight className="w-3 h-3 text-slate-600" />
                  <span className="text-slate-400">EVIDENCE:</span>
                  <span className="text-blue-400">{c.evidence_references?.length || 0} src</span>
                  <ArrowRight className="w-3 h-3 text-slate-600" />
                  <span className="text-slate-400">STATE:</span>
                  <span className="text-amber-300 font-bold">{c.status}</span>
                </div>

                {/* Dynamic Health Badge */}
                <div className={`px-2 py-0.5 rounded flex items-center space-x-1.5 border text-[10px] font-mono ${health.classes}`} title={health.desc}>
                  <span className={`w-1.5 h-1.5 rounded-full ${health.dot}`}></span>
                  <span>{health.label}</span>
                </div>
              </div>

              <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
                
                {/* 1. Left Side: Relational Actors (Promisor -> Promisee) */}
                <div className="w-full lg:w-72 shrink-0">
                  <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-1.5 flex items-center space-x-1.5">
                    <span>Obligation Relationship</span>
                    <span className="text-slate-600">•</span>
                    <span className={c.obligation_direction === 'THEY_OWE_US' ? 'text-blue-400 font-semibold' : 'text-indigo-400'}>
                      {c.obligation_direction === 'THEY_OWE_US' ? 'They Owe Us' : 'We Owe Them'}
                    </span>
                  </div>

                  <div className="flex items-center space-x-2 text-xs">
                    <div className="px-2.5 py-1 rounded-md bg-slate-950 border border-slate-800/80 font-medium text-slate-200 max-w-[130px] truncate" title={c.promisor.name}>
                      {c.promisor.name}
                    </div>
                    <ArrowRight className="w-3.5 h-3.5 text-slate-500 shrink-0" />
                    <div className="px-2.5 py-1 rounded-md bg-slate-950 border border-slate-800/80 font-medium text-slate-200 max-w-[130px] truncate" title={c.promisee.name}>
                      {c.promisee.name}
                    </div>
                  </div>

                  {c.promisor.organization && (
                    <p className="text-[11px] text-slate-400 mt-1 truncate">
                      Org: {c.promisor.organization}
                    </p>
                  )}
                </div>

                {/* 2. Middle: Commitment Core Node & Evidence Trail */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center space-x-2 mb-1">
                    <h3 className="text-sm font-semibold text-white truncate group-hover:text-blue-300 transition">
                      {c.title}
                    </h3>
                  </div>

                  <p className="text-xs text-slate-400 line-clamp-2 mb-3">
                    {c.description}
                  </p>

                  {/* Evidence Pills */}
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-[10px] text-slate-400 uppercase font-mono tracking-wider mr-1">
                      Evidence ({c.evidence_references.length}):
                    </span>
                    {c.evidence_references.slice(0, 3).map((ev, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] bg-slate-950 border border-slate-800 text-slate-300"
                        title={ev.snippet}
                      >
                        {ev.source_type === 'EMAIL' && <Mail className="w-3 h-3 text-blue-400" />}
                        {ev.source_type === 'CONTRACT' && <FileText className="w-3 h-3 text-indigo-400" />}
                        {ev.source_type === 'PROJECT' && <Briefcase className="w-3 h-3 text-emerald-400" />}
                        <span className="truncate max-w-[140px]">{ev.title}</span>
                      </span>
                    ))}
                    {c.evidence_references.length > 3 && (
                      <span className="text-[11px] text-slate-400 font-mono">
                        +{c.evidence_references.length - 3} more
                      </span>
                    )}
                  </div>
                </div>

                {/* 3. Right Side: Lifecycle State, Next Action & Deadlines */}
                <div className="w-full lg:w-64 shrink-0 flex flex-col items-start lg:items-end justify-between border-t lg:border-t-0 border-slate-800/80 pt-3 lg:pt-0">
                  <div className="flex items-center space-x-2">
                    {/* State Badge */}
                    <span className={`px-2.5 py-1 rounded-md text-xs font-mono uppercase tracking-wide border ${statusTheme}`}>
                      {c.status}
                    </span>
                  </div>

                  {/* Deadline / Overdue Clock */}
                  <div className="mt-2.5 flex items-center space-x-1.5 text-xs text-slate-400 font-mono">
                    <Clock className="w-3.5 h-3.5 text-slate-500" />
                    <span>Due: {c.due_date ? new Date(c.due_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : 'No Deadline'}</span>
                    {c.is_overdue && (
                      <span className="text-[10px] text-rose-400 font-semibold uppercase bg-rose-950/60 px-1.5 py-0.5 rounded border border-rose-900">
                        Overdue Drift
                      </span>
                    )}
                  </div>

                  {/* Proposed Action Indicator */}
                  {c.next_action && (
                    <div className="mt-2 text-xs flex items-center space-x-1.5 text-amber-400 font-medium">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping"></span>
                      <span className="truncate max-w-[190px]">{c.next_action.description}</span>
                    </div>
                  )}
                </div>

                <div className="hidden lg:flex items-center text-slate-600 group-hover:text-slate-300 transition">
                  <ChevronRight className="w-5 h-5" />
                </div>

              </div>
            </div>
          );
        })}

        {filtered.length === 0 && (
          <div className="text-center py-12 border border-dashed border-slate-800 rounded-xl">
            <p className="text-slate-400 text-sm">No commitments match the selected filter criteria.</p>
          </div>
        )}
      </div>
    </div>
  );
}
