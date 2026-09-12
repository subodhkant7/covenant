import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import CommitmentMap from './components/CommitmentMap';
import DecisionSurface from './components/DecisionSurface';
import TheyOweWeOwe from './components/TheyOweWeOwe';
import CommitmentDetail from './components/CommitmentDetail';
import AgentTimeline from './components/AgentTimeline';
import { 
  fetchStats, 
  fetchCommitments, 
  fetchPendingDecisions, 
  fetchEvents,
  triggerScan,
  triggerSeed,
  approveDecision,
  rejectDecision,
  triggerVerification
} from './services/api';

export default function App() {
  const [activeTab, setActiveTab] = useState('map');
  const [stats, setStats] = useState(null);
  const [commitments, setCommitments] = useState([]);
  const [decisions, setDecisions] = useState([]);
  const [events, setEvents] = useState([]);
  const [selectedCommitment, setSelectedCommitment] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadAllData = async () => {
    try {
      const [statsData, commsData, decsData, evtsData] = await Promise.all([
        fetchStats(),
        fetchCommitments(),
        fetchPendingDecisions(),
        fetchEvents(50),
      ]);
      setStats(statsData);
      setCommitments(commsData);
      setDecisions(decsData);
      setEvents(evtsData);

      // Refresh selected commitment if open
      if (selectedCommitment) {
        const updated = commsData.find(c => c.id === selectedCommitment.id);
        if (updated) setSelectedCommitment(updated);
      }
    } catch (err) {
      console.error('Error loading Covenant state:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAllData();
    const interval = setInterval(loadAllData, 10000);
    return () => clearInterval(interval);
  }, []);

  const handleScan = async () => {
    setScanning(true);
    try {
      await triggerScan();
      await loadAllData();
    } catch (err) {
      console.error('Scan error:', err);
    } finally {
      setScanning(false);
    }
  };

  const handleSeed = async () => {
    setScanning(true);
    try {
      await triggerSeed();
      await loadAllData();
    } catch (err) {
      console.error('Seed error:', err);
    } finally {
      setScanning(false);
    }
  };

  const handleApprove = async (actionId, notes, editedPayload) => {
    try {
      await approveDecision(actionId, notes, editedPayload);
      await loadAllData();
    } catch (err) {
      alert('Approval error: ' + err.message);
    }
  };

  const handleReject = async (actionId, notes) => {
    try {
      await rejectDecision(actionId, notes);
      await loadAllData();
    } catch (err) {
      alert('Reject error: ' + err.message);
    }
  };

  const handleVerify = async (commitmentId) => {
    try {
      await triggerVerification(commitmentId, { simulated_signed_approval: true });
      await loadAllData();
    } catch (err) {
      alert('Verification error: ' + err.message);
    }
  };

  const handleSimulateReply = async (commitmentId) => {
    try {
      await simulateReply(commitmentId);
      await loadAllData();
    } catch (err) {
      alert('Simulation error: ' + err.message);
    }
  };

  return (
    <div className="min-h-screen bg-[#090d12] text-slate-200 flex flex-col font-sans">
      
      {/* App Header */}
      <Header
        stats={stats}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onScan={handleScan}
        onSeed={handleSeed}
        scanning={scanning}
      />

      {/* Main Content Area */}
      <main className="w-full px-4 sm:px-6 lg:px-8 xl:px-10 py-5 flex-1">
        {loading ? (
          <div className="py-24 text-center">
            <div className="inline-block w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full animate-spin"></div>
            <p className="mt-3 text-xs font-mono text-slate-400">Loading Covenant Commitment Intelligence...</p>
          </div>
        ) : (
          <>
            {activeTab === 'map' && (
              <CommitmentMap
                commitments={commitments}
                onSelectCommitment={(c) => setSelectedCommitment(c)}
                selectedId={selectedCommitment?.id}
              />
            )}

            {activeTab === 'decisions' && (
              <DecisionSurface
                decisions={decisions}
                onApprove={handleApprove}
                onReject={handleReject}
              />
            )}

            {activeTab === 'directional' && (
              <TheyOweWeOwe
                commitments={commitments}
                onSelectCommitment={(c) => setSelectedCommitment(c)}
              />
            )}

            {activeTab === 'timeline' && (
              <AgentTimeline events={events} />
            )}
          </>
        )}
      </main>

      {/* Detail Inspector Drawer */}
      <CommitmentDetail
        commitment={selectedCommitment}
        onClose={() => setSelectedCommitment(null)}
        onVerify={handleVerify}
        onSimulateReply={handleSimulateReply}
      />

      {/* Bottom Footer / Status Line */}
      <footer className="border-t border-slate-800/80 bg-[#0d121a] py-3 text-[11px] font-mono text-slate-400">
        <div className="w-full px-4 sm:px-6 lg:px-8 xl:px-10 flex flex-col sm:flex-row items-center justify-between gap-2">
          <div>
            <span>Workspace: </span>
            <strong className="text-slate-300">Northstar Studio LLC</strong>
            <span className="mx-2">•</span>
            <span>Persistence: </span>
            <strong className="text-slate-300">SQLite Async WAL</strong>
            <span className="mx-2">•</span>
            <span>LLM: </span>
            <strong className="text-slate-300">Ollama / Pluggable Local</strong>
          </div>
          <div>
            <span>Powered by Strands Agents • Agents for Humans Hackathon</span>
          </div>
        </div>
      </footer>

    </div>
  );
}
