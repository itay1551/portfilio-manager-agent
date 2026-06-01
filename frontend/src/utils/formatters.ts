import type { PipelineContext } from "../api/types";

export function formatProhibited(tickers: string[] | null | undefined): string {
  if (!tickers?.length) {
    return "*No prohibited tickers identified.*";
  }
  return tickers.join(", ");
}

export function formatPortfolioTable(
  portfolio: PipelineContext["portfolio"] | null | undefined,
): string {
  if (!portfolio?.length) {
    return "*No portfolio generated yet.*";
  }
  const lines = ["| Symbol | Shares | Last price |", "| --- | ---: | ---: |"];
  for (const row of portfolio) {
    lines.push(`| ${row.symbol} | ${row.quantity} | $${row.last_price} |`);
  }
  return lines.join("\n");
}

export function formatVar(value: number | null | undefined): string {
  if (value == null) {
    return "*VaR not calculated.*";
  }
  return `**$${value.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}** (1-day, 99% confidence)`;
}

export function formatEmail(email: string | null | undefined): string {
  if (!email) {
    return "*Draft email will appear after the pipeline completes.*";
  }
  return email;
}

export interface OutputMarkdown {
  prohibited: string;
  portfolio: string;
  var: string;
  email: string;
}

export function renderOutputsFromContext(
  ctx: PipelineContext | null | undefined,
): OutputMarkdown {
  if (!ctx) {
    return {
      prohibited: "*Run the pipeline to see results.*",
      portfolio: "*No portfolio yet.*",
      var: "*VaR not calculated.*",
      email: "*No draft email yet.*",
    };
  }
  return {
    prohibited: formatProhibited(ctx.prohibited_tickers),
    portfolio: formatPortfolioTable(ctx.portfolio),
    var: formatVar(ctx.valueAtRisk),
    email: formatEmail(ctx.draft_email),
  };
}
