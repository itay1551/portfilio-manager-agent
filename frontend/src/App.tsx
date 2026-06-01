import { useCallback, useEffect, useState } from "react";
import { CHAT_RUNNING, CHAT_WELCOME_PENDING } from "./api/types";
import { Chat } from "./components/Chat";
import { ConnectionSettingsPanel } from "./components/ConnectionSettings";
import {
  defaultPipelineForm,
  PipelineSetup,
} from "./components/PipelineSetup";
import { PipelineOutputs } from "./components/PipelineOutputs";
import { useChat } from "./hooks/useChat";
import { usePipeline } from "./hooks/usePipeline";
import { useSettings } from "./hooks/useSettings";
import type { PipelineFormValues } from "./api/types";

export default function App() {
  const { settings, updateSettings } = useSettings();
  const pipeline = usePipeline();
  const chat = useChat();

  const [form, setForm] = useState<PipelineFormValues>(() => defaultPipelineForm());
  const [chatInput, setChatInput] = useState("");

  const [connectionOpen, setConnectionOpen] = useState(false);
  const [setupOpen, setSetupOpen] = useState(true);
  const [outputsOpen, setOutputsOpen] = useState(false);

  const chatVisible = pipeline.hasStarted || pipeline.isComplete;
  const chatInteractive = pipeline.isComplete;

  useEffect(() => {
    if (pipeline.isRunning) {
      chat.setWelcomeMessage(CHAT_RUNNING);
    } else if (!pipeline.hasStarted) {
      chat.setWelcomeMessage(CHAT_WELCOME_PENDING);
    }
  }, [
    pipeline.isRunning,
    pipeline.hasStarted,
    chat.setWelcomeMessage,
  ]);

  useEffect(() => {
    if (pipeline.isComplete) {
      chat.unlockChat();
      setSetupOpen(false);
      setOutputsOpen(true);
    }
  }, [pipeline.isComplete, chat.unlockChat]);

  useEffect(() => {
    if (pipeline.hasStarted && !pipeline.isComplete) {
      setOutputsOpen(true);
    }
  }, [pipeline.hasStarted, pipeline.isComplete]);

  const handleRunPipeline = useCallback(async () => {
    setOutputsOpen(true);
    chat.clearChat();
    chat.setWelcomeMessage(CHAT_RUNNING);
    await pipeline.runPipeline(settings, form);
  }, [pipeline, settings, form, chat]);

  const handleSendChat = useCallback(async () => {
    const text = chatInput;
    setChatInput("");
    await chat.sendMessage(text, settings, pipeline.context, (ctx) => {
      pipeline.updateOutputsFromContext(ctx);
    });
  }, [chatInput, chat, settings, pipeline]);

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>Neurosymbolic AI Demo</h1>
        <p className="subtitle">Powered by NVIDIA and Red Hat</p>
      </header>

      <ConnectionSettingsPanel
        settings={settings}
        open={connectionOpen}
        onToggle={() => setConnectionOpen((v) => !v)}
        onChange={updateSettings}
      />

      <Chat
        visible={chatVisible}
        interactive={chatInteractive}
        messages={chat.displayMessages}
        input={chatInput}
        sending={chat.sending}
        onInputChange={setChatInput}
        onSend={handleSendChat}
        onClear={() => {
          chat.clearChat();
          setChatInput("");
          if (pipeline.isComplete) {
            chat.unlockChat();
          } else if (pipeline.isRunning) {
            chat.setWelcomeMessage(CHAT_RUNNING);
          } else {
            chat.setWelcomeMessage(CHAT_WELCOME_PENDING);
          }
        }}
      />

      <PipelineOutputs
        outputs={pipeline.outputs}
        open={outputsOpen}
        visible={pipeline.hasStarted}
        onToggle={() => setOutputsOpen((v) => !v)}
      />

      <PipelineSetup
        open={setupOpen}
        onToggle={() => setSetupOpen((v) => !v)}
        form={form}
        onChange={(patch) => setForm((prev) => ({ ...prev, ...patch }))}
        onRun={handleRunPipeline}
        logLines={pipeline.logLines}
        running={pipeline.isRunning}
      />
    </div>
  );
}
