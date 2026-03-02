#!/usr/bin/env python3
import os
import sys
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def write_file(path, content):
    path = ROOT / path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')

# ============ ARQUIVOS ============

requirements = """fastapi
uvicorn
jinja2
python-multipart
pydantic
pandas
openpyxl
beautifulsoup4
keyring
pyinstaller"""

config_py = """import json
from pathlib import Path

DEFAULT_CONFIG = {
    "host": "127.0.0.1",
    "port": 8001,
    "open_browser": True
}

def config_path() -> Path:
    return Path(__file__).resolve().parent / "config.json"

def load_config() -> dict:
    path = config_path()
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
        return DEFAULT_CONFIG.copy()
    try:
        return {**DEFAULT_CONFIG, **json.loads(path.read_text(encoding="utf-8"))}
    except Exception:
        return DEFAULT_CONFIG.copy()
"""

run_app_py = """import time
import webbrowser
import threading
import urllib.request
import uvicorn
from config import load_config

def wait_health(url: str, timeout_s: int = 20) -> bool:
    deadline = time.time() + timeout_s
    while True:
        now = time.time()
        if now >= deadline:
            return False
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.25)

def start_server(host: str, port: int):
    from main import app
    uvicorn.run(app, host=host, port=port, log_level="info")

def main():
    cfg = load_config()
    host = cfg.get("host", "127.0.0.1")
    port = int(cfg.get("port", 8001))
    open_browser = bool(cfg.get("open_browser", True))
    th = threading.Thread(target=start_server, args=(host, port), daemon=True)
    th.start()
    base = f"http://{host}:{port}"
    ok = wait_health(f"{base}/health", timeout_s=25)
    if open_browser and ok:
        webbrowser.open(base)
    th.join()

if __name__ == "__main__":
    main()
"""

auth_store_py = """import keyring
SERVICE_NAME = "EmailToolIMAP"

def save_password(email_addr: str, app_password: str) -> None:
    keyring.set_password(SERVICE_NAME, email_addr, app_password)

def load_password(email_addr: str) -> str | None:
    return keyring.get_password(SERVICE_NAME, email_addr)

def delete_password(email_addr: str) -> None:
    try:
        keyring.delete_password(SERVICE_NAME, email_addr)
    except Exception:
        pass
"""

classifier_py = """import re
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
    hay = subject + "\\n" + body

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
"""

excel_export_py = """from typing import List, Dict
from datetime import datetime
import pandas as pd

def export_to_excel(rows: List[Dict]) -> str:
    df = pd.DataFrame(rows)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = f"emails_{ts}.xlsx"
    preferred = ["uid", "conta", "data", "remetente", "assunto", "pasta", "categoria", "servico", "trecho"]
    cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
    df = df[cols]
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Emails")
        if "categoria" in df.columns:
            for cat, name in [("password_recovery", "Recuperacao_Senha"), ("subscription", "Assinaturas"), ("other", "Outros")]:
                sub = df[df["categoria"] == cat].copy()
                if not sub.empty:
                    sub.to_excel(writer, index=False, sheet_name=name)
    return path
"""

