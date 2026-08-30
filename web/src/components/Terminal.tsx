import { useEffect, useRef } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import { AttachAddon } from '@xterm/addon-attach';
import '@xterm/xterm/css/xterm.css';

/** 内置终端面板（xterm.js + 后端 PTY WebSocket，对齐 DSH Web UI 内置终端） */
export default function TerminalPanel({ onClose }: { onClose?: () => void }) {
  const mountRef = useRef<HTMLDivElement>(null);
  const termRef = useRef<Terminal | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const term = new Terminal({
      cursorBlink: true,
      fontSize: 13,
      lineHeight: 1.2,
      scrollback: 2000,
      theme: {
        background: '#0d1117',
        foreground: '#c9d1d9',
        cursor: '#58a6ff',
        selectionBackground: '#264f78',
      },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(mount);
    fit.fit();
    termRef.current = term;

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${proto}//${window.location.host}/api/v1/terminal/ws`);
    wsRef.current = ws;
    ws.binaryType = 'arraybuffer';
    ws.onopen = () => {
      // 触发首行 shell 提示符
      if (ws.readyState === WebSocket.OPEN) ws.send('\r');
    };
    term.loadAddon(new AttachAddon(ws));

    // 窗口尺寸变化 → 控制帧（\x01 + JSON）通知后端 resize PTY
    term.onResize(({ cols, rows }) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send('\x01' + JSON.stringify({ cols, rows }));
      }
    });
    const onWinResize = () => fit.fit();
    window.addEventListener('resize', onWinResize);

    return () => {
      window.removeEventListener('resize', onWinResize);
      try { ws.close(); } catch { /* noop */ }
      term.dispose();
      termRef.current = null;
    };
  }, []);

  return (
    <div className="terminal-panel">
      <div className="terminal-head">
        <span className="terminal-title">🖥️ 内置终端</span>
        <span className="terminal-hint">shell 直连本机 · 仅 127.0.0.1</span>
        {onClose && (
          <button className="tb-btn" title="关闭终端" onClick={onClose}>✕</button>
        )}
      </div>
      <div className="terminal-body" ref={mountRef} />
    </div>
  );
}
