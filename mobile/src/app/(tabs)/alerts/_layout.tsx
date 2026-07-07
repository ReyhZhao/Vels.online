import { Stack } from 'expo-router';
import { HeaderBell } from '@/components/HeaderBell';
import { colors } from '@/lib/theme';

export default function AlertsLayout() {
  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: colors.card },
        headerTintColor: colors.foreground,
        headerTitleStyle: { fontWeight: '600' },
        headerRight: () => <HeaderBell />,
        contentStyle: { backgroundColor: colors.background },
      }}
    >
      <Stack.Screen name="index" options={{ title: 'Alert Inbox' }} />
      <Stack.Screen name="[id]" options={{ title: 'Alert' }} />
    </Stack>
  );
}