imap_client_py = """from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import imaplib, ssl, email
from email.header import decode_header
from bs4 import BeautifulSoup

@dataclass
class IMAPConfig:
    server: str
    user: str
    password: str
    default_mailbox: str = "INBOX"
    trash_mailbox: str = "Trash"

class IMAPClient:
    def __init__(self, cfg: IMAPConfig):
        self.cfg = cfg
        self.mail = None
        self._connect()

    def _connect(self) -> None:
        ctx = ssl.create_default_context()
        self.mail = imaplib.IMAP4_SSL(self.cfg.server, ssl_context=ctx)
        self.mail.login(self.cfg.user, self.cfg.password)

    def _select(self, folder: Optional[str]) -> str:
        mailbox = folder or self.cfg.default_mailbox
        status, _ = self.mail.select(mailbox)
        if status != "OK":
            raise RuntimeError(f"Falha ao selecionar mailbox: {mailbox}")
        return mailbox

    def list_folders(self) -> List[str]:
        status, data = self.mail.list()
        if status != "OK":
            return []
        folders = []
        for line in data:
            if not line:
                continue
            s = line.decode(errors="ignore")
            parts = s.split(' "/" ')
            if len(parts) == 2:
                folders.append(parts[1].strip().strip('"'))
        return sorted(list(set(folders)))

    def create_folder(self, folder: str) -> None:
        status, _ = self.mail.create(folder)
        if status != "OK":
            raise RuntimeError(f"Não foi possível criar a pasta: {folder}")

    def _decode_mime_header(self, value: Optional[str]) -> str:
        if not value:
            return ""
        decoded = decode_header(value)
        out = []
        for chunk, enc in decoded:
            if isinstance(chunk, bytes):
                out.append(chunk.decode(enc or "utf-8", errors="ignore"))
            else:
                out.append(str(chunk))
        return "".join(out)

    def _extract_text_body(self, msg: email.message.Message) -> str:
        if msg.is_multipart():
            html_fallback = None
            for part in msg.walk():
                ctype = part.get_content_type()
                disp = str(part.get("Content-Disposition") or "").lower()
                if "attachment" in disp:
                    continue
                payload = part.get_payload(decode=True)
                if not payload:
                    continue
                if ctype == "text/plain":
                    return payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
                if ctype == "text/html" and html_fallback is None:
                    html_fallback = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
            if html_fallback:
                soup = BeautifulSoup(html_fallback, "html.parser")
                return soup.get_text(" ", strip=True)
            return ""
        payload = msg.get_payload(decode=True) or b""
        return payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")

    def _build_search_criteria(self, start_date: Optional[str], end_date: Optional[str], body_search: Optional[str]) -> List[str]:
        criteria = []
        if start_date:
            criteria += ["SINCE", start_date]
        if end_date:
            criteria += ["BEFORE", end_date]
        if body_search:
            criteria += ["BODY", body_search]
        if not criteria:
            criteria = ["ALL"]
        return criteria

    def _search_uids(self, folder: Optional[str], start_date: Optional[str], end_date: Optional[str], body_search: Optional[str]) -> List[bytes]:
        self._select(folder)
        criteria = self._build_search_criteria(start_date, end_date, body_search)
        status, data = self.mail.uid("SEARCH", None, *criteria)
        if status != "OK":
            return []
        raw = data[0] or b""
        return [x for x in raw.split() if x.strip()]

    def fetch_emails_page(self, page: int, limit: int, folder: Optional[str], start_date: Optional[str], end_date: Optional[str], body_search: Optional[str]) -> Dict[str, Any]:
        uids = self._search_uids(folder, start_date, end_date, body_search)
        total = len(uids)
        uids = list(reversed(uids))
        start = (page - 1) * limit
        end = start + limit
        page_uids = uids[start:end]
        items = []
        for uid in page_uids:
            e = self._fetch_email_summary(uid, folder)
            if e:
                items.append(e)
        return {"items": items, "total": total}

    def fetch_emails_for_export(self, folder: Optional[str], start_date: Optional[str], end_date: Optional[str], body_search: Optional[str], max_items: int = 5000) -> List[Dict[str, Any]]:
        uids = self._search_uids(folder, start_date, end_date, body_search)
        uids = list(reversed(uids))[:max_items]
        out = []
        for uid in uids:
            e = self._fetch_email_summary(uid, folder)
            if e:
                out.append(e)
        return out

    def _fetch_email_summary(self, uid: bytes, folder: Optional[str]) -> Optional[Dict[str, Any]]:
        self._select(folder)
        status, data = self.mail.uid("FETCH", uid, "(BODY.PEEK[])")
        if status != "OK" or not data or not data[0]:
            return None
        raw = data[0][1]
        msg = email.message_from_bytes(raw)
        subject = self._decode_mime_header(msg.get("Subject"))
        sender = self._decode_mime_header(msg.get("From"))
        date = msg.get("Date") or ""
        body = self._extract_text_body(msg)
        return {
            "uid": uid.decode(errors="ignore"),
            "date": date,
            "sender": sender,
            "subject": subject,
            "body": body,
            "folder": folder or self.cfg.default_mailbox,
        }

    def permanent_delete(self, uids: List[str]) -> None:
        self._select(None)
        for uid in uids:
            self.mail.uid("STORE", uid, "+FLAGS", r"(\Deleted)")
        self.mail.expunge()

    def move_to_trash(self, uids: List[str]) -> None:
        self.move_to_folder(uids, self.cfg.trash_mailbox)

    def move_to_folder(self, uids: List[str], folder: str) -> None:
        self._select(None)
        for uid in uids:
            st, _ = self.mail.uid("COPY", uid, folder)
            if st != "OK":
                self.create_folder(folder)
                st2, _ = self.mail.uid("COPY", uid, folder)
                if st2 != "OK":
                    raise RuntimeError(f"Falha ao mover UID {uid} para {folder}")
            self.mail.uid("STORE", uid, "+FLAGS", r"(\Deleted)")
        self.mail.expunge()
"""

