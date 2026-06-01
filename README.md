# Neurosymbolic AI

Language Models (LMs) offer powerful reasoning and automation capabilities.  This demo presents a practical architectural pattern for agentic AI: a language model working in conjunction with a set of tools (aka agents) in order to solve a real-world financial services use case.

# Use Case

Imagine Mary, a portfolio manager for a leading asset management firm. Her new client, a pension fund, wants a portfolio that meets their investment guidelines, meets their risk tolerance, avoids conflicts, and, most importantly, meets their investment targets. Now imagine this multiplied tens and hundreds of times. 

The intuitive answer to this challenge is … AI to the rescue. For this to be true, it is necessary to combine the power of LMs and neural networks, providing natural language, reasoning and prediction capabilities, with methods based on logical reasoning and knowledge, such as quantitative analysis and rules-based systems. 

This demo will focus will be on a realistic example: an AI-supported portfolio manager that combines neural networks with symbolic AI into a single, coherent, multi-agent system.

# Architecture

* UI
* Orchestrator
* Investment Guidelines agent
* Portfolio Generator agent
* Value at Risk (VaR) calculator agent
* [Red Hat OpenShift](https://www.redhat.com/en/technologies/cloud-computing/openshift) (or [Podman](https://podman-desktop.io/)) to host the orchestrator, agents and language model
* Language model (LM)

# Project prequisites

* A container runtime environment.  For development, a good option is [Podman Desktop](https://podman-desktop.io/).  For production workloads, [Red Hat OpenShift](https://www.redhat.com/en/technologies/cloud-computing/openshift) faciliates running AI inference on GPUs and CPUs, AI training, tools and agentic workflows in a hybrid cloud environment.
* A language model (LM) that is available via an OpenAI-compliant API.  This demo has been tested with a [quantized Llama 3.3 (70B) model](https://huggingface.co/RedHatAI/Llama-3.3-70B-Instruct-quantized.w8a8).

# Configuration

The React UI can pre-fill connection settings from a `.env` file in the project root (values are baked in at container build time via `VITE_*` build args).

```bash
cp .env.example .env
# Edit .env with your LLM endpoint, API key, and model
```

| Variable | UI field | Description |
| --- | --- | --- |
| `OPENAI_API_ENDPOINT` | LLM URL | OpenAI-compatible base URL (e.g. `https://host/v1`) |
| `OPENAI_API_TOKEN` | API Key | API key for the LLM endpoint |
| `OPENAI_MODEL` | Model | Model name string |
| `ORCHESTRATOR_URL` | Orchestrator URL | Optional. Baked as `VITE_ORCHESTRATOR_URL` at UI build. Defaults to `http://localhost:5000/chat` locally, or `http://orchestrator:5000/chat` in Compose |

Alternative variable names are also supported: `LLM_URL`, `OPENAI_API_BASE`, `OPENAI_API_KEY`, `API_KEY`, `LLM_MODEL`, and `MODEL`.

Do not commit `.env` — it is listed in `.gitignore`. Use `.env.example` as the template.

# Build the solution (optional)

The containers needed to run the demo are available online.  However, if you would prefer to build from source:

```
git clone https://github.com/aric-rosenbaum/neurosymbolic-ai.git
cd neurosymbolic-ai
``` 

Create a virtual environment and activate it:
```
python3 -m venv .env
source .env/bin/activate
```

In the build directory, grant execute permssions to the build and deploy scripts:
```
chmod +x build/build_script.sh
chmod +x build/deploy_podman.sh
```

To build the application:
```
./build/build_script.sh
```

# Deployment: Podman Compose

From the project root, configure the UI (optional) and start all services:

```bash
cp .env.example .env   # optional — pre-fills LLM settings in the UI
make deploy-local
# or: podman compose -f deploy/local/compose.yml up -d --build
```

| Service | URL |
| --- | --- |
| UI | http://localhost:8080 |
| Orchestrator | http://localhost:5000 |

Open the UI at http://localhost:8080, expand **Connection settings** to set the LLM endpoint, API key, and model, then use the two-phase workflow below.

# Two-phase UI (agents-on-a-leash pipeline)

The UI mirrors the deterministic [agents-on-a-leash](https://github.com/aric-rosenbaum/agents-on-a-leash) flow without Fluxnova BPM.

## Tab 1 — Build portfolio

1. Set **Investment guidelines URL**, **Portfolio value**, **Number of symbols**, and **Max VaR**.
2. Click **Run pipeline**. A progress log shows each step:
   - Parse guidelines (prohibited tickers)
   - Build portfolio (retries if VaR exceeds max)
   - Calculate VaR
   - Generate draft client email (LLM)
3. Results appear in the **Results** accordion. On success, **Discuss portfolio** unlocks.

## Tab 2 — Discuss portfolio

- Review live **Portfolio outputs** (prohibited tickers, holdings, VaR, draft email).
- Chat about the portfolio; the orchestrator can call **portfolio** and **VaR** tools to mutate holdings and risk.
- Outputs refresh after each response when the context changes.
- Ask explicitly to **regenerate the draft email** if needed (not automatic on portfolio changes).

# Orchestrator API

| Endpoint | Method | Purpose |
| --- | --- | --- |
| `/pipeline` | POST | Run full pipeline in one request |
| `/pipeline/guidelines` | POST | Parse investment guidelines PDF URL |
| `/pipeline/portfolio` | POST | Build equities portfolio |
| `/pipeline/var` | POST | Calculate value at risk |
| `/pipeline/email` | POST | Generate draft client email |
| `/chat` | POST | Phase 2 chat with `context` + `history`; legacy agentic chat without `context` |

### `POST /pipeline` body

```json
{
  "url_investment_guidelines": "https://…/guidelines.pdf",
  "portfolio_value": 1000000,
  "qty_symbols": 5,
  "max_var": 35000,
  "config": {
    "llmUrl": "https://your-llm/v1",
    "apiKey": "sk-…",
    "model": "your-model"
  }
}
```

### `POST /chat` with portfolio context (Phase 2)

```json
{
  "message": "What is the VaR in plain language?",
  "history": [{"role": "user", "content": "…"}, {"role": "assistant", "content": "…"}],
  "context": { "prohibited_tickers": [], "portfolio": [], "valueAtRisk": 0, "draft_email": "…" },
  "config": { "llmUrl": "…", "apiKey": "…", "model": "…" }
}
```

Response includes `content` and updated `context`.

# Deployment: Podman (individual containers)

To faciliate communication between the Orchestrator and the agents, first create a Podman network:
```
podman network create neurosymbolic-ai
```

Now, launch the containers:
```
podman run -d -p 5000:5000 --name orchestrator --network neurosymbolic-ai quay.io/aric-rosenbaum/neurosymbolic-ai/orchestrator:latest
podman run -d -p 7001:7001 --name neurosymbolic-ai-risk --network neurosymbolic-ai quay.io/aric-rosenbaum/neurosymbolic-ai/neurosymbolic-ai-risk:latest
podman run -d -p 7002:7002 --name neurosymbolic-ai-portfolio --network neurosymbolic-ai quay.io/aric-rosenbaum/neurosymbolic-ai/neurosymbolic-ai-portfolio:latest
podman run -d -p 7003:7003 --name neurosymbolic-ai-guidelines --network neurosymbolic-ai quay.io/aric-rosenbaum/neurosymbolic-ai/neurosymbolic-ai-guidelines:latest
```

# Deployment: OpenShift (Helm)

The `deploy/helm/` directory is a Helm chart. Install with defaults (always-on agents):

```bash
make deploy-cluster
# or: helm upgrade --install neurosymbolic-ai deploy/helm -n neurosymbolic-ai --create-namespace
```

To deploy with serverless (Knative) agents instead:

```bash
helm upgrade --install neurosymbolic-ai deploy/helm \
  -n neurosymbolic-ai --create-namespace \
  --set serverless.enabled=true
```

Override the image registry or tag:

```bash
helm upgrade --install neurosymbolic-ai deploy/helm \
  -n neurosymbolic-ai --create-namespace \
  --set image.registry=ghcr.io/your-org \
  --set image.tag=v1.2.3
```

See `deploy/helm/values.yaml` for all configurable values.

### Grant access to private container images (skip if images are public)
If the container images are private, you need to create a secret and grant access to the project.  Here's an example of how to do this with GHCR:
```
# Create secret
oc create secret docker-registry ghcr-creds \
  --docker-server=ghcr.io \
  --docker-username=<github-username> \
  --docker-password=<github-token> \
  --docker-email=<github-email-address> \
  -n neurosymbolic-ai

# Grant secret to project
oc secrets link default ghcr-creds --for=pull -n neurosymbolic-ai
```

# Run It

<b>UI:</b> Launch the UI at http://localhost:8080 when using Podman Compose, or the route URL when deployed on OpenShift (for example `http://ui-neurosymbolic-ai.apps-crc.testing/`).

<b>Config the UI:</b> If you created a `.env` file from `.env.example`, the orchestrator URL, LLM endpoint, API key, and model are loaded automatically. Expand **Connection settings** to review or override them. Otherwise, enter the LLM endpoint, API key, and model manually.

<b>Example 1:</b> Enter a simple prompt that doesn't require any tools: 
```
What is the capital of France?
```
Output:
```
The capital of France is Paris.
```

<b>Example 2:</b> Calculate the value at risk of a portfolio: 
```
Calculate the 1-day value at risk (VaR) of the following portfolio at a 0.99 confidence: 100 shares of IBM, 100 shares of NVDA and 50 shares of AAPL.  Report the result in a client friendly manner.
```
Output:
```
The 1-day value at risk (VaR) of the portfolio at a 0.99 confidence is $2339.55. This means that there is a 1% chance that the portfolio will lose more than $2339.55 in a single day.
```

<b>Example 3:</b> Build a $1,000,000 portoflio: 
```
Build an equities portfolio with 5 ticker symbols and a total value of $1 million.  For the portfolio, report back each ticker symbol, name of the company, number of shares, and last price.
```
Output:
```
The portfolio consists of the following ticker symbols, company names, number of shares, and last prices:
- JNJ, Johnson & Johnson, 1035, $193.22
- USB, U.S. Bancorp, 4377, $45.69
- BMY, Bristol Myers Squibb Company, 4584, $43.63
- TXN, Texas Instruments Incorporated, 1132, $176.58
- USB, U.S. Bancorp, 4377, $45.69
```

<b>Example 4:</b> Parse an investment guideline: 
```
I have a new client and have uploaded their investment guidelines to the following URL: https://d15bgksgja6rr0.cloudfront.net/Neurosymbolic-Inc-Investment-Guidelines.pdf.  What ticker symbols are prohibited per their guidelines?
```
Output:
```
The prohibited ticker symbols per the client's guidelines are CVX, TGT, WMT, and XOM.
```

<b>Example 5:</b> Muti-tool example: 
```
- I have a new client and have uploaded their investment guidelines to the following URL: https://d15bgksgja6rr0.cloudfront.net/Neurosymbolic-Inc-Investment-Guidelines.pdf.
- Build an equities portfolio with 5 ticker symbols and a total value of $1 million.  Exclude the ticker symbols you just calculated.  For the portfolio, report back each ticker symbol, name of the company, number of shares, and last price.
- Also tell me the 1-day value at risk (VaR) of the portfolio at a 0.99 confidence.
```
Output:
```
The prohibited ticker symbols for the new client are CVX, TGT, WMT, and XOM.

The equities portfolio with 5 ticker symbols and a total value of $1 million, excluding the prohibited symbols, is:

| Ticker Symbol | Company Name | Number of Shares | Last Price |
| --- | --- | --- | --- |
| ISRG | Intuitive Surgical, Inc. | 448 | 446.13 |
| BKNG | Booking Holdings Inc. | 39 | 5070.02 |
| HD | The Home Depot, Inc. | 510 | 391.9 |
| ADBE | Adobe Inc. | 600 | 333.26 |
| CHTR | Charter Communications, Inc. | 790 | 253.16 |

The 1-day value at risk (VaR) of the portfolio at a 0.99 confidence is $32,871.91.
```

## Trouble shooting

### Podman: Stuck in "Starting"
If Podman is stuck in "Starting" for Podman Desktop, try issuing the following in the Terminal: "podman machine start"

### "Requested resource" error when executing "ksvc-risk.yaml"
Serverless requires the "Red Hat OpenShift Serverless" Operator to be installed.  In the OpenShift UI, check if "Red Hat OpenShift Serverless" in installed in "Installed Operators."  

If it is not installed, search for "serverless" in the "Software Catalog" and install it.  Once installed, click "Red Hat OpenShift Serverless" in "Installed Operators" and click "Create instance" under "Knative Serving" in the "knative-serving" project.  

Alternatively, run the traditional, always-on containers.
