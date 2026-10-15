import { useEffect, useState } from 'react';

type Readiness = { status: string; database: string; schema: string };

export default function App() {
  const [ready, setReady] = useState<Readiness | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  async function refresh() {
    setLoading(true); setError(''); setReady(null);
    try {
      const response = await fetch('/api/ready', { signal: AbortSignal.timeout(8000) });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error?.message || 'The service is unavailable.');
      setReady(data);
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Unable to connect.');
    } finally { setLoading(false); }
  }
  useEffect(() => { void refresh(); }, []);
  return <div className="workspace">
    <aside><a className="brand" href="/" aria-label="Northstar Cloud home"><span className="logo">✦</span> Northstar<span className="cloud">CLOUD</span></a>
      <p className="nav-label">SUPPORT OPERATIONS</p><a className="nav-current" href="#overview">◈ &nbsp; Overview</a>
      <div className="sidebar-footer"><span className="avatar">NC</span><div>Development workspace<small>Foundation release</small></div></div>
    </aside>
    <main id="overview"><header><span>Workspace / Overview</span><span className="tag">Development</span></header>
      <div className="page-heading"><p className="eyebrow">NORTHSTAR CLOUD</p><h1>Support operations</h1><p>A reliable foundation for policy-grounded customer support.</p></div>
      <section className="status-card" aria-labelledby="service-title"><div className="card-heading"><div><p className="eyebrow">SYSTEM STATUS</p><h2 id="service-title">Service readiness</h2></div><button onClick={() => void refresh()} disabled={loading}>{loading ? 'Checking…' : 'Check again'}</button></div>
        {loading && <p role="status">Checking the API and database…</p>}
        {error && <div role="alert" className="error"><strong>Service needs attention</strong><p>{error}</p><small>Check database configuration and run migrations, then try again.</small></div>}
        {ready && <div role="status" className="healthy"><span className="dot" /><div><strong>Ready for requests</strong><p>Database {ready.database} · Schema {ready.schema}</p></div></div>}
      </section>
      <section className="info-grid"><article><span className="step">01</span><h2>Connected infrastructure</h2><p>Readiness checks the database and migration revision. The status above comes directly from the API.</p></article><article><span className="step">02</span><h2>Built in stages</h2><p>Customer cases, policy retrieval, controlled actions, and operator review will appear as their implementation gates pass.</p></article></section>
      <footer>Northstar Cloud · Fictional SaaS business · No live model calls in this release</footer>
    </main></div>;
}
