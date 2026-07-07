import { useEffect, useState } from 'react';
import { StyleSheet, TextInput, View } from 'react-native';
import { Search } from 'lucide-react-native';
import { colors, fontSize, radius, spacing } from '../lib/theme';

interface SearchBarProps {
  placeholder?: string;
  onSearch: (term: string) => void;
  debounceMs?: number;
}

/** Debounced search input matching the web app's list search affordance. */
export function SearchBar({ placeholder = 'Search…', onSearch, debounceMs = 350 }: SearchBarProps) {
  const [value, setValue] = useState('');

  useEffect(() => {
    const handle = setTimeout(() => onSearch(value.trim()), debounceMs);
    return () => clearTimeout(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <View style={styles.wrapper}>
      <Search size={16} color={colors.muted} />
      <TextInput
        style={styles.input}
        placeholder={placeholder}
        placeholderTextColor={colors.muted}
        value={value}
        onChangeText={setValue}
        autoCapitalize="none"
        autoCorrect={false}
        returnKeyType="search"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    backgroundColor: colors.secondary,
    borderColor: colors.border,
    borderWidth: 1,
    borderRadius: radius,
    marginHorizontal: spacing.lg,
    marginVertical: spacing.sm,
    paddingHorizontal: spacing.md,
  },
  input: {
    flex: 1,
    color: colors.foreground,
    fontSize: fontSize.md,
    paddingVertical: 10,
  },
});
