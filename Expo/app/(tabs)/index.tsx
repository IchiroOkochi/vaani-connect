import { useMemo, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Linking,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  TextInput,
  View,
} from 'react-native';

import { ThemedText } from '@/components/themed-text';
import { ThemedView } from '@/components/themed-view';
import { SUPPORTED_LANGUAGES, type SupportedLanguage } from '@/constants/languages';
import {
  API_BASE_URL,
  toAbsoluteAudioUrl,
  translateSpeech,
  translateText,
  type TranslationResponse,
} from '@/services/api';

type Mode = 'text' | 'speech';

export default function HomeScreen() {
  const [mode, setMode] = useState<Mode>('text');
  const [sourceLanguage, setSourceLanguage] = useState<SupportedLanguage>('English');
  const [targetLanguage, setTargetLanguage] = useState<SupportedLanguage>('Hindi');
  const [inputText, setInputText] = useState('');
  const [recordingBlob, setRecordingBlob] = useState<Blob | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [result, setResult] = useState<TranslationResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const mediaRecorderRef = useRef<any>(null);
  const chunksRef = useRef<any[]>([]);

  const canTranslate = useMemo(
    () => (mode === 'text' ? inputText.trim().length > 0 : Boolean(recordingBlob)),
    [inputText, mode, recordingBlob],
  );

  async function toggleRecording() {
    if (Platform.OS !== 'web') {
      Alert.alert(
        'Speech input needs web in this build',
        'Use Expo Web for recording or add expo-av in a network-enabled setup.',
      );
      return;
    }

    if (!isRecording) {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };

      recorder.onstop = () => {
        setRecordingBlob(new Blob(chunksRef.current, { type: 'audio/webm' }));
        stream.getTracks().forEach((track) => track.stop());
      };

      recorder.start();
      mediaRecorderRef.current = recorder;
      setResult(null);
      setIsRecording(true);
      return;
    }

    mediaRecorderRef.current?.stop();
    setIsRecording(false);
  }

  async function runTranslation() {
    setIsLoading(true);
    try {
      const response =
        mode === 'text'
          ? await translateText({ text: inputText.trim(), sourceLanguage, targetLanguage })
          : await translateSpeech({ audioBlob: recordingBlob!, sourceLanguage, targetLanguage });

      setResult(response);
      if (response.audio_url) await playAudio(response.audio_url);
    } catch {
      Alert.alert('Translation failed', `Unable to reach backend at ${API_BASE_URL}.`);
    } finally {
      setIsLoading(false);
    }
  }

  async function playAudio(audioUrl: string) {
    const absolute = toAbsoluteAudioUrl(audioUrl);
    if (!absolute) return;

    if (Platform.OS === 'web') {
      const audio = new Audio(absolute);
      await audio.play();
      return;
    }

    await Linking.openURL(absolute);
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <ThemedText type="title">Vaani Connect</ThemedText>
      <ThemedText>Translate by text or speech, and get spoken output.</ThemedText>

      <View style={styles.segmentRow}>
        {(['text', 'speech'] as const).map((currentMode) => (
          <Pressable
            key={currentMode}
            style={[styles.segmentButton, mode === currentMode && styles.segmentActive]}
            onPress={() => {
              setMode(currentMode);
              setResult(null);
            }}>
            <ThemedText style={mode === currentMode ? styles.segmentActiveText : undefined}>
              {currentMode === 'text' ? 'Text Input' : 'Speech Input'}
            </ThemedText>
          </Pressable>
        ))}
      </View>

      <LanguagePicker title="Source language" selected={sourceLanguage} onSelect={setSourceLanguage} />
      <LanguagePicker title="Target language" selected={targetLanguage} onSelect={setTargetLanguage} />

      {mode === 'text' ? (
        <ThemedView style={styles.card}>
          <ThemedText type="defaultSemiBold">Enter text</ThemedText>
          <TextInput
            value={inputText}
            onChangeText={setInputText}
            placeholder="Type or paste text here"
            multiline
            style={styles.input}
          />
        </ThemedView>
      ) : (
        <ThemedView style={styles.card}>
          <ThemedText type="defaultSemiBold">Record speech</ThemedText>
          <Pressable
            style={[styles.recordButton, isRecording && styles.stopButton]}
            onPress={toggleRecording}>
            <ThemedText style={styles.recordButtonText}>
              {isRecording ? 'Stop Recording' : 'Start Recording'}
            </ThemedText>
          </Pressable>
          <ThemedText>{recordingBlob ? 'Audio captured and ready.' : 'No audio recorded yet.'}</ThemedText>
        </ThemedView>
      )}

      <Pressable
        onPress={runTranslation}
        disabled={!canTranslate || isLoading}
        style={[styles.translateButton, (!canTranslate || isLoading) && styles.disabledButton]}>
        {isLoading ? <ActivityIndicator color="#fff" /> : <ThemedText style={styles.ctaText}>Translate</ThemedText>}
      </Pressable>

      {result ? (
        <ThemedView style={styles.resultCard}>
          {result.transcribed_text ? (
            <>
              <ThemedText type="defaultSemiBold">Recognized speech</ThemedText>
              <ThemedText>{result.transcribed_text}</ThemedText>
            </>
          ) : null}

          <ThemedText type="defaultSemiBold">Translated text</ThemedText>
          <ThemedText>{result.translated_text}</ThemedText>

          {result.audio_url ? (
            <Pressable style={styles.playButton} onPress={() => playAudio(result.audio_url!)}>
              <ThemedText style={styles.playText}>Play Voice Output</ThemedText>
            </Pressable>
          ) : null}
        </ThemedView>
      ) : null}
    </ScrollView>
  );
}

