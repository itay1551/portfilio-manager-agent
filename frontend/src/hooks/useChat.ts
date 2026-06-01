import { useCallback, useState } from "react";
import { postChat } from "../api/client";
import type { ChatMessage, ConnectionSettings, PipelineContext } from "../api/types";
import { CHAT_WELCOME_READY } from "../api/types";

export function useChat() {
  const [displayMessages, setDisplayMessages] = useState<ChatMessage[]>([]);
  const [apiHistory, setApiHistory] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);

  const clearChat = useCallback(() => {
    setDisplayMessages([]);
    setApiHistory([]);
  }, []);

  const sendMessage = useCallback(
    async (
      userText: string,
      settings: ConnectionSettings,
      context: PipelineContext | null,
      onContextUpdate?: (ctx: PipelineContext) => void,
    ): Promise<string | null> => {
      const trimmed = userText.trim();
      if (!trimmed) {
        return null;
      }

      if (!context) {
        const reply = "Run **Portfolio setup** first to build a portfolio.";
        setDisplayMessages((prev) => [
          ...prev,
          { role: "user", content: trimmed },
          { role: "assistant", content: reply },
        ]);
        return reply;
      }

      const userMessage: ChatMessage = { role: "user", content: trimmed };
      const historyForApi = [...apiHistory];
      setDisplayMessages((prev) => [...prev, userMessage]);
      setSending(true);

      try {
        const { reply, context: updatedContext } = await postChat(
          settings,
          trimmed,
          historyForApi,
          context,
        );

        const assistantMessage: ChatMessage = { role: "assistant", content: reply };
        setApiHistory((prev) => [...prev, userMessage, assistantMessage]);
        setDisplayMessages((prev) => [...prev, assistantMessage]);

        if (updatedContext) {
          onContextUpdate?.(updatedContext);
        }

        return reply;
      } catch (e) {
        const errMsg = `Error: ${e instanceof Error ? e.message : String(e)}`;
        setDisplayMessages((prev) => [
          ...prev,
          { role: "assistant", content: errMsg },
        ]);
        return errMsg;
      } finally {
        setSending(false);
      }
    },
    [apiHistory],
  );

  const setWelcomeMessage = useCallback((content: string) => {
    setDisplayMessages([{ role: "assistant", content }]);
  }, []);

  const unlockChat = useCallback(() => {
    setDisplayMessages([{ role: "assistant", content: CHAT_WELCOME_READY }]);
    setApiHistory([]);
  }, []);

  return {
    displayMessages,
    apiHistory,
    sending,
    sendMessage,
    clearChat,
    setWelcomeMessage,
    unlockChat,
  };
}
