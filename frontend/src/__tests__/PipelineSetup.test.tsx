import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { PipelineSetup, defaultPipelineForm } from "../components/PipelineSetup";

describe("PipelineSetup", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders form defaults and run button", () => {
    render(
      <PipelineSetup
        open
        onToggle={() => {}}
        form={defaultPipelineForm()}
        onChange={() => {}}
        onRun={() => {}}
        logLines={[]}
        running={false}
      />,
    );

    expect(screen.getByRole("button", { name: /run pipeline/i })).toBeEnabled();
    expect(screen.getByDisplayValue("1000000")).toBeInTheDocument();
  });

  it("calls onRun when clicked", async () => {
    const user = userEvent.setup();
    const onRun = vi.fn();

    render(
      <PipelineSetup
        open
        onToggle={() => {}}
        form={defaultPipelineForm()}
        onChange={() => {}}
        onRun={onRun}
        logLines={[]}
        running={false}
      />,
    );

    await user.click(screen.getByRole("button", { name: /run pipeline/i }));
    expect(onRun).toHaveBeenCalledOnce();
  });

  it("shows progress log lines", async () => {
    render(
      <PipelineSetup
        open
        onToggle={() => {}}
        form={defaultPipelineForm()}
        onChange={() => {}}
        onRun={() => {}}
        logLines={["Parsing investment guidelines..."]}
        running
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/Parsing investment guidelines/)).toBeInTheDocument();
    });
  });
});
