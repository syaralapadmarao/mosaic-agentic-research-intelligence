import { useState, useCallback } from 'react';
import Sidebar from './components/Sidebar';
import MetricsTable from './components/MetricsTable';
import GuidanceTracker from './components/GuidanceTracker';
import StatusBar from './components/StatusBar';

const TABS = [
  { id: 'metrics', label: 'Tab 1: Metrics Tracker' },
  { id: 'guidance', label: 'Tab 2: Guidance Tracker' },
];

export default function App() {
  const [company, setCompany] = useState('');
  const [schemaKey, setSchemaKey] = useState('');
  const [activeTab, setActiveTab] = useState('metrics');
  const [refreshKey, setRefreshKey] = useState(0);

  const handlePipelineComplete = useCallback(() => {
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
                  <span className="text-[10px] px-2 py-0.5 rounded font-medium uppercase"
                    style={{ background: 'var(--bg-tertiary)', color: 'var(--text-muted)' }}>
                    {schemaKey || 'no schema'}
                  </span>
                )}
              </div>
              {company && (
                <p className="text-[11px] mt-0.5" style={{ color: 'var(--text-muted)' }}>
                  Rows = metrics from company schema · Columns = quarters ·
                  Click any <span style={{ color: 'var(--accent)' }}>[p.XX]</span> to view source in PDF
                </p>
              )}
            </div>

            {/* Tabs */}
            <div className="flex items-center gap-0.5 p-0.5 rounded-lg"
              style={{ background: 'var(--bg-tertiary)' }}>
              {TABS.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className="px-3 py-1.5 rounded-md text-xs font-medium transition-all"
                  style={{
                    background: activeTab === tab.id ? 'var(--bg-secondary)' : 'transparent',
                    color: activeTab === tab.id ? 'var(--text-primary)' : 'var(--text-muted)',
                    boxShadow: activeTab === tab.id ? '0 1px 3px rgba(0,0,0,0.3)' : 'none',
                  }}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          </div>
        </header>

        {/* Content */}
        <main className="flex-1 overflow-auto p-4" style={{ background: 'var(--bg-primary)' }}>
          <div className="rounded-lg border overflow-hidden"
            style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>
            {activeTab === 'metrics' && (
              <MetricsTable key={`m-${company}-${refreshKey}`} company={company} />
            )}
            {activeTab === 'guidance' && (
              <GuidanceTracker key={`g-${company}-${refreshKey}`} company={company} />
            )}
          </div>
        </main>

        {/* Status bar */}
        <StatusBar
          company={company}
          schemaKey={schemaKey}
          onPipelineComplete={handlePipelineComplete}
        />
      </div>
    </div>
  );
}
