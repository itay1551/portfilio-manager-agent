import { useEffect, useRef, type KeyboardEvent } from "react";
import type { ChatMessage } from "../api/types";
import { Markdown } from "./Markdown";

interface ChatProps {
  visible: boolean;
  interactive: boolean;
  messages: ChatMessage[];
  input: string;
  sending: boolean;
  onInputChange: (value: string) => void;
  onSend: () => void;
  onClear: () => void;
}

export function Chat({
  visible,
  interactive,
  messages,
  input,
  sending,
  onInputChange,
  onSend,
  onClear,
}: ChatProps) {
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [messages, sending]);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (interactive && !sending && input.trim()) {
        onSend();
      }
    }
  };

  if (!visible) {
    return null;
  }

  return (
    <section className="chat-section" id="chat-section">
      <h3>Discuss your portfolio</h3>
      <div className="chat-messages" ref={listRef}>
        {messages.map((msg, i) => (
          <div key={i} className={`chat-bubble chat-${msg.role}`}>
            <div className="markdown-body">
              <Markdown>{msg.content}</Markdown>
            </div>
          </div>
        ))}
        {sending && (
          <div className="chat-bubble chat-assistant">
            <span className="chat-typing">Thinking…</span>
          </div>
        )}
      </div>
      <div className="chat-controls">
        <textarea
          id="chat-msg-input"
          rows={1}
          value={input}
          placeholder="Enter to send | Shift+Enter for new line"
          disabled={!interactive || sending}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
        />
        <div className="chat-buttons">
          <button
            type="button"
            id="chat-send-btn"
            className="btn btn-primary"
            disabled={!interactive || sending || !input.trim()}
            onClick={onSend}
          >
            Send
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={!interactive || sending}
            onClick={onClear}
          >
            Clear chat
          </button>
        </div>
      </div>
    </section>
  );
}
