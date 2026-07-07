import AsyncStorage from '@react-native-async-storage/async-storage';

const STORAGE_KEY = 'vels.serverUrl';

export const DEFAULT_SERVER_URL = 'https://vels.online';

let currentServerUrl: string = DEFAULT_SERVER_URL;

/** Trim whitespace, default to https://, strip trailing slashes. */
export function normalizeServerUrl(input: string): string {
  let url = (input || '').trim();
  if (!url) return DEFAULT_SERVER_URL;
  if (!/^https?:\/\//i.test(url)) {
    url = `https://${url}`;
  }
  return url.replace(/\/+$/, '');
}

export function getServerUrl(): string {
  return currentServerUrl;
}

export function setServerUrl(url: string): void {
  currentServerUrl = normalizeServerUrl(url);
}

export async function loadServerUrl(): Promise<string> {
  try {
    const stored = await AsyncStorage.getItem(STORAGE_KEY);
    if (stored) currentServerUrl = stored;
  } catch {
    // storage unavailable — keep default
  }
  return currentServerUrl;
}

export async function saveServerUrl(url: string): Promise<string> {
  const normalized = normalizeServerUrl(url);
  currentServerUrl = normalized;
  try {
    await AsyncStorage.setItem(STORAGE_KEY, normalized);
  } catch {
    // storage unavailable — in-memory value still applies for this session
  }
  return normalized;
}
