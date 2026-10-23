import { useRef, useState } from 'react';
import { Document, UploadEntry, validateBatch, validateFile, prepareUpload } from './model';

type Props = { documents: Document[]; target?: string; batch: boolean; onSave: (documents: Document[]) => void; onClose: () => void; onBusy: (busy: boolean) => void };
export default function Upload({ documents, target, batch, onSave, onClose, onBusy }: Props) {
  const [entries, setEntries] = useState<UploadEntry[]>([]);
  const [results, setResults] = useState<Record<number, string>>({});
  const [done, setDone] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const input = useRef<HTMLInputElement>(null);
  function add(files: FileList | null) {
    if (!files || busy || done.length) return;
    const next = Array.from(files).map(file => ({ file, title: file.name.replace(/\.[^.]+$/, '').replaceAll('-', ' '), category: 'General', document_id: target ?? '' }));
    if (entries.length + next.length > (batch ? 10 : 1)) { setError(batch ? 'Select up to 10 files.' : 'Select one file, or use batch upload.'); return; }
    setEntries([...entries, ...next]); setError('');
  }
  function update(index: number, patch: Partial<UploadEntry>) { setEntries(entries.map((e, i) => i === index ? { ...e, ...patch } : e)); }
  async function submit() {
    const pending = entries.filter((_, i) => !done.includes(i));
    const invalid = validateBatch(pending);
    if (invalid) { setError(invalid); return; }
    setBusy(true); onBusy(true); setError('');
    let current = [...documents];
    const completed = [...done];
    for (const [i, entry] of entries.entries()) {
      if (done.includes(i)) continue;
      setResults(r => ({ ...r, [i]: 'Validating and fingerprinting…' }));
      try {
        const doc = await prepareUpload(entry, current);
        current = [...current.filter(d => d.document_id !== doc.document_id), doc];
        completed.push(i);
        setResults(r => ({ ...r, [i]: doc.versions.at(-1)!.state === 'Awaiting worker' ? 'Added · awaiting backend extraction' : 'Added · text preview ready for review' }));
      } catch (err) { setResults(r => ({ ...r, [i]: err instanceof Error ? err.message : 'Unable to read file. Please retry.' })); }
    }
    onSave(current); setDone(completed); setBusy(false); onBusy(false);
  }
  return <section className="upload-page">
    <button className="text-button" onClick={onClose} disabled={busy}>← Back to documents</button>
    <div className="page-heading"><p className="eyebrow">ADD TO YOUR KNOWLEDGE</p><h1>{target ? 'Upload a replacement' : batch ? 'Batch upload' : 'Upload a document'}</h1><p>Prepare source material for extraction and human review.</p></div>
    <div className="upload-layout"><div className="panel upload-panel">
      <h2>1. Choose your source files</h2><p>PDF, DOCX, Markdown or plain text · 5 MiB per file{batch ? ' · 10 files / 10 MiB per batch' : ''}</p>
      <div className="dropzone" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); add(e.dataTransfer.files); }}>
        <span className="upload-icon" aria-hidden="true">↑</span><h3>Drop {batch ? 'your files' : 'a file'} here</h3><p>or select from your computer</p><button disabled={busy || done.length > 0} onClick={() => input.current?.click()}>Browse files</button>
        <input ref={input} aria-label="Source files" type="file" accept=".pdf,.docx,.md,.txt" multiple={batch} hidden disabled={busy || done.length > 0} onChange={e => { add(e.target.files); e.target.value = ''; }} />
      </div>
      {entries.length > 0 && <h2 className="metadata-title">2. Confirm document relationships</h2>}
      {entries.map((entry, i) => <fieldset key={i} disabled={busy || done.includes(i)} className="upload-entry"><legend>{entry.file.name} <span className="muted">· {(entry.file.size / 1024).toFixed(1)} KiB</span></legend>
        <label>Upload as<select value={entry.document_id} onChange={e => update(i, { document_id: e.target.value })}><option value="">New logical document</option>{documents.map(d => <option key={d.document_id} value={d.document_id}>Replacement: {d.title}</option>)}</select></label>
        {entry.document_id ? <p className="note">A new version will be attached to the selected document. Its current published version stays available until this replacement is approved.</p> : <div className="form-grid"><label>Document title<input value={entry.title} maxLength={160} onChange={e => update(i, { title: e.target.value })} /></label><label>Collection<select value={entry.category} onChange={e => update(i, { category: e.target.value })}>{['General', 'People operations', 'Customer support', 'Security', 'Product'].map(c => <option key={c}>{c}</option>)}</select></label></div>}
        {validateFile(entry.file) && <p className="inline-error">{validateFile(entry.file)}</p>}
        {results[i] && <p role="status" className={done.includes(i) ? 'success-text' : 'inline-error'}>{results[i]}</p>}
        {!done.includes(i) && done.length === 0 && <button className="text-button" onClick={() => { setEntries(entries.filter((_, n) => n !== i)); setResults({}); }}>Remove file</button>}
      </fieldset>)}
      {error && <div className="error" role="alert">{error}</div>}
      <div className="form-actions"><span>{done.length ? `${done.length} of ${entries.length} files added` : `${entries.length} files selected`}</span><button className="primary" disabled={busy || !entries.length || done.length === entries.length} onClick={() => void submit()}>{busy ? 'Preparing files…' : 'Validate & add to preview'}</button></div>
    </div><aside className="upload-help panel"><p className="eyebrow">WHAT HAPPENS NEXT</p><ol><li><strong>Validate & fingerprint</strong><p>Check file limits and detect duplicate bytes with SHA-256.</p></li><li><strong>Extract & prepare</strong><p>Preserve source references and create readable sections. PDF and DOCX require Docling on the worker.</p></li><li><strong>Review before publication</strong><p>Extraction alone never makes a version eligible for search.</p></li></ol><div className="note">Matching content does not establish a version relationship. You choose the document explicitly.</div><p className="muted">Preview only: files stay in this browser session. No originals are stored or sent to a server. Refreshing clears your changes.</p></aside></div>
  </section>;
}
