/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_ECO_API?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
