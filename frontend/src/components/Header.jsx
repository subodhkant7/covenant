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
  ArrowUpRight,
  Radio,
  Cpu
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
      
      {/* 1. Brand & Controls Row */}
      <div className="w-full px-6 sm:px-8 lg:px-10 xl:px-12 py-3.5 flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-800/60">
        
        {/* Brand & Tagline */}
        <div className="flex items-center space-x-3.5">
          <div className="relative flex items-center justify-center w-11 h-11 rounded-xl bg-gradient-to-br from-blue-600 to-indigo-700 shadow-md shadow-blue-500/20 text-white shrink-0">
            <ShieldCheck className="w-7 h-7" />
            <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-emerald-400 border-2 border-[#0d121a]"></div>
          </div>
          <div>
            <div className="flex items-center space-x-2.5">
              <span className="text-2xl font-bold tracking-tight text-white font-mono">COVENANT</span>
              <span className="px-2.5 py-0.5 text-xs font-semibold tracking-wider uppercase rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20 font-mono">
                Commitment Intelligence
              </span>
              <span className="hidden sm:inline-flex px-2.5 py-0.5 text-xs font-medium tracking-wide rounded bg-emerald-950/60 text-emerald-300 border border-emerald-800/80 font-mono">
                Strands Agents Runtime
              </span>
            </div>
            <p className="text-xs sm:text-sm text-slate-400 font-normal mt-0.5">
              Commitment Intelligence &amp; Fulfillment Verification
            </p>
          </div>
        </div>

        {/* Agent Controls & Runtime State */}
        <div className="flex items-center space-x-3">
          <div className="hidden lg:flex items-center space-x-2 px-3.5 py-1.5 rounded-lg bg-slate-900/80 border border-slate-800/80 text-xs font-mono text-slate-400">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
            <span className="text-slate-300">Policy Engine:</span>
            <span className="text-emerald-400 font-bold">Deterministic</span>
          </div>

          <button
            onClick={onScan}
            disabled={scanning}
            className="flex items-center space-x-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white text-xs font-semibold shadow-sm transition duration-150 ease-in-out cursor-pointer"
          >
            <Radar className={`w-4 h-4 ${scanning ? 'animate-spin' : ''}`} />
            <span>{scanning ? 'Agent Scanning...' : 'Run Agent Cycle'}</span>
          </button>
          
          <button
            onClick={onSeed}
            className="flex items-center space-x-1.5 px-3.5 py-2 rounded-lg bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700 text-slate-300 text-xs font-medium transition cursor-pointer"
            title="Reset Northstar Studio Workspace Dataset"
          >
            <RotateCcw className="w-4 h-4" />
            <span>Reseed</span>
          </button>
        </div>

      </div>

      {/* 2. Executive KPI Strip (Immediately Below Top Bar) */}
      {stats && (
        <div className="bg-slate-950/40 border-b border-slate-800/50 py-2.5">
          <div className="w-full px-6 sm:px-8 lg:px-10 xl:px-12 flex flex-wrap items-center justify-between gap-3 text-xs">
            
            {/* Core Metrics */}
            <div className="flex flex-wrap items-center gap-3">
              
              {/* They Owe */}
              <div className="px-4 py-1.5 rounded-lg bg-slate-900/90 border border-slate-800 flex items-center space-x-2.5 shadow-sm">
                <ArrowDownLeft className="w-4 h-4 text-blue-400" />
                <span className="text-slate-400 font-medium">They Owe:</span>
                <span className="font-bold text-slate-200 font-mono text-base">{stats.they_owe_count}</span>
                <span className="text-xs text-blue-400/90 font-mono uppercase font-semibold">Inbound</span>
              </div>

              {/* We Owe */}
              <div className="px-4 py-1.5 rounded-lg bg-slate-900/90 border border-slate-800 flex items-center space-x-2.5 shadow-sm">
                <ArrowUpRight className="w-4 h-4 text-indigo-400" />
                <span className="text-slate-400 font-medium">We Owe:</span>
                <span className="font-bold text-slate-200 font-mono text-base">{stats.we_owe_count}</span>
                <span className="text-xs text-indigo-400/90 font-mono uppercase font-semibold">Outbound</span>
              </div>

              {/* Overdue */}
              <div className={`px-4 py-1.5 rounded-lg border flex items-center space-x-2.5 shadow-sm ${
                stats.overdue_count > 0 
                  ? 'bg-rose-950/50 border-rose-800/70 text-rose-300' 
                  : 'bg-slate-900/90 border-slate-800 text-slate-400'
              }`}>
                <AlertTriangle className={`w-4 h-4 ${stats.overdue_count > 0 ? 'text-rose-400 animate-bounce' : ''}`} />
                <span className="font-medium">Overdue:</span>
                <span className="font-bold font-mono text-base">{stats.overdue_count}</span>
                {stats.overdue_count > 0 && (
                  <span className="text-xs font-mono uppercase bg-rose-900/60 px-1.5 py-0.5 rounded text-rose-200 font-bold">
                    Action Req
                  </span>
                )}
              </div>

              {/* Approvals */}
              <div className={`px-4 py-1.5 rounded-lg border flex items-center space-x-2.5 shadow-sm ${
                stats.awaiting_approval_count > 0 
                  ? 'bg-amber-950/50 border-amber-800/70 text-amber-300' 
                  : 'bg-slate-900/90 border-slate-800 text-slate-400'
              }`}>
                <CheckCircle2 className={`w-4 h-4 ${stats.awaiting_approval_count > 0 ? 'text-amber-400 animate-pulse' : ''}`} />
                <span className="font-medium">Approvals:</span>
                <span className="font-bold font-mono text-base">{stats.awaiting_approval_count}</span>
                {stats.awaiting_approval_count > 0 && (
                  <span className="text-xs font-mono uppercase bg-amber-900/60 px-1.5 py-0.5 rounded text-amber-200 font-bold">
                    Policy Gate
                  </span>
                )}
              </div>

            </div>

            {/* Agent Status */}
            <div className="flex items-center space-x-3 text-xs font-mono">
              <div className="hidden md:flex items-center space-x-2.5 px-3.5 py-1.5 rounded bg-slate-900 border border-slate-800 text-slate-400">
                <Radio className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
                <span className="text-slate-300">Agent Status:</span>
                <span className="text-cyan-400 font-bold">AUTONOMOUS MONITORING</span>
                <span className="text-slate-600">•</span>
                <span className="text-slate-400">10s Cycle</span>
                <span className="text-slate-600">•</span>
                <span className="text-emerald-400 font-bold">ZERO SELF-ATTESTATION</span>
              </div>
            </div>

          </div>
        </div>
      )}

      {/* 3. Navigation Tabs */}
      <div className="w-full px-6 sm:px-8 lg:px-10 xl:px-12 flex space-x-8 text-sm font-medium overflow-x-auto">
        <button
          onClick={() => setActiveTab('map')}
          className={`py-3.5 border-b-2 flex items-center space-x-2 transition cursor-pointer ${
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
          className={`py-3.5 border-b-2 flex items-center space-x-2 transition cursor-pointer ${
            activeTab === 'decisions'
              ? 'border-amber-500 text-amber-400 font-semibold'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <CheckCircle2 className="w-4 h-4" />
          <span>Decision Surface</span>
          {stats?.awaiting_approval_count > 0 && (
            <span className="px-2 py-0.5 rounded-full text-xs font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
              {stats.awaiting_approval_count}
            </span>
          )}
        </button>

        <button
          onClick={() => setActiveTab('directional')}
          className={`py-3.5 border-b-2 flex items-center space-x-2 transition cursor-pointer ${
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
          className={`py-3.5 border-b-2 flex items-center space-x-2 transition cursor-pointer ${
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
