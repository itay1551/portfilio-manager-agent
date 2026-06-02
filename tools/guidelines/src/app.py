# Name:     app.py
# Purpose:  Parse an investment guideline
# Author:   Aric Rosenbaum


from flask import Flask, request, jsonify
import os
import random

import re
from io import BytesIO
import requests
from typing import List
from threading import Lock
from datetime import datetime

from pdfminer.high_level import extract_text
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neural_network import MLPClassifier
from sklearn.pipeline import Pipeline
import joblib
app = Flask(__name__)

'''
Design a portfolio based on specified criteria:
  - Portfolio size
  - Excluded ticker symbols

POST http://localhost:7003/tools/prohibited_symbols
{
  "url_investment_guidelines": "https://d15bgksgja6rr0.cloudfront.net/Neurosymbolic-Inc-Investment-Guidelines.pdf"
}

curl -X POST \
    -H "Content-Type: application/json" \
    -d '{"url_investment_guidelines": "https://d15bgksgja6rr0.cloudfront.net/Neurosymbolic-Inc-Investment-Guidelines.pdf"}' \
    http://localhost:7003/tools/prohibited_symbols

'''


# ---- Advertised tools (JSON Schema params) ----
TOOLS = [
    {
        "type": "function",
        "name": "prohibited_symbols",
        "description": "Given a client number or URL, parse an investment guidelines document to determine prohibited ticker symbols",
        "parameters": {
            "type": "object",
            "properties": {
                "url_investment_guidelines": {
                    "type": "string",
                    "description": "URL where the document can be found in the DMS"
                },
                "client": {
                    "type": "string",
                    "description": "Client number as defined in the document management system"
                }
            }
        }
    }
]

# ----------------------------
# Config
# ----------------------------
MODEL_PATH = os.environ.get("MODEL_PATH", "models/investment-guidelines-mlp.joblib")


# ----------------------------
# Helpers
# ----------------------------

SENT_SPLIT_RE = re.compile(r"(?:\n\s*[-•]\s*|\n{2,}|(?<=[\.\!\?\:\;])\s+)")

# Expand stopwords (non-tickers that happen to be uppercase)
UPPER_STOP = {
    "AND","OR","NOT","ANY","ALL","THE","FUND","FUNDS","ETF","ETFS","INDEX","INDICES",
    "USA","US","USD","NYSE","NASDAQ","AMEX","OTC","S&P","DJIA","RUSSELL","NO","BUY","SELL",
    "HOLD","DO","SHALL","MAY","MUST","ARE","IS","IN","OF","ON","TO","FOR","WITH",
}

# Company suffixes to detect "part-of-a-name" context
COMPANY_SUFFIXES = {
    "INC","INC.","CORP","CORPORATION","CO","CO.","COMPANY","LTD","LTD.","PLC","LLC","LP","LLP",
    "S.A.","S.A","N.V.","NV","AG","SE","SAS","GMBH","BV","AB"
}

# Short, ambiguous tokens that are real tickers sometimes, but easy false positives out of context
AMBIGUOUS_SHORT = {"AI","UK","EU","US","EV","PE","ESG","ETF","NAV"}

# Cues that usually mean we’re actually talking about tickers / restrictions
PROHIBITION_CUES_RE = re.compile(
    r"\b(prohibit|restricted|ban|blacklist|forbid|do not (?:own|purchase|hold)|"
    r"not permitted|disallow|exclude|avoid no (?:new )?positions?)\b", re.I
)

# Avoid matching tokens that are immediately followed by rating-style suffixes like "-1" or "+"
# Hyphen class includes various unicode hyphens: - – — -
TICKER_RE = re.compile(r"\b([A-Z]{1,5}(?:\.[A-Z])?)\b(?!\s*[-–—-]\s*\d|\s*[+-])")

# Words that indicate we're talking about credit ratings rather than tickers
RATING_CONTEXT_RE = re.compile(
    r"\b(rating|ratings|rated|credit\s+quality|commercial\s+paper|CP|money\s+market|"
    r"moody'?s|standard\s*&\s*poor'?s|s&?p\b|fitch|dbrs|kroll)\b",
    re.I
)

# Single/short tokens commonly used in ratings vocab; we skip them in rating contexts
RATING_START_TOKENS = {"A","AA","AAA","B","BB","BBB","C","CC","CCC","D","P","F","R"}

