import csv

portfolio = []

with open("backend/portfolio/portfolio.csv", newline="") as file:
    reader = csv.DictReader(file)

    for row in reader:
        portfolio.append({
            "ticker": row["ticker"],
            "value": float(row["value"])
        })

total_value = sum(position["value"] for position in portfolio)

print("==============================")
print("ARGOS PORTFOLIO ENGINE v0.2")
print("==============================")
print(f"Valor total: US$ {total_value:,.2f}")
print("------------------------------")

for position in portfolio:
    weight = position["value"] / total_value * 100
    print(f"{position['ticker']}: US$ {position['value']:,.2f} | {weight:.2f}%")

print("------------------------------")
print("Status: OK")