import type { ConnectionSettings } from "../api/types";
import { CollapsibleSection } from "./CollapsibleSection";

interface ConnectionSettingsPanelProps {
  settings: ConnectionSettings;
  open: boolean;
  onToggle: () => void;
  onChange: (patch: Partial<ConnectionSettings>) => void;
}

export function ConnectionSettingsPanel({
  settings,
  open,
  onToggle,
  onChange,
}: ConnectionSettingsPanelProps) {
  return (
    <CollapsibleSection title="Connection settings" open={open} onToggle={onToggle}>
      <div className="form-row">
        <label>
          Orchestrator URL
          <input
            type="text"
            value={settings.orchestratorUrl}
            placeholder="http://localhost:5000/chat"
            onChange={(e) => onChange({ orchestratorUrl: e.target.value })}
          />
        </label>
        <label>
          LLM URL
          <input
            type="text"
            value={settings.llmUrl}
            placeholder="http://localhost:8000/v1"
            onChange={(e) => onChange({ llmUrl: e.target.value })}
          />
        </label>
      </div>
      <div className="form-row">
        <label>
          API Key
          <input
            type="password"
            value={settings.apiKey}
            placeholder="sk-..."
            onChange={(e) => onChange({ apiKey: e.target.value })}
          />
        </label>
        <label>
          Model
          <input
            type="text"
            value={settings.model}
            placeholder="llama-3-3-70b-instruct-w8a8"
            onChange={(e) => onChange({ model: e.target.value })}
          />
        </label>
      </div>
    </CollapsibleSection>
  );
}