# ---- Helpers ----
def json_args():
    data = request.get_json(silent=True)
    if data is None:
        return {}, ("Invalid or missing JSON body.", 400)
    return data, None

def split_sentences(text: str) -> List[str]:
    parts = SENT_SPLIT_RE.split(text)
    # Clean & keep only non-empty lines with a bit of body
    return [p.strip() for p in parts if p and len(p.strip()) >= 3]

def _next_words(text: str, start: int, max_chars: int = 24) -> str:
    return text[start:start+max_chars]

def _prev_words(text: str, end: int, max_chars: int = 24) -> str:
    b = max(0, end - max_chars)
    return text[b:end]

def _looks_like_company_context(text: str, start: int, end: int) -> bool:
    """
    Heuristic: reject candidates that appear inside a proper company name like:
      'Neurosymbolic AI, Inc.' or 'Acme Widgets PLC'
    Rules:
      - If immediately followed by ', Inc.' / ' Inc' / ', LLC' etc. (within a few chars)
      - If previous word is TitleCase and next token is a company suffix
      - If candidate is sandwiched between TitleCase words and followed by a comma
    """
    before = _prev_words(text, start)
    after = _next_words(text, end)

    # 1) Followed by a company suffix (optionally via comma)
    if re.search(r"^\s*,?\s*(?:" + "|".join(COMPANY_SUFFIXES) + r")\b\.?", after, re.I):
        return True

    # Grab nearest previous/next words
    m_prev = re.search(r"([A-Za-z][A-Za-z0-9&\.\-]+)\s*$", before)
    m_next = re.search(r"^\s*([A-Za-z][A-Za-z0-9&\.\-]+)", after)
    prev_word = m_prev.group(1) if m_prev else ""
    next_word = m_next.group(1) if m_next else ""

    def _is_titlecase(w: str) -> bool:
        return bool(re.match(r"^[A-Z][a-z].*", w))

    # 2) TitleCase before + immediate comma, then company suffix soon after
    if _is_titlecase(prev_word) and after.lstrip().startswith(","):
        if re.search(r"^\s*,\s*(?:" + "|".join(COMPANY_SUFFIXES) + r")\b\.?", after, re.I):
            return True

    # 3) TitleCase before and after (multi-word company name), e.g., 'Foo AI Holdings'
    if _is_titlecase(prev_word) and _is_titlecase(next_word):
        return True

    return False

def _is_parenthesized_ticker(text: str, start: int, end: int) -> bool:
    """Allow patterns like 'C3.ai (AI)'."""
    before = _prev_words(text, start, 3)
    after = _next_words(text, end, 3)
    return "(" in before or ")" in after  # relaxed but effective for '(TICKER)'

def _is_exchange_colon_pattern(text: str, start: int) -> bool:
    # Accept patterns like "NYSE: A" or "NASDAQ: C"
    lookback = text[max(0, start - 12):start].upper()
    return any(x in lookback for x in ("NYSE:", "NASDAQ:", "AMEX:", "CBOE:", "BATS:"))

def _is_rating_tail(after: str) -> bool:
    """
    True if immediate text after a token looks like a rating suffix:
      A-1, AA-, BBB+, F1+, R-1(low) etc.
    """
    return bool(re.match(r"^\s*[-–—-]?\s*(?:\d(?:\s*\((?:low|high)\))?|[+-])", after))

def _is_credit_rating_token(token: str, line: str, start: int, end: int) -> bool:
    """
    Decide if token (A, AA, P, F, etc.) is acting as a rating, not a ticker.
    Heuristics:
      - Immediately followed by a rating tail (e.g., '-1', '+', '-')
      - Line contains rating context words and token is a common rating prefix
    """
    after = line[end:end+12]
    if _is_rating_tail(after):
        return True
    if RATING_CONTEXT_RE.search(line) and token in RATING_START_TOKENS and len(token) <= 3:
        return True
    return False

