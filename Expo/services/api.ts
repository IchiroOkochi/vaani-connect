import { Platform } from 'react-native';

import type { SupportedLanguage } from '@/constants/languages';

const envBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL;

const defaultBaseUrl = Platform.select({
  android: 'http://10.0.2.2:8000',
  ios: 'http://localhost:8000',
  web: 'http://localhost:8000',
  default: 'http://localhost:8000',
});

export const API_BASE_URL = (envBaseUrl ?? defaultBaseUrl ?? '').replace(/\/$/, '');

export type TranslationResponse = {
  source_text?: string;
  transcribed_text?: string;
  translated_text: string;
  audio_url?: string | null;
};

export async function fetchSupportedLanguages(): Promise<SupportedLanguage[]> {
  const res = await fetch(`${API_BASE_URL}/languages`);
  if (!res.ok) {
    throw new Error(`Language fetch failed (${res.status})`);
  }

  const payload: unknown = await res.json();
  if (!Array.isArray(payload)) {
    throw new Error('Language fetch returned invalid payload');
  }

  return payload.filter((item): item is SupportedLanguage => typeof item === 'string');
}

export async function translateText(params: {
  text: string;
  sourceLanguage: SupportedLanguage;
  targetLanguage: SupportedLanguage;
}): Promise<TranslationResponse> {
  const res = await fetch(`${API_BASE_URL}/translate/text`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text: params.text,
      source_language: params.sourceLanguage,
      target_language: params.targetLanguage,
      include_speech: true,
    }),
  });

  if (!res.ok) {
    throw new Error(`Text translation failed (${res.status})`);
  }

  return res.json();
}

export async function translateSpeech(params: {
  audioBlob: Blob;
  sourceLanguage: SupportedLanguage;
  targetLanguage: SupportedLanguage;
}): Promise<TranslationResponse> {
  const data = new FormData();
  data.append('audio', params.audioBlob, 'recording.webm');
  data.append('source_language', params.sourceLanguage);
  data.append('target_language', params.targetLanguage);

  const res = await fetch(`${API_BASE_URL}/translate/speech`, {
    method: 'POST',
    body: data,
  });

  if (!res.ok) {
    throw new Error(`Speech translation failed (${res.status})`);
  }

  return res.json();
}

export function toAbsoluteAudioUrl(audioUrl?: string | null): string | undefined {
  if (!audioUrl) return undefined;
  if (audioUrl.startsWith('http://') || audioUrl.startsWith('https://')) return audioUrl;
  return `${API_BASE_URL}${audioUrl.startsWith('/') ? '' : '/'}${audioUrl}`;
}
