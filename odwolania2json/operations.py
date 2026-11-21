"""Operacje stosowane przez reguły ekstrakcji."""
import re
from datetime import date

from .model import FLAGS

MONTHS = ("stycznia lutego marca kwietnia maja czerwca lipca sierpnia "
          "września października listopada grudnia").split()
DATE = (r"(?:20\d{2}[-./]\d{1,2}[-./]\d{1,2}|\d{1,2}[-./]\d{1,2}[-./]20\d{2}|"
        + r"\d{1,2}[ \t\n]+(?:" + "|".join(MONTHS) + r")[ \t\n]+20\d{2})")


def normalize_date(value):
    parts = re.split(r"[-./ ]+", value.casefold().strip())
    if len(parts) != 3:
        return None
    try:
        if len(parts[0]) == 4:
            year, month, day = map(int, parts)
        else:
            day, year = int(parts[0]), int(parts[2])
            month = int(parts[1]) if parts[1].isdigit() else MONTHS.index(parts[1]) + 1
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def normalize(value, operation):
    value = " ".join(value.split())
    if not value:
        return None
    if operation == "date":
        return normalize_date(value)
    if operation == "digits":
        return re.sub(r"\D", "", value) or None
    if operation == "money":
        number = re.sub(r"[^0-9,.\-]", "", value)
        if re.search(r"[,.]\d{2}$", number):
            number = re.sub(r"[,.]", "", number[:-3]) + "." + number[-2:]
        else:
            number = re.sub(r"[,.]", "", number)
        try:
            return float(number)
        except ValueError:
            return None
    if operation == "integer":
        return int(value) if value.isdecimal() else None
    if operation == "compact":
        return re.sub(r"\s", "", value)
    if operation == "ted":
        issued = re.fullmatch(r"(20\d{2})\s*/\s*S\s*\d{1,3}\s*-\s*(\d{5,8})", value, FLAGS)
        if issued:
            return f"{issued[2]}-{issued[1]}"
        return re.sub(r"\s", "", value)
    if operation == "identifier":
        return value.rstrip(".")
    if operation == "title":
        quoted = re.fullmatch(r"[„“\"](.+?)[”\"]\.?", value)
        return quoted[1] if quoted else value
    if operation == "text":
        return value
    raise ValueError(f"Nieznana operacja {operation}")


def apply_fields(result, fields, text, offset=0, prefix=()):
    for name, rules in fields.items():
        for rule in rules:
            pattern = rule["pattern"].replace("<DATE>", DATE)
            for match in re.finditer(pattern, text, FLAGS):
                value = normalize(match.group(1), rule.get("operation", "text"))
                if value is not None:
                    result.put((*prefix, *name.split(".")), value, offset + match.start(1), rule["name"])
                    break
            else:
                continue
            break
