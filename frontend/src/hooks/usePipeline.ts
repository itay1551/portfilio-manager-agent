import { useCallback, useRef, useState } from "react";
import {
  orchestratorBase,
  llmConfig,
  postEmail,
  postGuidelines,
  postPortfolio,
  postVar,
  validatePipelineInputs,
} from "../api/client";
import type {
  ConnectionSettings,
  PipelineContext,
  PipelineFormValues,
  PipelineStatus,
} from "../api/types";
import { MAX_PIPELINE_ATTEMPTS } from "../api/types";
import type { OutputMarkdown } from "../utils/formatters";
import {
  formatPortfolioTable,
  formatProhibited,
  formatVar,
  renderOutputsFromContext,
} from "../utils/formatters";

export interface PipelineState {
  status: PipelineStatus;
  logLines: string[];
  context: PipelineContext | null;
  outputs: OutputMarkdown;
  error: string | null;
}

const INITIAL_OUTPUTS: OutputMarkdown = {
  prohibited: "*No results yet.*",
  portfolio: "*No portfolio yet.*",
  var: "*VaR not calculated.*",
  email: "*No draft email yet.*",
};

function initialState(): PipelineState {
  return {
    status: "idle",
    logLines: [],
    context: null,
    outputs: INITIAL_OUTPUTS,
    error: null,
  };
}

function runningOutputs(
  prohibitedTickers: string[],
  portfolioList: PipelineContext["portfolio"],
  valueAtRisk: number,
  patch: Partial<OutputMarkdown>,
): OutputMarkdown {
  return {
    prohibited:
      patch.prohibited ?? formatProhibited(prohibitedTickers),
    portfolio:
      patch.portfolio ??
      (portfolioList.length
        ? formatPortfolioTable(portfolioList)
        : "*No portfolio yet.*"),
    var:
      patch.var ??
      (valueAtRisk > 0 ? formatVar(valueAtRisk) : "*VaR not calculated.*"),
    email: patch.email ?? "*No draft email yet.*",
  };
}

