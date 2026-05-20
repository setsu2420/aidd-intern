import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import App from './App';
import { darkTheme, lightTheme } from './theme';
import { useLayoutStore } from './store/layoutStore';

export default function Root() {
  const themeMode = useLayoutStore((s) => s.themeMode);
  const theme = themeMode === 'light' ? lightTheme : darkTheme;

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <App />
    </ThemeProvider>
  );
}
