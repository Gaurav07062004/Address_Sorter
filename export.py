import io
import pandas as pd

COLUMNS = ["Street 1", "Street 2", "City", "Locality"]


def to_excel_bytes(rows: list[dict], extra_columns: tuple = ()) -> bytes:
    df = pd.DataFrame(rows, columns=COLUMNS + list(extra_columns))
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        df.to_excel(xw, index=False, sheet_name="Addresses")
        ws = xw.sheets["Addresses"]
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = min(
                50, max(len(str(c.value or "")) for c in col) + 2)
    return buf.getvalue()