export function usePipeline() {
  const [state, setState] = useState<PipelineState>(initialState);
  const runningRef = useRef(false);

  const runPipeline = useCallback(
    async (settings: ConnectionSettings, form: PipelineFormValues) => {
      if (runningRef.current) {
        return;
      }
      runningRef.current = true;

      const logLines: string[] = [];
      const base = orchestratorBase(settings.orchestratorUrl);
      let prohibitedTickers: string[] = [];
      let guidelinesRaw: unknown;
      let portfolioList: PipelineContext["portfolio"] = [];
      let valueAtRisk = 0;

      const setRunning = (patch: Partial<OutputMarkdown>) => {
        setState({
          status: "running",
          logLines: [...logLines],
          context: null,
          outputs: runningOutputs(
            prohibitedTickers,
            portfolioList,
            valueAtRisk,
            patch,
          ),
          error: null,
        });
      };

      const fail = (patch: Partial<OutputMarkdown>) => {
        runningRef.current = false;
        setState({
          status: "error",
          logLines: [...logLines],
          context: null,
          outputs: runningOutputs(
            prohibitedTickers,
            portfolioList,
            valueAtRisk,
            patch,
          ),
          error: logLines.at(-1) ?? "Pipeline failed",
        });
      };

      const validationError = validatePipelineInputs(
        settings,
        form.portfolioValue,
        form.qtySymbols,
        form.maxVar,
      );
      if (validationError) {
        logLines.push(`**Error:** ${validationError}`);
        runningRef.current = false;
        setState({
          status: "error",
          logLines: [...logLines],
          context: null,
          outputs: INITIAL_OUTPUTS,
          error: validationError,
        });
        return;
      }

      setRunning({
        prohibited: "...",
        portfolio: "...",
        var: "...",
        email: "...",
      });

      logLines.push("Parsing investment guidelines...");
      try {
        const g = await postGuidelines(base, form.urlInvestmentGuidelines);
        prohibitedTickers = g.prohibited_tickers ?? [];
        guidelinesRaw = g.guidelines_raw;
        logLines.push(
          `Done: Guidelines parsed - ${prohibitedTickers.length} prohibited ticker(s).`,
        );
      } catch (e) {
        logLines.push(`**Error:** ${e instanceof Error ? e.message : String(e)}`);
        fail({
          prohibited: "*Failed.*",
          portfolio: "-",
          var: "-",
          email: "-",
        });
        return;
      }

      setRunning({ portfolio: "...", var: "...", email: "..." });

      let attempts = 0;
      while (attempts < MAX_PIPELINE_ATTEMPTS) {
        attempts += 1;
        logLines.push(`Building portfolio (attempt ${attempts})...`);
        setRunning({ portfolio: "*Building...*", var: "...", email: "..." });

        try {
          const p = await postPortfolio(
            base,
            form.portfolioValue,
            form.qtySymbols,
            prohibitedTickers,
          );
          portfolioList = p.portfolio ?? [];
          logLines.push(
            `Done: Portfolio built - ${portfolioList.length} position(s).`,
          );
        } catch (e) {
          logLines.push(`**Error:** ${e instanceof Error ? e.message : String(e)}`);
          fail({ portfolio: "*Failed.*", var: "-", email: "-" });
          return;
        }

        logLines.push("Calculating VaR...");
        setRunning({ var: "*Calculating...*", email: "..." });

        try {
          const v = await postVar(base, portfolioList);
          valueAtRisk = Number(v.valueAtRisk ?? 0);
          logLines.push(
            `Done: VaR calculated - $${valueAtRisk.toLocaleString("en-US", { minimumFractionDigits: 2 })}.`,
          );
        } catch (e) {
          logLines.push(`**Error:** ${e instanceof Error ? e.message : String(e)}`);
          fail({ var: "*Failed.*", email: "-" });
          return;
        }

        if (valueAtRisk <= form.maxVar) {
          logLines.push("Done: VaR within limit.");
          break;
        }

        logLines.push(
          `VaR $${valueAtRisk.toLocaleString("en-US", { minimumFractionDigits: 2 })} exceeds max $${form.maxVar.toLocaleString("en-US", { minimumFractionDigits: 2 })} - retrying...`,
        );
        setRunning({ email: "..." });
      }

      if (valueAtRisk > form.maxVar) {
        logLines.push(
          `**Error:** Could not meet max VaR after ${MAX_PIPELINE_ATTEMPTS} attempts.`,
        );
        fail({ email: "-" });
        return;
      }

      logLines.push("Generating draft client email...");
      setRunning({ email: "*Generating email...*" });

      const config = llmConfig(settings.llmUrl, settings.apiKey, settings.model);
      let draftEmail = "";

      try {
        const e = await postEmail(base, portfolioList, valueAtRisk, config);
        draftEmail = e.draft_email ?? "";
        logLines.push("Done: Draft email generated.");
      } catch (e) {
        logLines.push(
          `**Error generating email:** ${e instanceof Error ? e.message : String(e)}`,
        );
        fail({ email: "*Email generation failed.*" });
        return;
      }

      const context: PipelineContext = {
        prohibited_tickers: prohibitedTickers,
        guidelines_raw: guidelinesRaw,
        portfolio: portfolioList,
        valueAtRisk,
        confidence: 0.99,
        draft_email: draftEmail,
        inputs: {
          url_investment_guidelines: form.urlInvestmentGuidelines,
          portfolio_value: form.portfolioValue,
          qty_symbols: form.qtySymbols,
          max_var: form.maxVar,
        },
      };

      logLines.push("**Pipeline complete.** You can use the chat above.");
      runningRef.current = false;
      setState({
        status: "complete",
        logLines: [...logLines],
        context,
        outputs: renderOutputsFromContext(context),
        error: null,
      });
    },
    [],
  );

  const resetPipeline = useCallback(() => {
    runningRef.current = false;
    setState(initialState());
  }, []);

  const updateOutputsFromContext = useCallback((ctx: PipelineContext) => {
    setState((prev) => ({
      ...prev,
      context: ctx,
      outputs: renderOutputsFromContext(ctx),
    }));
  }, []);

  return {
    ...state,
    runPipeline,
    resetPipeline,
    updateOutputsFromContext,
    isRunning: state.status === "running",
    hasStarted: state.status !== "idle",
    isComplete: state.status === "complete",
  };
}
