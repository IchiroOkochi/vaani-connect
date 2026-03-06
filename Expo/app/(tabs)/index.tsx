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
import { SUPPORTED_LANGUAGES, type SupportedLanguage } from '@/constants/languages';
import {
  API_BASE_URL,
  toAbsoluteAudioUrl,
  translateSpeech,
  translateText,
  type TranslationResponse,
} from '@/services/api';

export default function HomeScreen() {
  const [sourceLanguage, setSourceLanguage] = useState<SupportedLanguage>('English');
  const [targetLanguage, setTargetLanguage] = useState<SupportedLanguage>('Hindi');
  const [inputText, setInputText] = useState('');
  const [outputText, setOutputText] = useState('');
  const [latestAudioUrl, setLatestAudioUrl] = useState<string | null>(null);
  const [isRecording, setIsRecording] = useState(false);
  const [isTranslatingText, setIsTranslatingText] = useState(false);
  const [isTranslatingSpeech, setIsTranslatingSpeech] = useState(false);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const canTranslateText = useMemo(() => inputText.trim().length > 0 && !isTranslatingSpeech, [inputText, isTranslatingSpeech]);

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
        'Use Expo Web for recording or add expo-av in a network-enabled setup.',
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
    if (Platform.OS === 'web') {
      const audio = new Audio(audioUrl);
      await audio.play();
      return;
    }

    await Linking.openURL(audioUrl);
  }

  function switchLanguages() {
    setInputText(outputText);
    setOutputText(inputText);
    setLatestAudioUrl(null);
    setSourceLanguage(targetLanguage);
    setTargetLanguage(sourceLanguage);
  }

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <ThemedText style={styles.title}>Vaani Connect</ThemedText>

      <View style={styles.recordRow}>
        <Pressable
          style={[styles.circleButton, isRecording && styles.circleButtonStop]}
          onPress={toggleRecording}
          disabled={isTranslatingSpeech || isTranslatingText}>
          {isTranslatingSpeech ? (
            <ActivityIndicator color="#0b1220" />
          ) : (
            <ThemedText style={styles.recordIcon}>{isRecording ? '⏹' : '⏺'}</ThemedText>
          )}
        </Pressable>
        <ThemedText style={styles.buttonLabel}>{isRecording ? 'Stop Recording' : 'Record Button'}</ThemedText>
      </View>

      <LanguagePicker title="Input Language" selected={sourceLanguage} onSelect={setSourceLanguage} />
      <LanguagePicker title="Output Language" selected={targetLanguage} onSelect={setTargetLanguage} />

      <View style={styles.textBox}>
        <TextInput
          value={inputText}
          onChangeText={setInputText}
          placeholder="Input Text Box"
          placeholderTextColor="#8d8d8d"
          multiline
          style={styles.input}
        />
      </View>

      <View style={styles.arrowRow}>
        <Pressable style={styles.arrowButton} onPress={switchLanguages}>
          <ThemedText style={styles.arrowText}>⇅</ThemedText>
        </Pressable>
      </View>

      <Pressable
        style={[styles.translateButton, (!canTranslateText || isTranslatingText) && styles.disabledButton]}
        onPress={translateFromText}
        disabled={!canTranslateText || isTranslatingText}>
        {isTranslatingText ? (
          <ActivityIndicator color="#071322" />
        ) : (
          <ThemedText style={styles.translateButtonText}>Translate</ThemedText>
        )}
      </Pressable>

      <View style={styles.textBox}>
        <TextInput
          value={outputText}
          editable={false}
          placeholder="Out put Text Box"
          placeholderTextColor="#8d8d8d"
          multiline
          style={[styles.input, styles.outputInput]}
        />
      </View>

      <View style={styles.speakRow}>
        <ThemedText style={styles.buttonLabel}>Speak Output button</ThemedText>
        <Pressable style={styles.circleButton} onPress={playOutputAudio}>
          <ThemedText style={styles.speakIcon}>▶</ThemedText>
        </Pressable>
      </View>

      <ThemedText style={styles.footer}>All the credibilities</ThemedText>
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
    <View style={styles.languageBlock}>
      <ThemedText style={styles.languageTitle}>{title}</ThemedText>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
        {SUPPORTED_LANGUAGES.map((language) => (
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

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: '#000' },
  content: {
    paddingHorizontal: 24,
    paddingTop: 44,
    paddingBottom: 56,
    gap: 18,
  },
  title: {
    color: '#f5f5f5',
    fontSize: 56,
    lineHeight: 62,
    fontWeight: '300',
    letterSpacing: 0.3,
  },
  recordRow: {
    marginTop: 6,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  speakRow: {
    marginTop: 4,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: 12,
  },
  circleButton: {
    width: 46,
    height: 46,
    borderRadius: 23,
    backgroundColor: '#66b7f2',
    alignItems: 'center',
    justifyContent: 'center',
  },
  circleButtonStop: { backgroundColor: '#f97316' },
  recordIcon: {
    color: '#0b1220',
    fontSize: 20,
    lineHeight: 20,
    fontWeight: '700',
  },
  buttonLabel: {
    color: '#f5f5f5',
    fontSize: 16,
  },
  textBox: {
    minHeight: 164,
    borderWidth: 2,
    borderColor: '#ececec',
    paddingHorizontal: 16,
    paddingVertical: 14,
    justifyContent: 'center',
  },
  input: {
    minHeight: 132,
    color: '#f5f5f5',
    fontSize: 36,
    lineHeight: 42,
    textAlign: 'center',
    textAlignVertical: 'center',
  },
  outputInput: {
    opacity: 0.92,
  },
  arrowRow: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 24,
  },
  arrowButton: {
    width: 48,
    height: 48,
    borderRadius: 24,
    borderWidth: 1,
    borderColor: '#ececec',
    alignItems: 'center',
    justifyContent: 'center',
  },
  arrowText: {
    color: '#f5f5f5',
    fontSize: 28,
    lineHeight: 30,
    fontWeight: '500',
  },
  translateButton: {
    backgroundColor: '#66b7f2',
    borderRadius: 999,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 44,
    paddingHorizontal: 20,
  },
  translateButtonText: {
    color: '#071322',
    fontSize: 16,
    fontWeight: '700',
  },
  disabledButton: {
    opacity: 0.4,
  },
  speakIcon: {
    color: '#0b1220',
    fontSize: 16,
    fontWeight: '700',
  },
  footer: {
    marginTop: 36,
    marginBottom: 20,
    color: '#f5f5f5',
    alignSelf: 'flex-end',
    fontSize: 20,
  },
  languageBlock: {
    gap: 8,
  },
  languageTitle: {
    color: '#f5f5f5',
    fontSize: 13,
    opacity: 0.85,
  },
  chipRow: {
    gap: 10,
    paddingBottom: 2,
  },
  chip: {
    borderWidth: 1,
    borderColor: '#4a4a4a',
    borderRadius: 999,
    paddingHorizontal: 14,
    paddingVertical: 7,
  },
  chipActive: {
    backgroundColor: '#66b7f2',
    borderColor: '#66b7f2',
  },
  chipLabel: {
    color: '#f5f5f5',
  },
  chipLabelActive: {
    color: '#071322',
    fontWeight: '600',
  },
});
