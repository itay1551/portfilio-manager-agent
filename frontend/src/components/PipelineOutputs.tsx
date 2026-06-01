import type { OutputMarkdown } from "../utils/formatters";
import { CollapsibleSection } from "./CollapsibleSection";
import { Markdown } from "./Markdown";

interface PipelineOutputsProps {
  outputs: OutputMarkdown;
  open: boolean;
  visible: boolean;
  onToggle: () => void;
}

function OutputBlock({ title, content }: { title: string; content: string }) {
  return (
    <div className="output-block">
      <h4>{title}</h4>
      <div className="markdown-body">
        <Markdown>{content}</Markdown>
      </div>
    </div>
  );
}

export function PipelineOutputs({
  outputs,
  open,
  visible,
  onToggle,
}: PipelineOutputsProps) {
  return (
    <CollapsibleSection
      title="Portfolio outputs"
      open={open}
      visible={visible}
      onToggle={onToggle}
    >
      <OutputBlock title="Prohibited tickers" content={outputs.prohibited} />
      <OutputBlock title="Portfolio" content={outputs.portfolio} />
      <OutputBlock title="Value at Risk" content={outputs.var} />
      <OutputBlock title="Draft client email" content={outputs.email} />
    </CollapsibleSection>
  );
}
