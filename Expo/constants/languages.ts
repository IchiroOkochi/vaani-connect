export const SUPPORTED_LANGUAGES = [
  'English',
  'Hindi',
  'Telugu',
  'Tamil',
  'Kannada',
  'Malayalam',
  'Bengali',
  'Marathi',
] as const;

export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];
