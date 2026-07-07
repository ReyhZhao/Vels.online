import { Stack } from 'expo-router';
import { HeaderBell } from '@/components/HeaderBell';
import { colors } from '@/lib/theme';

export default function IncidentsLayout() {
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
      <Stack.Screen name="index" options={{ title: 'Incidents' }} />
      <Stack.Screen name="[id]" options={{ title: 'Incident' }} />
    </Stack>
  );
}
