import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import Connected from './Connected';

afterEach(() => vi.unstubAllGlobals());
const record = { id: 'version-1', policy_id: 'leave', title: 'Leave policy', version: 1, sensitivity: 'PUBLIC', status: 'READY', extraction_status: 'VERIFIED', extraction_revision: 1, lifecycle: 'PENDING_REVIEW', review_status: 'DONE', publication_status: 'PENDING_REVIEW', sections: [], events: [], assessments: [{ id: 'a', provider: 'none', model_id: null, assessment_status: 'unavailable', needs_review: true, risk_level: 'high', explanation: 'Human inspection required.', review_reasons: ['ai_processing_not_permitted'], supporting_references: [] }] };

it('requires classification and uses an authenticated server upload', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => ({ document: record, duplicate: false }) }).mockResolvedValueOnce({ ok: true, json: async () => [record] }).mockResolvedValueOnce({ ok: true, json: async () => record });
  vi.stubGlobal('fetch', fetcher);
  render(<Connected />);
  fireEvent.change(screen.getByLabelText('Administrator token'), { target: { value: 'private-test-token' } });
  expect(screen.getByLabelText('Sensitivity')).toHaveValue('');
  expect(screen.getByLabelText('Sensitivity')).toBeRequired();
  fireEvent.change(screen.getByLabelText('Policy identifier'), { target: { value: 'leave' } });
  fireEvent.change(screen.getByLabelText('Title'), { target: { value: 'Leave policy' } });
  fireEvent.change(screen.getByLabelText('Sensitivity'), { target: { value: 'PUBLIC' } });
  fireEvent.change(screen.getByLabelText('Source file'), { target: { files: [new File(['Policy'], 'policy.txt')] } });
  fireEvent.submit(screen.getByRole('button', { name: 'Upload to private storage' }).closest('form')!);
  await screen.findByText('Human inspection required.');
  expect(fetcher.mock.calls[0][0]).toBe('/api/admin/documents');
  expect(fetcher.mock.calls[0][1].headers.Authorization).toBe('Bearer private-test-token');
  expect(fetcher.mock.calls[0][1].body.get('sensitivity')).toBe('PUBLIC');
  expect(screen.getByRole('button', { name: 'Save human decision' })).toBeDisabled();
});

it('persists an explicit human decision with a required reason', async () => {
  const fetcher = vi.fn().mockResolvedValueOnce({ ok: true, json: async () => [record] }).mockResolvedValueOnce({ ok: true, json: async () => record }).mockResolvedValueOnce({ ok: true, json: async () => ({ ...record, publication_status: 'APPROVED' }) }).mockResolvedValueOnce({ ok: true, json: async () => [] });
  vi.stubGlobal('fetch', fetcher);
  render(<Connected />);
  fireEvent.change(screen.getByLabelText('Administrator token'), { target: { value: 'private-test-token' } });
  fireEvent.click(screen.getByRole('button', { name: 'Load documents' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Leave policy · v1' }));
  await screen.findByText('Human inspection required.');
  fireEvent.change(screen.getByLabelText('Decision reason'), { target: { value: 'I checked the source manually.' } });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save human decision' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Save human decision' }));
  await screen.findByText('Human decision saved.');
  expect(JSON.parse(fetcher.mock.calls[2][1].body)).toEqual({ decision: 'APPROVED', reason: 'I checked the source manually.' });
});
