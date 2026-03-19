export const SUPPORTED_LANGUAGES = [
  'English',
  'Assamese',
  'Bodo',
  'Dogri',
  'Gujarati',
  'Hindi',
  'Kannada',
  'Kashmiri',
  'Konkani',
  'Maithili',
  'Malayalam',
  'Bengali',
  'Manipuri',
  'Marathi',
  'Nepali',
  'Odia',
  'Punjabi',
  'Sanskrit',
  'Santali',
  'Sindhi',
  'Tamil',
  'Telugu',
  'Urdu',
] as const;

export type SupportedLanguage = string;

export const LANGUAGE_LABELS: Record<string, string> = {
  English: 'अंग्रेज़ी',
  Assamese: 'অসমীয়া',
  Bodo: 'बड़ो',
  Dogri: 'डोगरी',
  Gujarati: 'ગુજરાતી',
  Hindi: 'हिन्दी',
  Kannada: 'ಕನ್ನಡ',
  Kashmiri: 'कश्मीरी',
  Konkani: 'कोंकणी',
  Maithili: 'मैथिली',
  Malayalam: 'മലയാളം',
  Bengali: 'বাংলা',
  Manipuri: 'মণিপুরী',
  Marathi: 'मराठी',
  Nepali: 'नेपाली',
  Odia: 'ଓଡ଼ିଆ',
  Punjabi: 'ਪੰਜਾਬੀ',
  Sanskrit: 'संस्कृत',
  Santali: 'संताली',
  Sindhi: 'सिंधी',
  Tamil: 'தமிழ்',
  Telugu: 'తెలుగు',
  Urdu: 'اردو',
};

export function getLanguageLabel(language: string): string {
  return LANGUAGE_LABELS[language] ?? language;
}
