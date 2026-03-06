const BASE = '/api';

async function fetchJSON(url) {
  const res = await fetch(`${BASE}${url}`);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

export async function getCompanies() {
  return fetchJSON('/companies');
}

export async function getSchemas() {
  return fetchJSON('/schemas');
}

export async function getMetrics(company) {
  return fetchJSON(`/metrics/${encodeURIComponent(company)}`);
}

export async function getCitations(company) {
  return fetchJSON(`/citations/${encodeURIComponent(company)}`);
}

export async function getGuidance(company) {
  return fetchJSON(`/guidance/${encodeURIComponent(company)}`);
}

export async function getDeltas(company) {
  return fetchJSON(`/deltas/${encodeURIComponent(company)}`);
}

export async function getSentimentConfig() {
  return fetchJSON('/sentiment-config');
}

export async function runPipeline(company, schemaKey) {
  const res = await fetch(`${BASE}/pipeline/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ company, schema_key: schemaKey }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `API error: ${res.status}`);
  }
  return res.json();
}

export async function getPipelineStatus(company) {
  return fetchJSON(`/pipeline/status/${encodeURIComponent(company)}`);
}
