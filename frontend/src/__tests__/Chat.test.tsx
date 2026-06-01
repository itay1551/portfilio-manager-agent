import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Chat } from "../components/Chat";

describe("Chat", () => {
  it("does not render when not visible", () => {
    render(
      <Chat
        visible={false}
        interactive={false}
        messages={[]}
        input=""
        sending={false}
        onInputChange={() => {}}
        onSend={() => {}}
        onClear={() => {}}
      />,
    );

    expect(screen.queryByText(/Discuss your portfolio/)).not.toBeInTheDocument();
  });

  it("disables input when not interactive", () => {
    render(
      <Chat
        visible
        interactive={false}
        messages={[{ role: "assistant", content: "Welcome" }]}
        input=""
        sending={false}
        onInputChange={() => {}}
        onSend={() => {}}
        onClear={() => {}}
      />,
    );

    expect(screen.getByPlaceholderText(/Enter to send/)).toBeDisabled();
  });

  it("sends on button click", async () => {
    const user = userEvent.setup();
    const onSend = vi.fn();

    render(
      <Chat
        visible
        interactive
        messages={[]}
        input="Hello"
        sending={false}
        onInputChange={() => {}}
        onSend={onSend}
        onClear={() => {}}
      />,
    );

    await user.click(screen.getByRole("button", { name: /send/i }));
    expect(onSend).toHaveBeenCalledOnce();
  });
});
