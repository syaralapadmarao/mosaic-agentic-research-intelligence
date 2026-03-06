import { useState, useRef } from 'react';
import { runPipeline, getPipelineStatus } from '../api';

export default function StatusBar({ company, schemaKey, onPipelineComplete }) {
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState('');
  const timer = useRef(null);

  const execute = async () => {
    if (!company || !schemaKey) return;
    setRunning(true);
    setError('');
    setProgress('Starting pipeline…');
    try {
      await runPipeline(company, schemaKey);
      pollStatus();
    } catch (e) {
      setError(e.message || 'Failed to start pipeline');
      setRunning(false);
    }
  };

  const pollStatus = () => {
    timer.current = setInterval(async () => {
      try {
        const s = await getPipelineStatus(company);
        if (s.status === 'running') {
          setProgress(s.message || 'Processing…');
        } else if (s.status === 'done') {
          setProgress('Complete');
          clearInterval(timer.current);
          setRunning(false);
          onPipelineComplete?.();
        } else if (s.status === 'error') {
          setError(s.message || 'Pipeline failed');
          clearInterval(timer.current);
          setRunning(false);
        } else {
          setProgress(s.message || 'Processing…');
        }
      } catch {
        /* ignore transient poll errors */
      }
    }, 2000);
  };

  return (
    <footer className="shrink-0 px-4 py-2 flex items-center justify-between border-t"
      style={{ background: 'var(--bg-secondary)', borderColor: 'var(--border)' }}>

      {/* Left — progress */}
      <div className="flex items-center gap-2 text-xs min-w-0">
        {running && (
          <span className="animate-spin w-3 h-3 border border-t-transparent rounded-full"
            style={{ borderColor: 'var(--accent)', borderTopColor: 'transparent' }} />
        )}
        {error ? (
          <span className="truncate" style={{ color: 'var(--red)' }}>{error}</span>
        ) : (
          <span className="truncate" style={{ color: 'var(--text-muted)' }}>{progress || 'Ready'}</span>
        )}
      </div>

      {/* Right — action */}
      <button
        onClick={execute}
        disabled={running || !company || !schemaKey}
        className="px-4 py-1.5 rounded-md text-xs font-semibold transition-all disabled:opacity-30"
        style={{
          background: 'var(--accent)',
          color: '#fff',
        }}
      >
        {running ? 'Running…' : '▶  Run Pipeline'}
      </button>
    </footer>
  );
}
