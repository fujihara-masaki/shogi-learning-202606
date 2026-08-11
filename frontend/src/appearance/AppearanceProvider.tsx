import { type ReactNode, useState } from "react";
import { DEFAULT_APPEARANCE_SETTINGS, loadAppearanceSettings, resetAppearanceSettings, saveAppearanceSettings } from "./storage";
import { AppearanceContext } from "./useAppearance";

export function AppearanceProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState(loadAppearanceSettings);
  const [storageWarning, setStorageWarning] = useState(false);

  function update(next: typeof settings) {
    setSettings(next);
    setStorageWarning(!saveAppearanceSettings(next));
  }

  return (
    <AppearanceContext.Provider value={{
      ...settings,
      setPieceTheme: (pieceTheme) => update({ ...settings, pieceTheme }),
      setBoardTheme: (boardTheme) => update({ ...settings, boardTheme }),
      resetToDefaults: () => {
        setSettings({ ...DEFAULT_APPEARANCE_SETTINGS });
        setStorageWarning(!resetAppearanceSettings());
      },
      storageWarning,
    }}>
      {children}
    </AppearanceContext.Provider>
  );
}
