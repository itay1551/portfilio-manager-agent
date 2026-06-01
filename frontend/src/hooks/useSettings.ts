import { useCallback, useState } from "react";
import type { ConnectionSettings } from "../api/types";

function envDefault(keys: string[], fallback = ""): string {
  for (const key of keys) {
    const value = import.meta.env[key as keyof ImportMetaEnv];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return fallback;
}

export function loadDefaultSettings(): ConnectionSettings {
  return {
    orchestratorUrl: envDefault(
      ["VITE_ORCHESTRATOR_URL"],
      "/api/chat",
    ),
    llmUrl: envDefault(["VITE_OPENAI_API_ENDPOINT"], ""),
    apiKey: envDefault(["VITE_OPENAI_API_TOKEN"], ""),
    model: envDefault(["VITE_OPENAI_MODEL"], ""),
  };
}

export function useSettings() {
  const [settings, setSettings] = useState<ConnectionSettings>(loadDefaultSettings);

  const updateSettings = useCallback(
    (patch: Partial<ConnectionSettings>) => {
      setSettings((prev) => ({ ...prev, ...patch }));
    },
    [],
  );

  return { settings, updateSettings };
}
