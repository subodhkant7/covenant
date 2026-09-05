import React, { useState, useEffect } from 'react';
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
  AlertTriangle,
  Layers,
  UserCheck,
  Cpu,
  History,
  Scale,
  ExternalLink,
  ChevronRight,
  CheckCircle,
  XCircle,
  HelpCircle,
  Eye
} from 'lucide-react';
import { fetchCommitmentTrace } from '../services/api';

export default function CommitmentDetail({ commitment, onClose, onVerify, onSimulateReply }) {
  const [trace, setTrace] = useState(null);
  const [loadingTrace, setLoadingTrace] = useState(false);
  const [traceError, setTraceError] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const [simulating, setSimulating] = useState(false);
  const [activeViewTab, setActiveViewTab] = useState('trace'); // 'trace' | 'timeline' | 'evidence'

  const loadTrace = async (id) => {
    if (!id) return;
    setLoadingTrace(true);
    setTraceError(null);
    try {
      const data = await fetchCommitmentTrace(id);
      setTrace(data);
    } catch (err) {
      console.error('Error fetching decision trace:', err);
      setTraceError(err.message || 'Failed to load trace');
    } finally {
      setLoadingTrace(false);
    }
  };

  useEffect(() => {
    if (commitment?.id) {
      loadTrace(commitment.id);
    } else {
      setTrace(null);
    }
  }, [commitment?.id]);

  if (!commitment) return null;

  const handleVerify = async () => {
    setVerifying(true);
    try {
      await onVerify(commitment.id);
      await loadTrace(commitment.id);
    } finally {
      setVerifying(false);
    }
  };

  const handleSimulate = async () => {
    setSimulating(true);
    try {
      await onSimulateReply(commitment.id);
      await loadTrace(commitment.id);
    } finally {
      setSimulating(false);
    }
  };

  const currentState = trace?.current_state || commitment.status;
  const currentRisk = trace?.current_risk || commitment.risk;
  const health = trace?.health || commitment.health;

  const assessment = trace?.evidence_assessment || commitment.evidence_assessment || commitment.metadata?.evidence_assessment;
  const factualClaims = assessment?.factual_claims?.filter(c => c.is_fact) || [];
  const inferentialClaims = assessment?.factual_claims?.filter(c => !c.is_fact) || [];
  const conflicts = assessment?.conflicts || [];
  const corroborations = assessment?.corroborations || [];
  const evidenceGaps = assessment?.evidence_gaps || [];


  // Status visual attributes
  const getStatusBadge = (status) => {
    switch (status) {
      case 'RESOLVED':
        return {
          bg: 'bg-emerald-950/80 border-emerald-500/40 text-emerald-300',
          dot: 'bg-emerald-400',
          label: 'RESOLVED (VERIFIED)',
        };
      case 'VERIFYING':
        return {
          bg: 'bg-blue-950/80 border-blue-500/40 text-blue-300',
          dot: 'bg-blue-400 animate-pulse',
          label: 'VERIFYING (AWAITING PROOF)',
        };
      case 'AWAITING_APPROVAL':
        return {
          bg: 'bg-amber-950/80 border-amber-500/40 text-amber-300',
          dot: 'bg-amber-400 animate-ping',
          label: 'AWAITING HUMAN APPROVAL',
        };
      case 'FAILED':
        return {
          bg: 'bg-rose-950/80 border-rose-500/40 text-rose-300',
          dot: 'bg-rose-400',
          label: 'VERIFICATION FAILED',
        };
      case 'EXECUTING':
        return {
          bg: 'bg-purple-950/80 border-purple-500/40 text-purple-300',
          dot: 'bg-purple-400 animate-spin',
          label: 'EXECUTING DISPATCH',
        };
      default:
        return {
          bg: 'bg-slate-800 border-slate-700 text-slate-300',
          dot: 'bg-slate-400',
          label: status,
        };
    }
  };

  const statusBadge = getStatusBadge(currentState);

  return (
    <div className="fixed inset-y-0 right-0 w-full max-w-2xl bg-[#0b0f17] border-l border-slate-800 shadow-2xl z-50 overflow-y-auto flex flex-col font-sans">
      
      {/* Header Bar */}
      <div className="p-5 border-b border-slate-800 bg-[#0d131d]/95 backdrop-blur sticky top-0 z-20 flex items-start justify-between gap-4">
        <div className="space-y-1.5 flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-blue-500/10 text-blue-400 border border-blue-500/20 font-semibold">
              {commitment.category}
            </span>
            <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-mono uppercase border flex items-center space-x-1.5 font-bold ${statusBadge.bg}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${statusBadge.dot}`} />
              <span>{statusBadge.label}</span>
            </span>
            <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-slate-800 text-slate-300 border border-slate-700">
              Risk: <strong className={currentRisk === 'HIGH' || currentRisk === 'CRITICAL' ? 'text-rose-400' : 'text-amber-400'}>{currentRisk}</strong>
            </span>
            <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-slate-800/80 text-slate-400 border border-slate-700/80">
              Health: {health}
            </span>
          </div>
          <h2 className="text-base font-bold text-white leading-snug break-words">
            {commitment.title}
          </h2>
          <div className="text-[11px] text-slate-400 flex items-center space-x-2">
            <span>Promisee: <strong className="text-slate-300">{commitment.promisee?.name}</strong></span>
            <span>•</span>
            <span>Promisor: <strong className="text-slate-300">{commitment.promisor?.name}</strong></span>
          </div>
        </div>

        <button
          onClick={onClose}
          className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white transition cursor-pointer shrink-0"
          title="Close trace view"
        >
          <X className="w-5 h-5" />
        </button>
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-slate-800 bg-[#0d121b] px-6 text-xs font-mono">
        <button
          onClick={() => setActiveViewTab('trace')}
          className={`py-3 px-3 border-b-2 font-medium flex items-center space-x-2 transition cursor-pointer ${
            activeViewTab === 'trace'
              ? 'border-blue-500 text-blue-400 bg-blue-500/5'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          <span>Decision Trace</span>
        </button>
        <button
          onClick={() => setActiveViewTab('timeline')}
          className={`py-3 px-3 border-b-2 font-medium flex items-center space-x-2 transition cursor-pointer ${
            activeViewTab === 'timeline'
              ? 'border-blue-500 text-blue-400 bg-blue-500/5'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <History className="w-3.5 h-3.5" />
          <span>Audit Log ({trace?.timeline?.length || commitment.action_history?.length || 0})</span>
        </button>
        <button
          onClick={() => setActiveViewTab('evidence')}
          className={`py-3 px-3 border-b-2 font-medium flex items-center space-x-2 transition cursor-pointer ${
            activeViewTab === 'evidence'
              ? 'border-blue-500 text-blue-400 bg-blue-500/5'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <FileText className="w-3.5 h-3.5" />
          <span>Evidence ({trace?.evidence?.length || commitment.evidence_references?.length || 0})</span>
        </button>
      </div>

      {/* Content Body */}
      <div className="p-6 space-y-6 flex-1 text-xs">

        {loadingTrace && (
          <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 text-center space-y-2">
            <div className="inline-block w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
            <p className="text-[11px] font-mono text-slate-400">Loading authoritative decision trace &amp; audit telemetry...</p>
          </div>
        )}

        {traceError && (
          <div className="p-3 rounded-lg bg-rose-950/40 border border-rose-800 text-rose-300 text-xs flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <AlertTriangle className="w-4 h-4 shrink-0 text-rose-400" />
              <span>{traceError}</span>
            </div>
            <button
              onClick={() => loadTrace(commitment.id)}
              className="px-2 py-1 rounded bg-rose-900/60 hover:bg-rose-800 text-[10px] font-mono cursor-pointer"
            >
              Retry
            </button>
          </div>
        )}

        {/* ==================================================================== */}
        {/* WORLD CHANGES / SIMULATION CONTROLS                                  */}
        {/* ==================================================================== */}
        <div className="p-4 rounded-xl bg-gradient-to-r from-blue-950/40 via-slate-900 to-indigo-950/40 border border-blue-800/40 space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div>
              <span className="text-[11px] font-mono uppercase font-bold text-blue-300 flex items-center space-x-1.5">
                <Radio className="w-3.5 h-3.5 text-blue-400" />
                <span>External Environment Simulation ("World Changes")</span>
              </span>
              <p className="text-[11px] text-slate-400 mt-0.5">
                Simulate external counterparty observing dispatched remedy and returning formal response.
              </p>
            </div>

            <button
              onClick={handleSimulate}
              disabled={simulating || currentState === 'RESOLVED'}
              className="px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white font-semibold flex items-center space-x-1.5 transition cursor-pointer text-xs shrink-0"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${simulating ? 'animate-spin' : ''}`} />
              <span>{simulating ? 'Simulating...' : 'Simulate Reply'}</span>
            </button>
          </div>

          <div className="flex items-center space-x-3 pt-1 border-t border-slate-800/60">
            <button
              onClick={handleVerify}
              disabled={verifying}
              className="flex-1 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-750 border border-slate-700 text-slate-200 font-medium flex items-center justify-center space-x-1.5 transition cursor-pointer text-xs"
            >
              <ShieldCheck className={`w-3.5 h-3.5 text-blue-400 ${verifying ? 'animate-spin' : ''}`} />
              <span>{verifying ? 'Running VerificationGate...' : 'Run Independent Verification Pass'}</span>
            </button>
          </div>
        </div>

        {/* ==================================================================== */}
        {/* TAB 1: DECISION TRACE (MAIN VIEW)                                    */}
        {/* ==================================================================== */}
        {activeViewTab === 'trace' && (
          <div className="space-y-6">

            {/* 10-STAGE CHRONOLOGICAL STEPPER */}
            <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between border-b border-slate-800/80 pb-2">
                <span className="text-[11px] font-mono uppercase font-bold text-slate-300 tracking-wider flex items-center space-x-1.5">
                  <Activity className="w-3.5 h-3.5 text-blue-400" />
                  <span>Authoritative Lifecycle Sequence</span>
                </span>
                <span className="text-[10px] font-mono text-slate-400">{trace?.stages?.length || 10} Decision Stages</span>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-[10px] font-mono">
                {(trace?.stages || [
                  { step: 1, name: "Commitment detected", status: "COMPLETED" },
                  { step: 2, name: "Evidence gathered", status: "COMPLETED" },
                  { step: 3, name: "Risk calculated", status: "COMPLETED" },
                  { step: 4, name: "Action proposed", status: "COMPLETED" },
                  { step: 5, name: "Policy decision", status: "COMPLETED" },
                  { step: 6, name: "Human approval", status: currentState === 'AWAITING_APPROVAL' ? 'ACTIVE' : 'COMPLETED' },
                  { step: 7, name: "Action executed", status: ['VERIFYING', 'RESOLVED'].includes(currentState) ? 'COMPLETED' : 'PENDING' },
                  { step: 8, name: "Verification started", status: ['VERIFYING', 'RESOLVED'].includes(currentState) ? 'COMPLETED' : 'PENDING' },
                  { step: 9, name: "Verification evidence", status: currentState === 'RESOLVED' ? 'COMPLETED' : (currentState === 'VERIFYING' ? 'ACTIVE' : 'PENDING') },
                  { step: 10, name: "Final outcome", status: currentState === 'RESOLVED' ? 'COMPLETED' : (currentState === 'FAILED' ? 'FAILED' : 'PENDING') },
                ]).map((st) => {
                  const isDone = st.status === 'COMPLETED';
                  const isActive = st.status === 'ACTIVE';
                  const isFailed = st.status === 'FAILED';
                  return (
                    <div
                      key={st.step}
                      className={`p-2 rounded border flex flex-col justify-between transition ${
                        isDone
                          ? 'bg-emerald-950/20 border-emerald-800/60 text-emerald-300'
                          : isActive
                          ? 'bg-blue-950/30 border-blue-500/80 text-blue-300 ring-1 ring-blue-500/40'
                          : isFailed
                          ? 'bg-rose-950/30 border-rose-700 text-rose-300'
                          : 'bg-slate-900/40 border-slate-800 text-slate-400'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="font-bold opacity-70">#{st.step}</span>
                        {isDone && <CheckCircle className="w-3 h-3 text-emerald-400" />}
                        {isActive && <div className="w-2 h-2 rounded-full bg-blue-400 animate-ping" />}
                        {isFailed && <XCircle className="w-3 h-3 text-rose-400" />}
                        {!isDone && !isActive && !isFailed && <Clock className="w-3 h-3 opacity-40" />}
                      </div>
                      <span className="font-semibold leading-tight line-clamp-2">{st.name}</span>
                      <span className="text-[9px] uppercase tracking-wider opacity-60 mt-1">{st.status}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* DETAILED FACET PANELS */}
            <div className="space-y-4">

              {/* SECTION 1: COMMITMENT & DISCOVERY */}
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="text-[11px] font-mono uppercase font-bold text-blue-400 flex items-center space-x-1.5">
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>1. Commitment Discovery &amp; Extracted Promise</span>
                  </span>
                  <span className="text-[10px] font-mono text-slate-400">Authority: CommitmentAgent</span>
                </div>

                <div className="space-y-2">
                  <div>
                    <span className="text-[10px] font-mono text-slate-400 block uppercase font-semibold">Extracted Promise Text</span>
                    <p className="text-slate-200 italic bg-slate-900/70 p-2.5 rounded border border-slate-800 mt-1">
                      "{commitment.description}"
                    </p>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-[11px] pt-1">
                    <div>
                      <span className="text-[10px] font-mono text-slate-400 uppercase">Obligation Direction:</span>
                      <p className="font-semibold text-slate-200 mt-0.5">
                        {commitment.obligation_direction === 'THEY_OWE_US' ? 'They Owe Us (Inbound)' : 'We Owe Them (Outbound)'}
                      </p>
                    </div>
                    <div>
                      <span className="text-[10px] font-mono text-slate-400 uppercase">Deadline &amp; Temporal Status:</span>
                      <p className={`font-semibold mt-0.5 font-mono ${commitment.is_overdue ? 'text-rose-400' : 'text-slate-200'}`}>
                        {commitment.due_date ? new Date(commitment.due_date).toLocaleString() : 'N/A'}
                        {commitment.is_overdue ? ` (${trace?.risk?.days_overdue || commitment.days_overdue || 0}d overdue)` : ''}
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              {/* SECTION 2: EVIDENCE INTELLIGENCE & CORROBORATION */}
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="text-[11px] font-mono uppercase font-bold text-blue-400 flex items-center space-x-1.5">
                    <FileText className="w-3.5 h-3.5" />
                    <span>2. Evidence Intelligence &amp; Multi-Source Corroboration</span>
                  </span>
                  <span className="text-[10px] font-mono text-slate-400">Authority: EvidenceAgent (Strands Synthesis)</span>
                </div>

                {/* SYNTHESIZED ASSESSMENT FINDING */}
                <div className="p-3 rounded-lg bg-blue-950/25 border border-blue-800/60 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-mono uppercase font-bold text-blue-300 flex items-center space-x-1.5">
                      <Sparkles className="w-3.5 h-3.5 text-blue-400" />
                      <span>Synthesized Evidence Finding</span>
                    </span>
                    <div className="flex items-center space-x-1.5">
                      {assessment?.is_blocking_downstream && (
                        <span className="px-1.5 py-0.5 rounded text-[9px] font-mono uppercase bg-rose-950/80 text-rose-300 border border-rose-800/80 font-bold">
                          Downstream Work Blocked
                        </span>
                      )}
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-blue-900/60 text-blue-200 border border-blue-700">
                        {Math.round((assessment?.confidence || 0.96) * 100)}% Confidence
                      </span>
                    </div>
                  </div>
                  <p className="text-slate-100 text-xs font-semibold leading-relaxed">
                    {assessment?.finding || "Multi-source evidence corroborated across workspace records."}
                  </p>
                  {assessment?.rationale && (
                    <p className="text-slate-400 italic text-[11px] pt-0.5">
                      "{assessment.rationale}"
                    </p>
                  )}
                </div>

                {/* CROSS-SOURCE CORROBORATION */}
                {corroborations.length > 0 && (
                  <div className="p-3 rounded-lg bg-emerald-950/25 border border-emerald-500/50 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono uppercase font-bold text-emerald-300 flex items-center space-x-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                        <span>Cross-Source Corroboration ({corroborations.length})</span>
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-mono uppercase bg-emerald-900/60 text-emerald-200 border border-emerald-700">
                        Corroborated
                      </span>
                    </div>
                    {corroborations.map((corr, cIdx) => (
                      <p key={cIdx} className="text-emerald-100 text-[11px] leading-snug">
                        {corr}
                      </p>
                    ))}
                  </div>
                )}

                {/* EVIDENCE GAP / MISSING EXPECTED RECORD */}
                {evidenceGaps.length > 0 && (
                  <div className="p-3 rounded-lg bg-amber-950/25 border border-amber-500/50 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono uppercase font-bold text-amber-300 flex items-center space-x-1.5">
                        <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                        <span>Expected Evidence Gap / Missing Record ({evidenceGaps.length})</span>
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-mono uppercase bg-amber-900/60 text-amber-200 border border-amber-700">
                        Evidence Gap
                      </span>
                    </div>
                    {evidenceGaps.map((gap, gIdx) => (
                      <p key={gIdx} className="text-amber-100 text-[11px] leading-snug">
                        {gap}
                      </p>
                    ))}
                  </div>
                )}

                {/* CROSS-SOURCE EVIDENCE CONFLICT ALERT (GENUINE CONTRADICTIONS ONLY) */}
                {conflicts.length > 0 && (
                  <div className="p-3 rounded-lg bg-rose-950/25 border border-rose-500/60 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] font-mono uppercase font-bold text-rose-300 flex items-center space-x-1.5">
                        <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                        <span>Cross-Source Contradiction Detected ({conflicts.length})</span>
                      </span>
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-mono uppercase bg-rose-900/60 text-rose-200 border border-rose-700">
                        Conflict Alert
                      </span>
                    </div>
                    {conflicts.map((conf, cIdx) => (
                      <div key={cIdx} className="p-2.5 rounded bg-rose-950/40 border border-rose-900/60 space-y-1 text-xs">
                        <div className="flex items-center space-x-2 font-mono text-[10px]">
                          <span className="px-1.5 py-0.5 rounded bg-rose-900/80 text-rose-200 font-bold border border-rose-700/60">
                            {conf.source_a}
                          </span>
                          <span className="text-rose-400 font-bold">⟷</span>
                          <span className="px-1.5 py-0.5 rounded bg-rose-900/80 text-rose-200 font-bold border border-rose-700/60">
                            {conf.source_b}
                          </span>
                          <span className="text-rose-400/80 ml-auto uppercase text-[9px]">
                            [{conf.conflict_type}]
                          </span>
                        </div>
                        <p className="text-rose-100 text-[11px] leading-snug">
                          {conf.description}
                        </p>
                      </div>
                    ))}
                  </div>
                )}

                {/* FACTUAL CLAIMS VS INFERRED FINDINGS */}
                {(factualClaims.length > 0 || inferentialClaims.length > 0) && (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-1">
                    {/* DOCUMENTARY FACTS */}
                    <div className="p-3 rounded-lg bg-emerald-950/20 border border-emerald-800/60 space-y-2">
                      <div className="flex items-center justify-between border-b border-emerald-900/60 pb-1.5">
                        <span className="text-[10px] font-mono uppercase font-bold text-emerald-300 flex items-center space-x-1.5">
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                          <span>Documentary Facts ({factualClaims.length})</span>
                        </span>
                        <span className="text-[9px] font-mono text-emerald-400/80 uppercase">Verified Records</span>
                      </div>
                      <div className="space-y-1.5">
                        {factualClaims.map((claim, idx) => (
                          <div key={idx} className="p-2 rounded bg-slate-900/80 border border-emerald-900/40 space-y-0.5 text-xs">
                            <div className="flex items-center justify-between font-mono text-[10px]">
                              <span className="font-bold text-emerald-400">[{claim.source_id}]</span>
                              <span className="text-slate-400">{Math.round((claim.confidence || 0.95) * 100)}% Conf</span>
                            </div>
                            <p className="text-slate-200 text-[11px] leading-snug">{claim.claim}</p>
                          </div>
                        ))}
                      </div>
                    </div>

                    {/* ANALYTICAL INFERENCES */}
                    <div className="p-3 rounded-lg bg-purple-950/20 border border-purple-800/60 space-y-2">
                      <div className="flex items-center justify-between border-b border-purple-900/60 pb-1.5">
                        <span className="text-[10px] font-mono uppercase font-bold text-purple-300 flex items-center space-x-1.5">
                          <Cpu className="w-3.5 h-3.5 text-purple-400" />
                          <span>Analytical Inferences ({inferentialClaims.length})</span>
                        </span>
                        <span className="text-[9px] font-mono text-purple-400/80 uppercase">Derived Insights</span>
                      </div>
                      <div className="space-y-1.5">
                        {inferentialClaims.map((claim, idx) => (
                          <div key={idx} className="p-2 rounded bg-slate-900/80 border border-purple-900/40 space-y-0.5 text-xs">
                            <div className="flex items-center justify-between font-mono text-[10px]">
                              <span className="font-bold text-purple-400">[{claim.source_id}]</span>
                              <span className="text-slate-400">{Math.round((claim.confidence || 0.89) * 100)}% Conf</span>
                            </div>
                            <p className="text-slate-200 text-[11px] leading-snug">{claim.claim}</p>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* PRIMARY WORKSPACE EVIDENCE CITATIONS */}
                <div className="space-y-2 pt-1">
                  <span className="text-[10px] font-mono uppercase font-semibold text-slate-400 block">
                    Primary Workspace Records ({trace?.evidence?.length || commitment.evidence_references?.length || 0})
                  </span>
                  <div className="space-y-2">
                    {(trace?.evidence || commitment.evidence_references || []).map((ev, idx) => (
                      <div key={idx} className="p-2.5 rounded bg-slate-900/80 border border-slate-800 space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-mono font-bold text-blue-400 text-[11px]">
                            [{ev.source_type?.toUpperCase()} {ev.source_id}]
                          </span>
                          <span className="text-[10px] font-mono text-slate-400">
                            {Math.round((ev.confidence || 0.9) * 100)}% Confidence
                          </span>
                        </div>
                        <p className="font-semibold text-slate-200 text-xs">{ev.title}</p>
                        <p className="text-slate-400 italic text-[11px]">"{ev.snippet}"</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>


              {/* SECTION 3: RISK & DRIFT CALCULATION */}
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="text-[11px] font-mono uppercase font-bold text-blue-400 flex items-center space-x-1.5">
                    <ShieldAlert className="w-3.5 h-3.5" />
                    <span>3. Risk &amp; Drift Assessment</span>
                  </span>
                  <span className="text-[10px] font-mono text-slate-400">Authority: RiskAgent</span>
                </div>

                <div className="grid grid-cols-2 gap-3 text-[11px]">
                  <div>
                    <span className="text-[10px] font-mono text-slate-400 uppercase">Risk Level</span>
                    <p className={`font-bold font-mono text-sm mt-0.5 ${
                      ['HIGH', 'CRITICAL'].includes(currentRisk) ? 'text-rose-400' : 'text-amber-400'
                    }`}>
                      {currentRisk}
                    </p>
                  </div>
                  <div>
                    <span className="text-[10px] font-mono text-slate-400 uppercase">Downstream Dependency Impact</span>
                    <p className="text-slate-300 mt-0.5">
                      {trace?.risk?.blocking_impact || 'No downstream obligations blocked'}
                    </p>
                  </div>
                </div>

                <div className="p-2.5 rounded bg-slate-900/60 border border-slate-800 text-[11px] text-slate-300">
                  <span className="font-mono uppercase text-[10px] text-slate-400 font-semibold block mb-0.5">Assessment Rationale</span>
                  {trace?.risk?.rationale || 'Risk calculated from deadline proximity, counterparty relationship, and delivery state.'}
                </div>
              </div>

              {/* SECTION 4 & 5: PROPOSED ACTION & POLICY DECISION */}
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="text-[11px] font-mono uppercase font-bold text-blue-400 flex items-center space-x-1.5">
                    <Scale className="w-3.5 h-3.5" />
                    <span>4 &amp; 5. Proposed Remedy &amp; Policy Decision</span>
                  </span>
                  <span className="text-[10px] font-mono text-slate-400">Authority: ResolutionAgent + PolicyAgent</span>
                </div>

                {commitment.next_action ? (
                  <div className="space-y-3">
                    <div className="p-2.5 rounded bg-slate-900 border border-slate-800 space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-amber-400 font-mono text-[11px]">
                          {commitment.next_action.action_type}
                        </span>
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-800 text-slate-300">
                          Status: {commitment.next_action.status}
                        </span>
                      </div>
                      <p className="text-slate-200 text-xs font-medium">{commitment.next_action.description}</p>
                      {commitment.next_action.recipient && (
                        <p className="text-[11px] text-slate-400 font-mono">
                          Recipient: {commitment.next_action.recipient}
                        </p>
                      )}
                    </div>

                    <div className="p-2.5 rounded bg-amber-950/20 border border-amber-800/60 space-y-1">
                      <div className="flex items-center justify-between text-amber-300 text-[11px] font-mono font-semibold">
                        <span>Policy: {trace?.policy_decision?.decision || 'HUMAN_APPROVAL_REQUIRED'}</span>
                        <span>Required: {trace?.policy_decision?.requires_human_approval ? 'YES' : 'NO'}</span>
                      </div>
                      <div className="text-[11px] text-slate-300 space-y-0.5">
                        <span className="text-[10px] font-mono text-slate-400 block uppercase">Policy Rule Triggered:</span>
                        {(trace?.policy_decision?.rules_triggered || [commitment.next_action.approval_reason]).map((rule, idx) => (
                          <div key={idx} className="font-mono text-amber-200 bg-amber-950/40 p-1.5 rounded border border-amber-900/50">
                            {rule}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="text-slate-400 italic text-[11px]">No operational remedy required or proposed.</p>
                )}
              </div>

              {/* SECTION 6 & 7: HUMAN APPROVAL & RUNTIME DISPATCH */}
              <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="text-[11px] font-mono uppercase font-bold text-blue-400 flex items-center space-x-1.5">
                    <UserCheck className="w-3.5 h-3.5" />
                    <span>6 &amp; 7. Human Approval &amp; Runtime Dispatch</span>
                  </span>
                  <span className="text-[10px] font-mono text-slate-400">Authority: Human Operator + ExecutionEngine</span>
                </div>

                <div className="grid grid-cols-2 gap-3 text-[11px]">
                  <div className="p-2.5 rounded bg-slate-900/80 border border-slate-800 space-y-1">
                    <span className="text-[10px] font-mono text-slate-400 uppercase block font-semibold">Human Authorization</span>
                    <p className="font-bold text-slate-200">
                      Status: <span className={
                        trace?.approval?.status === 'APPROVED' ? 'text-emerald-400' : 
                        trace?.approval?.status === 'PENDING' ? 'text-amber-400' : 'text-slate-400'
                      }>{trace?.approval?.status || (currentState === 'AWAITING_APPROVAL' ? 'PENDING' : 'APPROVED')}</span>
                    </p>
                    {trace?.approval?.reviewer && (
                      <p className="text-slate-400 text-[10px]">Reviewed By: <strong className="text-slate-300">{trace.approval.reviewer}</strong></p>
                    )}
                    {trace?.approval?.decision_timestamp && (
                      <p className="text-slate-500 text-[10px]">{new Date(trace.approval.decision_timestamp).toLocaleTimeString()}</p>
                    )}
                  </div>

                  <div className="p-2.5 rounded bg-slate-900/80 border border-slate-800 space-y-1">
                    <span className="text-[10px] font-mono text-slate-400 uppercase block font-semibold">ExecutionEngine Dispatch</span>
                    <p className="font-bold text-slate-200">
                      Status: <span className={
                        trace?.execution?.status === 'COMPLETED' ? 'text-emerald-400' : 'text-slate-400'
                      }>{trace?.execution?.status || (['VERIFYING', 'RESOLVED'].includes(currentState) ? 'COMPLETED' : 'NOT_STARTED')}</span>
                    </p>
                    {trace?.execution?.tool_name && (
                      <p className="text-slate-400 text-[10px] font-mono">Tool: <strong className="text-blue-300">{trace.execution.tool_name}</strong></p>
                    )}
                    {trace?.execution?.execution_id && (
                      <p className="text-slate-500 text-[10px] font-mono">ID: {trace.execution.execution_id}</p>
                    )}
                  </div>
                </div>

                <div className="text-[11px] text-slate-400 italic bg-slate-900/40 p-2 rounded border border-slate-800">
                  {trace?.execution?.result_summary || 'Dispatch executed through authoritative Covenant runtime engine into external communication stream.'}
                </div>
              </div>

              {/* SECTION 8, 9 & 10: VERIFICATION & FINAL OUTCOME */}
              <div className={`p-4 rounded-xl border space-y-3 ${
                currentState === 'RESOLVED' 
                  ? 'bg-emerald-950/20 border-emerald-800/80' 
                  : currentState === 'FAILED'
                  ? 'bg-rose-950/20 border-rose-800/80'
                  : 'bg-slate-950 border-slate-800'
              }`}>
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="text-[11px] font-mono uppercase font-bold text-blue-400 flex items-center space-x-1.5">
                    <ShieldCheck className="w-3.5 h-3.5" />
                    <span>8, 9 &amp; 10. Verification &amp; Final Outcome</span>
                  </span>
                  <span className="text-[10px] font-mono text-slate-400">Authority: VerificationGate</span>
                </div>

                <div className="space-y-2 text-[11px]">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-300">Authoritative Gate Result:</span>
                    <span className={`px-2 py-0.5 rounded font-mono font-bold text-[10px] ${
                      trace?.verification?.gate_result === 'PASSED' || currentState === 'RESOLVED'
                        ? 'bg-emerald-900/60 text-emerald-300 border border-emerald-700'
                        : trace?.verification?.gate_result === 'FAILED' || currentState === 'FAILED'
                        ? 'bg-rose-900/60 text-rose-300 border border-rose-700'
                        : 'bg-blue-900/40 text-blue-300 border border-blue-800'
                    }`}>
                      {trace?.verification?.gate_result || (currentState === 'RESOLVED' ? 'PASSED' : 'AWAITING_COUNTERPARTY_RESPONSE')}
                    </span>
                  </div>

                  <p className="text-slate-300 bg-slate-900/70 p-2.5 rounded border border-slate-800 text-xs">
                    {trace?.verification?.rationale || commitment.verification_result?.rationale || 
                      'Awaiting fresh counterparty evidence. VerificationGate evaluates independent proof before task closure.'}
                  </p>

                  {/* Fresh Evidence for Verification */}
                  {trace?.verification?.fresh_evidence?.length > 0 && (
                    <div className="space-y-1 pt-1">
                      <span className="text-[10px] font-mono uppercase text-emerald-400 font-semibold block">
                        Fresh Corroborating Evidence Used for Verification:
                      </span>
                      {trace.verification.fresh_evidence.map((fe, idx) => (
                        <div key={idx} className="p-2 rounded bg-emerald-950/30 border border-emerald-800/60 text-emerald-300 text-xs">
                          <div className="flex items-center space-x-2 font-mono text-[10px]">
                            <span className="font-bold">[{fe.source_id}]</span>
                            <span>{fe.title}</span>
                          </div>
                          <p className="text-slate-300 italic text-[11px] mt-0.5">"{fe.snippet}"</p>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Final Outcome Box */}
                  <div className={`p-3 rounded-lg border flex items-start space-x-3 mt-2 ${
                    currentState === 'RESOLVED'
                      ? 'bg-emerald-950/40 border-emerald-500/60 text-emerald-200'
                      : currentState === 'FAILED'
                      ? 'bg-rose-950/40 border-rose-500/60 text-rose-200'
                      : 'bg-blue-950/30 border-blue-800/60 text-blue-200'
                  }`}>
                    {currentState === 'RESOLVED' ? (
                      <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
                    ) : currentState === 'FAILED' ? (
                      <XCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
                    ) : (
                      <Activity className="w-5 h-5 text-blue-400 shrink-0 mt-0.5 animate-pulse" />
                    )}
                    <div>
                      <div className="font-bold text-xs uppercase font-mono tracking-wider">
                        Outcome: {currentState}
                      </div>
                      <p className="text-slate-300 text-xs mt-0.5">
                        {trace?.final_outcome?.summary || (
                          currentState === 'RESOLVED' 
                            ? 'Commitment successfully resolved with multi-source independent verification.'
                            : 'Currently undergoing active recovery and verification loop.'
                        )}
                      </p>
                    </div>
                  </div>

                </div>
              </div>

            </div>

          </div>
        )}

        {/* ==================================================================== */}
        {/* TAB 2: AUDIT LOG TIMELINE                                            */}
        {/* ==================================================================== */}
        {activeViewTab === 'timeline' && (
          <div className="space-y-3">
            <div className="flex items-center justify-between text-slate-400 text-[11px] font-mono border-b border-slate-800 pb-2">
              <span className="uppercase font-bold text-slate-300">Authoritative Audit Trail</span>
              <span className="text-[10px]">Source: SQLite Immutable Log (`agent_events`)</span>
            </div>

            <div className="space-y-2">
              {(trace?.timeline || []).map((t, idx) => (
                <div key={idx} className="p-3 rounded-lg bg-slate-950 border border-slate-800/80 space-y-1.5 font-mono text-[11px]">
                  <div className="flex items-center justify-between text-slate-400">
                    <span className="font-bold text-blue-400">{t.actor}</span>
                    <span className="text-[10px] text-slate-500">{new Date(t.timestamp).toLocaleString()}</span>
                  </div>
                  <div className="flex items-center space-x-2">
                    <span className="px-1.5 py-0.2 rounded text-[10px] bg-slate-800 text-slate-300 uppercase">
                      {t.event_type}
                    </span>
                    <span className={`px-1.5 py-0.2 rounded text-[10px] ${
                      t.result_status === 'SUCCESS' ? 'bg-emerald-950 text-emerald-400 border border-emerald-900' : 'bg-slate-800 text-slate-400'
                    }`}>
                      {t.result_status}
                    </span>
                    {t.state_after && (
                      <span className="text-amber-400 text-[10px]">→ {t.state_after}</span>
                    )}
                  </div>
                  <p className="font-sans text-xs text-slate-200 mt-1">{t.summary}</p>
                  {t.rationale && (
                    <p className="font-sans text-[11px] text-slate-400 italic">"{t.rationale}"</p>
                  )}
                </div>
              ))}

              {(!trace?.timeline || trace.timeline.length === 0) && (
                <div className="p-6 text-center text-slate-500 text-xs font-mono">
                  No historical telemetry records found in audit database for this commitment.
                </div>
              )}
            </div>
          </div>
        )}

        {/* ==================================================================== */}
        {/* TAB 3: EVIDENCE REPOSITORY                                           */}
        {/* ==================================================================== */}
        {activeViewTab === 'evidence' && (
          <div className="space-y-4">
            <div className="flex items-center justify-between text-slate-400 text-[11px] font-mono border-b border-slate-800 pb-2">
              <span className="uppercase font-bold text-slate-300">Corroborated Workspace Evidence &amp; Intelligence</span>
              <span className="text-[10px]">{trace?.evidence?.length || commitment.evidence_references?.length || 0} Records</span>
            </div>

            {/* SYNTHESIZED ASSESSMENT FINDING */}
            <div className="p-3.5 rounded-xl bg-blue-950/25 border border-blue-800/60 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-mono uppercase font-bold text-blue-300 flex items-center space-x-1.5">
                  <Sparkles className="w-3.5 h-3.5 text-blue-400" />
                  <span>Synthesized Multi-Source Finding</span>
                </span>
                <div className="flex items-center space-x-1.5">
                  {assessment?.is_blocking_downstream && (
                    <span className="px-1.5 py-0.5 rounded text-[9px] font-mono uppercase bg-rose-950/80 text-rose-300 border border-rose-800/80 font-bold">
                      Downstream Work Blocked
                    </span>
                  )}
                  <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-blue-900/60 text-blue-200 border border-blue-700">
                    {Math.round((assessment?.confidence || 0.96) * 100)}% Confidence
                  </span>
                </div>
              </div>
              <p className="text-slate-100 text-xs font-semibold leading-relaxed">
                {assessment?.finding || "Multi-source evidence corroborated across workspace records."}
              </p>
              {assessment?.rationale && (
                <p className="text-slate-400 italic text-[11px]">
                  "{assessment.rationale}"
                </p>
              )}
            </div>

            {/* CROSS-SOURCE CORROBORATION */}
            {corroborations.length > 0 && (
              <div className="p-3.5 rounded-xl bg-emerald-950/25 border border-emerald-500/50 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-mono uppercase font-bold text-emerald-300 flex items-center space-x-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                    <span>Cross-Source Corroboration ({corroborations.length})</span>
                  </span>
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-mono uppercase bg-emerald-900/60 text-emerald-200 border border-emerald-700">
                    Corroborated
                  </span>
                </div>
                {corroborations.map((corr, cIdx) => (
                  <p key={cIdx} className="text-emerald-100 text-[11px] leading-snug">
                    {corr}
                  </p>
                ))}
              </div>
            )}

            {/* EVIDENCE GAP / MISSING RECORD */}
            {evidenceGaps.length > 0 && (
              <div className="p-3.5 rounded-xl bg-amber-950/25 border border-amber-500/50 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-mono uppercase font-bold text-amber-300 flex items-center space-x-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                    <span>Expected Evidence Gap / Missing Record ({evidenceGaps.length})</span>
                  </span>
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-mono uppercase bg-amber-900/60 text-amber-200 border border-amber-700">
                    Evidence Gap
                  </span>
                </div>
                {evidenceGaps.map((gap, gIdx) => (
                  <p key={gIdx} className="text-amber-100 text-[11px] leading-snug">
                    {gap}
                  </p>
                ))}
              </div>
            )}

            {/* CROSS-SOURCE EVIDENCE CONFLICT ALERT (GENUINE CONTRADICTIONS ONLY) */}
            {conflicts.length > 0 && (
              <div className="p-3.5 rounded-xl bg-rose-950/25 border border-rose-500/60 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-mono uppercase font-bold text-rose-300 flex items-center space-x-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                    <span>Cross-Source Evidence Contradiction ({conflicts.length})</span>
                  </span>
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-mono uppercase bg-rose-900/60 text-rose-200 border border-rose-700">
                    Conflict Detected
                  </span>
                </div>
                {conflicts.map((conf, cIdx) => (
                  <div key={cIdx} className="p-2.5 rounded bg-rose-950/40 border border-rose-900/60 space-y-1 text-xs">
                    <div className="flex items-center space-x-2 font-mono text-[10px]">
                      <span className="px-1.5 py-0.5 rounded bg-rose-900/80 text-rose-200 font-bold border border-rose-700/60">
                        {conf.source_a}
                      </span>
                      <span className="text-rose-400 font-bold">⟷</span>
                      <span className="px-1.5 py-0.5 rounded bg-rose-900/80 text-rose-200 font-bold border border-rose-700/60">
                        {conf.source_b}
                      </span>
                      <span className="text-rose-400/80 ml-auto uppercase text-[9px]">
                        [{conf.conflict_type}]
                      </span>
                    </div>
                    <p className="text-rose-100 text-[11px] leading-snug">
                      {conf.description}
                    </p>
                  </div>
                ))}
              </div>
            )}

            {/* FACT VS INFERENCE BREAKDOWN */}
            {(factualClaims.length > 0 || inferentialClaims.length > 0) && (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {/* DOCUMENTARY FACTS */}
                <div className="p-3 rounded-lg bg-emerald-950/20 border border-emerald-800/60 space-y-2">
                  <div className="flex items-center justify-between border-b border-emerald-900/60 pb-1.5">
                    <span className="text-[10px] font-mono uppercase font-bold text-emerald-300 flex items-center space-x-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                      <span>Documentary Facts ({factualClaims.length})</span>
                    </span>
                    <span className="text-[9px] font-mono text-emerald-400/80 uppercase">Verified Records</span>
                  </div>
                  <div className="space-y-1.5">
                    {factualClaims.map((claim, idx) => (
                      <div key={idx} className="p-2 rounded bg-slate-900/80 border border-emerald-900/40 space-y-0.5 text-xs">
                        <div className="flex items-center justify-between font-mono text-[10px]">
                          <span className="font-bold text-emerald-400">[{claim.source_id}]</span>
                          <span className="text-slate-400">{Math.round((claim.confidence || 0.95) * 100)}% Conf</span>
                        </div>
                        <p className="text-slate-200 text-[11px] leading-snug">{claim.claim}</p>
                      </div>
                    ))}
                  </div>
                </div>

                {/* ANALYTICAL INFERENCES */}
                <div className="p-3 rounded-lg bg-purple-950/20 border border-purple-800/60 space-y-2">
                  <div className="flex items-center justify-between border-b border-purple-900/60 pb-1.5">
                    <span className="text-[10px] font-mono uppercase font-bold text-purple-300 flex items-center space-x-1.5">
                      <Cpu className="w-3.5 h-3.5 text-purple-400" />
                      <span>Analytical Inferences ({inferentialClaims.length})</span>
                    </span>
                    <span className="text-[9px] font-mono text-purple-400/80 uppercase">Derived Insights</span>
                  </div>
                  <div className="space-y-1.5">
                    {inferentialClaims.map((claim, idx) => (
                      <div key={idx} className="p-2 rounded bg-slate-900/80 border border-purple-900/40 space-y-0.5 text-xs">
                        <div className="flex items-center justify-between font-mono text-[10px]">
                          <span className="font-bold text-purple-400">[{claim.source_id}]</span>
                          <span className="text-slate-400">{Math.round((claim.confidence || 0.89) * 100)}% Conf</span>
                        </div>
                        <p className="text-slate-200 text-[11px] leading-snug">{claim.claim}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}

            <div className="space-y-3 pt-2">
              <span className="text-[10px] font-mono uppercase font-semibold text-slate-400 block">
                All Corroborated Workspace Records
              </span>

              {(trace?.evidence || commitment.evidence_references || []).map((ev, idx) => (
                <div key={idx} className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-blue-950/80 text-blue-300 border border-blue-800">
                        {ev.source_type}
                      </span>
                      <span className="font-mono text-slate-300 font-bold text-xs">{ev.source_id}</span>
                    </div>
                    <span className="font-mono text-[10px] text-slate-400">
                      Confidence: {Math.round((ev.confidence || 0.9) * 100)}%
                    </span>
                  </div>
                  <h4 className="font-bold text-slate-200 text-xs">{ev.title}</h4>
                  <div className="bg-slate-900 p-2.5 rounded border border-slate-800 text-slate-300 italic text-xs">
                    "{ev.snippet}"
                  </div>
                  {ev.timestamp && (
                    <div className="text-[10px] font-mono text-slate-500 text-right">
                      Recorded: {new Date(ev.timestamp).toLocaleString()}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

      </div>

    </div>
  );
}
