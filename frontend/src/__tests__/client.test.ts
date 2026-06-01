import { describe, expect, it, beforeAll, afterEach, afterAll } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import {
  extractReply,
  orchestratorBase,
  postChat,
  postGuidelines,
  postPortfolio,
  postVar,
  validatePipelineInputs,
} from "../api/client";

const server = setupServer();

beforeAll(() => server.listen());
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("orchestratorBase", () => {
  it("strips /chat suffix", () => {
    expect(orchestratorBase("http://localhost:5000/chat")).toBe(
      "http://localhost:5000",
    );
  });

  it("returns default when empty", () => {
    expect(orchestratorBase("")).toBe("/api");
  });
});

describe("extractReply", () => {
  it("reads content field", () => {
    expect(extractReply({ content: "hello" })).toBe("hello");
  });

  it("returns empty when content missing", () => {
    expect(extractReply({ reply: "hi" })).toBe("");
  });
});

describe("validatePipelineInputs", () => {
  const settings = {
    orchestratorUrl: "http://localhost:5000/chat",
    llmUrl: "http://llm/v1",
    apiKey: "key",
    model: "model",
  };

  it("returns null for valid inputs", () => {
    expect(validatePipelineInputs(settings, 1_000_000, 5, 35_000)).toBeNull();
  });

  it("requires LLM config", () => {
    expect(
      validatePipelineInputs({ ...settings, apiKey: "" }, 1_000_000, 5, 35_000),
    ).toMatch(/Connection settings/);
  });
});

describe("API client", () => {
  it("postGuidelines calls correct endpoint", async () => {
    server.use(
      http.post("http://localhost:5000/pipeline/guidelines", async () =>
        HttpResponse.json({ prohibited_tickers: ["X"], guidelines_raw: {} }),
      ),
    );

    const result = await postGuidelines(
      "http://localhost:5000",
      "https://example.com/g.pdf",
    );
    expect(result.prohibited_tickers).toEqual(["X"]);
  });

  it("postPortfolio returns portfolio", async () => {
    server.use(
      http.post("http://localhost:5000/pipeline/portfolio", async () =>
        HttpResponse.json({
          portfolio: [{ symbol: "AAPL", quantity: 10, last_price: 100 }],
        }),
      ),
    );

    const result = await postPortfolio(
      "http://localhost:5000",
      1_000_000,
      5,
      [],
    );
    expect(result.portfolio).toHaveLength(1);
  });

  it("postVar returns valueAtRisk", async () => {
    server.use(
      http.post("http://localhost:5000/pipeline/var", async () =>
        HttpResponse.json({ valueAtRisk: 12000 }),
      ),
    );

    const result = await postVar("http://localhost:5000", [
      { symbol: "AAPL", quantity: 10, last_price: 100 },
    ]);
    expect(result.valueAtRisk).toBe(12000);
  });

  it("postChat returns reply and context", async () => {
    server.use(
      http.post("http://localhost:5000/chat", async () =>
        HttpResponse.json({
          content: "Updated portfolio",
          context: {
            prohibited_tickers: [],
            portfolio: [{ symbol: "MSFT", quantity: 5, last_price: 200 }],
            valueAtRisk: 8000,
            confidence: 0.99,
            draft_email: "Dear client",
            inputs: {
              url_investment_guidelines: "u",
              portfolio_value: 1_000_000,
              qty_symbols: 5,
              max_var: 35_000,
            },
          },
        }),
      ),
    );

    const result = await postChat(
      {
        orchestratorUrl: "http://localhost:5000/chat",
        llmUrl: "http://llm/v1",
        apiKey: "key",
        model: "model",
      },
      "hello",
      [],
      {
        prohibited_tickers: [],
        portfolio: [],
        valueAtRisk: 0,
        confidence: 0.99,
        draft_email: "",
        inputs: {
          url_investment_guidelines: "u",
          portfolio_value: 1_000_000,
          qty_symbols: 5,
          max_var: 35_000,
        },
      },
    );

    expect(result.reply).toBe("Updated portfolio");
    expect(result.context?.valueAtRisk).toBe(8000);
  });

  it("throws on HTTP error", async () => {
    server.use(
      http.post("http://localhost:5000/pipeline/guidelines", async () =>
        HttpResponse.json({ error: "bad url" }, { status: 500 }),
      ),
    );

    await expect(
      postGuidelines("http://localhost:5000", "bad"),
    ).rejects.toThrow("bad url");
  });
});
