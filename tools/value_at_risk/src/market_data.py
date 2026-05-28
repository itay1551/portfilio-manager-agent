# Name:     market_data.py
# Purpose:  Market Data
# Author:   Aric Rosenbaum


import json
import requests
from requests.status_codes import codes
import pandas as pd
import yfinance as yf
import time


class MarketData:

    # # Constructor
    # def __init__(self, url = None, cache_name = None, username = None, password = None):
    #     if url is not None and cache_name is not None and username is not None and password is not None:
    #         self.use_data_grid = True
    #         self._username = username
    #         self._password = password
    #         self._cache_url = url + "/rest/v2/caches/" + cache_name
    #     else:
    #         self.use_data_grid = False
  

    # Return a dataframe of daily closing prices
    def get(self, symbols, start, end):

        # Create an empty dataframe to hold closing prices
        #  - Each row will be a trading day
        #  - One column per element in the symbols list
        symbols_price = pd.DataFrame()

        # Iterate thru symbols
        for symbol in symbols:

            # Fetch symbol data and add closing prices to dataframe
            df = self._fetch_yahoo_data(symbol.lower(), start, end)
            symbols_price[symbol] = df["Close"]

        return symbols_price


    # Fetch data from Yahoo
    def _fetch_yahoo_data(self, symbol, start, end):
        data = yf.download(symbol, start=start, end=end)
        return data
