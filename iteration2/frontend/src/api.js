const API = '/api';

export async function fetchCompanies() {
  const res = await fetch(`${API}/companies`);
  return res.json();
}

export async function submitQuery(company, query) {
  const res = await fetch(`${API}/research/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ company, query }),
  });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function startIngestion(company) {
  const res = await fetch(`${API}/research/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ company }),
  });
  return res.json();
}

export async function pollIngestStatus(company) {
  const res = await fetch(`${API}/research/ingest/status/${company}`);
  return res.json();
}

export async function fetchSources(company) {
  const res = await fetch(`${API}/research/sources/${company}`);
  return res.json();
}

export async function fetchConsensus(company) {
  const res = await fetch(`${API}/research/consensus/${company}`);
  return res.json();
}

export async function fetchInsights(company) {
  const res = await fetch(`${API}/research/insights/${company}`);
  return res.json();
}

export async function fetchDivergences(company) {
  const res = await fetch(`${API}/research/divergences/${company}`);
  return res.json();
}

export async function fetchStats(company) {
  const res = await fetch(`${API}/research/stats/${company}`);
  return res.json();
}

export async function fetchCacheStats(company) {
  const res = await fetch(`${API}/research/cache/${company}`);
  return res.json();
}

export async function fetchMnpiAudit(company) {
  const res = await fetch(`${API}/research/mnpi-audit?company=${company || ''}`);
  return res.json();
}

export async function fetchPrice(company) {
  const res = await fetch(`${API}/finance/price/${company}`);
  return res.json();
}

export async function fetchPeers(company) {
  const res = await fetch(`${API}/finance/peers/${company}`);
  return res.json();
}
