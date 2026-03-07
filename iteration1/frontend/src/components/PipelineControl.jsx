import { useState, useRef, useEffect } from 'react';
import { runPipeline, getPipelineStatus } from '../api';

const NODE_LABELS = {
  parse_pdf: 'Parsing PDF',
  classify: 'Classifying document',
  extract_metrics: 'Extracting metrics',
  calculate_metrics: 'Calculating derived metrics',
  validate_metrics: 'Validating metrics',
  assemble_table: 'Assembling metrics table',
  extract_guidance: 'Extracting guidance',
  detect_deltas: 'Detecting guidance deltas',
  assemble_guidance: 'Assembling guidance table',
  processing: 'Processing',
};

export default function PipelineControl({ company, schemaKey, onPipelineComplete, onPipelineStart }) {
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState('');
  const timer = useRef(null);

  useEffect(() => {
    if (timer.current) clearInterval(timer.current);
    setRunning(false);
    setProgress('');
    setError('');
  }, [company]);

  const execute = async () => {
    if (!company || !schemaKey) return;
    setRunning(true);
    setError('');
    setProgress('Starting pipeline...');
    onPipelineStart?.();
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
          const file = s.current_file || '';
          const node = s.current_node || '';
          const nodeLabel = NODE_LABELS[node] || node;
          const fileProgress = s.total ? `[${(s.progress || 0) + 1}/${s.total}]` : '';
          setProgress(
            file
              ? `${fileProgress} ${file} — ${nodeLabel}...`
              : s.message || 'Processing...'
          );
        } else if (s.status === 'complete') {
          setProgress(s.message || 'Complete');
          clearInterval(timer.current);
          setRunning(false);
          onPipelineComplete?.();
        } else if (s.status === 'error') {
          setError(s.message || 'Pipeline failed');
          clearInterval(timer.current);
          setRunning(false);
        } else {
          setProgress(s.message || 'Processing...');
        }
      } catch {
        /* ignore transient poll errors */
      }
    }, 2000);
  };

  return (
    <div className="flex items-center gap-3">
      {/* Status text (shown when running or after completion) */}
      {(running || progress || error) && (
        <div className="flex items-center gap-2 text-xs max-w-[280px]">
          {running && (
            <span className="animate-spin w-3.5 h-3.5 border-2 border-t-transparent rounded-full shrink-0"
              style={{ borderColor: 'var(--accent)', borderTopColor: 'transparent' }} />
          )}
          {error ? (
            <span className="truncate font-medium" style={{ color: 'var(--red)' }}>{error}</span>
          ) : (
            <span className="truncate" style={{ color: 'var(--text-secondary)' }}>
              {progress}
            </span>
          )}
        </div>
      )}

      {/* Run button */}
      <button
        onClick={execute}
        disabled={running || !company || !schemaKey}
        className="px-5 py-2 rounded-lg text-sm font-bold transition-all disabled:opacity-30 shrink-0"
        style={{
          background: running ? 'var(--amber)' : 'var(--accent)',
          color: '#fff',
          boxShadow: (!running && company && schemaKey) ? '0 2px 8px rgba(79,143,247,0.35)' : 'none',
        }}
      >
        {running ? 'Running...' : 'Run Pipeline'}
      </button>
    </div>
  );
}
