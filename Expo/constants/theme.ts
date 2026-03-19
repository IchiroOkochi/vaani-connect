import { Platform } from 'react-native';

const lightAccent = '#c96f2d';
const darkAccent = '#f2a65a';

export const Colors = {
  light: {
    text: '#1c2324',
    background: '#f5efe3',
    tint: lightAccent,
    icon: '#6f756c',
    tabIconDefault: '#79807b',
    tabIconSelected: lightAccent,
    surface: '#fffaf1',
    border: 'rgba(28, 35, 36, 0.08)',
  },
  dark: {
    text: '#f7f2e8',
    background: '#071317',
    tint: darkAccent,
    icon: '#8ea29d',
    tabIconDefault: '#7e8f8b',
    tabIconSelected: darkAccent,
    surface: '#10242a',
    border: 'rgba(233, 228, 212, 0.12)',
  },
};

export const Fonts = Platform.select({
  ios: {
    sans: 'Avenir Next',
    serif: 'Georgia',
    rounded: 'Arial Rounded MT Bold',
    mono: 'Menlo',
  },
  android: {
    sans: 'sans-serif-medium',
    serif: 'serif',
    rounded: 'sans-serif',
    mono: 'monospace',
  },
  default: {
    sans: 'sans-serif',
    serif: 'serif',
    rounded: 'sans-serif',
    mono: 'monospace',
  },
  web: {
    sans: "'Avenir Next', 'Trebuchet MS', 'Segoe UI', sans-serif",
    serif: "'Iowan Old Style', 'Palatino Linotype', 'Book Antiqua', Georgia, serif",
    rounded: "'Trebuchet MS', 'Avenir Next', sans-serif",
    mono: "'SFMono-Regular', Consolas, 'Liberation Mono', monospace",
  },
});
