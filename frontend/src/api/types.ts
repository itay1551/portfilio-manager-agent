export const DEFAULT_GUIDELINES_URL =
  "https://d15bgksgja6rr0.cloudfront.net/Neurosymbolic-Inc-Investment-Guidelines.pdf";

export const MAX_PIPELINE_ATTEMPTS = 10;

export const CHAT_WELCOME_PENDING =
  "Run **Portfolio setup** below, then click **Run pipeline**. " +
  "Chat will unlock when the pipeline finishes.";

export const CHAT_RUNNING =
  "Pipeline is running... Please wait. You can chat when it completes.";

export const CHAT_WELCOME_READY =
  "Your portfolio is ready. Ask about prohibited symbols, holdings, risk, " +
  "or request changes (e.g. swap a symbol or recalculate VaR).";

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  role: ChatRole;
  content: string;
}

export interface PortfolioPosition {
  symbol: string;
  quantity: number;
  last_price: number;
}

export interface PipelineInputs {
  url_investment_guidelines: string;
  portfolio_value: number;
  qty_symbols: number;
  max_var: number;
}

export interface PipelineContext {
  prohibited_tickers: string[];
  guidelines_raw?: unknown;
  portfolio: PortfolioPosition[];
  valueAtRisk: number;
  confidence: number;
  draft_email: string;
  inputs: PipelineInputs;
}

export interface LlmConfig {
  llmUrl: string;
  apiKey: string;
  model: string;
}

export interface ConnectionSettings {
  orchestratorUrl: string;
  llmUrl: string;
  apiKey: string;
  model: string;
}

export interface PipelineFormValues {
  urlInvestmentGuidelines: string;
  portfolioValue: number;
  qtySymbols: number;
  maxVar: number;
}

export type PipelineStatus = "idle" | "running" | "complete" | "error";

export interface GuidelinesResponse {
  prohibited_tickers: string[];
  guidelines_raw?: unknown;
}

export interface PortfolioResponse {
  portfolio: PortfolioPosition[];
}

export interface VarResponse {
  valueAtRisk: number;
}

export interface EmailResponse {
  draft_email: string;
}

export interface ChatResponse {
  content?: string;
  reply?: string;
  message?: string;
  context?: PipelineContext;
  error?: string;
}
