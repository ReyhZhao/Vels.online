import { Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, fontSize, radius, spacing } from '../lib/theme';

interface SegmentedProps {
  options: readonly string[];
  labels?: Record<string, string>;
  selected: string;
  onSelect: (value: string) => void;
}

export function Segmented({ options, labels = {}, selected, onSelect }: SegmentedProps) {
  return (
    <View style={styles.wrapper}>
      {options.map((option) => {
        const active = option === selected;
        return (
          <Pressable
            key={option}
            onPress={() => onSelect(option)}
            style={[styles.segment, active && styles.segmentActive]}
            accessibilityRole="tab"
            accessibilityState={{ selected: active }}
          >
            <Text style={[styles.text, active && styles.textActive]}>
              {labels[option] ?? option}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    flexDirection: 'row',
    backgroundColor: colors.secondary,
    borderRadius: radius,
    borderWidth: 1,
    borderColor: colors.border,
    marginHorizontal: spacing.lg,
    marginVertical: spacing.sm,
    padding: 3,
  },
  segment: {
    flex: 1,
    paddingVertical: 8,
    borderRadius: radius - 3,
    alignItems: 'center',
  },
  segmentActive: {
    backgroundColor: colors.primary,
  },
  text: {
    color: colors.muted,
    fontSize: fontSize.sm,
    fontWeight: '600',
  },
  textActive: {
    color: colors.primaryForeground,
  },
});