main_py = """import secrets
from typing import List, Optional, Literal
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from imap_client import IMAPClient, IMAPConfig
from classifier import classify_email
from excel_export import export_to_excel
from auth_store import save_password, load_password

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

ActionType = Literal["delete", "trash", "move", "create_folder"]
SESSIONS = {}
COOKIE_NAME = "emailtool_session"

class EmailItem(BaseModel):
    uid: str
    date: str
    sender: str
    subject: str
    folder: str
    category: str
    service: Optional[str] = None
    snippet: str

class EmailsResponse(BaseModel):
    items: List[EmailItem]
    page: int
    limit: int
    total: int

class ActionRequest(BaseModel):
    action: ActionType
    folder: Optional[str] = None
    uids: List[str] = Field(min_length=1)

class LoginRequest(BaseModel):
    email: str
    app_password: str
    imap_server: str = "imap.gmail.com"
    mailbox: str = "INBOX"
    trash: str = "[Gmail]/Trash"
    remember: bool = True

def get_imap_client(request: Request) -> IMAPClient:
    session_id = request.cookies.get(COOKIE_NAME)
    if not session_id or session_id not in SESSIONS:
        raise HTTPException(status_code=401, detail="Não autenticado. Acesse /login.")
    s = SESSIONS[session_id]
    password = load_password(s["email"])
    if not password:
        raise HTTPException(status_code=401, detail="Senha não encontrada no cofre do Windows. Faça login novamente.")
    cfg = IMAPConfig(
        server=s["server"],
        user=s["email"],
        password=password,
        default_mailbox=s["mailbox"],
        trash_mailbox=s["trash"],
    )
    return IMAPClient(cfg)

@app.get("/health")
async def health():
    return JSONResponse({"ok": True})

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/auth/login")
async def do_login(req: LoginRequest, response: Response):
    if req.remember:
        save_password(req.email, req.app_password)
    session_id = secrets.token_urlsafe(24)
    SESSIONS[session_id] = {
        "email": req.email,
        "server": req.imap_server,
        "mailbox": req.mailbox,
        "trash": req.trash,
    }
    response.set_cookie(COOKIE_NAME, session_id, httponly=True, samesite="lax")
    return {"status": "success"}

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    session_id = request.cookies.get(COOKIE_NAME)
    if not session_id or session_id not in SESSIONS:
        return RedirectResponse(url="/login")
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/emails", response_model=EmailsResponse)
async def list_emails(
    request: Request,
    page: int = 1,
    limit: int = 100,
    folder: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
):
    client = get_imap_client(request)
    data = client.fetch_emails_page(
        page=page,
        limit=limit,
        folder=folder,
        start_date=start_date,
        end_date=end_date,
        body_search=search,
    )
    items: List[EmailItem] = []
    for e in data["items"]:
        cat, service, snippet = classify_email(e)
        if category and cat != category:
            continue
        items.append(
            EmailItem(
                uid=e["uid"],
                date=e["date"],
                sender=e["sender"],
                subject=e["subject"],
                folder=e["folder"],
                category=cat,
                service=service,
                snippet=snippet,
            )
        )
    return EmailsResponse(items=items, page=page, limit=limit, total=data["total"])

@app.post("/actions/execute")
async def execute_action(req: ActionRequest, request: Request):
    client = get_imap_client(request)
    if req.action in ("move", "create_folder") and not req.folder:
        raise HTTPException(status_code=400, detail="folder é obrigatório para move/create_folder.")
    if req.action == "create_folder":
        client.create_folder(req.folder)
        return {"status": "success"}
    if req.action == "delete":
        client.permanent_delete(req.uids)
        return {"status": "success"}
    if req.action == "trash":
        client.move_to_trash(req.uids)
        return {"status": "success"}
    if req.action == "move":
        client.move_to_folder(req.uids, req.folder)
        return {"status": "success"}
    raise HTTPException(status_code=400, detail="Ação inválida.")

@app.get("/export")
async def export_xlsx(
    request: Request,
    folder: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    search: Optional[str] = None,
    category: Optional[str] = None,
    max_items: int = 5000,
):
    client = get_imap_client(request)
    emails = client.fetch_emails_for_export(
        folder=folder,
        start_date=start_date,
        end_date=end_date,
        body_search=search,
        max_items=max_items,
    )
    rows = []
    for e in emails:
        cat, service, snippet = classify_email(e)
        if category and cat != category:
            continue
        rows.append(
            {
                "uid": e["uid"],
                "conta": client.cfg.user,
                "data": e["date"],
                "remetente": e["sender"],
                "assunto": e["subject"],
                "pasta": e["folder"],
                "categoria": cat,
                "servico": service,
                "trecho": snippet,
            }
        )
    file_path = export_to_excel(rows)
    return FileResponse(
        file_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename="emails.xlsx",
    )
"""

