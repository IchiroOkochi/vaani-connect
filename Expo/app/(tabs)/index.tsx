import MaterialIcons from '@expo/vector-icons/MaterialIcons';
import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Animated,
  Linking,
  Modal,
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
import { getLanguageLabel, SUPPORTED_LANGUAGES, type SupportedLanguage } from '@/constants/languages';
import { Fonts } from '@/constants/theme';
import { getUiCopy, UI_SUBTITLES } from '@/constants/ui-copy';
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
const RESULT_CARD_SCROLL_Y = 0;

type LanguageField = 'source' | 'target';

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
  const [languagePickerField, setLanguagePickerField] = useState<LanguageField | null>(null);
  const [languageQuery, setLanguageQuery] = useState('');

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const scrollRef = useRef<ScrollView | null>(null);
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const liftAnim = useRef(new Animated.Value(20)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(fadeAnim, {
        toValue: 1,
        duration: 450,
        useNativeDriver: true,
      }),
      Animated.timing(liftAnim, {
        toValue: 0,
        duration: 450,
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
        setSourceLanguage((current) => (fetched.includes(current) ? current : fetched.includes('English') ? 'English' : fetched[0]));
        setTargetLanguage((current) => (fetched.includes(current) ? current : fetched.find((item) => item !== 'English') ?? fetched[0]));
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
  const compactLayout = width < 410;
  const ui = useMemo(() => getUiCopy(sourceLanguage), [sourceLanguage]);
  const statusTone = isRecording
    ? { color: DANGER, label: ui.statusListening }
    : activeRequest
      ? { color: ACCENT_STRONG, label: ui.statusWorking }
      : { color: SUCCESS, label: ui.statusReady };
  const pickerSelection = languagePickerField === 'target' ? targetLanguage : sourceLanguage;
  const filteredLanguages = useMemo(() => {
    const query = languageQuery.trim().toLowerCase();
    if (!query) return availableLanguages;

    return availableLanguages.filter((language) => {
      const nativeLabel = getLanguageLabel(language).toLowerCase();
      return language.toLowerCase().includes(query) || nativeLabel.includes(query);
    });
  }, [availableLanguages, languageQuery]);
  const hasResult = outputText.trim().length > 0 || isTranslatingText || isTranslatingSpeech;

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
      Alert.alert(ui.alertTranslateFailedTitle, API_BASE_URL);
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

    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ y: RESULT_CARD_SCROLL_Y, animated: true });
    });
  }

  async function toggleRecording() {
    if (Platform.OS !== 'web') {
      Alert.alert(ui.alertWebNeededTitle, ui.alertWebNeededMessage);
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
            Alert.alert(ui.alertSpeechFailedTitle, API_BASE_URL);
          } finally {
            setIsTranslatingSpeech(false);
          }
        };

        recorder.start();
        mediaRecorderRef.current = recorder;
        setIsRecording(true);
      } catch {
        Alert.alert(ui.alertMicPermissionTitle, ui.alertMicPermissionMessage);
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
        Alert.alert(ui.alertNoOutputTitle, ui.alertNoOutputMessage);
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
        Alert.alert(ui.alertVoiceUnavailableTitle, API_BASE_URL);
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

  function openLanguagePicker(field: LanguageField) {
    setLanguageQuery('');
    setLanguagePickerField(field);
  }

  function closeLanguagePicker() {
    setLanguagePickerField(null);
    setLanguageQuery('');
  }

  function handleLanguageSelect(language: SupportedLanguage) {
    if (languagePickerField === 'source') {
      setSourceLanguage(language);
    } else if (languagePickerField === 'target') {
      setTargetLanguage(language);
    }

    closeLanguagePicker();
  }

  return (
    <View style={styles.screen}>
      <View style={[styles.blob, styles.blobLarge]} />
      <View style={[styles.blob, styles.blobSmall]} />

      <ScrollView
        ref={scrollRef}
        style={styles.scroll}
        contentContainerStyle={[
          styles.content,
          {
            paddingTop: insets.top + 16,
            paddingBottom: Math.max(insets.bottom + 110, 130),
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
          <View style={styles.panel}>
            <View style={styles.topRow}>
              <View style={[styles.statusPill, { borderColor: statusTone.color }]}>
                <View style={[styles.statusDot, { backgroundColor: statusTone.color }]} />
                <ThemedText style={styles.statusText}>{statusTone.label}</ThemedText>
              </View>
              <ThemedText style={styles.panelMeta}>
                {availableLanguages.length} {ui.languageWord}
              </ThemedText>
            </View>

            <View style={[styles.languageRoute, compactLayout && styles.languageRouteCompact]}>
              <LanguageSelector
                title={ui.from}
                subtitle={UI_SUBTITLES.from}
                selected={sourceLanguage}
                onPress={() => openLanguagePicker('source')}
              />
              <Pressable
                style={[styles.swapButton, activeRequest && styles.swapButtonDisabled]}
                onPress={switchLanguages}
                disabled={activeRequest}>
                <MaterialIcons name="swap-horiz" size={22} color={PANEL_ALT} />
              </Pressable>
              <LanguageSelector
                title={ui.to}
                subtitle={UI_SUBTITLES.to}
                selected={targetLanguage}
                onPress={() => openLanguagePicker('target')}
              />
            </View>

            <View style={styles.actionRow}>
              <ActionButton
                icon={isRecording ? 'stop-circle' : 'keyboard-voice'}
                title={isRecording ? ui.stop : ui.record}
                subtitle={UI_SUBTITLES.record}
                accent={isRecording ? DANGER : ACCENT}
                onPress={toggleRecording}
                disabled={activeRequest}
                loading={isTranslatingSpeech}
              />
              <ActionButton
                icon="play-circle-filled"
                title={isPlayingAudio ? ui.playing : ui.listen}
                subtitle={UI_SUBTITLES.listen}
                accent="#f7d46b"
                onPress={playOutputAudio}
                disabled={activeRequest || (!outputText.trim() && !latestAudioUrl)}
                loading={isPlayingAudio}
              />
            </View>
          </View>

          {hasResult ? (
            <EditorCard
              label={ui.resultLabel}
              title={isTranslatingSpeech ? ui.speechResultTitle : ui.resultTitle}
              subtitle={UI_SUBTITLES.result}
              value={outputText}
              placeholder={ui.resultPlaceholder}
              editable={false}
              compact={compactLayout}
              footer={latestAudioUrl ? ui.voiceReady : ''}
            />
          ) : null}

          <EditorCard
            label={ui.inputLabel}
            title={isRecording ? ui.inputRecordingTitle : ui.inputTitle}
            subtitle={UI_SUBTITLES.input}
            value={inputText}
            placeholder={ui.inputPlaceholder}
            editable
            compact={compactLayout}
            onChangeText={setInputText}
            footer={`${inputText.trim().length}`}
          />

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
                <ThemedText style={styles.translateTitle}>{isTranslatingText ? ui.translating : ui.translate}</ThemedText>
                <ThemedText style={styles.translateSubtitle}>{UI_SUBTITLES.translate}</ThemedText>
              </View>
            </View>
          </Pressable>
        </Animated.View>
      </ScrollView>

      <Modal visible={languagePickerField !== null} transparent animationType="slide" onRequestClose={closeLanguagePicker}>
        <Pressable style={styles.modalBackdrop} onPress={closeLanguagePicker}>
          <Pressable style={styles.modalSheet} onPress={() => {}}>
            <View style={styles.modalHandle} />

            <View style={styles.modalHeader}>
              <View style={styles.modalHeaderCopy}>
                <ThemedText style={styles.modalTitle}>{ui.chooseLanguage}</ThemedText>
                <ThemedText style={styles.modalSubtitle}>{UI_SUBTITLES.modal}</ThemedText>
              </View>
              <Pressable style={styles.modalCloseButton} onPress={closeLanguagePicker}>
                <MaterialIcons name="close" size={20} color={TEXT_PRIMARY} />
              </Pressable>
            </View>

            <View style={styles.searchField}>
              <MaterialIcons name="search" size={18} color={TEXT_MUTED} />
              <View style={styles.searchCopy}>
                <TextInput
                  value={languageQuery}
                  onChangeText={setLanguageQuery}
                  placeholder={ui.searchLanguage}
                  placeholderTextColor="rgba(174, 188, 183, 0.55)"
                  style={styles.searchInput}
                  autoCapitalize="none"
                  autoCorrect={false}
                />
                <ThemedText style={styles.searchSubtitle}>{UI_SUBTITLES.search}</ThemedText>
              </View>
            </View>

            <ScrollView style={styles.languageList} showsVerticalScrollIndicator={false}>
              {filteredLanguages.length > 0 ? (
                filteredLanguages.map((language) => (
                  <Pressable
                    key={language}
                    style={[styles.languageRow, language === pickerSelection && styles.languageRowActive]}
                    onPress={() => handleLanguageSelect(language)}>
                    <View style={styles.languageRowCopy}>
                      <ThemedText style={[styles.languageRowLabel, language === pickerSelection && styles.languageRowLabelActive]}>
                        {getLanguageLabel(language)}
                      </ThemedText>
                      <ThemedText style={styles.languageRowSubtitle}>{language}</ThemedText>
                    </View>
                    {language === pickerSelection ? (
                      <MaterialIcons name="check-circle" size={20} color={ACCENT_STRONG} />
                    ) : (
                      <MaterialIcons name="chevron-right" size={20} color={TEXT_MUTED} />
                    )}
                  </Pressable>
                ))
              ) : (
                <View style={styles.emptyState}>
                  <ThemedText style={styles.emptyTitle}>{ui.noLanguageFound}</ThemedText>
                  <ThemedText style={styles.emptySubtitle}>{ui.tryAnotherWord}</ThemedText>
                </View>
              )}
            </ScrollView>
          </Pressable>
        </Pressable>
      </Modal>
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

function LanguageSelector({
  title,
  subtitle,
  selected,
  onPress,
}: {
  title: string;
  subtitle: string;
  selected: SupportedLanguage;
  onPress: () => void;
}) {
  return (
    <Pressable style={styles.languageCard} onPress={onPress}>
      <View style={styles.languageHeading}>
        <ThemedText style={styles.languageTitle}>{title}</ThemedText>
        <ThemedText style={styles.languageSubtitle}>{subtitle}</ThemedText>
      </View>
      <View style={styles.languageCardFooter}>
        <View style={styles.languageCardCopy}>
          <ThemedText style={styles.languageValue}>{getLanguageLabel(selected)}</ThemedText>
          <ThemedText style={styles.languageValueSubtitle}>{selected}</ThemedText>
        </View>
        <MaterialIcons name="expand-more" size={22} color={TEXT_PRIMARY} />
      </View>
    </Pressable>
  );
}

function EditorCard({
  label,
  title,
  subtitle,
  value,
  placeholder,
  editable,
  compact,
  onChangeText,
  footer,
}: {
  label: string;
  title: string;
  subtitle: string;
  value: string;
  placeholder: string;
  editable: boolean;
  compact?: boolean;
  onChangeText?: (value: string) => void;
  footer: string;
}) {
  return (
    <View style={styles.editorCard}>
      <View style={styles.editorHeader}>
        <ThemedText style={styles.editorLabel}>{label}</ThemedText>
        <ThemedText style={styles.editorTitle}>{title}</ThemedText>
        <ThemedText style={styles.editorSubtitle}>{subtitle}</ThemedText>
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
          style={[styles.editorInput, compact && styles.editorInputCompact]}
        />
      </View>
      {footer ? <ThemedText style={styles.editorFooter}>{footer}</ThemedText> : null}
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
    paddingHorizontal: 18,
  },
  stack: {
    gap: 16,
  },
  blob: {
    position: 'absolute',
    borderRadius: 999,
    opacity: 0.35,
  },
  blobLarge: {
    width: 260,
    height: 260,
    backgroundColor: '#16454f',
    top: -90,
    right: -80,
  },
  blobSmall: {
    width: 180,
    height: 180,
    backgroundColor: '#533026',
    bottom: 100,
    left: -60,
  },
  panel: {
    backgroundColor: SURFACE,
    borderRadius: 26,
    borderWidth: 1,
    borderColor: SURFACE_BORDER,
    padding: 18,
    gap: 14,
  },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  statusPill: {
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
    letterSpacing: 0.3,
  },
  panelMeta: {
    color: TEXT_MUTED,
    fontSize: 13,
    lineHeight: 18,
  },
  languageRoute: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  languageRouteCompact: {
    flexDirection: 'column',
    alignItems: 'stretch',
  },
  languageCard: {
    flex: 1,
    minHeight: 118,
    justifyContent: 'space-between',
    backgroundColor: PANEL_ALT,
    borderWidth: 1,
    borderColor: 'rgba(247, 242, 232, 0.08)',
    borderRadius: 22,
    padding: 16,
  },
  languageHeading: {
    gap: 3,
  },
  languageTitle: {
    color: TEXT_PRIMARY,
    fontSize: 16,
    lineHeight: 20,
    fontWeight: '700',
  },
  languageSubtitle: {
    color: TEXT_MUTED,
    fontSize: 12,
    lineHeight: 16,
  },
  languageCardFooter: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 10,
  },
  languageCardCopy: {
    flex: 1,
    gap: 2,
  },
  languageValue: {
    color: TEXT_PRIMARY,
    fontSize: 18,
    lineHeight: 24,
    fontWeight: '700',
    fontFamily: Fonts.serif,
  },
  languageValueSubtitle: {
    color: TEXT_MUTED,
    fontSize: 12,
    lineHeight: 16,
  },
  swapButton: {
    width: 52,
    height: 52,
    borderRadius: 26,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: ACCENT_STRONG,
    alignSelf: 'center',
  },
  swapButtonDisabled: {
    opacity: 0.45,
  },
  actionRow: {
    flexDirection: 'row',
    gap: 12,
  },
  actionButton: {
    flex: 1,
    minHeight: 100,
    backgroundColor: PANEL_ALT,
    borderWidth: 1,
    borderColor: SURFACE_BORDER,
    borderRadius: 22,
    padding: 14,
    gap: 12,
  },
  actionButtonDisabled: {
    opacity: 0.5,
  },
  actionIcon: {
    width: 42,
    height: 42,
    borderRadius: 21,
    alignItems: 'center',
    justifyContent: 'center',
  },
  actionCopy: {
    gap: 3,
  },
  actionTitle: {
    color: TEXT_PRIMARY,
    fontSize: 16,
    lineHeight: 21,
    fontWeight: '700',
  },
  actionSubtitle: {
    color: TEXT_MUTED,
    fontSize: 12,
    lineHeight: 16,
  },
  editorCard: {
    backgroundColor: SURFACE,
    borderRadius: 26,
    borderWidth: 1,
    borderColor: SURFACE_BORDER,
    padding: 18,
    gap: 12,
  },
  editorHeader: {
    gap: 3,
  },
  editorLabel: {
    color: ACCENT_STRONG,
    fontSize: 12,
    lineHeight: 16,
    letterSpacing: 0.8,
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
  editorSubtitle: {
    color: TEXT_MUTED,
    fontSize: 12,
    lineHeight: 16,
  },
  editorField: {
    minHeight: 144,
    backgroundColor: PANEL,
    borderRadius: 22,
    borderWidth: 1,
    borderColor: 'rgba(247, 242, 232, 0.08)',
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  editorFieldMuted: {
    backgroundColor: PANEL_ALT,
  },
  editorInput: {
    minHeight: 112,
    color: TEXT_PRIMARY,
    fontSize: 18,
    lineHeight: 26,
  },
  editorInputCompact: {
    minHeight: 96,
    fontSize: 17,
    lineHeight: 24,
  },
  editorFooter: {
    color: TEXT_MUTED,
    fontSize: 12,
    lineHeight: 16,
  },
  translateButton: {
    backgroundColor: ACCENT,
    borderRadius: 26,
    paddingHorizontal: 20,
    paddingVertical: 16,
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
    gap: 12,
    justifyContent: 'center',
  },
  translateCopy: {
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
    fontSize: 12,
    lineHeight: 16,
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(4, 10, 12, 0.62)',
    justifyContent: 'flex-end',
  },
  modalSheet: {
    backgroundColor: SURFACE,
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    paddingHorizontal: 20,
    paddingTop: 12,
    paddingBottom: 28,
    gap: 16,
    maxHeight: '82%',
  },
  modalHandle: {
    alignSelf: 'center',
    width: 54,
    height: 5,
    borderRadius: 999,
    backgroundColor: 'rgba(247, 242, 232, 0.18)',
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
  },
  modalHeaderCopy: {
    flex: 1,
    gap: 4,
  },
  modalTitle: {
    color: TEXT_PRIMARY,
    fontSize: 22,
    lineHeight: 28,
    fontWeight: '700',
    fontFamily: Fonts.serif,
  },
  modalSubtitle: {
    color: TEXT_MUTED,
    fontSize: 12,
    lineHeight: 16,
  },
  modalCloseButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: PANEL_ALT,
  },
  searchField: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    backgroundColor: PANEL_ALT,
    borderWidth: 1,
    borderColor: 'rgba(247, 242, 232, 0.08)',
    borderRadius: 18,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  searchCopy: {
    flex: 1,
    gap: 2,
  },
  searchInput: {
    color: TEXT_PRIMARY,
    fontSize: 16,
    lineHeight: 22,
    padding: 0,
  },
  searchSubtitle: {
    color: TEXT_MUTED,
    fontSize: 12,
    lineHeight: 16,
  },
  languageList: {
    minHeight: 220,
  },
  languageRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    backgroundColor: PANEL_ALT,
    borderWidth: 1,
    borderColor: 'rgba(247, 242, 232, 0.08)',
    borderRadius: 18,
    paddingHorizontal: 16,
    paddingVertical: 14,
    marginBottom: 10,
  },
  languageRowActive: {
    borderColor: ACCENT,
    backgroundColor: 'rgba(242, 166, 90, 0.12)',
  },
  languageRowCopy: {
    flex: 1,
    gap: 2,
  },
  languageRowLabel: {
    color: TEXT_PRIMARY,
    fontSize: 16,
    lineHeight: 22,
  },
  languageRowLabelActive: {
    fontWeight: '700',
  },
  languageRowSubtitle: {
    color: TEXT_MUTED,
    fontSize: 12,
    lineHeight: 16,
  },
  emptyState: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 36,
    gap: 6,
  },
  emptyTitle: {
    color: TEXT_PRIMARY,
    fontSize: 16,
    lineHeight: 22,
    fontWeight: '600',
  },
  emptySubtitle: {
    color: TEXT_MUTED,
    fontSize: 12,
    lineHeight: 16,
  },
});
