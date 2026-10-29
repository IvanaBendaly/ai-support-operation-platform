import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ExtractionVerification, { type ExtractionDocument } from './ExtractionVerification';

afterEach(() => vi.unstubAllGlobals());
const document: ExtractionDocument = {
  id: 'version-1', filename: 'leave.pdf', media_type: 'application/pdf', status: 'READY', extraction_status: 'HUMAN_REQUIRED', extraction_revision: 1,
  sections: [{ id: 's1', source: 'page:1;item:#/texts/0;heading:Leave', text: 'Allow 20 days.' }, { id: 's2', source: 'page:2;item:#/tables/0;heading:Leave', text: 'Plan | Days' }],
  extractions: [{ revision: 1, status: 'HUMAN_REQUIRED', actor: 'worker', reason: '', payload: {
    attempts: [{ metadata: { parser: 'docling', parser_version: '2.143.0' }, quality: { outcome: 'UNCERTAIN', checks: [{ rule: 'ocr_score', status: 'NOT_EVALUATED', detail: 'Score: None', source: '2' }] } }],
    dpp: { checks: [{ rule: 'visual_reading_order', status: 'NOT_EVALUATED', detail: 'Compare with the original page (DPP §5.9).' }] },
    field_assessment: { status: 'SKIPPED', reason: 'external_processing_prohibited' },
  } }],
};

it('highlights questionable passages and shows parser evidence', () => {
  render(<ExtractionVerification document={document} token="t" onSaved={async () => {}} />);
  expect(screen.getAllByRole('note')).toHaveLength(1);
  expect(screen.getByLabelText('Extracted passage 2').closest('fieldset')).toContainElement(screen.getByRole('note'));
  expect(screen.getByText(/Parser attempt 1: docling 2.143.0 · UNCERTAIN/)).toBeInTheDocument();
  expect(screen.getByText('external_processing_prohibited')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Accept extracted content' })).toBeDisabled();
});

it('submits corrections with the reviewed revision and a reason', async () => {
  const fetcher = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
  const saved = vi.fn().mockResolvedValue(undefined);
  vi.stubGlobal('fetch', fetcher);
  render(<ExtractionVerification document={document} token="private-test-token" onSaved={saved} />);
  fireEvent.change(screen.getByLabelText('Extracted passage 1'), { target: { value: 'Allow 25 days.' } });
  fireEvent.change(screen.getByLabelText('Verification reason'), { target: { value: 'Fixed the day count.' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save and accept corrections' }));
  await waitFor(() => expect(saved).toHaveBeenCalled());
  const [url, init] = fetcher.mock.calls[0];
  expect(url).toBe('/api/admin/documents/version-1/verification');
  expect(init.headers.Authorization).toBe('Bearer private-test-token');
  const body = JSON.parse(init.body);
  expect(body).toMatchObject({ decision: 'CORRECT', reason: 'Fixed the day count.', revision: 1 });
  expect(body.corrections[0]).toEqual({ source: document.sections![0].source, text: 'Allow 25 days.' });
});