def extract_tickers(line: str) -> List[str]:
    """
    Context-aware ticker extraction:
      - Skip tokens in company-name contexts (existing helper)
      - Skip tokens that look like CREDIT RATINGS (A-1, P-1, F1+, etc.)
      - Be strict with short/ambiguous tokens (A, P, AI, etc.)
    """
    candidates = [(m.group(1), m.start(1), m.end(1)) for m in TICKER_RE.finditer(line)]
    if not candidates:
        return []

    has_cues = bool(PROHIBITION_CUES_RE.search(line))

    tickers: List[str] = []
    for c, s, e in candidates:
        # Global stops
        if c in UPPER_STOP:
            continue

        # Company-name context (your existing helper)
        if _looks_like_company_context(line, s, e):
            continue

        # Credit ratings context (new)
        if _is_credit_rating_token(c, line, s, e):
            continue

        # STRONGER RULES for very short tokens (1–2 letters):
        # Only accept if parenthesized OR exchange-colon pattern OR explicit prohibition cues.
        if len(c) <= 2:
            if not (_is_parenthesized_ticker(line, s, e) or _is_exchange_colon_pattern(line, s) or has_cues):
                continue

        # For 2–3 letter highly ambiguous tokens (e.g., 'AI'), also require stronger context
        if len(c) == 2 and c in {"AI","US","EU","UK","EV","PE","ES","ET","CP"}:
            if not (_is_parenthesized_ticker(line, s, e) or _is_exchange_colon_pattern(line, s) or has_cues):
                continue

        tickers.append(c)

    return tickers

# ----------------------------
# Model train / save / load
# ----------------------------

