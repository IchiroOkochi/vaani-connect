import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Animated,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
  useWindowDimensions,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { ThemedText } from '@/components/themed-text';
import { SUPPORTED_LANGUAGES, type SupportedLanguage } from '@/constants/languages';
import { Fonts } from '@/constants/theme';
import {
  API_BASE_URL,
  fetchSupportedLanguages,
  toAbsoluteAudioUrl,
  translateSpeech,
  translateText,
  type TranslationResponse,
} from '@/services/api';

const SURFACE = '#10242a';
const SURFACE_BORDER = 'rgba(233, 228, 212, 0.12)';
const PANEL = '#17333a';
const PANEL_ALT = '#0d1b1f';
const ACCENT = '#f2a65a';
const ACCENT_STRONG = '#ffd07a';
const TEXT_PRIMARY = '#f7f2e8';
const TEXT_MUTED = '#aebcb7';
const SUCCESS = '#8fd19e';
const DANGER = '#ff8d7a';

export default function HomeScreen() {
  const insets = useSafeAreaInsets();
  const { width } = useWindowDimensions();
  const [availableLanguages, setAvailableLanguages] = useState<SupportedLanguage[]>([...SUPPORTED_LANGUAGES]);
  const [sourceLanguage, setSourceLanguage] = useState<SupportedLanguage>('English');
  const [targetLanguage, setTargetLanguage] = useState<SupportedLanguage>('Hindi');
  const [inputText, setInputText] = useState('');
  const [outputText, setOutputText] = useState('');
  const [latestAudioUrl, setLatestAudioUrl] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranslatingText, setIsTranslatingText] = useState(false);
  const [isTranslatingSpeech, setIsTranslatingSpeech] = useState(false);
  const [isPlayingAudio, setIsPlayingAudio] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const liftAnim = useRef(new Animated.Value(24)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 650,
        useNativeDriver: true,
      }),
      Animated.timing(liftAnim, {
        toValue: 0,
        duration: 650,
        useNativeDriver: true,
      }),
    ]).start();
  }, [fadeAnim, liftAnim]);

  useEffect(() => {
    let isMounted = true;

    async function loadLanguages() {
      try {
        const fetched = await fetchSupportedLanguages();
        if (!isMounted || fetched.length === 0) return;

        setAvailableLanguages(fetched);
        setSourceLanguage((current) => (fetched.includes(current) ? current : fetched[0]));
        setTargetLanguage((current) => (fetched.includes(current) ? current : fetched[1] ?? fetched[0]));
      } catch {
        // Keep fallback language list when backend language endpoint is unavailable.
      }
    }

    loadLanguages();
    return () => {
      isMounted = false;
    };
  }, []);

  const activeRequest = isTranslatingText || isTranslatingSpeech;
  const canTranslateText = useMemo(
    () => inputText.trim().length > 0 && !isTranslatingSpeech,
    [inputText, isTranslatingSpeech],
  );
  const statusTone = isRecording
    ? { color: DANGER, label: 'Listening live' }
    : activeRequest
      ? { color: ACCENT_STRONG, label: 'Working on your translation' }
      : { color: SUCCESS, label: 'Ready for text or speech' };
  const compactLayout = width < 410;

  async function translateFromText() {
    if (!inputText.trim()) return;

    setIsTranslatingText(true);
    try {
      const response = await translateText({
        text: inputText.trim(),
        sourceLanguage,
        targetLanguage,
      });
      applyTranslation(response);
    } catch {
      Alert.alert('Translation failed', `Unable to reach backend at ${API_BASE_URL}.`);
    } finally {
      setIsTranslatingText(false);
    }
  }

  function applyTranslation(response: TranslationResponse) {
    if (response.transcribed_text) {
      setInputText(response.transcribed_text);
    }
    setOutputText(response.translated_text);
    setLatestAudioUrl(response.audio_url ?? null);
  }

  async function toggleRecording() {
    if (Platform.OS !== 'web') {
      Alert.alert(
        'Speech input needs web in this build',
        'Use Expo Web for recording or add native recording support in a later frontend pass.',
      );
      return;
    }

    if (!isRecording) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const recorder = new MediaRecorder(stream);
        chunksRef.current = [];

        recorder.ondataavailable = (event) => {
          if (event.data.size > 0) chunksRef.current.push(event.data);
        };

        recorder.onstop = async () => {
          stream.getTracks().forEach((track) => track.stop());

          const audioBlob = new Blob(chunksRef.current, { type: 'audio/webm' });
          setIsTranslatingSpeech(true);
          try {
            const response = await translateSpeech({
              audioBlob,
              sourceLanguage,
              targetLanguage,
            });
            applyTranslation(response);
          } catch {
            Alert.alert('Speech translation failed', `Unable to reach backend at ${API_BASE_URL}.`);
          } finally {
            setIsTranslatingSpeech(false);
          }
        };

        recorder.start();
        mediaRecorderRef.current = recorder;
        setIsRecording(true);
      } catch {
        Alert.alert('Microphone permission required', 'Please allow microphone access to record speech.');
      }
      return;
    }

    mediaRecorderRef.current?.stop();
    setIsRecording(false);
  }

  async function playOutputAudio() {
    const absolute = toAbsoluteAudioUrl(latestAudioUrl);

    if (!absolute) {
      if (!outputText.trim()) {
        Alert.alert('No output yet', 'Translate something first, then play the voice output.');
        return;
      }

      try {
        setIsTranslatingText(true);
        const response = await translateText({
          text: inputText.trim(),
          sourceLanguage,
          targetLanguage,
        });
        applyTranslation(response);
        const generatedAudioUrl = toAbsoluteAudioUrl(response.audio_url);
        if (generatedAudioUrl) {
          await playAudio(generatedAudioUrl);
        }
      } catch {
        Alert.alert('Voice output unavailable', `Unable to reach backend at ${API_BASE_URL}.`);
      } finally {
        setIsTranslatingText(false);
      }

      return;
    }

    await playAudio(absolute);
  }

  async function playAudio(audioUrl: string) {
    setIsPlayingAudio(true);
    try {
      if (Platform.OS === 'web') {
        const audio = new Audio(audioUrl);
        await audio.play();
        return;
      }

      await Linking.openURL(audioUrl);
    } finally {
      setIsPlayingAudio(false);
    }
  }

  function switchLanguages() {
    setInputText(outputText);
    setOutputText(inputText);
    setLatestAudioUrl(null);
    setSourceLanguage(targetLanguage);
    setTargetLanguage(sourceLanguage);
  }

  return (
    <View style={styles.screen}>
      <View style={[styles.blob, styles.blobLarge]} />
      <View style={[styles.blob, styles.blobSmall]} />
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
        <Animated.View
          style={[
            styles.stack,
            {
              opacity: fadeAnim,
              transform: [{ translateY: liftAnim }],
            },
          ]}>
          <View style={styles.heroCard}>
            <View style={[styles.statusPill, { borderColor: statusTone.color }]}>
              <View style={[styles.statusDot, { backgroundColor: statusTone.color }]} />
              <ThemedText style={styles.statusText}>{statusTone.label}</ThemedText>
            </View>
            <ThemedText style={styles.kicker}>Voice-first translation studio</ThemedText>
            <ThemedText style={styles.title}>Vaani Connect</ThemedText>
            <ThemedText style={styles.subtitle}>
              Move between speech and text quickly, keep the language controls visible, and play translated audio
              without losing your place.
            </ThemedText>

            <View style={[styles.heroStats, compactLayout && styles.heroStatsCompact]}>
              <StatBadge icon="translate" label={`${sourceLanguage} to ${targetLanguage}`} />
              <StatBadge icon="graphic-eq" label={Platform.OS === 'web' ? 'Live mic on web' : 'Text mode everywhere'} />
              <StatBadge icon="volume-up" label={latestAudioUrl ? 'Voice response ready' : 'Audio generated on demand'} />
            </View>
          </View>

          <View style={[styles.actionRow, compactLayout && styles.actionColumn]}>
            <ActionButton
              icon={isRecording ? 'stop-circle' : 'keyboard-voice'}
              title={isRecording ? 'Stop capture' : 'Record speech'}
              subtitle={Platform.OS === 'web' ? 'Use your microphone for live input' : 'Available on Expo Web in this build'}
              accent={isRecording ? DANGER : ACCENT}
              onPress={toggleRecording}
              disabled={activeRequest}
              loading={isTranslatingSpeech}
            />
            <ActionButton
              icon="swap-horiz"
              title="Swap languages"
              subtitle="Flip source and destination instantly"
              accent="#8fd3c7"
              onPress={switchLanguages}
              disabled={activeRequest}
            />
            <ActionButton
              icon="play-circle-filled"
              title={isPlayingAudio ? 'Playing output' : 'Play response'}
              subtitle={latestAudioUrl ? 'Use the latest generated voice clip' : 'Generate audio if needed'}
              accent="#f7d46b"
              onPress={playOutputAudio}
              disabled={activeRequest || (!outputText.trim() && !latestAudioUrl)}
              loading={isPlayingAudio}
            />
          </View>

          <View style={styles.panel}>
            <View style={styles.panelHeader}>
              <ThemedText style={styles.panelTitle}>Language routing</ThemedText>
              <ThemedText style={styles.panelMeta}>Backend source: {availableLanguages.length} supported options</ThemedText>
            </View>

            <LanguagePicker
              title="Input language"
              caption="This drives text translation and speech recognition."
              languages={availableLanguages}
              selected={sourceLanguage}
              onSelect={setSourceLanguage}
            />
            <LanguagePicker
              title="Output language"
              caption="The translated text and generated audio will follow this selection."
              languages={availableLanguages}
              selected={targetLanguage}
              onSelect={setTargetLanguage}
            />
          </View>

          <View style={styles.editorGrid}>
            <EditorCard
              label="Source"
              title="Type or dictate your phrase"
              helper={isRecording ? 'Recording in progress. Press stop when you are done.' : 'Paste text or use the microphone action above.'}
              value={inputText}
              placeholder="Start with a phrase, question, or short instruction."
              onChangeText={setInputText}
              editable
              footer={`${inputText.trim().length} characters`}
            />
            <EditorCard
              label="Result"
              title="Translated output"
              helper={outputText ? 'Review the translated text, then play the audio response if you need voice output.' : 'Your translated text will appear here.'}
              value={outputText}
              placeholder="Nothing translated yet."
              editable={false}
              footer={latestAudioUrl ? 'Voice clip attached to latest response' : 'Audio will be generated by the backend'}
            />
          </View>

          <Pressable
            style={[styles.translateButton, (!canTranslateText || isTranslatingText) && styles.translateButtonDisabled]}
            onPress={translateFromText}
            disabled={!canTranslateText || isTranslatingText}>
            <View style={styles.translateInner}>
              {isTranslatingText ? (
                <ActivityIndicator color={PANEL_ALT} />
              ) : (
                <MaterialIcons name="auto-awesome" size={22} color={PANEL_ALT} />
              )}
              <View style={styles.translateCopy}>
                <ThemedText style={styles.translateTitle}>
                  {isTranslatingText ? 'Translating now' : 'Translate text'}
                </ThemedText>
                <ThemedText style={styles.translateSubtitle}>
                  {inputText.trim() ? 'Send the current source text to the backend' : 'Enter source text to begin'}
                </ThemedText>
              </View>
            </View>
          </Pressable>

          <View style={styles.footerCard}>
            <View style={styles.footerRow}>
              <ThemedText style={styles.footerLabel}>API endpoint</ThemedText>
              <ThemedText style={styles.footerValue}>{API_BASE_URL}</ThemedText>
            </View>
            <View style={styles.footerRow}>
              <ThemedText style={styles.footerLabel}>Best experience</ThemedText>
              <ThemedText style={styles.footerValue}>
                Web for live recording, any target for text translation and playback
              </ThemedText>
            </View>
          </View>
        </Animated.View>
      </ScrollView>
    </View>
  );
}

