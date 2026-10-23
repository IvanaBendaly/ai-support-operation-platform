import { describe, expect, it } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import App from '../App';
import { MAX_FILE, normalize, prepareUpload, sectionsFor, transition, validateBatch, validateFile } from './model';

function file(name: string, text: string) {
  const bytes = new TextEncoder().encode(text);
  return { name, size: bytes.byteLength, arrayBuffer: async () => bytes.buffer } as File;
}
const entry = (name = 'policy.md', text = '# Policy\nLeave must be approved.') => ({ file: file(name, text), title: 'Leave policy', category: 'People operations', document_id: '' });

describe('upload preparation', () => {
  it('checks format, empty files, per-file and aggregate limits', () => {
    expect(validateFile(file('program.exe', 'data'))).toContain('PDF');
    expect(validateFile(file('empty.txt', ''))).toContain('Empty');
    expect(validateFile({ name: 'large.pdf', size: MAX_FILE + 1 } as File)).toContain('5 MiB');
    expect(validateBatch(Array.from({ length: 11 }, () => entry()))).toContain('10 files');
    expect(validateBatch(Array.from({ length: 3 }, () => ({ ...entry(), file: { name: 'a.pdf', size: MAX_FILE } as File })))).toContain('10 MiB');
    expect(validateBatch([{ ...entry(), title: ' ' }])).toContain('title');
  });
  it('creates a distinct document and revision without publishing or embedding', async () => {
    const doc = await prepareUpload(entry(), []);
    expect(doc.document_id).not.toBe(doc.versions[0].version_id);
    expect(doc.versions[0].state).toBe('Needs review');
    expect(doc.versions[0].original_hash).toMatch(/^[a-f0-9]{64}$/);
    expect(doc.versions[0].sections[0].version_id).toBe(doc.versions[0].version_id);
  });
  it('requires an explicit document selection for replacement and keeps the active version', async () => {
    let doc = await prepareUpload(entry(), []);
    doc = transition(doc, doc.versions[0].version_id, 'Published');
    const replacement = await prepareUpload({ ...entry('new.txt', 'A different revision.'), document_id: doc.document_id }, [doc]);
    expect(replacement.document_id).toBe(doc.document_id);
    expect(replacement.versions.map(v => v.revision)).toEqual([1, 2]);
    expect(replacement.versions[0].state).toBe('Published');
    expect(replacement.versions[1].state).toBe('Needs review');
    await expect(prepareUpload({ ...entry(), document_id: 'missing' }, [])).rejects.toThrow('no longer exists');
  });
  it('detects duplicate bytes and normalized text without assigning a relationship', async () => {
    const doc = await prepareUpload(entry('first.md', '# Policy\r\nLeave.  '), []);
    await expect(prepareUpload(entry('second.txt', '# Policy\r\nLeave.  '), [doc])).rejects.toThrow('Identical file');
    await expect(prepareUpload(entry('second.md', '# Policy\nLeave.'), [doc])).rejects.toThrow('Identical normalized text');
    expect(doc.versions).toHaveLength(1);
  });
  it('does not fabricate Docling extraction', async () => {
    const doc = await prepareUpload(entry('policy.docx', 'unvalidated bytes'), []);
    expect(doc.versions[0].state).toBe('Awaiting worker');
    expect(doc.versions[0].sections).toEqual([]);
    expect(() => transition(doc, doc.versions[0].version_id, 'Published')).toThrow('Only an extracted');
  });
  it('rejects unreadable text and retains conservative normalization', async () => {
    await expect(prepareUpload(entry('blank.txt', '  \r\n '), [])).rejects.toThrow('No readable text');
    await expect(prepareUpload(entry('binary.txt', 'A\u0000B'), [])).rejects.toThrow('binary');
    expect(normalize('Do NOT refund $100.  \r\nKeep:  A  B')).toBe('Do NOT refund $100.\nKeep:  A  B');
    const sections = sectionsFor('# Policy\n' + 'a'.repeat(2001), 'v1');
    expect(sections).toHaveLength(3);
    expect(sections[2].source).toContain('2001');
  });
  it('supersedes publication atomically and never revives old versions on deactivation', async () => {
    let doc = await prepareUpload(entry(), []);
    doc = transition(doc, doc.versions[0].version_id, 'Published');
    doc = await prepareUpload({ ...entry('v2.txt', 'Updated policy'), document_id: doc.document_id }, [doc]);
    doc = transition(doc, doc.versions[1].version_id, 'Published');
    expect(doc.versions.map(v => v.state)).toEqual(['Superseded', 'Published']);
    doc = transition(doc, doc.versions[1].version_id, 'Inactive');
    expect(doc.versions.map(v => v.state)).toEqual(['Superseded', 'Inactive']);
  });
});

describe('admin workspace', () => {
  it('starts empty, labels the preview, and supports searching examples', () => {
    render(<App />);
    expect(screen.getByText('Your knowledge starts here')).toBeInTheDocument();
    expect(screen.getByText(/Changes disappear on refresh/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Load examples' }));
    fireEvent.change(screen.getByLabelText('Search documents'), { target: { value: 'refund' } });
    expect(screen.getByRole('button', { name: 'Customer refund guidelines' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Employee leave policy' })).not.toBeInTheDocument();
  });
  it('requires confirmation to publish, and shows separate document and version identities', () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Load examples' }));
    fireEvent.click(screen.getByRole('button', { name: 'Customer refund guidelines' }));
    expect(screen.getByText('example-document-2')).toBeInTheDocument();
    expect(screen.getByText('example-version-2')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Approve & publish' }));
    expect(screen.queryByRole('button', { name: 'Deactivate version' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm in preview' }));
    expect(screen.getByRole('button', { name: 'Deactivate version' })).toBeInTheDocument();
  });
  it('uploads a batch with per-file results and retries failures without duplicating successes', async () => {
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'Batch upload' }));
    fireEvent.change(screen.getByLabelText('Source files'), { target: { files: [file('good.md', '# Good\nContent'), file('empty.txt', '  ')] } });
    fireEvent.click(screen.getByRole('button', { name: 'Validate & add to preview' }));
    expect(await screen.findByText('1 of 2 files added')).toBeInTheDocument();
    expect(screen.getByText('No readable text was found.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Validate & add to preview' }));
    expect(await screen.findByText('1 of 2 files added')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('button', { name: /Back to documents/ })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: /Back to documents/ }));
    expect(screen.getByRole('button', { name: 'good' })).toBeInTheDocument();
  });
});