def train_default_model() -> Pipeline:
    """
    A lightweight neural net (MLP) to classify whether a sentence/line indicates prohibition.
    Trains on synthetic examples that capture compliance phrasing.
    """
    positives = [
        # Direct "prohibited" / "do not own"
        "The following tickers are prohibited: AAPL, TSLA, MSFT.",
        "Do not own the following securities: AMZN and META.",
        "The portfolio must not hold shares of GOOGL, BRK.B, JPM.",
        "The fund shall not own NVDA, INTC, or AMD under any circumstances.",
        "Ownership of LMT and NOC is prohibited per defense exclusion.",
        "Prohibited holdings: XOM, CVX and COP.",
        "Securities barred from purchase include AIG and C.",
        "Do not purchase any shares of T or VZ.",
        "Avoid holding MO and PM; tobacco is not permitted.",
        "Zero exposure is allowed to BA and LHX; these issuers are prohibited.",
        # Restricted / blacklist / ban list
        "Restricted list includes BRK.B even if held indirectly.",
        "Blacklist contains META, SNAP, and PINS due to data privacy issues.",
        "Ban list: EQNR, BP, SHEL are not permitted in any account.",
        "Trading in RIVN and LCID is prohibited until further notice.",
        "The manager is barred from purchasing RBLX and U.",
        "Forbidden securities are COIN and HOOD.",
        "The following issuers are restricted: CRM, NOW, MDB.",
        "Hard prohibition applies to SHOP and SQ.",
        "Prohibited list effective Jan 1: PYPL, AXP, MA, V.",
        "No new or existing positions in BABA, JD, BIDU are allowed.",
        # Exclude / divest / do not include
        "Exclude holdings TSLA and NKLA from the portfolio construction.",
        "The portfolio shall exclude shares of GM, F, and STLA.",
        "Divest from oil majors XOM and CVX; reinvestment is prohibited.",
        "Sell down any exposure to SNAP and do not re-enter the name.",
        "We will not buy BRK.B or JPM.",
        "Must not include RCL or CCL due to travel policy.",
        "The fund shall avoid DAL and UAL; airline issuers are excluded.",
        "Explicit exclusion: TSM, ASML and AVGO.",
        "No exposure to META, GOOGL or SNAP due to policy restrictions.",
        "Exclude all holdings in cannabis producers TLRY and CGC.",
        # ESG / sanctions / sector prohibitions with tickers
        "Investments in tobacco companies (MO, PM) are not permitted.",
        "Thermal coal producers such as BTU are prohibited.",
        "Under sanctions policy, investing in RSX and OGZPY is prohibited.",
        "Weapons manufacturers (LMT, NOC) are disallowed.",
        "Gambling operators (MGM, WYNN) are prohibited per mandate.",
        "Adult entertainment distributors (RICK) are excluded.",
        "Controversial weapons screen prohibits ODFL and RTX.",
        "The negative screen bans alcohol producers like DEO.",
        "Fossil fuel exclusion: XOM, CVX, BP are blacklisted.",
        "Privacy violations list prohibits META and SNAP.",
        # Language variants / tricky grammar
        "Managers shall refrain from owning GME or AMC.",
        "The mandate forbids maintaining positions in BBBYQ and PRTYQ.",
        "Holdings of TSLA are not allowed in this strategy.",
        "Positions in BA and LMT are expressly not permitted.",
        "We are prohibited from purchasing ABNB during the lockout period.",
        "No purchase or retention of COIN is permitted.",
        "This policy bans equities of SHOP and SQ.",
        "Restricted due to conflict: MS and GS are prohibited.",
        "Under the exclusion policy, CRYPTO proxy equities like COIN are banned.",
        "Absolute exclusion list: META; GOOGL; SNAP.",
        # “Even if” / “including derivatives or funds” variants
        "Prohibition covers AAPL and MSFT including derivatives and funds.",
        "Not permitted to hold TSLA directly or indirectly via ETFs.",
        "Buying or holding GOOGL through any instrument is prohibited.",
        "Exposure to XOM via index derivatives is disallowed.",
        "No direct, synthetic, or look-through ownership of NVDA is permitted.",
        "Do not hold JPM, including swaps or total-return instruments.",
        # Policy voice / headings in-sentence
        "Prohibited holdings—effective immediately: AMZN, AAPL.",
        "Restricted Securities (Do Not Own): META; SNAP; PINS.",
        "Ban List Update: CVX and XOM added; purchase is prohibited.",
        "Exclusion Rule: BRK.B, JPM; no holdings allowed.",
    ]

    negatives = [
        # Clearly permitted / allowed
        "The following tickers are permitted: AAPL, TSLA, MSFT.",
        "Target allocation includes AMZN and META.",
        "Holdings may include GOOGL and JPM subject to limits.",
        "The fund may buy BRK.B or JPM if risk limits allow.",
        "Technology sector exposure includes NVDA and INTC.",
        "Energy tickers XOM and CVX are benchmarks only.",
        "Portfolio can purchase T and VZ under normal conditions.",
        "Financials such as C and BAC are permitted within 10%.",
        "The strategy allows owning LMT and NOC when hedged.",
        "Exposure to MO and PM is allowed up to 1% aggregate.",
        # Neutral policy language (not a prohibition)
        "This policy outlines general investment principles.",
        "No more than 5% in any single issuer.",
        "Managers should consider liquidity when trading AAPL or MSFT.",
        "The index includes XOM, CVX and COP as top weights.",
        "Examples include AMZN, AAPL, and MSFT in the large-cap growth set.",
        "We monitor META and SNAP for risk but they remain eligible.",
        "The watchlist contains TSLA and RIVN for review only.",
        "We may increase GOOGL and MSFT exposure after the rebalance.",
        "These names—BA, LMT—have been removed from the ban proposal.",
        "Divestment discussion around XOM and CVX is ongoing and undecided.",
        # Phrasings that negate a prohibition
        "The prohibition no longer applies to META and SNAP.",
        "TSLA is not prohibited under the updated policy.",
        "Restrictions were lifted for JPM and C effective last quarter.",
        "The blacklist previously included BP but it has been cleared.",
        "Holding NVDA is now allowed following committee approval.",
        "Gambling operators like MGM and WYNN are no longer excluded.",
        "The fund is not required to avoid BA and LMT.",
        "Coal names such as BTU are not on the exclusion list.",
        "COIN is not banned provided KYC controls are in place.",
        "There is no restriction on owning AMZN within this product.",
        # Ambiguous but non-prohibitive guidance
        "Avoid concentration in AAPL but the security is permitted.",
        "Managers should exercise caution with SNAP due to volatility.",
        "We prefer to underweight XOM and CVX at current valuations.",
        "ESG review may apply to MO and PM but no restriction is set.",
        "Securities such as SHOP and SQ require additional approval.",
        "The committee will evaluate BRK.B for potential inclusion.",
        "Please prepare analytics on TSLA and NKLA for tomorrow.",
        "Discussion item: whether to exclude LHX or RTX next quarter.",
        "Draft proposal suggests banning COIN, pending vote.",
        "We benchmark against an index containing GOOGL, META, and AMZN.",
        # Headings / references to lists without enforcing prohibition
        "Appendix lists prior restricted names for historical context: AAPL, TSLA.",
        "The report summarizes the old prohibition list from 2020.",
        "The watchlist is informational and does not imply exclusion.",
        "The policy mentions sanctions generally but does not name tickers.",
        "An example paragraph mentions META and SNAP in a case study.",
        "Training materials cite BP and SHEL to illustrate energy risk.",
        "Our research note on XOM and CVX discusses fundamentals only.",
        "The compliance FAQ defines what a blacklist is.",
        "Meeting minutes recorded a vote about BRK.B but took no action.",
        "We are collecting feedback on a proposed exclusion framework.",
    ]

    X = positives + negatives
    y = [1] * len(positives) + [0] * len(negatives)

    model = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), lowercase=True, max_features=8000)),
        ("mlp", MLPClassifier(hidden_layer_sizes=(64,),
                              activation="relu",
                              solver="adam",
                              random_state=42,
                              max_iter=400))
    ])
    model.fit(X, y)
    return model