function StatBadge({ icon, label }: { icon: keyof typeof MaterialIcons.glyphMap; label: string }) {
  return (
    <View style={styles.statBadge}>
      <MaterialIcons name={icon} size={16} color={ACCENT_STRONG} />
      <ThemedText style={styles.statLabel}>{label}</ThemedText>
    </View>
  );
}

function ActionButton({
  icon,
  title,
  subtitle,
  accent,
  onPress,
  disabled,
  loading,
}: {
  icon: keyof typeof MaterialIcons.glyphMap;
  title: string;
  subtitle: string;
  accent: string;
  onPress: () => void;
  disabled?: boolean;
  loading?: boolean;
}) {
  return (
    <Pressable style={[styles.actionButton, disabled && styles.actionButtonDisabled]} onPress={onPress} disabled={disabled}>
      <View style={[styles.actionIcon, { backgroundColor: accent }]}>
        {loading ? <ActivityIndicator color={PANEL_ALT} /> : <MaterialIcons name={icon} size={22} color={PANEL_ALT} />}
      </View>
      <View style={styles.actionCopy}>
        <ThemedText style={styles.actionTitle}>{title}</ThemedText>
        <ThemedText style={styles.actionSubtitle}>{subtitle}</ThemedText>
      </View>
    </Pressable>
  );
}

