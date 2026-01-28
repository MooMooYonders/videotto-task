import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';

describe('App submit button regression', () => {
  it('updates status when submitting a valid URL', async () => {
    // Mock fetch so the test does not depend on a real backend
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ jobId: 'test-job-id', status: 'ok' }),
    } as Response);
    // @ts-expect-error - assign to global in test environment
    global.fetch = mockFetch;

    const user = userEvent.setup();

    render(<App />);

    // Initial state
    expect(screen.getByText(/Status:/i)).toBeInTheDocument();
    expect(screen.getByText(/Waiting for input/i)).toBeInTheDocument();

    // Enter a URL
    const input = screen.getByPlaceholderText('https://www.dropbox.com/...');
    await user.type(input, 'https://www.dropbox.com/some-video');

    // Click the submit button
    const button = screen.getByRole('button', { name: /analyze video/i });
    await user.click(button);

    // After clicking and receiving a successful response, we should see "Analysis completed"
    expect(await screen.findByText(/Analysis completed/i)).toBeInTheDocument();
  });
});

