# Name:     portfolio.py
# Purpose:  Portfolio of assets
# Author:   Aric Rosenbaum


import datetime
import numpy as np
import pandas as pd
import yfinance as yf 
from scipy.stats import norm


class Portfolio:

    # Constructor
    def __init__(self):
        self.df = pd.DataFrame(columns = ['Symbol', 'Quantity', 'Price', 'MTM', 'Weight'])
        self.df.set_index('Symbol')
 

    # Add a position to the portfolio
    def addPosition(self, symbol, quantity = 0, price = 0):

        # Get price if none provided
        if price == 0:
            #df_price = web.DataReader(symbol, 'yahoo', datetime.date.today() - datetime.timedelta(days=7), datetime.date.today())
            #df_price = df_price["Adj Close"]
            #price = df_price.iloc[-1]
            data = yf.Ticker(symbol)
            price = round(data.history(period='10d')['Close'].iloc[-1], 3)


        # N.B. - DataFrame.append() is inefficient for continually adding rows.  Other techniques provide better performance, but
        #        append() gets the job done for this risk architecture example.
        #self.df = self.df.append({'Symbol': symbol, 'Quantity': quantity, 'Price': price, 'MTM': quantity * price}, ignore_index = True)
        self.df.loc[len(self.df)]  = {'Symbol': symbol, 'Quantity': quantity, 'Price': price, 'MTM': quantity * price}

    # How many positions we have?
    def rows(self):
        return self.df.shape[0]


    # Calculate the weight of each symbol in the portfolio
    def weights(self):

        # Calculate portfolio MTM and then the weight of each position's MTM
        portfolio_mtm = self.mtm()
        if portfolio_mtm != 0:
            self.df['Weight'] = self.df['MTM'] / portfolio_mtm

        # Convert weight column to an array
        weights = self.df.loc[:, 'Weight'].values

        return  weights   


    # Calculate the portfolio's mark-to-market (MTM)
    def mtm(self):
        return self.df['MTM'].sum()


    # Unique symbols in portfolio
    def symbols(self):
        return self.df['Symbol'].unique()


    # Mean return for portfolio given the mean return for each symbol and the weights of each position
    def mean_return(self, symbol_mean_return, position_weights):
        return symbol_mean_return.dot(position_weights)


    # Variance of a portfolio's return given the weights of each position and a covariance matrix 
    def variance(self, weights, covariance_matrix):
        return weights.T.dot(covariance_matrix).dot(weights)


    # Standard deviation (aka volatility) of a portfolio
    def std_dev(self, variance):
        return np.sqrt(variance)