function LanguagePicker({
  title,
  caption,
  languages,
  selected,
  onSelect,
}: {
  title: string;
  caption: string;
  languages: SupportedLanguage[];
  selected: SupportedLanguage;
  onSelect: (language: SupportedLanguage) => void;
}) {
  return (
    <View style={styles.languageBlock}>
      <View style={styles.languageHeading}>
        <ThemedText style={styles.languageTitle}>{title}</ThemedText>
        <ThemedText style={styles.languageCaption}>{caption}</ThemedText>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
        {languages.map((language) => (
          <Pressable
            key={language}
            onPress={() => onSelect(language)}
            style={[styles.chip, selected === language && styles.chipActive]}>
            <ThemedText style={[styles.chipLabel, selected === language && styles.chipLabelActive]}>{language}</ThemedText>
          </Pressable>
        ))}
      </ScrollView>
    </View>
  );
}

function EditorCard({
  label,
  title,
  helper,
  value,
  placeholder,
  editable,
  onChangeText,
  footer,
}: {
  label: string;
  title: string;
  helper: string;
  value: string;
  placeholder: string;
  editable: boolean;
  onChangeText?: (value: string) => void;
  footer: string;
}) {
  return (
    <View style={styles.editorCard}>
      <View style={styles.editorHeader}>
        <ThemedText style={styles.editorLabel}>{label}</ThemedText>
        <ThemedText style={styles.editorTitle}>{title}</ThemedText>
        <ThemedText style={styles.editorHelper}>{helper}</ThemedText>
      </View>
      <View style={[styles.editorField, !editable && styles.editorFieldMuted]}>
        <TextInput
          value={value}
          onChangeText={onChangeText}
          placeholder={placeholder}
          placeholderTextColor="rgba(174, 188, 183, 0.55)"
          multiline
          editable={editable}
          textAlignVertical="top"
          style={styles.editorInput}
        />
      </View>
      <ThemedText style={styles.editorFooter}>{footer}</ThemedText>
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
  },
  stack: {
    gap: 18,
  },
  blob: {
    position: 'absolute',
    borderRadius: 999,
    opacity: 0.35,
  },
  blobLarge: {
    width: 280,
    height: 280,
    backgroundColor: '#16454f',
    top: -80,
    right: -70,
  },
  blobSmall: {
    width: 200,
    height: 200,
    backgroundColor: '#533026',
    bottom: 90,
    left: -70,
  },
  heroCard: {
    backgroundColor: SURFACE,
    borderWidth: 1,
    borderColor: SURFACE_BORDER,
    borderRadius: 28,
    padding: 24,
    gap: 12,
    shadowColor: '#000',
    shadowOpacity: 0.22,
    shadowRadius: 18,
    shadowOffset: { width: 0, height: 10 },
    elevation: 10,
  },
  statusPill: {
    alignSelf: 'flex-start',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 7,
    backgroundColor: 'rgba(8, 19, 22, 0.92)',
  },
  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  statusText: {
    color: TEXT_PRIMARY,
    fontSize: 12,
    lineHeight: 16,
    fontFamily: Fonts.rounded,
    letterSpacing: 0.4,
  },
  kicker: {
    color: ACCENT_STRONG,
    fontSize: 13,
    lineHeight: 18,
    letterSpacing: 1,
    textTransform: 'uppercase',
    fontFamily: Fonts.rounded,
  },
  title: {
    color: TEXT_PRIMARY,
    fontSize: 44,
    lineHeight: 46,
    fontWeight: '700',
    fontFamily: Fonts.serif,
  },
  subtitle: {
    color: TEXT_MUTED,
    fontSize: 16,
    lineHeight: 24,
  },
  heroStats: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    paddingTop: 4,
  },
  heroStatsCompact: {
    flexDirection: 'column',
  },
  statBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: 'rgba(247, 242, 232, 0.06)',
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  statLabel: {
    color: TEXT_PRIMARY,
    fontSize: 13,
    lineHeight: 18,
  },
  actionRow: {
    flexDirection: 'row',
    gap: 12,
  },
  actionColumn: {
    flexDirection: 'column',
  },
  actionButton: {
    flex: 1,
    minHeight: 120,
    backgroundColor: PANEL_ALT,
    borderWidth: 1,
    borderColor: SURFACE_BORDER,
    borderRadius: 24,
    padding: 16,
    gap: 14,
  },
  actionButtonDisabled: {
    opacity: 0.5,
  },
  actionIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionCopy: {
    gap: 6,
  },
  actionTitle: {
    color: TEXT_PRIMARY,
    fontSize: 17,
    lineHeight: 22,
    fontWeight: '600',
  },
  actionSubtitle: {
    color: TEXT_MUTED,
    fontSize: 13,
    lineHeight: 19,
  },
  panel: {
    backgroundColor: SURFACE,
    borderRadius: 28,
    borderWidth: 1,
    borderColor: SURFACE_BORDER,
    padding: 20,
    gap: 18,
  },
  panelHeader: {
    gap: 4,
  },
  panelTitle: {
    color: TEXT_PRIMARY,
    fontSize: 22,
    lineHeight: 28,
    fontFamily: Fonts.serif,
    fontWeight: '700',
  },
  panelMeta: {
    color: TEXT_MUTED,
    fontSize: 13,
    lineHeight: 18,
  },
  languageBlock: {
    gap: 10,
  },
  languageHeading: {
    gap: 3,
  },
  languageTitle: {
    color: TEXT_PRIMARY,
    fontSize: 16,
    lineHeight: 20,
    fontWeight: '600',
  },
  languageCaption: {
    color: TEXT_MUTED,
    fontSize: 13,
    lineHeight: 18,
  },
  chipRow: {
    gap: 10,
    paddingRight: 6,
  },
  chip: {
    borderWidth: 1,
    borderColor: 'rgba(247, 242, 232, 0.12)',
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 10,
    backgroundColor: PANEL_ALT,
  },
  chipActive: {
    backgroundColor: ACCENT,
    borderColor: ACCENT,
  },
  chipLabel: {
    color: TEXT_PRIMARY,
    fontSize: 14,
    lineHeight: 18,
  },
  chipLabelActive: {
    color: PANEL_ALT,
    fontWeight: '700',
  },
  editorGrid: {
    gap: 14,
  },
  editorCard: {
    backgroundColor: SURFACE,
    borderRadius: 28,
    borderWidth: 1,
    borderColor: SURFACE_BORDER,
    padding: 20,
    gap: 14,
  },
  editorHeader: {
    gap: 5,
  },
  editorLabel: {
    color: ACCENT_STRONG,
    fontSize: 12,
    lineHeight: 16,
    letterSpacing: 1,
    textTransform: 'uppercase',
    fontFamily: Fonts.rounded,
  },
  editorTitle: {
    color: TEXT_PRIMARY,
    fontSize: 22,
    lineHeight: 28,
    fontWeight: '700',
    fontFamily: Fonts.serif,
  },
  editorHelper: {
    color: TEXT_MUTED,
    fontSize: 14,
    lineHeight: 20,
  },
  editorField: {
    minHeight: 190,
    backgroundColor: PANEL,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: 'rgba(247, 242, 232, 0.08)',
    paddingHorizontal: 16,
    paddingVertical: 16,
  },
  editorFieldMuted: {
    backgroundColor: PANEL_ALT,
  },
  editorInput: {
    minHeight: 156,
    color: TEXT_PRIMARY,
    fontSize: 20,
    lineHeight: 29,
  },
  editorFooter: {
    color: TEXT_MUTED,
    fontSize: 12,
    lineHeight: 16,
  },
  translateButton: {
    backgroundColor: ACCENT,
    borderRadius: 28,
    paddingHorizontal: 20,
    paddingVertical: 18,
    shadowColor: '#000',
    shadowOpacity: 0.18,
    shadowRadius: 14,
    shadowOffset: { width: 0, height: 8 },
    elevation: 8,
  },
  translateButtonDisabled: {
    opacity: 0.45,
  },
  translateInner: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
  },
  translateCopy: {
    flex: 1,
    gap: 2,
  },
  translateTitle: {
    color: PANEL_ALT,
    fontSize: 18,
    lineHeight: 23,
    fontWeight: '700',
  },
  translateSubtitle: {
    color: 'rgba(13, 27, 31, 0.74)',
    fontSize: 13,
    lineHeight: 18,
  },
  footerCard: {
    backgroundColor: 'rgba(16, 36, 42, 0.8)',
    borderRadius: 24,
    borderWidth: 1,
    borderColor: SURFACE_BORDER,
    padding: 18,
    gap: 12,
  },
  footerRow: {
    gap: 4,
  },
  footerLabel: {
    color: ACCENT_STRONG,
    fontSize: 12,
    lineHeight: 16,
    letterSpacing: 1,
    textTransform: 'uppercase',
    fontFamily: Fonts.rounded,
  },
  footerValue: {
    color: TEXT_PRIMARY,
    fontSize: 14,
    lineHeight: 20,
  },
});
