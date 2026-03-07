import { useState, useRef, useEffect } from 'react';
import { submitQuery } from '../api';
import SourceBadges from './SourceBadges';
import DivergenceAlert from './DivergenceAlert';

const SAMPLE_QUERIES = [
  "What is the consensus view on revenue growth?",
  "How does management's guidance compare to sell-side estimates?",
  "Any insights from channel checks on competitive positioning?",
  "What are the key risk factors across analyst reports?",
  "Show me EBITDA margin trends and outlook",
];

export default function ResearchChat({ company, onAnswer }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function handleSubmit(query) {
    const q = query || input.trim();
    if (!q || !company) return;

    setMessages(prev => [...prev, { role: 'user', text: q }]);
    setInput('');
    setLoading(true);

    try {
      const res = await submitQuery(company, q);
      setMessages(prev => [...prev, { role: 'assistant', data: res }]);
      onAnswer?.(res);
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        data: { answer: `Error: ${err.message}`, response_state: 'Error' },
      }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-180px)]">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto space-y-4 pb-4">
        {messages.length === 0 && (
          <div className="text-center py-12">
            <h2 className="text-lg font-semibold text-slate-400 mb-4">
              Ask a research question about <span className="capitalize text-blue-400">{company}</span>
            </h2>
            <div className="flex flex-wrap gap-2 justify-center max-w-2xl mx-auto">
              {SAMPLE_QUERIES.map((q, i) => (
                <button
                  key={i}
                  onClick={() => handleSubmit(q)}
                  className="text-xs px-3 py-1.5 rounded-full bg-slate-800 text-slate-400 hover:bg-slate-700 hover:text-slate-200 transition-colors border border-slate-700"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-3xl rounded-2xl px-4 py-3 ${
              msg.role === 'user'
                ? 'bg-blue-600/30 text-blue-100 border border-blue-500/30'
                : 'bg-slate-800/70 text-slate-200 border border-slate-700/50'
            }`}>
              {msg.role === 'user' ? (
                <p className="text-sm">{msg.text}</p>
              ) : (
                <div>
                  {/* Response state badge */}
                  {msg.data?.response_state && msg.data.response_state !== 'Normal' && (
                    <div className={`inline-block text-xs px-2 py-0.5 rounded-full mb-2 ${
                      msg.data.response_state === 'Consensus Divergence' ? 'bg-amber-500/20 text-amber-400' :
                      msg.data.response_state === 'Stale' ? 'bg-yellow-500/20 text-yellow-400' :
                      msg.data.response_state === 'No Results' ? 'bg-red-500/20 text-red-400' :
                      'bg-slate-600/30 text-slate-400'
                    }`}>
                      {msg.data.response_state}
                    </div>
                  )}

                  {msg.data?.cached && (
                    <span className="inline-block text-xs px-2 py-0.5 rounded-full bg-green-500/20 text-green-400 mb-2 ml-2">
                      Cached
                    </span>
                  )}

                  {/* Answer text */}
                  <div className="text-sm whitespace-pre-wrap leading-relaxed">
                    {msg.data?.answer || ''}
                  </div>

                  {/* Divergence alerts */}
                  {msg.data?.divergences?.length > 0 && (
                    <div className="mt-3">
                      {msg.data.divergences.map((d, j) => (
                        <DivergenceAlert key={j} divergence={d} />
                      ))}
                    </div>
                  )}

                  {/* Source badges */}
                  {msg.data?.source_badges?.length > 0 && (
                    <SourceBadges badges={msg.data.source_badges} />
                  )}

                  {/* Stale warnings */}
                  {msg.data?.stale_warnings?.length > 0 && (
                    <div className="mt-2 text-xs text-yellow-500">
                      {msg.data.stale_warnings.map((w, j) => (
                        <div key={j}>Stale: {w.file} ({w.age_days}d old)</div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-slate-800/70 rounded-2xl px-4 py-3 border border-slate-700/50">
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <div className="w-2 h-2 rounded-full bg-blue-400 animate-pulse" />
                Researching...
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-slate-800 pt-3">
        <form onSubmit={e => { e.preventDefault(); handleSubmit(); }} className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder={`Ask about ${company}...`}
            className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-4 py-2.5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 focus:border-blue-500/50"
            disabled={loading || !company}
          />
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 disabled:text-slate-500 rounded-xl text-sm font-medium transition-colors"
          >
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
