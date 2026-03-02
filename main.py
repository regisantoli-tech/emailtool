import secrets
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