style_css = """:root{--bg:#0b0b0f;--text:rgba(255,255,255,.92);--muted:rgba(255,255,255,.62);--stroke:rgba(255,255,255,.12);--accent:#0a84ff;--danger:#ff453a;--shadow:0 20px 60px rgba(0,0,0,.55);--radius2:22px}*{box-sizing:border-box}html,body{height:100%}body{margin:0;font-family:ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial;background:radial-gradient(1200px 600px at 20% 10%,rgba(10,132,255,.22),transparent 60%),radial-gradient(900px 500px at 90% 30%,rgba(100,210,255,.16),transparent 55%),radial-gradient(900px 500px at 50% 90%,rgba(48,209,88,.10),transparent 55%),var(--bg);color:var(--text)}.container{max-width:1180px;margin:0 auto;padding:26px 18px 40px}.topbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px}.brand{display:flex;align-items:center;gap:10px;font-weight:650}.badge{font-size:12px;padding:6px 10px;border:1px solid var(--stroke);border-radius:999px;background:rgba(255,255,255,.04);color:var(--muted)}.grid{display:grid;grid-template-columns:420px 1fr;gap:16px}@media (max-width:980px){.grid{grid-template-columns:1fr}}.card{background:linear-gradient(180deg,rgba(255,255,255,.07),rgba(255,255,255,.05));border:1px solid var(--stroke);border-radius:var(--radius2);box-shadow:var(--shadow);backdrop-filter:blur(14px)}.card .hd{padding:16px 16px 10px;border-bottom:1px solid rgba(255,255,255,.08);display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.hd h2{margin:0;font-size:14px;font-weight:650;color:rgba(255,255,255,.86)}.hd .sub{margin-top:6px;font-size:12px;color:var(--muted);line-height:1.35}.card .bd{padding:14px 16px 16px}.field{display:flex;flex-direction:column;gap:6px;margin:10px 0}.field label{font-size:12px;color:var(--muted)}.input,select{width:100%;padding:10px 12px;border-radius:12px;border:1px solid var(--stroke);background:rgba(0,0,0,.22);color:var(--text);outline:none}.row2{display:grid;grid-template-columns:1fr 1fr;gap:10px}@media (max-width:520px){.row2{grid-template-columns:1fr}}.btns{display:flex;gap:10px;flex-wrap:wrap;margin-top:10px}.btn{padding:10px 12px;border-radius:12px;border:1px solid var(--stroke);background:rgba(255,255,255,.06);color:var(--text);cursor:pointer;font-weight:600}.btn:hover{background:rgba(255,255,255,.10)}.btn.primary{background:linear-gradient(180deg,rgba(10,132,255,.95),rgba(10,132,255,.78));border-color:rgba(10,132,255,.35)}.btn.danger{background:linear-gradient(180deg,rgba(255,69,58,.95),rgba(255,69,58,.72));border-color:rgba(255,69,58,.35)}.table-wrap{overflow:auto;border-radius:16px;border:1px solid rgba(255,255,255,.08)}table{width:100%;border-collapse:collapse;min-width:980px;background:rgba(0,0,0,.18)}th,td{padding:10px 10px;border-bottom:1px solid rgba(255,255,255,.08);vertical-align:top;font-size:13px}th{position:sticky;top:0;background:rgba(20,20,26,.92);backdrop-filter:blur(10px);z-index:1;text-align:left;font-size:12px;color:rgba(255,255,255,.72)}.muted{color:var(--muted);font-size:12px}.small{font-size:12px;color:var(--muted)}.code{font-family:monospace}.pager{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-top:12px}.hr{height:1px;background:rgba(255,255,255,.08);margin:12px 0}"""

