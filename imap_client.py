from dataclasses import dataclass
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