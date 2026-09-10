import run_bot_live15

live15 = run_bot_live15
live7 = live15.live7
bot = live15.bot

# Расширяем банк тривиальных названий.
# NaOH уже был в банке как «едкий натр» — добавляем второе допустимое название.
_updated_bank = []
for item in live7.TRIVIAL_BANK:
    if item["id"] == "sodium_hydroxide":
        names = tuple(dict.fromkeys(tuple(item["names"]) + ("каустическая сода",)))
        item = {**item, "names": names}
    _updated_bank.append(item)

_existing_ids = {item["id"] for item in _updated_bank}
if "sodium_chloride" not in _existing_ids:
    _updated_bank.append({
        "id": "sodium_chloride",
        "formula": "NaCl",
        "names": ("поваренная соль",),
    })

if "sodium_carbonate" not in _existing_ids:
    _updated_bank.append({
        "id": "sodium_carbonate",
        "formula": "Na₂CO₃",
        "names": ("кальцинированная сода",),
    })

live7.TRIVIAL_BANK = tuple(_updated_bank)
live7.TRIVIAL_BY_ID = {item["id"]: item for item in live7.TRIVIAL_BANK}


if __name__ == "__main__":
    live15.main()
