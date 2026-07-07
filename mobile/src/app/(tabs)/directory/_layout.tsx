import { Stack } from 'expo-router';
import { HeaderBell } from '@/components/HeaderBell';
import { colors } from '@/lib/theme';

export default function DirectoryLayout() {
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
      <Stack.Screen name="index" options={{ title: 'Directory' }} />
      <Stack.Screen name="contact/[id]" options={{ title: 'Contact' }} />
      <Stack.Screen name="asset/[id]" options={{ title: 'Asset' }} />
    </Stack>
  );
}
