export type Lifecycle = 'Awaiting worker' | 'Needs review' | 'Published' | 'Inactive' | 'Rejected' | 'Superseded';
export type Section = { id: string; version_id: string; title: string; source: string; text: string };
export type Version = { version_id: string; document_id: string; revision: number; filename: string; format: string; size: number; created: string; state: Lifecycle; sections: Section[]; original_hash: string; content_hash?: string; warnings: string[] };
export type Document = { document_id: string; title: string; category: string; versions: Version[] };
export type UploadEntry = { file: File; title: string; category: string; document_id: string };
export const MAX_FILE = 5 * 1024 * 1024;
export function validateFile(file: File): string | undefined {
  if (!/\.(pdf|docx|md|txt)$/i.test(file.name)) return 'Choose a PDF, DOCX, MD or TXT file.';
  if (!file.size) return 'Empty files cannot be uploaded.';
  if (file.size > MAX_FILE) return 'File exceeds the 5 MiB limit.';
}
export function validateBatch(entries: UploadEntry[]) {
  if (!entries.length) return 'Choose at least one file.';
  if (entries.length > 10) return 'A batch can contain up to 10 files.';
  if (entries.reduce((sum, e) => sum + e.file.size, 0) > 10 * 1024 * 1024) return 'Batch exceeds the 10 MiB total limit.';
  if (entries.some(e => !e.title.trim() || e.title.trim().length > 160)) return 'Each document needs a title of 1–160 characters.';
  return entries.map(e => validateFile(e.file)).find(Boolean);
}
export const normalize = (text: string) => text.normalize('NFC').replace(/\r\n?/g, '\n').split('\n').map(line => line.trimEnd()).join('\n');
export async function fingerprint(bytes: ArrayBuffer) {
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
}
export function sectionsFor(text: string, version_id: string): Section[] {
  const sections: Section[] = [];
  let title = 'Document text';
  text.split('\n').forEach((line, index) => {
    if (/^#{1,6}\s/.test(line)) title = line.replace(/^#{1,6}\s+/, '');
    if (!line.trim()) return;
    for (let start = 0; start < line.length; start += 2000) {
      sections.push({ id: `${version_id}-s${sections.length + 1}`, version_id, title, source: `Line ${index + 1} · characters ${start + 1}–${Math.min(start + 2000, line.length)}`, text: line.slice(start, start + 2000) });
    }
  });
  return sections;
}
export function eligible(version: Version) { return version.state === 'Published'; }
// Session-only adapter. No upload is sent to the legacy auto-publishing API.
// Replace this boundary with the authenticated worker-backed API in the backend phase.
export async function prepareUpload(entry: UploadEntry, documents: Document[]): Promise<Document> {
  const invalid = validateFile(entry.file);
  if (invalid) throw new Error(invalid);
  if (!entry.title.trim() || entry.title.trim().length > 160) throw new Error('A title of 1–160 characters is required.');
  const existing = documents.find(d => d.document_id === entry.document_id);
  if (entry.document_id && !existing) throw new Error('The selected document no longer exists.');
  const bytes = await entry.file.arrayBuffer();
  const original_hash = await fingerprint(bytes);
  const all = documents.flatMap(d => d.versions);
  const duplicate = all.find(v => v.original_hash === original_hash);
  if (duplicate) throw new Error(`Identical file already exists as ${duplicate.filename}, version ${duplicate.revision}. No version relationship was created.`);
  const format = entry.file.name.split('.').pop()!.toUpperCase();
  let text: string | undefined;
  let content_hash: string | undefined;
  if (format === 'TXT' || format === 'MD') {
    try { text = normalize(new TextDecoder('utf-8', { fatal: true }).decode(bytes)); }
    catch { throw new Error('The text file must use valid UTF-8 encoding.'); }
    if (text.length > 1_000_000) throw new Error('Text exceeds the one-million-character preview limit.');
    if (!text.trim()) throw new Error('No readable text was found.');
    if (text.includes('\u0000')) throw new Error('The file contains binary data, not readable text.');
    content_hash = await fingerprint(new TextEncoder().encode(text).buffer);
    const match = all.find(v => v.content_hash === content_hash);
    if (match) throw new Error(`Identical normalized text already exists in ${match.filename}. No version relationship was created.`);
  }
  const document_id = existing?.document_id ?? crypto.randomUUID();
  const version_id = crypto.randomUUID();
  const version: Version = { document_id, version_id, revision: Math.max(0, ...(existing?.versions.map(v => v.revision) ?? [])) + 1,
    filename: entry.file.name, format, size: entry.file.size, created: new Date().toISOString(), original_hash, content_hash,
    state: text ? 'Needs review' : 'Awaiting worker', sections: text ? sectionsFor(text, version_id) : [],
    warnings: text ? ['Browser text preview only. Server validation and AI review have not run.', ...(text.length < 100 ? ['Short document: verify the source is complete.'] : [])] : ['Docling extraction requires the backend worker. No text has been extracted.'] };
  return { document_id, title: existing?.title ?? entry.title.trim(), category: existing?.category ?? entry.category, versions: [...(existing?.versions ?? []), version] };
}
export function transition(document: Document, version_id: string, state: Lifecycle): Document {
  const selected = document.versions.find(v => v.version_id === version_id);
  if (!selected) throw new Error('Version no longer exists.');
  if (state === 'Published' && (selected.state !== 'Needs review' || !selected.sections.length)) throw new Error('Only an extracted version awaiting review can be published.');
  return { ...document, versions: document.versions.map(v => v.version_id === version_id ? { ...v, state } : state === 'Published' && v.state === 'Published' ? { ...v, state: 'Superseded' } : v) };
}
export function sampleDocuments(): Document[] {
  return [
    ['Employee leave policy', 'People operations', 'MD', 'Published'],
    ['Customer refund guidelines', 'Customer support', 'PDF', 'Needs review'],
    ['Information security handbook', 'Security', 'DOCX', 'Awaiting worker'],
    ['Subscription and billing FAQ', 'Customer support', 'TXT', 'Published'],
    ['Remote work policy', 'People operations', 'MD', 'Inactive'],
  ].map(([title, category, format, state], i) => {
    const document_id = `example-document-${i + 1}`, version_id = `example-version-${i + 1}`;
    const text = `# ${title}\nThis is example content for exploring the administration interface. Replace it with your own source document.\n\n## Scope\nThis sample is not an authoritative business policy.`;
    return { document_id, title, category, versions: [{ document_id, version_id, revision: 1, filename: `${title.toLowerCase().replaceAll(' ', '-')}.${format.toLowerCase()}`, format, size: 2400 + i * 4200, created: '2026-10-23T08:00:00Z', state: state as Lifecycle, original_hash: 'Example — not a computed fingerprint', warnings: ['Example data. AI review has not run.'], sections: state === 'Awaiting worker' ? [] : sectionsFor(text, version_id) }] };
  });
}
