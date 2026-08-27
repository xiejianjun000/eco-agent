import { StrictMode, Suspense, lazy, Component, type ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';

class ErrorBoundary extends Component<{ children: ReactNode }, { hasError: boolean }> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false };
  }
  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true };
  }
  override render(): ReactNode {
    if (this.state.hasError) {
      return <div style={{ padding: 24, color: '#e74c3c' }}>应用出现错误，请刷新重试</div>;
    }
    return this.props.children;
  }
}

/**
 * 全局错误收集器(挂载到 window)。ErrorBoundary 会把捕获到的错误发到这里,
 * 便于未来接入 Sentry / 自建上报 / 控制台调试。
 */
const errorCollector = (error: Error, context?: unknown): void => {
  // TODO: 接入正式上报服务 (window.__ECOAEGIS_ERROR__ 外部可覆写)
  // eslint-disable-next-line no-console
  console.error('[EcoAegis Global Error]', error, context ?? '');
};

(globalThis as unknown as Record<string, unknown>).__ECOAEGIS_ERROR__ =
  errorCollector;

/** 全局 window.onerror (Promise 之外的同步错误) */
globalThis.addEventListener(
  'error',
  (event: ErrorEvent) => {
    if (event.error instanceof Error) {
      errorCollector(event.error, {
        type: 'onerror',
        message: event.message,
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
      });
    }
  },
  { passive: true },
);

/** 全局 unhandledrejection (未处理的 Promise 拒绝) */
globalThis.addEventListener(
  'unhandledrejection',
  (event: PromiseRejectionEvent) => {
    const reason =
      event.reason instanceof Error
        ? event.reason
        : new Error(String(event.reason ?? 'Unhandled promise rejection'));
    errorCollector(reason, { type: 'unhandledrejection' });
  },
  { passive: true },
);

const App = lazy(() => import('./App').then((m) => ({ default: m.default })));

const appFallback = (
  <div
    style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100vh',
      color: '#7f8c8d',
      gap: 12,
      fontFamily:
        '-apple-system, "PingFang SC", "Microsoft YaHei", sans-serif',
    }}
  >
    <div
      style={{
        width: 36,
        height: 36,
        border: '3px solid #e0e0e0',
        borderTopColor: '#0a7d3c',
        borderRadius: '50%',
        animation: 'eco-load 0.8s linear infinite',
      }}
    />
    <span style={{ fontSize: 13 }}>EcoAegis 启动中...</span>
    <style>{`@keyframes eco-load{to{transform:rotate(360deg)}}`}</style>
  </div>
);

const rootEl = document.getElementById('root');
if (!rootEl) {
  throw new Error(
    "[EcoAegis] HTML root element '#root' not found, bootstrap aborted.",
  );
}

createRoot(rootEl).render(
  <StrictMode>
    <ErrorBoundary>
      <Suspense fallback={appFallback}>
        <App />
      </Suspense>
    </ErrorBoundary>
  </StrictMode>,
);
