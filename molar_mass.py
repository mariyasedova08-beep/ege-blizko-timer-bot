import re
from collections import OrderedDict

# Школьные относительные атомные массы, согласованные с таблицей Марии.
# Численные значения молярной массы (г/моль) совпадают с Mr для формулы.
ATOMIC_MASSES = {
    "H": 1,
    "Li": 7,
    "K": 39,
    "Na": 23,
    "N": 14,
    "Ba": 137,
    "Ca": 40,
    "Mg": 24,
    "Sr": 88,
    "Al": 27,
    "Cr": 52,
    "Fe": 56,
    "Mn": 55,
    "Zn": 65,
    "Ag": 108,
    "Hg": 201,
    "Pb": 207,
    "Sn": 119,
    "Cu": 64,
    "O": 16,
    "F": 19,
    "Cl": 35.5,
    "Br": 80,
    "I": 127,
    "S": 32,
    "P": 31,
    "C": 12,
    "Si": 28,
}

_SUBSCRIPT_TO_ASCII = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")


class MolarMassError(ValueError):
    pass


def normalize_formula(value):
    text = str(value or "").strip().translate(_SUBSCRIPT_TO_ASCII)
    text = text.replace(" ", "")
    text = text.replace("·", ".").replace("•", ".")
    text = text.replace("[", "(").replace("]", ")")
    return text


def _read_number(text, index):
    end = index
    while end < len(text) and text[end].isdigit():
        end += 1
    if end == index:
        return 1, index
    value = int(text[index:end])
    if value <= 0:
        raise MolarMassError("Индекс элемента должен быть больше нуля.")
    return value, end


def _merge(target, source, multiplier=1):
    for element, count in source.items():
        target[element] = target.get(element, 0) + count * multiplier


def _parse_group(text, index=0, inside_parentheses=False):
    counts = OrderedDict()

    while index < len(text):
        char = text[index]

        if char == ")":
            if not inside_parentheses:
                raise MolarMassError("Лишняя закрывающая скобка.")
            return counts, index + 1

        if char == "(":
            nested, next_index = _parse_group(text, index + 1, True)
            multiplier, next_index = _read_number(text, next_index)
            _merge(counts, nested, multiplier)
            index = next_index
            continue

        if char.isupper():
            end = index + 1
            while end < len(text) and text[end].islower():
                end += 1
            element = text[index:end]
            if element not in ATOMIC_MASSES:
                raise MolarMassError(
                    f"Элемента {element} нет в загруженной таблице молярных масс."
                )
            multiplier, end = _read_number(text, end)
            counts[element] = counts.get(element, 0) + multiplier
            index = end
            continue

        raise MolarMassError(f"Не понимаю символ «{char}» в формуле.")

    if inside_parentheses:
        raise MolarMassError("В формуле не закрыта скобка.")
    return counts, index


def calculate_molar_mass(value):
    formula = normalize_formula(value)
    if not formula:
        raise MolarMassError("Формула пустая.")

    if any(symbol in formula for symbol in ("^", "+", "-")):
        raise MolarMassError("Введи формулу вещества без заряда и без коэффициента реакции.")

    total_counts = OrderedDict()
    parts = formula.split(".")

    for part_index, part in enumerate(parts):
        if not part:
            raise MolarMassError("Проверь точку/знак кристаллизационной воды в формуле.")

        coefficient = 1
        match = re.match(r"^(\d+)(.+)$", part)
        if match:
            if part_index == 0:
                raise MolarMassError("Убери коэффициент перед формулой вещества.")
            coefficient = int(match.group(1))
            part = match.group(2)

        counts, parsed_to = _parse_group(part)
        if parsed_to != len(part):
            raise MolarMassError("Не получилось полностью разобрать формулу.")
        _merge(total_counts, counts, coefficient)

    mass = sum(ATOMIC_MASSES[element] * count for element, count in total_counts.items())
    return {
        "formula": formula.replace(".", "·"),
        "counts": total_counts,
        "mass": mass,
    }


def _format_number(value):
    value = float(value)
    if value.is_integer():
        return str(int(value))
    return f"{value:g}"


def format_result(value):
    result = calculate_molar_mass(value)
    pieces = []
    for element, count in result["counts"].items():
        atomic = ATOMIC_MASSES[element]
        pieces.append(f"{count}×{_format_number(atomic)}")

    return (
        f"⚗️ {result['formula']}\n\n"
        f"M = {_format_number(result['mass'])} г/моль\n\n"
        f"Расчёт: {' + '.join(pieces)} = {_format_number(result['mass'])}"
    )