login_html = """<!DOCTYPE html><html lang="pt-br"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width, initial-scale=1.0"/><title>EmailTool • Login</title><link rel="stylesheet" href="/static/style.css"></head><body><div class="container"><div class="topbar"><div class="brand">EmailTool <span class="badge">IMAP • Gmail</span></div><div class="badge">Localhost</div></div><div class="card"><div class="hd"><div><h2>Conectar conta</h2><div class="sub">Use <b>Senha de app</b> (16 caracteres). Não use sua senha normal do Gmail.</div></div></div><div class="bd"><div class="row2"><div class="field"><label>E-mail</label><input class="input" id="email" placeholder="seuemail@gmail.com" autocomplete="username"></div><div class="field"><label>Senha de app</label><input class="input" id="pass" type="password" placeholder="xxxx xxxx xxxx xxxx" autocomplete="current-password"></div></div><div class="row2"><div class="field"><label>Servidor IMAP</label><input class="input" id="server" value="imap.gmail.com"></div><div class="field"><label>Mailbox</label><input class="input" id="mailbox" value="INBOX"></div></div><div class="field"><label>Lixeira</label><input class="input" id="trash" value="[Gmail]/Trash"></div><div class="field" style="flex-direction:row;align-items:center;gap:10px;"><input id="remember" type="checkbox" checked><label for="remember" style="margin:0;">Salvar senha no Windows (Credential Manager)</label></div><div class="btns"><button class="btn primary" onclick="login()">Entrar</button></div><div class="small" id="status"></div></div></div></div><script>async function login(){const payload={email:document.getElementById("email").value.trim(),app_password:document.getElementById("pass").value,imap_server:document.getElementById("server").value.trim(),mailbox:document.getElementById("mailbox").value.trim(),trash:document.getElementById("trash").value.trim(),remember:document.getElementById("remember").checked};document.getElementById("status").textContent="Conectando...";const res=await fetch("/auth/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});if(!res.ok){let msg="Falha no login.";try{const err=await res.json();msg=err.detail||msg;}catch{}document.getElementById("status").textContent=msg;return;}window.location.href="/";}</script></body></html>"""

