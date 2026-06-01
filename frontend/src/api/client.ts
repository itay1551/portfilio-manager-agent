import type {
  ChatMessage,
  ChatResponse,
  ConnectionSettings,
  EmailResponse,
  GuidelinesResponse,
  LlmConfig,
  PipelineContext,
  PortfolioResponse,
  VarResponse,
} from "./types";

export function orchestratorBase(orchestratorUrl: string): string {
  const u = (orchestratorUrl || "").trim().replace(/\/+$/, "");
  if (u.endsWith("/chat")) {
    return u.slice(0, -"/chat".length);
  }
  return u || "/api";
}

export function llmConfig(
  llmUrl: string,
  apiKey: string,
  model: string,
): LlmConfig {
  return {
    llmUrl: (llmUrl || "").trim(),
    apiKey: (apiKey || "").trim(),
    model: (model || "").trim(),
  };
}

export function extractReply(obj: ChatResponse | null | undefined): string {
  if (!obj) {
    return "";
  }
  if (typeof obj.content === "string") {
    return obj.content;
  }
  return "";
}

async function postJson<T>(
  url: string,
  payload: unknown,
  timeoutMs = 300_000,
): Promise<T> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });

    const data = (await res.json().catch(() => ({}))) as T & { error?: string };

    if (!res.ok) {
      const err =
        typeof data.error === "string"
          ? data.error
          : `HTTP ${res.status}`;
      throw new Error(err);
    }

    return data;
  } finally {
    clearTimeout(timer);
  }
}

export async function postGuidelines(
  baseUrl: string,
  urlInvestmentGuidelines: string,
): Promise<GuidelinesResponse> {
  return postJson(`${baseUrl}/pipeline/guidelines`, {
    url_investment_guidelines: urlInvestmentGuidelines,
  });
}

export async function postPortfolio(
  baseUrl: string,
  portfolioValue: number,
  qtySymbols: number,
  prohibitedTickers: string[],
): Promise<PortfolioResponse> {
  return postJson(`${baseUrl}/pipeline/portfolio`, {
    portfolio_value: portfolioValue,
    qty_symbols: qtySymbols,
    prohibited_tickers: prohibitedTickers,
  });
}

export async function postVar(
  baseUrl: string,
  portfolio: PortfolioResponse["portfolio"],
): Promise<VarResponse> {
  return postJson(`${baseUrl}/pipeline/var`, { portfolio });
}

export async function postEmail(
  baseUrl: string,
  portfolio: PortfolioResponse["portfolio"],
  valueAtRisk: number,
  config: LlmConfig,
): Promise<EmailResponse> {
  return postJson(
    `${baseUrl}/pipeline/email`,
    { portfolio, valueAtRisk, config },
    180_000,
  );
}

export async function postChat(
  settings: ConnectionSettings,
  message: string,
  history: ChatMessage[],
  context: PipelineContext,
): Promise<{ reply: string; context?: PipelineContext }> {
  const base = orchestratorBase(settings.orchestratorUrl);
  const config = llmConfig(settings.llmUrl, settings.apiKey, settings.model);

  const data = await postJson<ChatResponse>(`${base}/chat`, {
    message,
    history,
    context,
    config,
  });

  return {
    reply: extractReply(data),
    context: data.context,
  };
}

export function validatePipelineInputs(
  settings: ConnectionSettings,
  portfolioValue: number,
  qtySymbols: number,
  maxVar: number,
): string | null {
  const config = llmConfig(settings.llmUrl, settings.apiKey, settings.model);
  if (!config.llmUrl || !config.apiKey || !config.model) {
    return "Set LLM URL, API key, and model in Connection settings.";
  }
  if (qtySymbols < 1 || qtySymbols > 10) {
    return "number of symbols must be between 1 and 10";
  }
  if (portfolioValue <= 0) {
    return "portfolio value must be positive";
  }
  if (maxVar <= 0) {
    return "max VaR must be positive";
  }
  return null;
}
