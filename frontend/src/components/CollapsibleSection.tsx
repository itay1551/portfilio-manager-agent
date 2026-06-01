import type { ReactNode } from "react";

interface CollapsibleSectionProps {
  title: string;
  open: boolean;
  visible?: boolean;
  onToggle: () => void;
  children: ReactNode;
  id?: string;
}

export function CollapsibleSection({
  title,
  open,
  visible = true,
  onToggle,
  children,
  id,
}: CollapsibleSectionProps) {
  if (!visible) {
    return null;
  }

  return (
    <section className="accordion" id={id}>
      <button
        type="button"
        className="accordion-header"
        onClick={onToggle}
        aria-expanded={open}
      >
        <span>{title}</span>
        <span className="accordion-chevron" aria-hidden>
          {open ? "▾" : "▸"}
        </span>
      </button>
      {open && <div className="accordion-body">{children}</div>}
    </section>
  );
}
