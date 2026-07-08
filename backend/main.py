from connectors.ubs_connector import load_positions
from portfolio.engine import analyze_portfolio

print("=" * 60)
print("                 ARGOS ALPHA")
print("=" * 60)

positions = load_positions()

portfolio = analyze_portfolio(positions)

print()
print(f"Patrimônio UBS : US$ {portfolio['total']:,.2f}")
print()

print("🔴 PRIORIDADE ALTA")
print("-" * 60)

for p in portfolio["high_priority"]:
    print(f"{p['weight']:5.2f}%   {p['name']}")

print()

print("🟡 PRIORIDADE MÉDIA")
print("-" * 60)

for p in portfolio["medium_priority"]:
    print(f"{p['weight']:5.2f}%   {p['name']}")

print()
print("=" * 60)
print("ARGOS pronto.")
print("=" * 60)