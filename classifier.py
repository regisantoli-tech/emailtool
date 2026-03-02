import re
from typing import Dict, Tuple, Optional

PASSWORD_RECOVERY_PATTERNS = [
    r"reset\s+password",
    r"password\s+reset",
    r"forgot\s+password",
    r"recupera(r|ção)\s+de\s+senha",
    r"redefini(r|ção)\s+de\s+senha",
    r"c[oó]digo\s+de\s+verifica[cç][aã]o",
    r"one[-\s]?time\s+password",
    r"\bOTP\b",
    r"c[oó]digo\s+de\s+seguran[cç]a",
]

SUBSCRIPTION_PATTERNS = [
    r"assinatura",
    r"subscription",
    r"your\s+plan",
    r"renova[cç][aã]o",
    r"trial",
    r"teste\s+gr[aá]tis",
    r"pagamento\s+recorrente",
    r"unsubscribe",
    r"descadastrar",
    r"cancelar\s+assinatura",
]

SERVICE_HINTS = [
    ("google", ["google", "gmail", "google workspace"]),
    ("microsoft", ["microsoft", "outlook", "office 365", "azure", "entra"]),
    ("amazon", ["amazon", "aws"]),
    ("meta", ["facebook", "instagram", "meta"]),
    ("apple", ["apple", "icloud"]),
    ("linkedin", ["linkedin"]),
    ("github", ["github"]),
]

def _norm(text: str) -> str:
    return (text or "").lower()

def _find_service(text: str) -> Optional[str]:
    t = _norm(text)
    for service, keys in SERVICE_HINTS:
        if any(k in t for k in keys):
            return service
    return None

def _snippet_around(text: str, keywords_regex: str, max_len: int = 220) -> str:
    t = (text or "").replace("\r", " ")
    m = re.search(keywords_regex, t, flags=re.IGNORECASE)
    if not m:
        return t.strip()[:max_len]
    start = max(0, m.start() - 80)
    end = min(len(t), m.end() + 120)
    snip = t[start:end].strip()
    return (snip[:max_len] + "…") if len(snip) > max_len else snip

def classify_email(email_obj: Dict) -> Tuple[str, Optional[str], str]:
    subject = _norm(email_obj.get("subject", ""))
    body = _norm(email_obj.get("body", ""))
    hay = subject + "\n" + body

    if any(re.search(p, hay, flags=re.IGNORECASE) for p in PASSWORD_RECOVERY_PATTERNS):
        service = _find_service(hay)
        snippet = _snippet_around(email_obj.get("body", ""), r"reset|redefin|recuper|OTP|c[oó]digo|password")
        return "password_recovery", service, snippet

    if any(re.search(p, hay, flags=re.IGNORECASE) for p in SUBSCRIPTION_PATTERNS):
        service = _find_service(hay)
        snippet = _snippet_around(email_obj.get("body", ""), r"assinatura|subscription|unsubscribe|renova|trial|cancel")
        return "subscription", service, snippet

    service = _find_service(hay)
    snippet = _snippet_around(email_obj.get("body", ""), r".", max_len=180)
    return "other", service, snippet