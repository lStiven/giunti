/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  /** Must match the backend's MAX_FILE_SIZE_MB; only used to warn before uploading. */
  readonly VITE_MAX_FILE_MB?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
