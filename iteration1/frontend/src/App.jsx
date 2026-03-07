import { useState, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import MetricsTable from './components/MetricsTable';
import GuidanceTracker from './components/GuidanceTracker';
import PipelineTrace from './components/PipelineTrace';
import PipelineControl from './components/PipelineControl';

const TABS = [
  { id: 'metrics', label: 'Metrics Tracker' },
  { id: 'guidance', label: 'Guidance Tracker' },
  { id: 'trace', label: 'Pipeline Trace' },
];

export default function App() {
  const [company, setCompany] = useState('');
  const [schemaKey, setSchemaKey] = useState('');
  const [activeTab, setActiveTab] = useState('metrics');
  const [refreshKey, setRefreshKey] = useState(0);

  const handlePipelineComplete = useCallback(() => {
    setRefreshKey(k => k + 1);
  }, []);

  const handlePipelineStart = useCallback(() => {
    setActiveTab('trace');
    setRefreshKey(k => k + 1);
  }, []);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar
        selected={company}
        onSelect={setCompany}
        schemaKey={schemaKey}
        onSchemaChange={setSchemaKey}
      />

      <div className="flex-1 flex flex-col overflow-hidden min-w-0">
        {/* Header */}
        <header className="shrink-0 border-b"
          style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
          <div className="flex items-center justify-between px-6 py-3">
            <div>
              <div className="flex items-center gap-3">
                <h2 className="text-lg font-semibold capitalize"
                  style={{ color: 'var(--text-primary)' }}>
                  {company || 'Select a company'}
                </h2>
                {company && (
                  <span className="text-[10px] px-2 py-0.5 rounded font-medium uppercase tracking-wide"
                    style={{ background: 'var(--bg-tertiary)', color: 'var(--text-muted)', border: '1px solid var(--border)' }}>
                    {schemaKey || 'no schema'}
                  </span>
                )}
              </div>
              {company && (
                <p className="text-[11px] mt-1" style={{ color: 'var(--text-muted)' }}>
                  Rows = metrics from schema &middot; Columns = quarters &middot;
                  Click <span style={{ color: 'var(--accent)' }}>[p.N]</span> to view source PDF
                </p>
              )}
            </div>

            {/* Pipeline button + Tabs */}
            <div className="flex items-center gap-4">
              <PipelineControl
                company={company}
                schemaKey={schemaKey}
                onPipelineComplete={handlePipelineComplete}
                onPipelineStart={handlePipelineStart}
              />

              <div className="flex items-center gap-1 p-1 rounded-lg"
                style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--border)' }}>
                {TABS.map((tab, i) => (
                  <button
                    key={tab.id}
                    onClick={() => setActiveTab(tab.id)}
                    className="px-4 py-1.5 rounded-md text-xs font-medium transition-all"
                    style={{
                      background: activeTab === tab.id ? 'var(--bg-secondary)' : 'transparent',
                      color: activeTab === tab.id ? 'var(--text-primary)' : 'var(--text-muted)',
                      boxShadow: activeTab === tab.id ? '0 1px 4px rgba(0,0,0,0.4)' : 'none',
                    }}
                  >
                    <span style={{ color: 'var(--text-muted)', marginRight: 4, fontSize: 10 }}>Tab {i + 1}:</span>
                    {tab.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto p-5" style={{ background: 'var(--bg-primary)' }}>
          <div className="rounded-xl border overflow-hidden"
            style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
            {activeTab === 'metrics' && (
              <MetricsTable key={`m-${company}-${refreshKey}`} company={company} />
            )}
            {activeTab === 'guidance' && (
              <GuidanceTracker key={`g-${company}-${refreshKey}`} company={company} />
            )}
            {activeTab === 'trace' && (
              <PipelineTrace key={`t-${company}-${refreshKey}`} company={company} />
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
