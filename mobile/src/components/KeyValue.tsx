import { StyleSheet, Text, View } from 'react-native';
import { colors, fontSize, spacing } from '../lib/theme';

interface KeyValueProps {
  label: string;
  value?: string | number | null;
  children?: React.ReactNode;
}

/** Detail-screen row: muted label on the left, value (or custom node) on the right. */
export function KeyValue({ label, value, children }: KeyValueProps) {
  return (
    <View style={styles.row}>
      <Text style={styles.label}>{label}</Text>
      {children ?? <Text style={styles.value}>{value ?? '—'}</Text>}
    </View>
  );
}

export function SectionHeader({ title }: { title: string }) {
  return <Text style={styles.section}>{title}</Text>;
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: 6,
  },
  label: {
    color: colors.muted,
    fontSize: fontSize.sm,
  },
  value: {
    color: colors.foreground,
    fontSize: fontSize.sm,
    flexShrink: 1,
    textAlign: 'right',
  },
  section: {
    color: colors.muted,
    fontSize: fontSize.xs,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginHorizontal: spacing.lg,
    marginTop: spacing.lg,
    marginBottom: spacing.xs,
  },
});