def ensure_dir(path: str):
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)

def save_model(model: Pipeline, path: str) -> str:
    ensure_dir(path)
    payload = {
        "model": model,
        "saved_at": datetime.utcnow().isoformat() + "Z",
        "sklearn_version": getattr(model, "__module__", "sklearn"),
        "type": "prohibition_mlp_pipeline_v1"
    }
    joblib.dump(payload, path)
    return path

def load_model(path: str) -> Pipeline:
    payload = joblib.load(path)
    # if older format was just the Pipeline, accept that too
    if isinstance(payload, Pipeline):
        return payload
    if isinstance(payload, dict) and "model" in payload:
        return payload["model"]
    raise ValueError("Unrecognized model file format")

model_lock = Lock()
clf: Pipeline = None
last_loaded_from = None

def bootstrap_model():
    global clf, last_loaded_from
    if os.path.exists(MODEL_PATH):
        try:
            print(f"Loading model: {MODEL_PATH}")
            clf = load_model(MODEL_PATH)
            last_loaded_from = os.path.abspath(MODEL_PATH)
            return
        except Exception as e:
            print(f"[model] Failed to load existing model ({MODEL_PATH}): {e}")
    print(f"Building model: {MODEL_PATH}")
    clf = train_default_model()
    save_model(clf, MODEL_PATH)
    last_loaded_from = os.path.abspath(MODEL_PATH)

bootstrap_model()


def fetch_pdf_text(url: str, timeout: int = 30) -> str:
    """
    Download a PDF from `url` and return extracted text.

    Raises:
        requests.HTTPError for non-2xx responses
        requests.RequestException for network issues
        Exception for parsing issues
     """

    # Get the doc from a remote URL (in chunks if needed)
    headers = {"User-Agent": "Mozilla/5.0"}
    with requests.get(url, stream=True, timeout=timeout, headers=headers) as r:
        r.raise_for_status()
        chunks = []
        for chunk in r.iter_content(chunk_size=65536):
            if chunk:
                chunks.append(chunk)
        data = b"".join(chunks)

    # Convert to bytes and extract text
    text = extract_text(BytesIO(data))

    return text.strip()


# ---- Routes ----
@app.get("/tools")
def list_tools():
    return jsonify(TOOLS)


@app.post("/tools/prohibited_symbols")
def prohibited_symbols():

    # Parse parameters
    data, err = json_args()
    if err:
        return err
    url_investment_guidelines = data.get("url_investment_guidelines")
    client = data.get("client", "")
    THRESH = float(data.get("threshold", 0.65))

    # If you want to simplify, just return with this array
    #return ["DUK", "PM", "XOM", "COP","CVX"]

    # Get investment guidelines - either locally in DMS or remote URL
    file_path = "docs/client-" + client + "/investment-guidelines.pdf"
    if os.path.isfile(file_path):
        # Parse document from local DMS (document management system) filestore
        print(f"Investment guidelines found in local DMS store for client {client}")
        text = extract_text(file_path)
    else:
        # Fetch doc from specified URL
        print(f"Fetching investment guidelines from remote url: {url_investment_guidelines}")
        text = fetch_pdf_text(url_investment_guidelines)

    # Split doc into sentences
    sentences = split_sentences(text)
    if not sentences:
        return jsonify({"prohibited_tickers": [], "matches": [], "meta": {"num_sentences": 0, "num_matches": 0}})

    # Get model
    with model_lock:
        probs = clf.predict_proba(sentences)[:, 1]

    # Parse doc, sentence by sentence
    # For each sentence, is the probability > threshold
    matches = []
    tickers_set = set()
    for sent, p in zip(sentences, probs):
        if p >= THRESH:
            toks = [t for t in extract_tickers(sent) if t not in UPPER_STOP]
            if toks:
                matches.append({
                    "sentence": sent,
                    "tickers": toks,
                    "score": round(float(p), 4)
                })
                tickers_set.update(toks)

    result = {
        "prohibited_tickers": sorted(tickers_set),
        "matches": matches,
        "meta": {
            "num_sentences": len(sentences),
            "num_matches": len(matches),
            "threshold": THRESH
        }
    }
    return jsonify(result), 200


