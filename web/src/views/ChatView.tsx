import React, { useEffect, useRef, useState } from 'react';
import { streamChat } from '../api';
import { renderMarkdown, escapeHtml } from '../utils/markdown';

interface Msg {
  role: 'user' | 'assistant';
  content: string;
}

export default function ChatView(): React.ReactElement {
  const [messages, setMessages] = useState<Msg[]>([
    { role: 'assistant', content: '你好，我是 ECO AGENT。生态环境执法领域的 AI 同事——可以问我法规、案卷、裁量、督察相关的问题。' },
  ]);
  const [input, setInput] = useState('');
  const [busy, setBusy] = useState(false);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const send = async () => {
    const text = input.trim();
    if (!text || busy) return;
    setInput('');
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((prev) => [...prev, { role: 'user', content: text }, { role: 'assistant', content: '' }]);
    setBusy(true);
    try {
      await streamChat(text, history, (delta) => {
        setMessages((prev) => {
          const next = [...prev];
          const last = next[next.length - 1];
          next[next.length - 1] = { role: 'assistant', content: last.content + delta };
          return next;
        });
      });
    } catch (e) {
      setMessages((prev) => {
        const next = [...prev];
        next[next.length - 1] = {
          role: 'assistant',
          content: `[连接失败] ${(e as Error).message}\n请确认已启动: eco server`,
        };
        return next;
      });
    } finally {
      setBusy(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void send();
    }
  };

  return (
    <div className="chat-box" style={{ height: 'calc(100vh - 120px)' }}>
      <div className="chat-log" ref={logRef}>
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="role">{m.role === 'user' ? '你' : 'ECO AGENT'}</div>
            <div
              className="bubble"
              // markdown 渲染器先转义后替换（防 XSS）
              dangerouslySetInnerHTML={{
                __html: m.role === 'assistant'
                  ? renderMarkdown(m.content)
                  : escapeHtml(m.content).replace(/\n/g, '<br/>'),
              }}
            />
          </div>
        ))}
      </div>
      <div className="chat-input-row">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="输入问题，Enter 发送，Shift+Enter 换行"
          rows={2}
        />
        <button className="btn" onClick={() => void send()} disabled={busy || !input.trim()}>
          {busy ? '生成中' : '发送'}
        </button>
      </div>
    </div>
  );
}
