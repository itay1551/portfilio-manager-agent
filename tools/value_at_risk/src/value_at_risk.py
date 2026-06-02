# Name:     value_at_risk.py
# Purpose:  Calculate value at risk for a portfolio of US equities using the variance-covariance method
# Author:   Aric Rosenbaum


import pandas as pd
from scipy.stats import norm


class ValueAtRisk:
    # Constructor
    def __init__(self):
        self.df_symbol_pct_change = pd.DataFrame()

    def calculate(self, portfolio, market_data, confidence):
        # Calculate daily % change for each symbol
        df_symbol_pct_change = market_data.pct_change()

        # Calculate mean return for each symbol over the time horizon
        symbol_return_mean = df_symbol_pct_change.mean()

        # Calculate covariance matrix
        df_covariance = df_symbol_pct_change.cov()

        # Calc portfolio mark-to-market (MTM) and weights
        portfolio_mtm = portfolio.mtm()
        portfolio_weights = portfolio.weights()

        # Calculate portfolio mean return and its variance and std dev (in percents)
        portfolio_return_mean = portfolio.mean_return(
            symbol_return_mean, portfolio_weights
        )
        portfolio_return_variance = portfolio.variance(portfolio_weights, df_covariance)
        portfolio_return_std_dev = portfolio.std_dev(portfolio_return_variance)

        # Calculate parametric VaR (aka variance covariance VaR)
        var = self._parametricVaR(
            confidence, portfolio_mtm, portfolio_return_mean, portfolio_return_std_dev
        )

        return round(var, 2)

    # Value at risk via parametric (aka variance covariance) method
    def _parametricVaR(self, confidence, portfolio_value, mean, std_dev):
        var_pct = norm.ppf(1 - confidence, mean, std_dev)
        var = portfolio_value * var_pct * -1

        return var

    # Expected shortfall (aka Conditional Value at Risk) via parametric (aka variance covariance) method
    def _parametricES(self, confidence, portfolio_value, mean, std_dev):
        es_pct = (
            (1 - confidence) ** -1 * norm.pdf(norm.ppf(1 - confidence)) * std_dev
        ) - mean
        es = portfolio_value * es_pct * -1

        return es
