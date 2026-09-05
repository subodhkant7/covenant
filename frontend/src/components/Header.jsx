import React from 'react';
import { 
  ShieldCheck, 
  Radar, 
  RotateCcw, 
  Layers, 
  CheckCircle2, 
  AlertTriangle, 
  Activity,
  ArrowDownLeft,
  ArrowUpRight
} from 'lucide-react';

export default function Header({ 
  stats, 
  activeTab, 
  setActiveTab, 
  onScan, 
  onSeed, 
  scanning 
}) {
  return (
    <header className="border-b border-slate-800 bg-[#0d121a]/95 backdrop-blur-md sticky top-0 z-40">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3.5 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        
        {/* Brand & Tagline */}
        <div className="flex items-center space-x-3.5">
          <div className="relative flex items-center justify-center w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-700 shadow-md shadow-blue-500/20 text-white">
            <ShieldCheck className="w-6 h-6" />
            <div className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-400 border-2 border-[#0d121a]"></div>
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="text-lg font-bold tracking-tight text-white font-mono">COVENANT</span>
              <span className="px-2 py-0.5 text-[10px] font-semibold tracking-wider uppercase rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                Agent Kernel v0.1
              </span>
            </div>
            <p className="text-xs text-slate-400 font-normal">
              Autonomous Commitment-Resolution &amp; Lifecycle Agent
            </p>
          </div>
        </div>

        {/* Live Operational Metrics */}
        {stats && (
          <div className="flex items-center space-x-2 text-xs">
            <div className="px-3 py-1.5 rounded-lg bg-slate-900/90 border border-slate-800 flex items-center space-x-2">
              <ArrowDownLeft className="w-3.5 h-3.5 text-blue-400" />
              <span className="text-slate-400">They Owe:</span>
              <span className="font-bold text-slate-200 font-mono">{stats.they_owe_count}</span>
            </div>
            <div className="px-3 py-1.5 rounded-lg bg-slate-900/90 border border-slate-800 flex items-center space-x-2">
              <ArrowUpRight className="w-3.5 h-3.5 text-indigo-400" />
              <span className="text-slate-400">We Owe:</span>
              <span className="font-bold text-slate-200 font-mono">{stats.we_owe_count}</span>
            </div>
            <div className={`px-3 py-1.5 rounded-lg border flex items-center space-x-2 ${
              stats.overdue_count > 0 
                ? 'bg-rose-950/40 border-rose-800/60 text-rose-300' 
                : 'bg-slate-900/90 border-slate-800 text-slate-400'
            }`}>
              <AlertTriangle className="w-3.5 h-3.5" />
              <span>Overdue:</span>
              <span className="font-bold font-mono">{stats.overdue_count}</span>
            </div>
            <div className={`px-3 py-1.5 rounded-lg border flex items-center space-x-2 ${
              stats.awaiting_approval_count > 0 
                ? 'bg-amber-950/40 border-amber-800/60 text-amber-300 animate-pulse' 
                : 'bg-slate-900/90 border-slate-800 text-slate-400'
            }`}>
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Approvals:</span>
              <span className="font-bold font-mono">{stats.awaiting_approval_count}</span>
            </div>
          </div>
        )}

        {/* Agent Controls */}
        <div className="flex items-center space-x-2.5">
          <button
            onClick={onScan}
            disabled={scanning}
            className="flex items-center space-x-2 px-3.5 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-medium shadow-sm transition duration-150 ease-in-out cursor-pointer"
          >
            <Radar className={`w-3.5 h-3.5 ${scanning ? 'animate-spin' : ''}`} />
            <span>{scanning ? 'Agent Scanning...' : 'Run Agent Cycle'}</span>
          </button>
          
          <button
            onClick={onSeed}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700 text-slate-300 text-xs font-medium transition cursor-pointer"
            title="Reset Northstar Studio Workspace Dataset"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Reseed</span>
          </button>
        </div>

      </div>

      {/* Navigation Tabs */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 flex space-x-6 text-xs font-medium border-t border-slate-800/60 overflow-x-auto">
        <button
          onClick={() => setActiveTab('map')}
          className={`py-2.5 border-b-2 flex items-center space-x-2 transition ${
            activeTab === 'map'
              ? 'border-blue-500 text-blue-400 font-semibold'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Layers className="w-4 h-4" />
          <span>Operational Commitment Map</span>
        </button>

        <button
          onClick={() => setActiveTab('decisions')}
          className={`py-2.5 border-b-2 flex items-center space-x-2 transition ${
            activeTab === 'decisions'
              ? 'border-amber-500 text-amber-400 font-semibold'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <CheckCircle2 className="w-4 h-4" />
          <span>Decision Surface</span>
          {stats?.awaiting_approval_count > 0 && (
            <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-amber-500/20 text-amber-300 border border-amber-500/30">
              {stats.awaiting_approval_count}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('directional')}
          className={`py-2.5 border-b-2 flex items-center space-x-2 transition ${
            activeTab === 'directional'
              ? 'border-indigo-500 text-indigo-400 font-semibold'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <ArrowDownLeft className="w-4 h-4" />
          <span>They Owe / We Owe</span>
        </button>

        <button
          onClick={() => setActiveTab('timeline')}
          className={`py-2.5 border-b-2 flex items-center space-x-2 transition ${
            activeTab === 'timeline'
              ? 'border-emerald-500 text-emerald-400 font-semibold'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Activity className="w-4 h-4" />
          <span>Agent Telemetry Log</span>
        </button>
      </div>
    </header>
  );
}
