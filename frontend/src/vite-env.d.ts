/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_API_URL?: string;
  readonly VITE_WS_URL?: string;
  readonly VITE_POLL_INTERVAL_MS?: string;
  readonly VITE_PUBLIC_REGISTRATION_ENABLED?: string;
  readonly VITE_AGENT_INSTALLER_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
