# Name:     app.py
# Purpose:  Calculate value at risk for a portfolio of US equities using the variance-covariance method
# Author:   Aric Rosenbaum


import datetime
import ast
from flask import Flask, request, jsonify
from market_data import MarketData
from portfolio import Portfolio
from value_at_risk import ValueAtRisk
import os

app = Flask(__name__)

"""
“Calculate the value of my portfolio with a 95% confidence interval given these positions: …”
and it will automatically call this tool.

curl -X POST \
    -H "Content-Type: application/json" \
    -d '{"confidence": 0.99, "portfolio": [{"symbol": "AAPL", "quantity": 10}, {"symbol": "IBM", "quantity": 100}, {"symbol": "NVDA", "quantity": 100}]}' \
    http://localhost:7001/tools/value_at_risk


POST http://localhost:7001/tools/value_at_risk
{
    "confidence": 0.99,
    "portfolio": [
        {"symbol": "NVDA", "quantity": 100},
        {"symbol": "T", "quantity": 55},
        {"symbol": "IBM", "quantity": 20}
    ]
}

"""


# ---- Advertised tools (JSON Schema params) ----
TOOLS = [
    {
        "type": "function",
        "name": "value_at_risk",
        "description": "Calculate value at risk (VaR) for a specified portfolio.",
        "parameters": {
            "type": "object",
            "properties": {
                "confidence": {
                    "type": "integer",
                    "description": "Confidence interval (i.e. 90, 95 or 99)",
                    "minimum": 50,
                    "maximum": 99,
                },
                "portfolio": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "symbol": {
                                "type": "string",
                                "description": "Ticker symbol, e.g., IBM, NVDA",
                            },
                            "quantity": {
                                "type": "integer",
                                "description": "Number of shares held",
                            },
                        },
                    },
                },
            },
        },
    }
]


# ---- Helpers ----
def json_args():
    data = request.get_json(silent=True)
    if data is None:
        return {}, ("Invalid or missing JSON body.", 400)
    return data, None


# ---- Routes ----
@app.get("/tools")
def list_tools():
    return jsonify(TOOLS)


# Value at risk endpoint
@app.post("/tools/value_at_risk")
def value_at_risk():
    try:
        request_data = request.get_json(silent=True) or {}
        confidence = request_data.get("confidence", 0.99)
        if isinstance(confidence, str):
            confidence = int(confidence)
        if 1 < confidence < 100:
            confidence = round(confidence / 100, 2)
        positions = request_data.get("portfolio")
        if not positions:
            return jsonify({"error": "portfolio is required"}), 400

        portfolio = Portfolio()
        if isinstance(positions, str):
            positions = ast.literal_eval(positions)
        for position in positions:
            portfolio.addPosition(position["symbol"], int(position["quantity"]))

        start = datetime.date.today() - datetime.timedelta(days=365)
        end = datetime.date.today()
        market_data = MarketData()
        hist_prices = market_data.get(portfolio.symbols(), start, end)

        var = ValueAtRisk()
        results = var.calculate(portfolio, hist_prices, confidence)

        data = {
            "confidence": confidence,
            "valueAtRisk": results,
            "valueAtRiskAsOf": int(
                datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000
            ),
        }
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": f"Tool: 'value_at_risk' failed: {e}"}), 500


@app.post("/tools/echo")
def echo():
    data, err = json_args()
    if err:
        return err
    return jsonify({"echo": data.get("text", "")})


# ---- Entrypoint ----
if __name__ == "__main__":
    port = int(os.getenv("PORT", "7001"))  # run multiple servers by changing PORT
    # For local dev; use gunicorn/waitress for production
    app.run(host="0.0.0.0", port=port, debug=True)
