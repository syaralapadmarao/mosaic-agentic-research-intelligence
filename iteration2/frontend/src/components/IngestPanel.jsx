import { useState, useEffect, useRef } from 'react';
import { startIngestion, pollIngestStatus } from '../api';

export default function IngestPanel({ company }) {
  const [status, setStatus] = useState(null);
  const [polling, setPolling] = useState(false);
  const intervalRef = useRef(null);

  useEffect(() => {
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  async function handleIngest() {
    if (!company) return;
    try {
      await startIngestion(company);
      setPolling(true);
      intervalRef.current = setInterval(async () => {
        const s = await pollIngestStatus(company);
        setStatus(s);
        if (s.status === 'complete' || s.status === 'error') {
          clearInterval(intervalRef.current);
          setPolling(false);
        }
      }, 2000);
    } catch (err) {
      setStatus({ status: 'error', message: err.message });
    }
  }

  const isRunning = status?.status === 'running' || polling;
  const progress = status?.total > 0 ? Math.round((status.progress / status.total) * 100) : 0;

  return (
    <div className="max-w-xl space-y-6">
      <div>
        <h3 className="text-sm font-semibold text-slate-300 mb-2">Document Ingestion</h3>
        <p className="text-xs text-slate-500 mb-4">
          Ingest all PDF and Markdown documents for <span className="capitalize text-slate-300">{company}</span>.
          Documents will be classified, processed through the MNPI gate, chunked, and embedded into ChromaDB.
        </p>

        <button
          onClick={handleIngest}
          disabled={isRunning || !company}
          className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-500 rounded-xl text-sm font-medium transition-colors"
        >
          {isRunning ? 'Ingesting...' : 'Start Ingestion'}
        </button>
      </div>

      {status && (
        <div className="p-4 rounded-xl bg-slate-800/50 border border-slate-700/50 space-y-3">
          {/* Status header */}
          <div className="flex items-center justify-between">
            <span className={`text-xs px-2 py-0.5 rounded-full ${
              status.status === 'running' ? 'bg-blue-500/20 text-blue-400' :
              status.status === 'complete' ? 'bg-green-500/20 text-green-400' :
              status.status === 'error' ? 'bg-red-500/20 text-red-400' :
              'bg-slate-600/20 text-slate-400'
            }`}>
              {status.status}
            </span>
            {status.total > 0 && (
              <span className="text-xs text-slate-400">{status.progress}/{status.total} files</span>
            )}
          </div>

          {/* Progress bar */}
          {isRunning && (
            <div className="w-full h-2 bg-slate-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
          )}

          {/* Current file */}
          {status.current_file && (
            <div className="text-xs text-slate-400">
              Processing: <span className="text-slate-300">{status.current_file}</span>
            </div>
          )}

          {/* Results */}
          {status.status === 'complete' && (
            <div className="text-xs text-green-400">
              Ingested {status.ingested} documents successfully.
            </div>
          )}

          {/* Errors */}
          {status.errors?.length > 0 && (
            <div className="text-xs space-y-1">
              <div className="text-red-400 font-medium">Errors:</div>
              {status.errors.map((e, i) => (
                <div key={i} className="text-red-300/70 pl-2">{e}</div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
