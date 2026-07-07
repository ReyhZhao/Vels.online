import { Stack } from 'expo-router';
import { HeaderBell } from '@/components/HeaderBell';
import { colors } from '@/lib/theme';

export default function HuntsLayout() {
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
      <Stack.Screen name="index" options={{ title: 'Threat Hunting' }} />
      <Stack.Screen name="new" options={{ title: 'New Hunt', presentation: 'modal' }} />
      <Stack.Screen name="[id]" options={{ title: 'Hunt' }} />
    </Stack>
  );
}