index_html = """<!DOCTYPE html><html lang="pt-br"><head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width, initial-scale=1.0"/><title>EmailTool • Caixa</title><link rel="stylesheet" href="/static/style.css"></head><body><div class="container"><div class="topbar"><div class="brand">EmailTool <span class="badge">Operações em lote</span></div><div class="badge" id="kpi_status">Status: pronto</div></div><div class="grid"><div class="card"><div class="hd"><div><h2>Filtros</h2><div class="sub">Datas em formato IMAP (ex.: <span class="code">01-Jan-2026</span>).</div></div></div><div class="bd"><div class="field"><label>Pasta (opcional)</label><input class="input" id="folder" placeholder="INBOX (ou vazio)"></div><div class="row2"><div class="field"><label>Data inicial (SINCE)</label><input class="input" id="start_date" placeholder="01-Jan-2026"></div><div class="field"><label>Data final (BEFORE)</label><input class="input" id="end_date" placeholder="01-Feb-2026"></div></div><div class="field"><label>Buscar no corpo (BODY)</label><input class="input" id="search" placeholder="Ex.: reset password, OTP, assinatura, invoice..."></div><div class="field"><label>Categoria</label><select id="category"><option value="">Todas</option><option value="password_recovery">Recuperação de senha</option><option value="subscription">Assinaturas</option><option value="other">Outros</option></select></div><div class="btns"><button class="btn primary" onclick="loadEmails(1)">Filtrar</button><button class="btn" onclick="loadEmails(1)">Recarregar</button></div><div class="hr"></div><div class="field"><label>Ação em lote</label><select id="bulk_action"><option value="trash">Enviar para lixeira</option><option value="move">Mover para pasta</option><option value="delete">Excluir definitivamente</option><option value="create_folder">Criar pasta</option></select></div><div class="field"><label>Pasta destino (se aplicável)</label><input class="input" id="target_folder" placeholder="Ex.: Assinaturas/Netflix"></div><div class="btns"><button class="btn danger" onclick="executeAction()">Executar</button><button class="btn" onclick="exportXlsx()">Exportar XLSX</button></div><div class="small" id="status"></div></div></div><div class="card"><div class="hd"><div><h2>E-mails</h2><div class="sub">Marque itens e execute ações em lote. Exportar respeita os filtros.</div></div><div class="badge">Página <span class="code" id="page">1</span> • Total <span class="code" id="total">0</span></div></div><div class="bd"><div class="table-wrap"><table><thead><tr><th style="width:36px;"><input type="checkbox" id="select_all"/></th><th style="width:190px;">Data</th><th style="width:240px;">Remetente</th><th>Assunto</th><th style="width:170px;">Categoria</th><th style="width:280px;">Trecho</th></tr></thead><tbody id="tbody"></tbody></table></div><div class="pager"><button class="btn" onclick="prevPage()">Anterior</button><div class="muted">Refine nos filtros à esquerda.</div><button class="btn" onclick="nextPage()">Próxima</button></div></div></div></div></div><script src="/static/app.js"></script></body></html>"""

app_js = """let currentPage = 1;
const limit = 100;
function qs(id){return document.getElementById(id);}
function setStatus(t){const el=qs("status"); if(el) el.textContent=t;}
function buildParams(page){
  const p=new URLSearchParams();
  p.set("page", page);
  p.set("limit", limit);
  const folder=(qs("folder")?.value||"").trim();
  const start_date=(qs("start_date")?.value||"").trim();
  const end_date=(qs("end_date")?.value||"").trim();
  const search=(qs("search")?.value||"").trim();
  const category=qs("category")?.value||"";
  if(folder) p.set("folder", folder);
  if(start_date) p.set("start_date", start_date);
  if(end_date) p.set("end_date", end_date);
  if(search) p.set("search", search);
  if(category) p.set("category", category);
  return p;
}
function escapeHtml(s){
  return String(s).replaceAll("&","&amp;").replaceAll("&lt;","&lt;").replaceAll(">","&gt;").replaceAll('"',"&quot;");
}
function selectedUids(){
  return Array.from(document.querySelectorAll(".cb:checked")).map(x=>x.value);
}
async function loadEmails(page){
  currentPage=page;
  setStatus("Carregando...");
  const params=buildParams(page);
  const res=await fetch(`/emails?${params.toString()}`);
  if(!res.ok){
    let msg="Erro ao carregar.";
    try{msg=(await res.json()).detail||msg;}catch{}
    setStatus(msg);
    return;
  }
  const data=await res.json();
  const tbody=qs("tbody");
  tbody.innerHTML="";
  (data.items||[]).forEach(item=>{
    const tr=document.createElement("tr");
    tr.innerHTML=`<td><input type="checkbox" class="cb" value="${escapeHtml(item.uid)}"/></td><td>${escapeHtml(item.date||"")}</td><td>${escapeHtml(item.sender||"")}</td><td>${escapeHtml(item.subject||"")}</td><td>${escapeHtml(item.category||"")}${item.service ? "<div class='muted'>"+escapeHtml(item.service)+"</div>" : ""}</td><td>${escapeHtml(item.snippet||"")}</td>`;
    tbody.appendChild(tr);
  });
  qs("page").textContent=String(data.page||page);
  qs("total").textContent=String(data.total||0);
  qs("select_all").checked=false;
  setStatus(`Itens nesta página: ${(data.items||[]).length}`);
}
async function executeAction(){
  const action=qs("bulk_action").value;
  const folder=(qs("target_folder").value||"").trim();
  const uids=selectedUids();
  if(uids.length===0){alert("Selecione pelo menos 1 e-mail."); return;}
  if(action==="delete"){const ok=confirm("ATENÇÃO: isso vai excluir definitivamente. Deseja continuar?"); if(!ok) return;}
  if((action==="move"||action==="create_folder") && !folder){alert("Informe a pasta destino."); return;}
  setStatus("Executando...");
  const res=await fetch("/actions/execute",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action, folder, uids})});
  if(!res.ok){let msg="Falha ao executar.";try{msg=(await res.json()).detail||msg;}catch{}alert(msg);setStatus("Falha.");return;}
  await loadEmails(currentPage);
  setStatus("Concluído.");
}
function exportXlsx(){
  const params=buildParams(1);
  params.delete("page");
  params.delete("limit");
  window.location.href = `/export?${params.toString()}`;
}
function prevPage(){ if(currentPage == 1) return; loadEmails(currentPage - 1); }
function nextPage(){ loadEmails(currentPage + 1); }
document.addEventListener("DOMContentLoaded", ()=>{
  const sel=qs("select_all");
  if(sel){
    sel.addEventListener("change", (e)=>{
      const checked=e.target.checked;
      document.querySelectorAll(".cb").forEach(cb=>cb.checked=checked);
    });
  }
  loadEmails(1);
});
"""

