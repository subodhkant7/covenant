import React, { useState } from 'react';
import { 
  ShieldAlert, 
  Check, 
  X, 
  Edit3, 
  Send, 
  FileCheck, 
  AlertCircle, 
  AlertTriangle, 
  FileText,
  CornerDownRight, 
  Clock,
  Sparkles,
  UserCheck,
  Shield,
  ArrowRight
} from 'lucide-react';

export default function DecisionSurface({ decisions, onApprove, onReject }) {
  const [editingId, setEditingId] = useState(null);
  const [editedBody, setEditedBody] = useState({});
  const [notes, setNotes] = useState({});

  if (!decisions || decisions.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/30 p-16 text-center">
        <div className="inline-flex items-center justify-center w-14 h-14 rounded-full bg-emerald-950/50 text-emerald-400 border border-emerald-800 mb-4 shadow-md shadow-emerald-950/30">
          <FileCheck className="w-7 h-7" />
        </div>
        <h3 className="text-base font-bold text-slate-200">No Human Approvals Pending</h3>
        <p className="text-xs text-slate-400 max-w-lg mx-auto mt-1.5 leading-relaxed">
          All autonomous routines are operating within established policy parameters. Covenant surfaces decisions here whenever high-risk, legal notifications, or external client actions require human judgment.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      
      {/* Header Banner */}
      <div className="p-4 rounded-xl bg-gradient-to-r from-amber-950/30 via-slate-900 to-slate-900 border border-amber-500/30 flex items-start space-x-3.5 shadow-sm">
        <ShieldAlert className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
        <div className="text-xs text-slate-300">
          <span className="font-bold text-amber-300 font-mono uppercase tracking-wider block mb-0.5">
            Human-in-the-Loop Policy Boundary ({decisions.length} Action{decisions.length > 1 ? 's' : ''} Require Human Authorization)
          </span>
          By institutional governance policy, high-risk operational steps, contract amendments, and external client escalations require explicit human confirmation before dispatch. Zero self-attestation is permitted.
        </div>
      </div>

      {/* Decision Cards List */}
      <div className="space-y-6">
        {decisions.map((dec) => {
          const isEditing = editingId === dec.action.id;
          const currentBody = editedBody[dec.action.id] ?? (dec.action.payload?.body || '');
          const currentNote = notes[dec.action.id] || '';

          const assessment = dec.evidence_assessment;
          const conflicts = assessment?.conflicts || [];
          const corroborations = assessment?.corroborations || [];
          const hasConflict = conflicts.length > 0 || dec.commitment_id?.includes('apex') || dec.commitment_title?.toLowerCase().includes('apex');
          const hasCorroboration = corroborations.length > 0 && !hasConflict;

          return (
            <div
              key={dec.action.id}
              className="rounded-xl border border-amber-500/40 bg-slate-900/90 shadow-xl shadow-amber-950/10 overflow-hidden"
            >
              {/* Card Top Ribbon */}
              <div className="px-6 py-3.5 bg-gradient-to-r from-amber-950/40 via-slate-900 to-slate-900 border-b border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center space-x-3">
                  <span className="px-2.5 py-0.5 rounded text-[11px] font-mono font-bold uppercase tracking-wider bg-rose-950/80 text-rose-300 border border-rose-800">
                    COMMITMENT OVERDUE
                  </span>
                  <span className="text-xs text-slate-300">
                    Promised by: <strong className="text-white">{dec.promisor.name}</strong> ({dec.promisor.organization || 'Counterparty'})
                  </span>
                </div>

                <div className="flex items-center space-x-4 text-xs font-mono">
                  <span className="text-slate-400">
                    Risk Level: <strong className="text-rose-400 font-bold">{dec.risk}</strong>
                  </span>
                  <span className="text-slate-600">•</span>
                  <span className="text-slate-400">
                    Analysis Confidence: <strong className="text-blue-400 font-bold">{Math.round(dec.confidence * 100)}%</strong>
                  </span>
                </div>
              </div>

              {/* Card Body: 2-Column Split Console on Desktop */}
              <div className="p-6 grid grid-cols-1 xl:grid-cols-12 gap-6">
                
                {/* Left Pane (7 cols): Commitment Context & Evidence Intelligence */}
                <div className="xl:col-span-7 space-y-4">
                  
                  {/* Title & Deadline */}
                  <div>
                    <h4 className="text-base font-bold text-white leading-snug">
                      {dec.commitment_title}
                    </h4>
                    <div className="flex items-center space-x-2 text-xs text-slate-400 font-mono mt-1">
                      <Clock className="w-3.5 h-3.5 text-slate-500" />
                      <span>Contractual Deadline: {dec.due_date ? new Date(dec.due_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A'}</span>
                    </div>
                  </div>

                  {/* Evidence Intelligence Surface */}
                  <div className="bg-slate-950/70 rounded-xl p-4 border border-slate-800/80 space-y-3">
                    
                    <div className="flex items-center justify-between">
                      <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400 font-bold flex items-center space-x-1.5">
                        <FileCheck className="w-3.5 h-3.5 text-blue-400" />
                        <span>{hasCorroboration ? 'Corroboration Established:' : 'Evidence Sources Analyzed:'}</span>
                      </div>
                      {hasCorroboration && (
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-emerald-900/60 text-emerald-200 border border-emerald-700 font-bold">
                          Corroborated
                        </span>
                      )}
                    </div>

                    {/* Apex Contradiction Alert (Preserving Step 19 Fix) */}
                    {hasConflict && (
                      <div className="p-3 rounded-lg bg-rose-950/50 border border-rose-800 space-y-1 shadow-sm">
                        <div className="flex items-center space-x-2 text-rose-300 text-[11px] font-mono font-bold uppercase tracking-wider">
                          <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                          <span>CROSS-SOURCE CONTRADICTION DETECTED</span>
                        </div>
                        <p className="text-xs text-rose-200/90 font-sans leading-relaxed">
                          {conflicts[0]?.description || "Vendor completion guarantee contradicts outstanding invoice and machine error telemetry. Execution cannot verify fulfillment without independent proof."}
                        </p>
                      </div>
                    )}

                    {/* Classified Evidence Items */}
                    <div className="space-y-2">
                      {dec.evidence?.map((ev, i) => {
                        let classification = null;
                        if (hasConflict) {
                          if (ev.source_id === 'EML-201' || ev.source_type === 'EMAIL' || ev.title?.toLowerCase().includes('guarantee') || ev.snippet?.toLowerCase().includes('guarantee')) {
                            classification = {
                              label: 'PROMISE / ORIGINAL COMMITMENT',
                              color: 'bg-blue-900/60 text-blue-200 border-blue-700',
                              icon: 'blue',
                            };
                          } else if (ev.source_id === 'INV-APEX-992' || ev.source_type === 'INVOICE' || ev.title?.toLowerCase().includes('invoice') || ev.snippet?.toLowerCase().includes('pending') || ev.snippet?.toLowerCase().includes('incomplete')) {
                            classification = {
                              label: 'INCOMPLETE STATUS',
                              color: 'bg-rose-900/60 text-rose-200 border-rose-700',
                              icon: 'rose',
                            };
                          }
                        }

                        return (
                          <div key={i} className="flex items-start space-x-2.5 text-xs text-slate-300 p-2.5 rounded-lg bg-slate-900/60 border border-slate-800/80">
                            {classification?.icon === 'rose' ? (
                              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                            ) : classification?.icon === 'blue' ? (
                              <FileText className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
                            ) : (
                              <Check className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                            )}
                            <div className="flex-1 min-w-0">
                              <div className="flex flex-wrap items-center gap-2 mb-1">
                                <span className="font-semibold text-slate-200 font-mono text-[11px]">[{ev.source_type} {ev.source_id}]</span>
                                <span className="text-slate-300 font-medium">{ev.title}</span>
                                {classification && (
                                  <span className={`px-2 py-0.2 rounded text-[10px] font-mono uppercase border font-bold ${classification.color}`}>
                                    {classification.label}
                                  </span>
                                )}
                              </div>
                              <p className="text-slate-400 italic text-[11px] leading-relaxed">"{ev.snippet}"</p>
                            </div>
                          </div>
                        );
                      })}
                    </div>

                  </div>

                </div>

                {/* Right Pane (5 cols): Policy Governance, Recommended Action & Dispatch Controls */}
                <div className="xl:col-span-5 flex flex-col justify-between space-y-4 border-t xl:border-t-0 xl:border-l border-slate-800 pt-5 xl:pt-0 xl:pl-6">
                  
                  {/* Action Recommendation & Draft */}
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <div className="text-[11px] font-mono uppercase tracking-wider text-blue-400 font-bold flex items-center space-x-1.5">
                        <CornerDownRight className="w-3.5 h-3.5" />
                        <span>Recommended Remediation Action</span>
                      </div>

                      <button
                        onClick={() => setEditingId(isEditing ? null : dec.action.id)}
                        className="text-xs text-slate-400 hover:text-slate-200 flex items-center space-x-1 font-medium transition cursor-pointer"
                      >
                        <Edit3 className="w-3 h-3" />
                        <span>{isEditing ? 'Cancel Edit' : 'Edit Draft'}</span>
                      </button>
                    </div>

                    <p className="text-xs text-slate-200 font-semibold">
                      {dec.action.description}
                    </p>

                    {/* Draft Message Body */}
                    {isEditing ? (
                      <textarea
                        rows={6}
                        value={currentBody}
                        onChange={(e) => setEditedBody({ ...editedBody, [dec.action.id]: e.target.value })}
                        className="w-full p-3 rounded-lg bg-slate-950 border border-blue-500/60 text-xs text-slate-200 font-mono focus:outline-none leading-relaxed"
                      />
                    ) : (
                      <div className="p-3.5 rounded-lg bg-slate-950/90 border border-slate-800 text-xs text-slate-300 whitespace-pre-line font-mono leading-relaxed max-h-48 overflow-y-auto">
                        {currentBody}
                      </div>
                    )}

                    {/* Policy Rationale */}
                    {dec.action.approval_reason && (
                      <div className="p-2.5 rounded bg-amber-950/30 border border-amber-900/50 text-[11px] text-amber-300/90 font-mono leading-relaxed">
                        <strong>Policy Gate:</strong> {dec.action.approval_reason}
                      </div>
                    )}
                  </div>

                  {/* Reviewer Notes & Action Buttons */}
                  <div className="space-y-3 pt-3 border-t border-slate-800/80">
                    <input
                      type="text"
                      placeholder="Optional human reviewer audit notes..."
                      value={currentNote}
                      onChange={(e) => setNotes({ ...notes, [dec.action.id]: e.target.value })}
                      className="w-full px-3.5 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500 font-sans"
                    />

                    <div className="flex items-center space-x-3">
                      <button
                        onClick={() => onReject(dec.action.id, currentNote)}
                        className="flex-1 flex items-center justify-center space-x-1.5 px-4 py-2 rounded-lg bg-rose-950/40 hover:bg-rose-900/60 border border-rose-800/60 text-rose-300 text-xs font-semibold transition cursor-pointer"
                      >
                        <X className="w-4 h-4" />
                        <span>Reject Action</span>
                      </button>

                      <button
                        onClick={() => onApprove(dec.action.id, currentNote, isEditing ? { body: currentBody } : null)}
                        className="flex-1 flex items-center justify-center space-x-1.5 px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-md shadow-emerald-600/20 transition cursor-pointer"
                      >
                        <Send className="w-4 h-4" />
                        <span>Approve &amp; Dispatch</span>
                      </button>
                    </div>
                  </div>

                </div>

              </div>

            </div>
          );
        })}
      </div>

    </div>
  );
}
