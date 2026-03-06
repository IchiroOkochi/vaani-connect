import { StyleSheet } from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { API_BASE_URL } from '@/services/api';

export default function BackendHelpScreen() {
  return (
    <ThemedView style={styles.container}>
      <ThemedText type="title">Backend setup</ThemedText>
      <ThemedText>Set your backend URL in EXPO_PUBLIC_API_BASE_URL if needed.</ThemedText>
      <ThemedText type="defaultSemiBold">Current API base URL</ThemedText>
      <ThemedText style={styles.url}>{API_BASE_URL}</ThemedText>
      <ThemedText>
        Required endpoints: /health, /translate/text, /translate/speech, and /audio/:filename.
      </ThemedText>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    padding: 16,
    gap: 10,
  },
  url: {
    padding: 10,
    borderWidth: 1,
    borderColor: '#ccc',
    borderRadius: 8,
  },
});