# ============ ESCRITA ============

print("📝 Criando arquivos...")
write_file("requirements.txt", requirements)
write_file("config.py", config_py)
write_file("run_app.py", run_app_py)
write_file("auth_store.py", auth_store_py)
write_file("classifier.py", classifier_py)
write_file("excel_export.py", excel_export_py)
write_file("imap_client.py", imap_client_py)
write_file("main.py", main_py)
write_file("static/style.css", style_css)
write_file("static/app.js", app_js)
write_file("templates/login.html", login_html)
write_file("templates/index.html", index_html)

# ============ VENV ============

venv_path = ROOT / ".venv"
if not (venv_path / "Scripts" / "python.exe").exists():
    print("📦 Criando ambiente virtual...")
    subprocess.run([sys.executable, "-m", "venv", str(venv_path)], check=True)

python_exe = str(venv_path / "Scripts" / "python.exe")

print("📥 Instalando dependências...")
subprocess.run([python_exe, "-m", "pip", "install", "--upgrade", "pip"], check=True, capture_output=True)
subprocess.run([python_exe, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=True, capture_output=True)

# ============ CONFIG ============

config_file = ROOT / "config.json"
if not config_file.exists():
    config_file.write_text(json.dumps({"host": "127.0.0.1", "port": 8001, "open_browser": True}, indent=2))

# ============ BUILD ============

if "--build-exe" in sys.argv:
    print("🏗️ Gerando executável...")
    for d in ["build", "dist"]:
        p = ROOT / d
        if p.exists():
            import shutil
            shutil.rmtree(p)
    spec = ROOT / "EmailTool.spec"
    if spec.exists():
        spec.unlink()
    
    subprocess.run([
        python_exe, "-m", "PyInstaller",
        "--onefile", "--name", "EmailTool",
        "--add-data", f"{ROOT / 'templates'};templates",
        "--add-data", f"{ROOT / 'static'};static",
        str(ROOT / "run_app.py")
    ], check=True)
    
    (ROOT / "dist" / "config.json").write_text(config_file.read_text())
    print(f"✅ OK: {ROOT / 'dist' / 'EmailTool.exe'}")
else:
    print("🚀 Iniciando aplicação...")
    subprocess.run([python_exe, str(ROOT / "run_app.py")], check=True)