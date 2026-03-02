import keyring

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