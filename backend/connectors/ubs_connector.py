import csv

file_path = "backend/connectors/UBS_Holdings_08_07_2026.csv"

print("==============================")
print("ARGOS UBS CONNECTOR v0.4")
print("==============================")

positions = []

with open(file_path, encoding="utf-8-sig") as file:
    next(file)
    reader = csv.reader(file)
    header = next(reader)

    symbol_index = header.index("SYMBOL")
    description_index = header.index("DESCRIPTION")
    value_index = header.index("VALUE")

    for row in reader:
        if len(row) == 1:
            row = next(csv.reader([row[0]]))

        if len(row) <= value_index:
            continue

        symbol = row[symbol_index].strip()
        description = row[description_index].strip()
        value = row[value_index].replace("$", "").replace(",", "").replace('"', "").strip()

        if value in ["", "N/A"]:
            continue

        value = float(value)

        positions.append({
            "symbol": symbol,
            "description": description,
            "value": value
        })

total_value = sum(p["value"] for p in positions)

for p in positions:
    weight = p["value"] / total_value * 100
    monitor = "SIM" if weight >= 3 else "NÃO"

    print(
        f"{p['symbol']} | "
        f"US$ {p['value']:,.2f} | "
        f"{weight:.2f}% | "
        f"Monitorar: {monitor}"
    )

print("------------------------------")
print(f"Total UBS: US$ {total_value:,.2f}")
print(f"Posições encontradas: {len(positions)}")
print("Status: OK")