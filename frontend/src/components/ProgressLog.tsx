import { Markdown } from "./Markdown";

interface ProgressLogProps {
  lines: string[];
}

export function ProgressLog({ lines }: ProgressLogProps) {
  const content = lines.length ? lines.join("\n") : "*Ready.*";

  return (
    <div className="progress-log markdown-body">
      <Markdown>{content}</Markdown>
    </div>
  );
}
