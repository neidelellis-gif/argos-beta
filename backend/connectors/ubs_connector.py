import csv

FILE_PATH = "backend/connectors/UBS_Holdings_08_07_2026.csv"


def classify_asset(symbol, description):
    text = description.upper()

    if "SAVINGS" in text or "SWEEP" in text:
        return "Caixa"
    if "MATURES" in text or "CALLABLE" in text or "RATE" in text or "NTS" in text:
        return "Renda Fixa"
    if "ETF" in text:
        return "ETF"
    if "FUND" in text:
        return "Fundo"
    if symbol != "N/A":
        return "Ação"

    return "Outros"


def get_display_name(symbol, description):
    return symbol if symbol != "N/A" else description


def load_positions():
    positions = []

    with open(FILE_PATH, encoding="utf-8-sig") as file:
        next(file)
        reader = csv.reader(file)
        header = next(reader)

        account_idx = header.index("ACCOUNT NUMBER")
        description_idx = header.index("DESCRIPTION")
        symbol_idx = header.index("SYMBOL")
        value_idx = header.index("VALUE")

        for row in reader:
            if len(row) == 1:
                row = next(csv.reader([row[0]]))

            if len(row) <= value_idx:
                continue

            symbol = row[symbol_idx].strip()
            description = row[description_idx].strip()
            value_text = row[value_idx].replace("$", "").replace(",", "").replace('"', "").strip()

            if value_text == "":
                continue

            value = float(value_text)

            positions.append({
                "account": row[account_idx],
                "symbol": symbol,
                "name": get_display_name(symbol, description),
                "description": description,
                "class": classify_asset(symbol, description),
                "value": value,
            })

    return positions