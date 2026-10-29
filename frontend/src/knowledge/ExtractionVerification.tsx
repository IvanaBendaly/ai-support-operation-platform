import { useEffect, useState } from 'react';

type Section = { id?: string; source: string; text: string };
type Check = { rule: string; status: string; detail: string; source?: string };
export type ExtractionDocument = {
  id: string; filename?: string; media_type?: string; status: string;
  extraction_status: string; extraction_revision: number; sections?: Section[];
  extractions?: { revision: number; status: string; actor: string; reason: string; payload: {
    attempts?: { metadata: { parser: string; parser_version?: string }; quality: { outcome: string; checks: Check[] }; error?: string }[];
    dpp?: { checks: Check[] }; field_assessment?: { status: string; reason?: string; fields?: { field: string; value: unknown; confidence: number | null; status: string; citations: unknown[] }[] };
  } }[];
};

export default function ExtractionVerification({ document, token, onSaved }: {
  document: ExtractionDocument; token: string; onSaved: () => Promise<void>;
}) {
  const [original, setOriginal] = useState('');
  const [originalText, setOriginalText] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [sections, setSections] = useState<Section[]>(document.sections ?? []);
  useEffect(() => () => { if (original) URL.revokeObjectURL(original); }, [original]);
  useEffect(() => { setSections(document.sections ?? []); setReason(''); }, [document]);
  async function loadOriginal() {
    setBusy(true); setError('');
    try {
      const response = await fetch(`/api/admin/documents/${document.id}/original`, { cache: 'no-store', headers: { Authorization: `Bearer ${token}` } });
      if (!response.ok) throw new Error('Original could not be loaded. Check access and storage.');
      const blob = await response.blob();
      setOriginal(URL.createObjectURL(blob));
      setOriginalText(document.media_type?.startsWith('text/') ? await blob.text() : null);
    } catch (err) { setError(String(err)); } finally { setBusy(false); }
  }
  async function decide(decision: string) {
    setBusy(true); setError('');
    try {
      const response = await fetch(`/api/admin/documents/${document.id}/verification`, {
        method: 'POST', cache: 'no-store', headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ decision, reason, revision: document.extraction_revision, ...(decision === 'CORRECT' ? { corrections: sections.map(({ source, text }) => ({ source, text })) } : {}) }),
      });
      if (!response.ok) { const body = await response.json(); throw new Error(body.error?.message ?? body.detail ?? 'Verification failed.'); }
      await onSaved();
    } catch (err) { setError(String(err)); } finally { setBusy(false); }
  }
  // Passages named by a failing or unevaluated check in the current revision need attention.
  const current = document.extractions?.find(r => r.revision === document.extraction_revision)?.payload;
  const flagged = [...(current?.attempts?.flatMap(a => a.quality.checks) ?? []), ...(current?.dpp?.checks ?? [])]
    .filter(c => c.status !== 'PASS' && c.source).map(c => c.source!);
  function attention(source: string) {
    const parts = source.split(';');
    return flagged.some(f => parts.includes(f) || parts.includes(`page:${f}`));
  }
  function checks(rows: Check[]) { return rows.map((c, i) => <li key={i}><strong>{c.status} · {c.rule}</strong> — {c.detail} <small>{c.source}</small></li>); }
  return <section aria-label="Extraction verification"><h3>Extraction verification · {document.extraction_status}</h3>
    <p>Compare the original with the extracted content. Acceptance verifies extraction only; publication requires a separate decision.</p>
    {error && <p role="alert">{error}</p>}
    <button disabled={busy} onClick={() => void loadOriginal()}>Load original for comparison</button>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
      <div><h4>Original file</h4>{original && <a href={original} download={document.filename ?? 'original'}>Download original</a>}
        {originalText !== null && <pre style={{ whiteSpace: 'pre-wrap' }}>{originalText}</pre>}
        {original && document.media_type === 'application/pdf' && <iframe sandbox="" title="Original PDF" src={original} style={{ width: '100%', height: 600 }} />}
        {original && document.media_type?.includes('wordprocessingml') && <p>Open the downloaded DOCX in an approved local viewer for visual comparison.</p>}
      </div>
      <div><h4>Extracted content and corrections</h4>{sections.map((s, i) => <fieldset key={i} disabled={busy} style={attention(s.source) ? { borderColor: '#b45309', borderWidth: 2 } : undefined}>
        {attention(s.source) && <p role="note"><strong>Needs attention:</strong> a check on this passage failed or could not be evaluated.</p>}
        <label>Source reference {i + 1}<input value={s.source} maxLength={500} onChange={e => setSections(sections.map((item, j) => j === i ? { ...item, source: e.target.value } : item))} /></label>
        <label>Extracted passage {i + 1}<textarea rows={6} value={s.text} onChange={e => setSections(sections.map((item, j) => j === i ? { ...item, text: e.target.value } : item))} /></label>
        <button onClick={() => setSections(sections.filter((_, j) => j !== i))}>Remove passage {i + 1}</button>
      </fieldset>)}<button disabled={busy} onClick={() => setSections([...sections, { source: '', text: '' }])}>Add missing passage</button></div>
    </div>
    {document.extractions?.map(record => <details key={record.revision} open={record.revision === document.extraction_revision}>
      <summary>Revision {record.revision} · {record.status} · {record.actor}</summary><p>{record.reason}</p>
      {record.payload.attempts?.map((attempt, i) => <article key={i}><h4>Parser attempt {i + 1}: {attempt.metadata.parser} {attempt.metadata.parser_version} · {attempt.quality.outcome}</h4>{attempt.error && <p>{attempt.error}</p>}<ul>{checks(attempt.quality.checks)}</ul></article>)}
      {record.payload.dpp && <><h4>Structural verification</h4><ul>{checks(record.payload.dpp.checks)}</ul></>}
      {record.payload.field_assessment && <><h4>Optional field assessment · {record.payload.field_assessment.status}</h4><p>{record.payload.field_assessment.reason}</p>{record.payload.field_assessment.fields?.map(field => <article key={field.field}><strong>{field.field} · {field.status}</strong><p>{JSON.stringify(field.value)} · confidence: {field.confidence ?? 'Unavailable'}</p><pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(field.citations, null, 2)}</pre></article>)}</>}
    </details>)}
    <label>Verification reason<textarea value={reason} maxLength={500} onChange={e => setReason(e.target.value)} /></label>
    <fieldset disabled={busy || !reason.trim() || ['QUEUED', 'PROCESSING', 'DUPLICATE'].includes(document.status)}>
      <button onClick={() => void decide('ACCEPT')}>Accept extracted content</button>
      <button onClick={() => void decide('CORRECT')}>Save and accept corrections</button>
      <button onClick={() => void decide('REJECT')}>Reject extraction</button>
      <button onClick={() => void decide('REPROCESS')}>Request reprocessing</button>
    </fieldset>
  </section>;
}
