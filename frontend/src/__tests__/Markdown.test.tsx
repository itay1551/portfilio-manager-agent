import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Markdown } from "../components/Markdown";
import { formatPortfolioTable } from "../utils/formatters";

describe("Markdown", () => {
  it("renders portfolio table as HTML table", () => {
    const table = formatPortfolioTable([
      { symbol: "AAPL", quantity: 100, last_price: 150.5 },
      { symbol: "MSFT", quantity: 50, last_price: 420 },
    ]);

    render(<Markdown>{table}</Markdown>);

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("MSFT")).toBeInTheDocument();
  });
});
