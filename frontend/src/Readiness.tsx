import { useEffect, useState } from 'react';

type ReadinessState = { status: string; database: string; schema: string; environment: string; version: string };
export default function Readiness() {
  const [ready, setReady] = useState<ReadinessState | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  async function refresh() {
    setLoading(true); setError(''); setReady(null);
    try {
      const response = await fetch('/api/ready', { signal: AbortSignal.timeout(8000) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message || 'The service is unavailable.');
      if (data.status !== 'ready' || data.database !== 'connected' || typeof data.schema !== 'string') {
        throw new Error('The service returned an invalid readiness response.');
      }
      setReady(data);
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Unable to connect.');
    } finally { setLoading(false); }
  }
  useEffect(() => { void refresh(); }, []);
  return <>
    <div className="page-heading"><p className="eyebrow">CONNECTED INFRASTRUCTURE</p><h1>System status</h1><p>Live API and database readiness. Document administration remains a frontend preview.</p></div>
    <section className="status-card" aria-labelledby="service-title">
      <div className="card-heading"><h2 id="service-title">Service readiness</h2><button onClick={() => void refresh()} disabled={loading}>{loading ? 'Checking…' : 'Check again'}</button></div>
      {loading && <p role="status">Checking the API and database…</p>}
      {error && <div role="alert" className="error"><strong>Service needs attention</strong><p>{error}</p><small>Check database configuration and run migrations, then try again.</small></div>}
      {ready && <div role="status" className="healthy"><strong>Ready for requests</strong><p>Database {ready.database} · Schema {ready.schema}</p></div>}
    </section>
  </>;
}