function LanguagePicker({
  title,
  selected,
  onSelect,
}: {
  title: string;
  selected: SupportedLanguage;
  onSelect: (language: SupportedLanguage) => void;
}) {
  return (
    <ThemedView style={styles.card}>
      <ThemedText type="defaultSemiBold">{title}</ThemedText>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
        {SUPPORTED_LANGUAGES.map((language) => (
          <Pressable
            key={language}
            onPress={() => onSelect(language)}
            style={[styles.chip, selected === language && styles.chipActive]}>
            <ThemedText style={selected === language ? styles.chipActiveText : undefined}>{language}</ThemedText>
          </Pressable>
        ))}
      </ScrollView>
    </ThemedView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1 },
  content: { padding: 16, gap: 12 },
  segmentRow: { flexDirection: 'row', gap: 8 },
  segmentButton: {
    flex: 1,
    borderWidth: 1,
    borderColor: '#ccc',
    borderRadius: 10,
    paddingVertical: 10,
    alignItems: 'center',
  },
  segmentActive: { backgroundColor: '#222' },
  segmentActiveText: { color: '#fff' },
  card: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 12,
    padding: 12,
    gap: 10,
  },
  chipRow: { flexDirection: 'row', gap: 8, paddingVertical: 2 },
  chip: {
    borderRadius: 999,
    borderWidth: 1,
    borderColor: '#bbb',
    paddingVertical: 6,
    paddingHorizontal: 12,
  },
  chipActive: { backgroundColor: '#4f46e5', borderColor: '#4f46e5' },
  chipActiveText: { color: '#fff' },
  input: {
    minHeight: 100,
    borderWidth: 1,
    borderColor: '#ccc',
    borderRadius: 10,
    padding: 10,
    textAlignVertical: 'top',
  },
  recordButton: {
    backgroundColor: '#0ea5e9',
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: 'center',
  },
  stopButton: { backgroundColor: '#ef4444' },
  recordButtonText: { color: '#fff', fontWeight: '700' },
  translateButton: {
    backgroundColor: '#16a34a',
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
  },
  disabledButton: { opacity: 0.5 },
  ctaText: { color: '#fff', fontWeight: '700' },
  resultCard: {
    borderWidth: 1,
    borderColor: '#86efac',
    borderRadius: 12,
    padding: 12,
    gap: 8,
    marginBottom: 40,
  },
  playButton: {
    marginTop: 6,
    backgroundColor: '#1d4ed8',
    borderRadius: 10,
    paddingVertical: 10,
    alignItems: 'center',
  },
  playText: { color: '#fff', fontWeight: '700' },
});
