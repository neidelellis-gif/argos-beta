from connectors.ubs_connector import load_positions

print("=" * 60)
print("                 ARGOS ALPHA")
print("=" * 60)

positions = load_positions()

total = sum(p["value"] for p in positions)

print()
print(f"Carteira UBS carregada com sucesso.")
print(f"Posições : {len(positions)}")
print(f"Patrimônio: US$ {total:,.2f}")

print()
print("Ativos monitorados (>3%)")
print("-" * 60)

for p in positions:

    weight = p["value"] / total * 100

    if weight >= 3:

        print(
            f"{p['name']:<40}"
            f"{p['class']:<15}"
            f"{weight:>6.2f}%"
        )

print()
print("=" * 60)
print("ARGOS pronto.")
print("=" * 60) 