import { ActivityIndicator, StyleSheet, Text, View } from 'react-native';
import { colors, fontSize, spacing } from '../lib/theme';

export function LoadingView() {
  return (
    <View style={styles.center} testID="loading-view">
      <ActivityIndicator color={colors.primary} size="large" />
    </View>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <View style={styles.center}>
      <Text style={styles.emptyText}>{message}</Text>
    </View>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <View style={styles.center}>
      <Text style={styles.errorText}>{message}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    minHeight: 160,
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.xl,
  },
  emptyText: {
    color: colors.muted,
    fontSize: fontSize.md,
    textAlign: 'center',
  },
  errorText: {
    color: colors.destructive,
    fontSize: fontSize.md,
    textAlign: 'center',
  },
});
