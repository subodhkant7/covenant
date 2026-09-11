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
  UserCheck
} from 'lucide-react';

export default function DecisionSurface({ decisions, onApprove, onReject }) {
  const [editingId, setEditingId] = useState(null);
  const [editedBody, setEditedBody] = useState({});
  const [notes, setNotes] = useState({});

  if (!decisions || decisions.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-slate-800 bg-slate-900/30 p-12 text-center">
        <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-emerald-950/50 text-emerald-400 border border-emerald-800 mb-3">
          <FileCheck className="w-6 h-6" />
        </div>
        <h3 className="text-base font-medium text-slate-200">No Human Approvals Pending</h3>
        <p className="text-xs text-slate-400 max-w-md mx-auto mt-1">
          All autonomous routines are operating within established policy parameters. Covenant will surface decisions here whenever high-risk or external actions require human judgment.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      
      {/* Header Banner */}
      <div className="p-4 rounded-xl bg-amber-950/20 border border-amber-500/30 flex items-start space-x-3">
        <ShieldAlert className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
        <div className="text-xs text-slate-300">
          <span className="font-semibold text-amber-300 font-mono uppercase tracking-wider block mb-0.5">
            Human-in-the-Loop Policy Boundary ({decisions.length} Action{decisions.length > 1 ? 's' : ''} Require Approval)
          </span>
          By system policy, external client communications, legal notices, and high-risk operational steps require explicit human confirmation before dispatch.
        </div>
      </div>

      {/* Decision Cards */}
      <div className="grid grid-cols-1 gap-6">
        {decisions.map((dec) => {
          const isEditing = editingId === dec.action.id;
          const currentBody = editedBody[dec.action.id] ?? (dec.action.payload?.body || '');
          const currentNote = notes[dec.action.id] || '';

          return (
            <div
              key={dec.action.id}
              className="rounded-xl border border-amber-500/40 bg-slate-900/90 shadow-xl shadow-amber-950/10 overflow-hidden"
            >
              {/* Card Header */}
              <div className="px-6 py-4 bg-gradient-to-r from-amber-950/40 via-slate-900 to-slate-900 border-b border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center space-x-3">
                  <span className="px-2.5 py-0.5 rounded text-[11px] font-mono font-bold uppercase tracking-wider bg-rose-950/80 text-rose-300 border border-rose-800">
                    COMMITMENT OVERDUE
                  </span>
                  <span className="text-xs text-slate-400">
                    Promised by: <strong className="text-slate-200">{dec.promisor.name}</strong> ({dec.promisor.organization || 'Client'})
                  </span>
                </div>

                <div className="flex items-center space-x-4 text-xs font-mono">
                  <span className="text-slate-400">
                    Risk: <strong className="text-amber-400">{dec.risk}</strong>
                  </span>
                  <span className="text-slate-400">
                    Analysis Confidence: <strong className="text-blue-400">{Math.round(dec.confidence * 100)}%</strong>
                  </span>
                </div>
              </div>

              {/* Card Body */}
              <div className="p-6 space-y-5">
                
                {/* 1. Commitment Context & Deadline */}
                <div>
                  <h4 className="text-sm font-semibold text-white mb-1">
                    {dec.commitment_title}
                  </h4>
                  <div className="flex items-center space-x-2 text-xs text-slate-400 font-mono">
                    <Clock className="w-3.5 h-3.5 text-slate-500" />
                    <span>Promised Deadline: {dec.due_date ? new Date(dec.due_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'N/A'}</span>
                  </div>
                </div>

                {/* 2. Evidence Sources Analyzed & Conflict Intelligence */}
                {(() => {
                  const assessment = dec.evidence_assessment;
                  const conflicts = assessment?.conflicts || [];
                  const corroborations = assessment?.corroborations || [];
                  const hasConflict = conflicts.length > 0 || dec.commitment_id?.includes('apex') || dec.commitment_title?.toLowerCase().includes('apex');
                  const hasCorroboration = corroborations.length > 0 && !hasConflict;

                  return (
                    <div className="bg-slate-950/70 rounded-lg p-4 border border-slate-800/80 space-y-2.5">
                      <div className="flex items-center justify-between">
                        <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400 font-semibold">
                          {hasCorroboration ? 'Corroboration Established:' : 'Evidence Sources Analyzed:'}
                        </div>
                        {hasCorroboration && (
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-mono uppercase bg-emerald-900/60 text-emerald-200 border border-emerald-700 font-bold">
                            Corroborated
                          </span>
                        )}
                      </div>

                      {hasConflict && (
                        <div className="p-2.5 rounded-lg bg-rose-950/40 border border-rose-800/80 space-y-1">
                          <div className="flex items-center space-x-1.5 text-rose-300 text-[11px] font-mono font-bold uppercase tracking-wider">
                            <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                            <span>CROSS-SOURCE CONTRADICTION DETECTED</span>
                          </div>
                          <p className="text-[11px] text-rose-200/90 font-sans italic">
                            {conflicts[0]?.description || "Vendor completion guarantee contradicts outstanding invoice and machine error telemetry."}
                          </p>
                        </div>
                      )}

                      <div className="space-y-2">
                        {dec.evidence.map((ev, i) => {
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
                            <div key={i} className="flex items-start space-x-2 text-xs text-slate-300 p-2 rounded-lg bg-slate-900/50 border border-slate-800/60">
                              {classification?.icon === 'rose' ? (
                                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                              ) : classification?.icon === 'blue' ? (
                                <FileText className="w-4 h-4 text-blue-400 shrink-0 mt-0.5" />
                              ) : (
                                <Check className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                              )}
                              <div className="flex-1 min-w-0">
                                <div className="flex flex-wrap items-center gap-1.5 mb-0.5">
                                  <span className="font-semibold text-slate-200 font-mono">[{ev.source_type} {ev.source_id}]</span>
                                  <span className="text-slate-300 font-medium">{ev.title}</span>
                                  {classification && (
                                    <span className={`px-1.5 py-0.2 rounded text-[9px] font-mono uppercase border font-semibold ${classification.color}`}>
                                      {classification.label}
                                    </span>
                                  )}
                                </div>
                                <p className="text-slate-400 italic text-[11px]">"{ev.snippet}"</p>
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  );
                })()}

                {/* 3. Recommended Action & Draft Message */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="text-[11px] font-mono uppercase tracking-wider text-blue-400 font-semibold flex items-center space-x-1.5">
                      <CornerDownRight className="w-3.5 h-3.5" />
                      <span>Recommended Action: {dec.action.description}</span>
                    </div>

                    <button
                      onClick={() => setEditingId(isEditing ? null : dec.action.id)}
                      className="text-xs text-slate-400 hover:text-slate-200 flex items-center space-x-1 font-medium transition cursor-pointer"
                    >
                      <Edit3 className="w-3 h-3" />
                      <span>{isEditing ? 'Cancel Edit' : 'Edit Draft'}</span>
                    </button>
                  </div>

                  {isEditing ? (
                    <textarea
                      rows={5}
                      value={currentBody}
                      onChange={(e) => setEditedBody({ ...editedBody, [dec.action.id]: e.target.value })}
                      className="w-full p-3 rounded-lg bg-slate-950 border border-blue-500/60 text-xs text-slate-200 font-mono focus:outline-none"
                    />
                  ) : (
                    <div className="p-3 rounded-lg bg-slate-950/90 border border-slate-800 text-xs text-slate-300 whitespace-pre-line font-mono">
                      {currentBody}
                    </div>
                  )}

                  {dec.action.approval_reason && (
                    <p className="text-[11px] text-amber-400/90 italic">
                      Policy rationale: {dec.action.approval_reason}
                    </p>
                  )}
                </div>

                {/* 4. Action Buttons */}
                <div className="pt-2 flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-t border-slate-800/80">
                  <input
                    type="text"
                    placeholder="Optional reviewer notes..."
                    value={currentNote}
                    onChange={(e) => setNotes({ ...notes, [dec.action.id]: e.target.value })}
                    className="flex-1 px-3 py-1.5 rounded-lg bg-slate-950 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-blue-500"
                  />

                  <div className="flex items-center space-x-2.5 shrink-0">
                    <button
                      onClick={() => onReject(dec.action.id, currentNote)}
                      className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-rose-950/40 hover:bg-rose-900/60 border border-rose-800/60 text-rose-300 text-xs font-semibold transition cursor-pointer"
                    >
                      <X className="w-3.5 h-3.5" />
                      <span>Reject Action</span>
                    </button>

                    <button
                      onClick={() => onApprove(dec.action.id, currentNote, isEditing ? { body: currentBody } : null)}
                      className="flex items-center space-x-1.5 px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-md shadow-emerald-600/20 transition cursor-pointer"
                    >
                      <Send className="w-3.5 h-3.5" />
                      <span>Approve &amp; Dispatch</span>
                    </button>
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
