import React, { useState } from 'react';
import { 
  X, 
  Clock, 
  ShieldAlert, 
  CheckCircle2, 
  FileText, 
  Mail, 
  Briefcase, 
  ArrowRight,
  ShieldCheck,
  Send,
  Activity,
  Sparkles,
  RefreshCw,
  Check,
  Radio,
  ArrowDownLeft,
  AlertTriangle
} from 'lucide-react';

export default function CommitmentDetail({ commitment, onClose, onVerify, onSimulateReply }) {
  const [verifying, setVerifying] = useState(false);
  const [simulating, setSimulating] = useState(false);

  if (!commitment) return null;

  const handleVerify = async () => {
    setVerifying(true);
    try {
      await onVerify(commitment.id);
    } finally {
      setVerifying(false);
    }
  };

  const handleSimulate = async () => {
    setSimulating(true);
    try {
      await onSimulateReply(commitment.id);
    } finally {
      setSimulating(false);
    }
  };

  return (
    <div className="fixed inset-y-0 right-0 w-full max-w-xl bg-slate-900 border-l border-slate-800 shadow-2xl z-50 overflow-y-auto flex flex-col">
      
      {/* Header */}
      <div className="p-5 border-b border-slate-800 bg-[#0d121a] flex items-start justify-between gap-4 sticky top-0 z-10">
        <div>
          <div className="flex items-center space-x-2 mb-1.5">
            <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-blue-500/10 text-blue-400 border border-blue-500/20">
              {commitment.category}
            </span>
            <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-slate-800 text-slate-300 border border-slate-700">
              {commitment.status}
            </span>
            <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-amber-950/60 text-amber-300 border border-amber-800">
              Health: {commitment.health}
            </span>
          </div>
          <h2 className="text-base font-bold text-white leading-snug">
            {commitment.title}
          </h2>
        </div>

        <button
          onClick={onClose}
          className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition cursor-pointer"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Content */}
      <div className="p-6 space-y-6 flex-1 text-xs">
        
        {/* ==================================================================== */}
        {/* Section 13: Dedicated Causal Evidence View                           */}
        {/* ==================================================================== */}
        <div className="p-5 rounded-xl bg-slate-950 border border-slate-800 space-y-4">
          <div className="flex items-center space-x-2 text-[11px] font-mono uppercase font-bold text-blue-400 tracking-wider border-b border-slate-800/80 pb-2">
            <Sparkles className="w-3.5 h-3.5" />
            <span>Causal Evidence Chain (Why Covenant Believes What It Believes)</span>
          </div>

          <div className="space-y-3">
            {/* 1. Commitment */}
            <div>
              <span className="text-[10px] font-mono uppercase text-slate-400 font-semibold block">1. COMMITMENT</span>
              <span className="font-semibold text-slate-200 text-xs">{commitment.title}</span>
            </div>

            {/* 2. Promise Quote & Promisor */}
            <div>
              <span className="text-[10px] font-mono uppercase text-slate-400 font-semibold block">2. EXTRACTED PROMISE</span>
              <p className="text-slate-300 italic bg-slate-900/60 p-2.5 rounded border border-slate-800 text-xs">
                "{commitment.description}"
              </p>
              <div className="text-[11px] text-slate-400 mt-1">
                Promised by: <strong className="text-slate-300">{commitment.promisor.name}</strong> ({commitment.promisor.organization || 'Client'}) to <strong className="text-slate-300">{commitment.promisee.name}</strong>
              </div>
            </div>

            {/* 3. Primary Sources */}
            <div>
              <span className="text-[10px] font-mono uppercase text-slate-400 font-semibold block">3. PRIMARY SOURCE REFERENCES</span>
              <div className="flex flex-wrap gap-1.5 mt-1">
                {commitment.source_references.map((src, idx) => (
                  <span key={idx} className="px-2 py-0.5 rounded bg-blue-950/60 border border-blue-800 text-blue-300 font-mono text-[11px]">
                    {src}
                  </span>
                ))}
              </div>
            </div>

            {/* 4. Supporting Corroborating Evidence */}
            <div>
              <span className="text-[10px] font-mono uppercase text-slate-400 font-semibold block mb-1">
                4. SUPPORTING CORROBORATING EVIDENCE ({commitment.evidence_references?.length || 0})
              </span>
              <div className="space-y-2">
                {commitment.evidence_references?.map((ev, i) => (
                  <div key={i} className="flex items-start space-x-2 text-xs bg-slate-900/80 p-2.5 rounded border border-slate-800">
                    <Check className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="font-mono text-blue-400 font-semibold">[{ev.source_type} {ev.source_id}]</span>
                        <span className="font-semibold text-slate-200">{ev.title}</span>
                        <span className="text-[10px] font-mono text-slate-400">({Math.round(ev.confidence * 100)}% conf)</span>
                      </div>
                      <p className="text-slate-400 italic text-[11px] mt-0.5">"{ev.snippet}"</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* 5. Current State & Dynamic Health */}
            <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between">
              <div>
                <span className="text-[10px] font-mono uppercase text-slate-400 font-semibold block">5. CURRENT STATE &amp; HEALTH</span>
                <div className="flex items-center space-x-2 mt-0.5">
                  <span className="font-bold text-amber-300 font-mono">{commitment.status}</span>
                  <span className="text-slate-500">•</span>
                  <span className="text-slate-300 font-mono">Health: {commitment.health}</span>
                </div>
              </div>
              <div className="text-right">
                <span className="text-[10px] font-mono uppercase text-slate-400 font-semibold block">DEADLINE</span>
                <span className={`font-mono font-semibold ${commitment.is_overdue ? 'text-rose-400' : 'text-slate-300'}`}>
                  {commitment.due_date ? new Date(commitment.due_date).toLocaleDateString() : 'N/A'}
                  {commitment.is_overdue ? ' (Overdue)' : ''}
                </span>
              </div>
            </div>

            {/* 6. Next Action */}
            {commitment.next_action && (
              <div className="pt-2 border-t border-slate-800/80">
                <span className="text-[10px] font-mono uppercase text-slate-400 font-semibold block">6. OPERATIONAL REMEDY (NEXT ACTION)</span>
                <div className="mt-1 p-2 rounded bg-slate-900 border border-slate-800 text-slate-300">
                  <strong className="text-amber-400">{commitment.next_action.action_type}:</strong> {commitment.next_action.description}
                  <span className="block text-[11px] text-slate-400 mt-0.5">Status: {commitment.next_action.status}</span>
                </div>
              </div>
            )}

            {/* 7. Verification State */}
            <div className="pt-2 border-t border-slate-800/80">
              <span className="text-[10px] font-mono uppercase text-slate-400 font-semibold block mb-1">
                7. INDEPENDENT OUTCOME VERIFICATION
              </span>
              {commitment.verification_result ? (
                <div className={`p-2.5 rounded border ${
                  commitment.verification_result.is_verified 
                    ? 'bg-emerald-950/40 border-emerald-800 text-emerald-300' 
                    : 'bg-amber-950/40 border-amber-800 text-amber-300'
                }`}>
                  <div className="font-semibold flex items-center space-x-1.5">
                    {commitment.verification_result.is_verified ? <Check className="w-4 h-4 text-emerald-400" /> : <AlertTriangle className="w-4 h-4 text-amber-400" />}
                    <span>{commitment.verification_result.is_verified ? 'Outcome Independently Verified & Resolved' : 'Awaiting Counterparty Response (Action Sent)'}</span>
                  </div>
                  <p className="text-slate-400 text-[11px] mt-1">
                    {commitment.verification_result.rationale}
                  </p>
                </div>
              ) : (
                <p className="text-slate-400 italic text-[11px]">
                  Pending verification. Covenant VerificationAgent will corroborate multi-source proof before resolution.
                </p>
              )}
            </div>

          </div>
        </div>

        {/* ==================================================================== */}
        {/* Section 10: "World Changes" Demo Simulation Control                  */}
        {/* ==================================================================== */}
        <div className="p-4 rounded-xl bg-gradient-to-r from-blue-950/30 via-slate-950 to-indigo-950/30 border border-blue-800/50 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <span className="text-[11px] font-mono uppercase font-bold text-blue-300 block">
                World Changes Simulation
              </span>
              <p className="text-[11px] text-slate-400">
                Simulate external counterparty observing the follow-up and sending a signed reply
              </p>
            </div>

            <button
              onClick={handleSimulate}
              disabled={simulating || commitment.status === 'RESOLVED'}
              className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white font-semibold flex items-center space-x-1.5 transition cursor-pointer"
            >
              <Radio className={`w-3.5 h-3.5 ${simulating ? 'animate-spin' : ''}`} />
              <span>{simulating ? 'Simulating...' : 'Simulate Client Reply'}</span>
            </button>
          </div>

          <div className="flex items-center space-x-3 pt-2">
            <button
              onClick={handleVerify}
              disabled={verifying}
              className="flex-1 px-3 py-1.5 rounded-lg bg-slate-850 hover:bg-slate-800 border border-slate-700 text-slate-200 font-medium flex items-center justify-center space-x-1.5 transition cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${verifying ? 'animate-spin' : ''}`} />
              <span>{verifying ? 'Running Verification...' : 'Run Independent Verification'}</span>
            </button>
          </div>
        </div>

        {/* Action History & State Transitions */}
        <div className="space-y-2">
          <span className="text-[11px] font-mono uppercase tracking-wider text-slate-400 font-semibold block">
            Machine Action Audit Trail:
          </span>

          <div className="space-y-2">
            {commitment.action_history?.map((hist, i) => (
              <div key={i} className="p-2.5 rounded-lg bg-slate-950 border border-slate-800/80 text-[11px] font-mono space-y-1">
                <div className="flex items-center justify-between text-slate-400">
                  <span className="font-semibold text-blue-400">{hist.agent_name}</span>
                  <span>{new Date(hist.timestamp).toLocaleTimeString()}</span>
                </div>
                <p className="text-slate-300 font-sans text-xs">
                  {hist.summary}
                </p>
                {hist.approved_by && (
                  <span className="text-amber-400 text-[10px]">
                    Authorized by: {hist.approved_by}
                  </span>
                )}
              </div>
            ))}
          </div>
        </div>

      </div>
    </div>
  );
}
