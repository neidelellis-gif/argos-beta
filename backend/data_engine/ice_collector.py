import yfinance as yf
from datetime import datetime

tickers = ["ICE", "MSFT", "SMH", "COHR", "BTC-USD", "ETH-USD"]

print("==============================")
print("ARGOS DATA ENGINE v0.2")
print("==============================")
print(f"Atualizado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
print("Fonte: Yahoo Finance / yfinance")
print("------------------------------")

for ticker in tickers:
    asset = yf.Ticker(ticker)
    data = asset.history(period="2d")

    last_row = data.tail(1).iloc[0]
    previous_row = data.tail(2).iloc[0]

    last_price = last_row["Close"]
    previous_close = previous_row["Close"]
    daily_change = ((last_price / previous_close) - 1) * 100

    print(f"{ticker}: US$ {last_price:.2f} | {daily_change:.2f}%")

print("------------------------------")
print("Status: OK")