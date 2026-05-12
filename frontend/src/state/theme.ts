/* Theme provider — light/dark switch persisted to localStorage.
 *
 * `tokens.css` already defines both palettes (dark by default, light
 * scoped under `:root[data-theme="light"]`). Switching themes is just
 * toggling the data-theme attribute on <html> and persisting the
 * choice.
 *
 * The Plot wrapper reads useTheme().theme to swap layout colors and
 * pick a plotly_white-style or plotly_dark-style palette.
 */

import { create } from "zustand";

export type Theme = "dark" | "light";

const STORAGE_KEY = "solarstata.theme";

const initialTheme = (): Theme => {
  if (typeof window === "undefined") return "dark";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  return stored === "light" ? "light" : "dark";
};

const apply = (theme: Theme) => {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", theme);
};

interface ThemeStore {
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggle: () => void;
}

export const useTheme = create<ThemeStore>((set, get) => {
  const initial = initialTheme();
  apply(initial);
  return {
    theme: initial,
    setTheme: (t) => {
      apply(t);
      try { window.localStorage.setItem(STORAGE_KEY, t); } catch { /* noop */ }
      set({ theme: t });
    },
    toggle: () => get().setTheme(get().theme === "dark" ? "light" : "dark"),
  };
});
