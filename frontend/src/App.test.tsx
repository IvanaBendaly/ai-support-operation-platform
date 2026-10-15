import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import App from './App';

describe('service readiness', () => {
  it('shows database evidence from the backend', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok: true, json: async () => ({status: 'ready', database: 'connected', schema: '0001'})}));
    render(<App />);
    expect(await screen.findByText('Ready for requests')).toBeInTheDocument();
    expect(screen.getByText('Database connected · Schema 0001')).toBeInTheDocument();
  });
  it('shows a failed readiness check and permits recovery', async () => {
    const fetcher = vi.fn().mockResolvedValueOnce({ok: false, json: async () => ({error: {message: 'Database or schema is unavailable.'}})}).mockResolvedValueOnce({ok: true, json: async () => ({status: 'ready', database: 'connected', schema: '0001'})});
    vi.stubGlobal('fetch', fetcher);
    render(<App />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Database or schema is unavailable.');
    expect(screen.queryByText('Ready for requests')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Check again'}));
    expect(await screen.findByText('Ready for requests')).toBeInTheDocument();
  });
  it('handles network failures without reporting success', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('Network unavailable')));
    render(<App />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Network unavailable');
  });
});
