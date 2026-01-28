import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import App from '../App';

describe('App submit button regression', () => {
  it('updates status when submitting a valid URL', async () => {
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

    // After clicking, we should at least see "Processing video..."
    expect(screen.getByText(/Processing video/i)).toBeInTheDocument();
  });
});

