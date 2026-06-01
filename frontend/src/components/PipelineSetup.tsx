import { DEFAULT_GUIDELINES_URL } from "../api/types";
import type { PipelineFormValues } from "../api/types";
import { CollapsibleSection } from "./CollapsibleSection";
import { ProgressLog } from "./ProgressLog";

interface PipelineSetupProps {
  open: boolean;
  onToggle: () => void;
  form: PipelineFormValues;
  onChange: (patch: Partial<PipelineFormValues>) => void;
  onRun: () => void;
  logLines: string[];
  running: boolean;
}

export function PipelineSetup({
  open,
  onToggle,
  form,
  onChange,
  onRun,
  logLines,
  running,
}: PipelineSetupProps) {
  return (
    <CollapsibleSection title="Portfolio setup" open={open} onToggle={onToggle}>
      <p className="section-desc">
        Run the deterministic pipeline: guidelines → portfolio → VaR gate → draft
        email.
      </p>
      <label className="full-width">
        Investment guidelines URL
        <input
          type="text"
          value={form.urlInvestmentGuidelines}
          onChange={(e) =>
            onChange({ urlInvestmentGuidelines: e.target.value })
          }
        />
      </label>
      <div className="form-row three-col">
        <label>
          Portfolio value (USD)
          <input
            type="number"
            min={1}
            step={1}
            value={form.portfolioValue}
            onChange={(e) =>
              onChange({ portfolioValue: Number(e.target.value) || 0 })
            }
          />
        </label>
        <label>
          Number of symbols
          <input
            type="number"
            min={1}
            max={10}
            step={1}
            value={form.qtySymbols}
            onChange={(e) =>
              onChange({ qtySymbols: Number(e.target.value) || 0 })
            }
          />
        </label>
        <label>
          Max 1-day VaR at 99% (USD)
          <input
            type="number"
            min={1}
            step={1}
            value={form.maxVar}
            onChange={(e) => onChange({ maxVar: Number(e.target.value) || 0 })}
          />
        </label>
      </div>
      <button
        type="button"
        className="btn btn-primary"
        onClick={onRun}
        disabled={running}
      >
        {running ? "Running…" : "Run pipeline"}
      </button>
      <ProgressLog lines={logLines} />
    </CollapsibleSection>
  );
}

export function defaultPipelineForm(): PipelineFormValues {
  return {
    urlInvestmentGuidelines: DEFAULT_GUIDELINES_URL,
    portfolioValue: 1_000_000,
    qtySymbols: 5,
    maxVar: 35_000,
  };
}
