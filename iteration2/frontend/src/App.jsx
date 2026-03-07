import { useState, useEffect } from 'react';
import Sidebar from './components/Sidebar';
import ResearchChat from './components/ResearchChat';
import MosaicBanner from './components/MosaicBanner';
import ConsensusView from './components/ConsensusView';
import SourcesPanel from './components/SourcesPanel';
import IngestPanel from './components/IngestPanel';
import { fetchCompanies, fetchStats, fetchPrice } from './api';

const TABS = ['Research', 'Consensus', 'Sources', 'Ingest'];

export default function App() {
  const [companies, setCompanies] = useState([]);
  const [selected, setSelected] = useState('');
  const [activeTab, setActiveTab] = useState('Research');
  const [stats, setStats] = useState(null);
  const [priceData, setPriceData] = useState(null);
  const [lastAnswer, setLastAnswer] = useState(null);

  useEffect(() => {
    fetchCompanies().then(cs => {
      setCompanies(cs);
      if (cs.length > 0) setSelected(cs[0].name);
    });
  }, []);

  useEffect(() => {
    if (!selected) return;
    fetchStats(selected).then(setStats).catch(() => setStats(null));
    fetchPrice(selected).then(d => {
      if (d.status === 'ok') setPriceData(d.data);
      else setPriceData(null);
    }).catch(() => setPriceData(null));
  }, [selected]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur">
        <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">
              Mosaic Research Assistant
            </h1>
            <span className="text-xs px-2 py-0.5 rounded-full bg-blue-500/20 text-blue-400 border border-blue-500/30">
              Iteration 2
            </span>
          </div>
          {priceData && (
            <div className="text-sm text-slate-400 flex items-center gap-4">
              <span className="font-mono font-bold text-slate-200">
                {'\u20B9'}{priceData.cmp?.toLocaleString()}
              </span>
              <span className={priceData.day_change_pct >= 0 ? 'text-green-400' : 'text-red-400'}>
                {priceData.day_change_pct >= 0 ? '+' : ''}{priceData.day_change_pct?.toFixed(1)}%
              </span>
              <span className="text-xs text-slate-500">MCap {'\u20B9'}{(priceData.market_cap_cr / 1000).toFixed(1)}K Cr</span>
            </div>
          )}
        </div>
      </header>

      <div className="max-w-7xl mx-auto flex gap-0">
        {/* Sidebar */}
        <Sidebar
          companies={companies}
          selected={selected}
          onSelect={setSelected}
          stats={stats}
        />

        {/* Main content */}
        <main className="flex-1 min-w-0">
          {/* Tabs */}
          <div className="border-b border-slate-800 px-4">
            <nav className="flex gap-1">
              {TABS.map(tab => (
                <button
                  key={tab}
                  onClick={() => setActiveTab(tab)}
                  className={`px-4 py-2.5 text-sm font-medium transition-colors ${
                    activeTab === tab
                      ? 'text-blue-400 border-b-2 border-blue-400'
                      : 'text-slate-500 hover:text-slate-300'
                  }`}
                >
                  {tab}
                </button>
              ))}
            </nav>
          </div>

          {/* Mosaic Banner */}
          {lastAnswer?.mosaic && activeTab === 'Research' && (
            <MosaicBanner mosaic={lastAnswer.mosaic} responseState={lastAnswer.response_state} />
          )}

          {/* Tab content */}
          <div className="p-4">
            {activeTab === 'Research' && (
              <ResearchChat
                company={selected}
                onAnswer={setLastAnswer}
              />
            )}
            {activeTab === 'Consensus' && (
              <ConsensusView company={selected} />
            )}
            {activeTab === 'Sources' && (
              <SourcesPanel company={selected} />
            )}
            {activeTab === 'Ingest' && (
              <IngestPanel company={selected} />
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
