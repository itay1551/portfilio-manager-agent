/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ORCHESTRATOR_URL: string;
  readonly VITE_OPENAI_API_ENDPOINT: string;
  readonly VITE_OPENAI_API_TOKEN: string;
  readonly VITE_OPENAI_MODEL: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

interface Window {
  __RUNTIME_CONFIG__?: Record<string, string>;
}
