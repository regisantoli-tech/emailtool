from typing import List, Dict
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