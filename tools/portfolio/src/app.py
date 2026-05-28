# Name:     app.py
# Purpose:  Build a stock portfolio
# Author:   Aric Rosenbaum

 
from flask import Flask, request, jsonify
import ast
import os
import random
import yfinance as yf

app = Flask(__name__)

'''
Design a portfolio based on specified criteria:
  - Portfolio size in US$ (default = 1m)
  - Excluded ticker symbols (default = none)
  - # of symbols to include in the portfolio (default = 5)

curl -X POST \
    -H "Content-Type: application/json" \
    -d '{"portfolio_value": 1000000, "qty_symbols": 5, "symbols_exclusion": ["T", "IBM", "NVDA"]}' \
    http://localhost:7002/tools/portfolio_equities
    
POST http://localhost:7002/tools/portfolio_equities
{
  "portfolio_value": 1000000,
  "symbols_exclusion": ["T", "IBM", "NVDA"],
  "qty_symbols": 5
}

'''


# ---- Advertised tools for Agentic AI consumption (JSON Schema params) ----
TOOLS = [
    {
        "type": "function",
        "name": "portfolio_equities",
        "description": "Build an equities portfolio of a given size without excluded symbols",
        "parameters": {
            "type": "object",
            "properties": {
                "portfolio_value": {
                    "type": "number",
                    "description": "Do not exceed value of portfolio",
                    "minimum": 0
                },
                "qty_symbols": {
                    "type": "number",
                    "description": "Quantity of ticker symbols to include in the portfolio",
                    "minimum": 0
                },
                "symbols_exclusion": {
                    "type": "array",
                    "description": "List of ticker symbols to exclude from the portfolio, e.g., IBM, NVDA",
                    "items": {
                        "type": "string",
                    }
                }
            }
        }
    }
]

# Define universe of S&P 100 stocks.
#   n.b. - In prod, this would likely be available via a web service or sitting in cache
SP_100 = [
  "AAPL", "ABBV", "ABT", "ACN", "ADBE", "AIG", "AMD", "AMGN", "AMT", "AMZN",
  "AVGO", "AXP", "BA", "BAC", "BK", "BKNG", "BLK", "BMY", "BRK-B", "C",
  "CAT", "CHTR", "CL", "CMCSA", "COF", "COP", "COST", "CRM", "CSCO", "CVS",
  "CVX", "DE", "DHR", "DIS", "DUK", "EMR", "FDX", "GD", "GE", "GILD",
  "GM", "GOOG", "GOOGL", "GS", "HD", "HON", "IBM", "INTC", "INTU", "ISRG",
  "JNJ", "JPM", "KO", "LIN", "LLY", "LMT", "LOW", "MA", "MCD", "MDLZ",
  "MDT", "MET", "META", "MMM", "MO", "MRK", "MS", "MSFT", "NEE", "NFLX",
  "NKE", "NOW", "NVDA", "ORCL", "PEP", "PFE", "PG", "PLTR", "PM", "PYPL",
  "QCOM", "RTX", "SBUX", "SCHW", "SO", "SPG", "T", "TGT", "TMO", "TMUS",
  "TSLA", "TXN", "UNH", "UNP", "UPS", "USB", "V", "VZ", "WFC", "WMT", "XOM"
]


# ---- Helpers ----
def json_args():
    data = request.get_json(silent=True)
    if data is None:
        return {}, ("Invalid or missing JSON body.", 400)
    return data, None

def last_price(symbol):
    data = yf.Ticker(symbol)
    price = data.history(period='10d')['Close'].iloc[-1]
    return round(price, 3)


# ---- Routes ----
@app.get("/tools")
def list_tools():
    return jsonify(TOOLS)


@app.post("/tools/portfolio_equities")
def portfolio_equities():

    # Parse parameters
    data, err = json_args()
    portfolio = []
    if err:
        return err
    try:
        requested_portfolio_value = int(data.get("portfolio_value", 1000000))
        symbols_exclusion = data.get("symbols_exclusion", [])
        qty_symbols = int(data.get("qty_symbols", 5))

        # Build a portfolio -- for this demo, 5 (default) stocks from the S&P 100 that are not in the exclusion list (equal weight)
        while len(portfolio) < qty_symbols:
            symbol = random.choice(SP_100)
            if symbol not in symbols_exclusion:
                price = last_price(symbol)
                shares = int(requested_portfolio_value / qty_symbols / price)
                portfolio.append({"symbol": symbol, "quantity": shares, "last_price": price})       
    except Exception as e:
        print(e)
        return {"error": f"Tool: 'portfolio_equities' failed: {e}"}

    # Return portfolio
    return portfolio


@app.post("/tools/echo")
def echo():
    data, err = json_args()
    if err:
        return err
    return jsonify({"echo": data.get("text", "")})


@app.post("/tools/echo2")
def echo2():

    print("----- REQUEST DEBUG -----")
    print("Method:", request.method)
    print("Headers:", dict(request.headers))
    print("Content-Type:", request.content_type)
    print("Raw body bytes:", request.get_data())
    print("Raw body text:", request.get_data(as_text=True))
    print("JSON parsed:", request.get_json(silent=True))
    print("-------------------------")
    data, err = json_args()
    if err:
        return err
    return jsonify({"echo": data.get("text", "")})
    #print("data:", data)
    #print("err:", err)    
    #return jsonify({"echo": "DEBUG"})


@app.post("/tools/post-text")
def post_text():
    return "It works"

@app.post("/tools/post-json")
def post_json():
    return jsonify({"echo": "It works"})

# ---- Entrypoint ----
if __name__ == "__main__":
    port = int(os.getenv("PORT", "7002"))  # run multiple servers by changing PORT
    # For local dev; use gunicorn/waitress for production
    app.run(host="0.0.0.0", port=port, debug=True)
