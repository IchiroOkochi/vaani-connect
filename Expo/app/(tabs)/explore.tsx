import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { Fonts } from '@/constants/theme';
import { API_BASE_URL } from '@/services/api';

type HealthState = 'idle' | 'loading' | 'online' | 'offline';

const REQUIRED_ENDPOINTS = [
  { path: '/health', note: 'Basic reachability check for the frontend.' },
  { path: '/languages', note: 'Populates the language pickers on the translate screen.' },
  { path: '/translate/text', note: 'Handles typed translation requests and optional speech output.' },
  { path: '/translate/speech', note: 'Accepts recorded audio and returns translated content.' },
  { path: '/audio/{filename}', note: 'Serves generated voice responses for playback.' },
];

export default function BackendHelpScreen() {
  const insets = useSafeAreaInsets();
  const [healthState, setHealthState] = useState<HealthState>('idle');
  const [lastCheckedAt, setLastCheckedAt] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const statusMeta = useMemo(() => {
    switch (healthState) {
      case 'online':
        return { label: 'Backend online', color: '#8fd19e', icon: 'check-circle' as const };
      case 'offline':
        return { label: 'Backend unreachable', color: '#ff8d7a', icon: 'error' as const };
      case 'loading':
        return { label: 'Checking connection', color: '#ffd07a', icon: 'autorenew' as const };
      default:
        return { label: 'Status not checked yet', color: '#9bb1ab', icon: 'radio-button-unchecked' as const };
    }
  }, [healthState]);

  const checkBackend = useCallback(async () => {
    setHealthState('loading');
    setErrorMessage(null);

    try {
      const res = await fetch(`${API_BASE_URL}/health`);
      if (!res.ok) {
        throw new Error(`Health check failed (${res.status})`);
      }

      setHealthState('online');
      setLastCheckedAt(new Date().toLocaleTimeString());
    } catch (error) {
      setHealthState('offline');
      setLastCheckedAt(new Date().toLocaleTimeString());
      setErrorMessage(error instanceof Error ? error.message : 'Unable to reach the backend.');
    }
  }, []);

  useEffect(() => {
    void checkBackend();
  }, [checkBackend]);

  return (
    <View style={styles.screen}>
      <View style={[styles.blob, styles.blobTop]} />
      <View style={[styles.blob, styles.blobBottom]} />
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={[
          styles.content,
          {
            paddingTop: insets.top + 20,
            paddingBottom: Math.max(insets.bottom + 112, 132),
          },
        ]}
        showsVerticalScrollIndicator={false}>
        <View style={styles.hero}>
          <ThemedText style={styles.kicker}>Environment</ThemedText>
          <ThemedText style={styles.title}>Connection dashboard</ThemedText>
          <ThemedText style={styles.subtitle}>
            This tab keeps the frontend grounded in the backend it depends on, with a quick health check and the
            contract the UI expects.
          </ThemedText>

          <View style={[styles.statusCard, { borderColor: statusMeta.color }]}>
            <View style={styles.statusTopRow}>
              <View style={styles.statusPill}>
                {healthState === 'loading' ? (
                  <ActivityIndicator color={statusMeta.color} size="small" />
                ) : (
                  <MaterialIcons name={statusMeta.icon} size={18} color={statusMeta.color} />
                )}
                <ThemedText style={styles.statusLabel}>{statusMeta.label}</ThemedText>
              </View>
              <Pressable style={styles.refreshButton} onPress={() => void checkBackend()}>
                <MaterialIcons name="refresh" size={18} color="#071317" />
                <ThemedText style={styles.refreshLabel}>Refresh</ThemedText>
              </Pressable>
            </View>

            <View style={styles.metaBlock}>
              <ThemedText style={styles.metaLabel}>Current API base URL</ThemedText>
              <ThemedText style={styles.codeBlock}>{API_BASE_URL}</ThemedText>
            </View>

            <View style={styles.inlineMeta}>
              <MetaChip icon="schedule" label={lastCheckedAt ? `Last checked at ${lastCheckedAt}` : 'Waiting for first check'} />
              <MetaChip icon="devices" label="Frontend only changes, backend untouched" />
            </View>

            {errorMessage ? <ThemedText style={styles.errorText}>{errorMessage}</ThemedText> : null}
          </View>
        </View>

        <View style={styles.section}>
          <ThemedText style={styles.sectionTitle}>Required backend contract</ThemedText>
          <ThemedText style={styles.sectionCopy}>
            These are the routes the current UI depends on. If one of them changes, this app will need corresponding
            frontend updates.
          </ThemedText>
          {REQUIRED_ENDPOINTS.map((endpoint) => (
            <View key={endpoint.path} style={styles.endpointCard}>
              <View style={styles.endpointRow}>
                <MaterialIcons name="link" size={18} color="#ffd07a" />
                <ThemedText style={styles.endpointPath}>{endpoint.path}</ThemedText>
              </View>
              <ThemedText style={styles.endpointNote}>{endpoint.note}</ThemedText>
            </View>
          ))}
        </View>

        <View style={styles.section}>
          <ThemedText style={styles.sectionTitle}>Local setup notes</ThemedText>
          <View style={styles.noteCard}>
            <NoteRow icon="terminal" text="Run the Python backend on port 8000, or point the app at another URL with EXPO_PUBLIC_API_BASE_URL." />
            <NoteRow icon="language" text="Use Expo Web when you want microphone capture in the current frontend build." />
            <NoteRow icon="graphic-eq" text="Typed translation and translated audio playback still work across platforms when the backend is available." />
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

function MetaChip({ icon, label }: { icon: keyof typeof MaterialIcons.glyphMap; label: string }) {
  return (
    <View style={styles.metaChip}>
      <MaterialIcons name={icon} size={16} color="#aebcb7" />
      <ThemedText style={styles.metaChipLabel}>{label}</ThemedText>
    </View>
  );
}

function NoteRow({ icon, text }: { icon: keyof typeof MaterialIcons.glyphMap; text: string }) {
  return (
    <View style={styles.noteRow}>
      <View style={styles.noteIcon}>
        <MaterialIcons name={icon} size={18} color="#071317" />
      </View>
      <ThemedText style={styles.noteText}>{text}</ThemedText>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: '#071317',
  },
  scroll: {
    flex: 1,
  },
  content: {
    paddingHorizontal: 20,
    gap: 18,
  },
  blob: {
    position: 'absolute',
    borderRadius: 999,
    opacity: 0.28,
  },
  blobTop: {
    width: 220,
    height: 220,
    backgroundColor: '#244c56',
    top: -70,
    left: -50,
  },
  blobBottom: {
    width: 260,
    height: 260,
    backgroundColor: '#5b3427',
    right: -70,
    bottom: 80,
  },
  hero: {
    gap: 14,
  },
  kicker: {
    color: '#ffd07a',
    fontSize: 13,
    lineHeight: 18,
    letterSpacing: 1,
    textTransform: 'uppercase',
    fontFamily: Fonts.rounded,
  },
  title: {
    color: '#f7f2e8',
    fontSize: 38,
    lineHeight: 42,
    fontWeight: '700',
    fontFamily: Fonts.serif,
  },
  subtitle: {
    color: '#aebcb7',
    fontSize: 16,
    lineHeight: 24,
  },
  statusCard: {
    backgroundColor: '#10242a',
    borderRadius: 28,
    borderWidth: 1,
    padding: 20,
    gap: 16,
  },
  statusTopRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 10,
  },
  statusPill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexShrink: 1,
  },
  statusLabel: {
    color: '#f7f2e8',
    fontSize: 16,
    lineHeight: 20,
    fontWeight: '600',
  },
  refreshButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: '#f2a65a',
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  refreshLabel: {
    color: '#071317',
    fontSize: 14,
    lineHeight: 18,
    fontWeight: '700',
  },
  metaBlock: {
    gap: 6,
  },
  metaLabel: {
    color: '#ffd07a',
    fontSize: 12,
    lineHeight: 16,
    letterSpacing: 1,
    textTransform: 'uppercase',
    fontFamily: Fonts.rounded,
  },
  codeBlock: {
    color: '#f7f2e8',
    fontSize: 15,
    lineHeight: 22,
    backgroundColor: '#0d1b1f',
    borderRadius: 18,
    paddingHorizontal: 14,
    paddingVertical: 14,
  },
  inlineMeta: {
    gap: 10,
  },
  metaChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: 'rgba(247, 242, 232, 0.05)',
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 9,
  },
  metaChipLabel: {
    color: '#aebcb7',
    fontSize: 13,
    lineHeight: 18,
  },
  errorText: {
    color: '#ff8d7a',
    fontSize: 14,
    lineHeight: 20,
  },
  section: {
    backgroundColor: '#10242a',
    borderRadius: 28,
    borderWidth: 1,
    borderColor: 'rgba(233, 228, 212, 0.12)',
    padding: 20,
    gap: 14,
  },
  sectionTitle: {
    color: '#f7f2e8',
    fontSize: 24,
    lineHeight: 30,
    fontWeight: '700',
    fontFamily: Fonts.serif,
  },
  sectionCopy: {
    color: '#aebcb7',
    fontSize: 14,
    lineHeight: 21,
  },
  endpointCard: {
    backgroundColor: '#0d1b1f',
    borderRadius: 20,
    padding: 16,
    gap: 8,
  },
  endpointRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  endpointPath: {
    color: '#f7f2e8',
    fontSize: 16,
    lineHeight: 20,
    fontWeight: '600',
  },
  endpointNote: {
    color: '#aebcb7',
    fontSize: 13,
    lineHeight: 19,
  },
  noteCard: {
    gap: 12,
  },
  noteRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
    backgroundColor: '#0d1b1f',
    borderRadius: 20,
    padding: 16,
  },
  noteIcon: {
    width: 34,
    height: 34,
    borderRadius: 17,
    backgroundColor: '#ffd07a',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 2,
  },
  noteText: {
    flex: 1,
    color: '#f7f2e8',
    fontSize: 14,
    lineHeight: 21,
  },
});
