import { useState } from 'react';
import {
  Alert as RNAlert,
  ScrollView,
  StyleSheet,
  Switch,
  Text,
  TextInput,
  View,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Button } from '@/components/Button';
import { KeyValue } from '@/components/KeyValue';
import api from '@/lib/api';
import { colors, fontSize, radius, spacing } from '@/lib/theme';

export default function NewHuntScreen() {
  const router = useRouter();
  const [seedText, setSeedText] = useState('');
  const [lookbackDays, setLookbackDays] = useState('30');
  const [allOrgs, setAllOrgs] = useState(true);
  const [starting, setStarting] = useState(false);

  async function startHunt() {
    const seed = seedText.trim();
    if (!seed) return;
    setStarting(true);
    try {
      const createRes = await api.post('/api/hunts/', {
        seed_kind: 'question',
        seed_text: seed,
        scope_all_orgs: allOrgs,
        lookback_days: Math.min(365, Math.max(1, parseInt(lookbackDays, 10) || 30)),
      });
      const huntId = createRes.data.id;
      await api.post(`/api/hunts/${huntId}/begin/`);
      router.replace({ pathname: '/hunts/[id]', params: { id: huntId } });
    } catch (err: any) {
      RNAlert.alert(
        'Could not start hunt',
        err?.response?.data?.detail ?? JSON.stringify(err?.response?.data ?? 'Please try again.'),
      );
      setStarting(false);
    }
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.label}>What are you hunting for?</Text>
      <TextInput
        style={styles.seedInput}
        multiline
        placeholder="e.g. Look for signs of credential stuffing against exposed RDP hosts"
        placeholderTextColor={colors.muted}
        value={seedText}
        onChangeText={setSeedText}
        testID="hunt-seed-input"
      />
      <View style={styles.options}>
        <KeyValue label="Hunt across all organisations">
          <Switch
            value={allOrgs}
            onValueChange={setAllOrgs}
            trackColor={{ true: colors.primary, false: colors.secondary }}
          />
        </KeyValue>
        <KeyValue label="Lookback (days)">
          <TextInput
            style={styles.daysInput}
            keyboardType="number-pad"
            value={lookbackDays}
            onChangeText={setLookbackDays}
            maxLength={3}
          />
        </KeyValue>
      </View>
      <Button
        title="Start hunt"
        onPress={startHunt}
        loading={starting}
        disabled={!seedText.trim()}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: colors.background,
  },
  content: {
    padding: spacing.lg,
  },
  label: {
    color: colors.muted,
    fontSize: fontSize.sm,
    marginBottom: spacing.sm,
  },
  seedInput: {
    minHeight: 120,
    backgroundColor: colors.secondary,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius,
    color: colors.foreground,
    fontSize: fontSize.md,
    padding: spacing.md,
    textAlignVertical: 'top',
    marginBottom: spacing.lg,
  },
  options: {
    marginBottom: spacing.lg,
  },
  daysInput: {
    backgroundColor: colors.secondary,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius,
    color: colors.foreground,
    fontSize: fontSize.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    minWidth: 64,
    textAlign: 'center',
  },
});