# @app.post("/tools/echo")
# def echo():
#     data, err = json_args()
#     if err:
#         return err
#     return jsonify({"echo": data.get("text", "")})


# @app.route("/extract", methods=["POST"])
# def extract_endpoint():
#     """
#     Upload a PDF via multipart/form-data under 'file'.
#     Returns JSON with prohibited tickers and matching sentences.
#     """
#     if "file" not in request.files:
#         return jsonify({"error": "Missing file"}), 400

#     text = extract_text(DOCS_PATH)
#     # f = request.files["file"]
#     # if not f or f.filename == "":
#     #     return jsonify({"error": "Empty file"}), 400

#     # try:
#     #     pdf_bytes = f.read()
#     #     text = extract_text(BytesIO(pdf_bytes)) or ""
#     # except Exception as e:
#     #     return jsonify({"error": f"PDF parse failed: {e}"}), 400

#     sentences = split_sentences(text)
#     if not sentences:
#         return jsonify({"prohibited_tickers": [], "matches": [], "meta": {"num_sentences": 0, "num_matches": 0}})

#     THRESH = float(request.args.get("threshold", 0.65))

#     with model_lock:
#         probs = clf.predict_proba(sentences)[:, 1]

#     matches = []
#     tickers_set = set()

#     for sent, p in zip(sentences, probs):
#         if p >= THRESH:
#             toks = [t for t in extract_tickers(sent) if t not in UPPER_STOP]
#             if toks:
#                 matches.append({
#                     "sentence": sent,
#                     "tickers": toks,
#                     "score": round(float(p), 4)
#                 })
#                 tickers_set.update(toks)

#     result = {
#         "prohibited_tickers": sorted(tickers_set),
#         "matches": matches,
#         "meta": {
#             "num_sentences": len(sentences),
#             "num_matches": len(matches),
#             "threshold": THRESH
#         }
#     }
#     return jsonify(result), 200


# @app.route("/model/save", methods=["POST"])
# def model_save():
#     """
#     Save the in-memory model to disk.
#     Optional JSON body: {"path": "/custom/path.joblib"}
#     """
#     data = request.get_json(silent=True) or {}
#     path = data.get("path") or MODEL_PATH
#     with model_lock:
#         try:
#             save_model(clf, path)
#             return jsonify({"ok": True, "saved_to": os.path.abspath(path)}), 200
#         except Exception as e:
#             return jsonify({"ok": False, "error": str(e)}), 500
        

# @app.route("/model/load", methods=["POST"])
# def model_load():
#     """
#     Load a model from disk into memory.
#     Optional JSON body: {"path": "/custom/path.joblib"}
#     """
#     global clf, last_loaded_from
#     data = request.get_json(silent=True) or {}
#     path = data.get("path") or MODEL_PATH
#     if not os.path.exists(path):
#         return jsonify({"ok": False, "error": f"Model file not found: {path}"}), 404
#     with model_lock:
#         try:
#             clf = load_model(path)
#             last_loaded_from = os.path.abspath(path)
#             return jsonify({"ok": True, "loaded_from": last_loaded_from}), 200
#         except Exception as e:
#             return jsonify({"ok": False, "error": str(e)}), 500
        

# ---- Entrypoint ----
if __name__ == "__main__":
    port = int(os.getenv("PORT", "7003"))  # run multiple servers by changing PORT
    # For local dev; use gunicorn/waitress for production
    app.run(host="0.0.0.0", port=port, debug=True)
