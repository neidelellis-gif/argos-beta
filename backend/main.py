from connectors.ubs_connector import load_positions

print("=" * 60)
print("                 ARGOS ALPHA")
print("=" * 60)

positions = load_positions()
total = sum(p["value"] for p in positions)

alta = []
media = []

for p in positions:

    weight = p["value"] / total * 100

    if weight >= 5:
        alta.append((weight, p))

    elif weight >= 3:
        media.append((weight, p))

alta.sort(reverse=True)
media.sort(reverse=True)

print()
print(f"Patrimônio UBS : US$ {total:,.2f}")
print()

print("🔴 PRIORIDADE ALTA")
print("-" * 60)

for weight, p in alta:
    print(f"{weight:5.2f}%   {p['name']}")

print()

print("🟡 PRIORIDADE MÉDIA")
print("-" * 60)

for weight, p in media:
    print(f"{weight:5.2f}%   {p['name']}")

print()
print("=" * 60)
print("ARGOS pronto.")
print("=" * 60)