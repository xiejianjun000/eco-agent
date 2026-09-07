// Vite 客户端类型声明
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_APP_TITLE: string;
  readonly VITE_API_BASE_URL: string;
  readonly VITE_MCP_SSE_ENDPOINT?: string;
  readonly VITE_CEMS_PLATFORM_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare const __APP_VERSION__: string;
declare const __BUILD_TIME__: string;
declare const __APP_ENV__: 'development' | 'production' | 'test';
