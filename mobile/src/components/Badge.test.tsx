import { render, screen } from '@testing-library/react-native';
import { Badge } from './Badge';

describe('Badge', () => {
  it('renders a humanized label', async () => {
    await render(<Badge label="in_progress" />);
    expect(screen.getByText('In progress')).toBeOnTheScreen();
  });
});
