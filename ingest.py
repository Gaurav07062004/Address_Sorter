import io
from pathlib import Path


def read_lines(filename: str, data: bytes) -> list[str]:
    """Return non-empty text lines from txt / csv / xlsx / docx / pdf."""
    ext = Path(filename).suffix.lower()
    if ext == ".txt":
        lines = data.decode("utf-8", errors="ignore").splitlines()
    elif ext == ".docx":
        import docx
        lines = [p.text for p in docx.Document(io.BytesIO(data)).paragraphs]
    elif ext == ".pdf":
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            lines = [ln for page in pdf.pages for ln in (page.extract_text() or "").splitlines()]
    elif ext in (".xlsx", ".csv"):
        import pandas as pd
        df = (pd.read_csv(io.BytesIO(data), header=None) if ext == ".csv"
              else pd.read_excel(io.BytesIO(data), header=None))
        lines = df.iloc[:, 0].dropna().astype(str).tolist()   # first column = one address per row
    else:
        raise ValueError(f"Unsupported file type: {ext}")
    return [ln.strip() for ln in lines if ln.strip()]
