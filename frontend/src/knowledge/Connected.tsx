import { useState } from 'react';
import ExtractionVerification, { type ExtractionDocument } from './ExtractionVerification';

type Assessment = { id: string; provider: string; model_id: string | null; assessment_status: string; needs_review: boolean; risk_level: string; explanation: string; review_reasons: string[]; supporting_references: { section_id: string; quote: string }[] };
type Record = ExtractionDocument & { id: string; policy_id: string; title: string; version: number; sensitivity: string; status: string; lifecycle: string; review_status: string; publication_status: string; error: string | null; sections?: { id: string; source: string; text: string }[]; assessments?: Assessment[]; events?: { action: string; reason: string; created_at: string }[] };

export default function Connected() {
  const [token, setToken] = useState('');
  const [records, setRecords] = useState<Record[]>([]);
  const [selected, setSelected] = useState<Record | null>(null);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [reason, setReason] = useState('');
  const [decision, setDecision] = useState('APPROVED');
  const [offset, setOffset] = useState(0);

  async function request(path: string, init: RequestInit = {}) {
    const response = await fetch('/api/admin/documents' + path, { ...init, cache: 'no-store', headers: { ...init.headers, Authorization: `Bearer ${token}` } });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error?.message ?? data.detail ?? 'Request failed.');
    return data;
  }
  async function run(work: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('');
    try { await work(); } catch (err) { setError(err instanceof Error ? err.message : 'Request failed.'); }
    finally { setBusy(false); }
  }
  async function list(nextOffset = offset) {
    setRecords(await request(`?offset=${nextOffset}&limit=25`)); setOffset(nextOffset);
  }
  async function inspect(id: string) { setSelected(await request('/' + encodeURIComponent(id))); }
  async function upload(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault(); const form = event.currentTarget; const data = new FormData(form);
    const replacement = data.get('replacement') === 'on'; data.delete('replacement');
    await run(async () => {
      const path = replacement ? `/policies/${encodeURIComponent(String(data.get('policy_id')))}/versions` : '';
      const result = await request(path, { method: 'POST', body: data });
      await list(0); await inspect(result.document.id);
      setNotice(result.duplicate ? 'Existing upload found. No new version was created.' : 'Upload stored. Refresh the document to follow processing and review.');
      form.reset();
    });
  }
  return <div className="readiness-wrapper">
    <div className="page-heading"><p className="eyebrow">CONNECTED ADMINISTRATION</p><h1>Stored documents</h1><p>Original files go to private storage. Processing and review decisions are saved by the backend.</p></div>
    <section className="panel"><h2>Administrator access</h2><p>The token stays in memory and is cleared when you leave this screen. All holders have administrator access; do not share it with readers.</p>
      <label>Administrator token<input disabled={busy} type="password" autoComplete="off" value={token} onChange={e => { setToken(e.target.value); setRecords([]); setSelected(null); }} /></label>
      <button disabled={busy || !token} onClick={() => void run(() => list(0))}>Load documents</button>
      <button disabled={busy} onClick={() => { setToken(''); setRecords([]); setSelected(null); setNotice(''); setError(''); }}>Clear session</button>
    </section>
    {error && <div className="error" role="alert">{error}</div>}{notice && <p role="status">{notice}</p>}
    <section className="panel"><h2>Upload a document</h2><form onSubmit={e => void upload(e)}><fieldset disabled={busy || !token}>
      <label>Policy identifier<input name="policy_id" required pattern="[a-z0-9][a-z0-9_-]{0,99}" placeholder="employee-leave" /></label>
      <label>Title<input name="title" required maxLength={160} /></label>
      <label>Sensitivity<select name="sensitivity" required defaultValue=""><option value="" disabled>Select a classification</option><option value="PUBLIC">Public</option><option value="INTERNAL">Internal</option><option value="CONFIDENTIAL">Confidential</option><option value="HIGHLY_RESTRICTED">Highly Restricted</option></select></label>
      <p className="note">Highly Restricted content is never sent to OpenAI. Restricted uploads require an approved private environment. Only approved Public documents enter the current search index.</p>
      <label>Source file<input name="file" type="file" required accept=".pdf,.docx,.md,.txt" /></label>
      <label><input name="replacement" type="checkbox" /> Replace an existing policy with this revision</label>
      <button className="primary" type="submit">Upload to private storage</button>
    </fieldset></form></section>
    <section className="panel"><h2>Stored versions</h2><button disabled={busy || !token} onClick={() => void run(() => list())}>Refresh list</button>
      {records.map(record => <p key={record.id}><button onClick={() => void run(() => inspect(record.id))} disabled={busy}>{record.title} · v{record.version}</button> — {record.sensitivity} · {record.lifecycle}</p>)}
      <button disabled={busy || offset === 0} onClick={() => void run(() => list(Math.max(0, offset - 25)))}>Previous page</button>
      <button disabled={busy || records.length < 25} onClick={() => void run(() => list(offset + 25))}>Next page</button>
    </section>
    {selected && <section className="panel"><h2>{selected.title} · v{selected.version}</h2><p>{selected.sensitivity} · Extraction: {selected.status} · Assessment: {selected.review_status} · Publication: {selected.publication_status}</p>
      <button disabled={busy} onClick={() => void run(() => inspect(selected.id))}>Refresh document</button>{selected.error && <p role="alert">{selected.error}</p>}
      <ExtractionVerification key={selected.id + token} document={selected} token={token} onSaved={async () => { await inspect(selected.id); await list(); }} />
      <h3>Review assessments</h3>{!selected.assessments?.length && <p>No assessment yet. The worker must finish before approval.</p>}
      {selected.assessments?.map(a => <article key={a.id}><p><strong>{a.assessment_status} · {a.risk_level}</strong> · {a.provider} / {a.model_id ?? 'No model'}</p><p>{a.needs_review ? 'Additional attention required' : 'No additional issues flagged; human approval is still required'}</p><p>{a.explanation}</p><p>{a.review_reasons.join(', ')}</p>{a.supporting_references.map((r, i) => <blockquote key={i}><p>{r.quote}</p><small>{r.section_id}</small></blockquote>)}</article>)}
      <h3>Extracted sections</h3>{selected.sections?.map(s => <article className="section-card" key={s.id}><small>{s.source}</small><p className="section-text">{s.text}</p></article>)}
      <h3>Human decision</h3><p>A model recommendation never authorizes publication. Record why you approve, reject or request a replacement.</p>
      <label>Decision<select value={decision} onChange={e => setDecision(e.target.value)}><option value="APPROVED">Approve</option><option value="REJECTED">Reject</option><option value="CHANGES_REQUESTED">Request changes</option></select></label>
      <label>Decision reason<textarea value={reason} onChange={e => setReason(e.target.value)} required maxLength={500} /></label>
      <button className="primary" disabled={busy || !reason.trim() || (decision === 'APPROVED' && (selected.extraction_status !== 'VERIFIED' || selected.status !== 'READY' || selected.review_status !== 'DONE' || selected.publication_status !== 'PENDING_REVIEW'))} onClick={() => void run(async () => {
        const result = await request(`/${selected.id}/decision`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision, reason }) });
        setSelected(result); setReason(''); await list(); setNotice('Human decision saved.');
      })}>Save human decision</button>
      <h3>Processing and decision history</h3>{selected.events?.map((e, i) => <p key={i}>{e.action} · {e.reason} · {new Date(e.created_at).toLocaleString()}</p>)}
    </section>}
  </div>;
}
