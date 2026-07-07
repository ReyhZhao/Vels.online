import { fireEvent, render, screen } from '@testing-library/react-native';
import { FilterChips } from './FilterChips';

describe('FilterChips', () => {
  it('selects a chip when tapped', async () => {
    const onSelect = jest.fn();
    await render(
      <FilterChips options={['critical', 'high']} selected={null} onSelect={onSelect} />,
    );
    await fireEvent.press(screen.getByText('Critical'));
    expect(onSelect).toHaveBeenCalledWith('critical');
  });

  it('clears the filter when the active chip is tapped', async () => {
    const onSelect = jest.fn();
    await render(
      <FilterChips options={['critical', 'high']} selected="critical" onSelect={onSelect} />,
    );
    await fireEvent.press(screen.getByText('Critical'));
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it('clears the filter via the All chip', async () => {
    const onSelect = jest.fn();
    await render(
      <FilterChips options={['critical']} selected="critical" onSelect={onSelect} allLabel="All" />,
    );
    await fireEvent.press(screen.getByText('All'));
    expect(onSelect).toHaveBeenCalledWith(null);
  });
});
