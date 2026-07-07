import { Pressable, ScrollView, StyleSheet, Text } from 'react-native';
import { humanize } from '../lib/format';
import { colors, fontSize, spacing } from '../lib/theme';

interface FilterChipsProps {
  options: readonly string[];
  selected: string | null;
  onSelect: (value: string | null) => void;
  allLabel?: string;
}

/** Horizontal single-select chip row; tapping the active chip clears the filter. */
export function FilterChips({ options, selected, onSelect, allLabel = 'All' }: FilterChipsProps) {
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.row}
    >
      <Chip label={allLabel} active={selected === null} onPress={() => onSelect(null)} />
      {options.map((option) => (
        <Chip
          key={option}
          label={humanize(option)}
          active={selected === option}
          onPress={() => onSelect(selected === option ? null : option)}
        />
      ))}
    </ScrollView>
  );
}

function Chip({ label, active, onPress }: { label: string; active: boolean; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={[styles.chip, active && styles.chipActive]}
      accessibilityRole="button"
      accessibilityState={{ selected: active }}
    >
      <Text style={[styles.chipText, active && styles.chipTextActive]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: {
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
  },
  chip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.secondary,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  chipActive: {
    backgroundColor: colors.primary,
    borderColor: colors.primary,
  },
  chipText: {
    color: colors.muted,
    fontSize: fontSize.sm,
    fontWeight: '500',
  },
  chipTextActive: {
    color: colors.primaryForeground,
  },
});
