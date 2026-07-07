import { StyleSheet, Text, View } from 'react-native';
import { humanize } from '../lib/format';
import { colors, fontSize } from '../lib/theme';

interface BadgeProps {
  label: string;
  color?: string;
}

/** Small tinted pill, used for severities, states and source kinds. */
export function Badge({ label, color = colors.muted }: BadgeProps) {
  return (
    <View style={[styles.badge, { backgroundColor: `${color}26`, borderColor: `${color}59` }]}>
      <Text style={[styles.text, { color }]} numberOfLines={1}>
        {humanize(label)}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 2,
    alignSelf: 'flex-start',
  },
  text: {
    fontSize: fontSize.xs,
    fontWeight: '600',
    textTransform: 'capitalize',
  },
});
