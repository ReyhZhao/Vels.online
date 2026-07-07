import { Redirect } from 'expo-router';
import { useAuth } from '@/context/AuthContext';
import { LoadingView } from '@/components/States';

export default function Index() {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) return <LoadingView />;
  return isAuthenticated ? <Redirect href="/(tabs)/incidents" /> : <Redirect href="/login" />;
}
