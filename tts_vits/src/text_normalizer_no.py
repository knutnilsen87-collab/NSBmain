import re
def normalize_no(text: str) -> str:
    t = text.strip()
    t = re.sub(r"\s+", " ", t)
    return t
