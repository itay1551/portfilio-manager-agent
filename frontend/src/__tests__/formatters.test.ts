import { describe, expect, it } from "vitest";
import {
  formatProhibited,
  formatVar,
  renderOutputsFromContext,
} from "../utils/formatters";

describe("formatters", () => {
  it("formatProhibited handles empty list", () => {
    expect(formatProhibited([])).toContain("No prohibited");
  });

  it("formatProhibited joins tickers", () => {
    expect(formatProhibited(["A", "B"])).toBe("A, B");
  });

  it("formatVar formats currency", () => {
    expect(formatVar(35000)).toContain("35,000.00");
  });

  it("renderOutputsFromContext returns placeholders when null", () => {
    const out = renderOutputsFromContext(null);
    expect(out.portfolio).toContain("No portfolio");
  });
});
