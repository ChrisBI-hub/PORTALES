from __future__ import annotations

import os
from pathlib import Path

import pandas as pd


# Archivo de entrada por defecto.
INPUT_FILE = "Facturas_2026-06-29T121106.xlsx"

# Hoja esperada de entrada y nombre deseado en salida.
SOURCE_SHEET_NAME = "Facturas_Seleccionadas"
OUTPUT_SHEET_NAME = "Facturas_Seleccionadas"

# Mapeo de NOMBRE_RECEPTOR hacia hoja destino.
RECEPTOR_TO_SHEET = {
    "SANOFI PASTEUR": "SPA",
    "AZTECA VACUNAS": "AVA",
    "SANOFI MEXICO": "SME",
}

# Columnas obligatorias para el proceso.
REQUIRED_COLUMNS = [
    "FECHA",
    "TOTAL",
    "SERIE",
    "FOLIO",
    "FECHA_RECEPCION",
    "NOMBRE_RECEPTOR",
]

# Columnas que conservarán las hojas filtradas.
FILTERED_COLUMNS = [
    "FECHA",
    "TOTAL",
    "Folio_ABC",
    "FECHA_RECEPCION",
    "NOMBRE_RECEPTOR",
]


def build_folio_abc(df: pd.DataFrame) -> pd.Series:
    """Construye la columna Folio_ABC concatenando SERIE + FOLIO como texto."""
    serie = df["SERIE"].fillna("").astype(str).str.strip()
    folio = df["FOLIO"].fillna("").astype(str).str.strip()
    return serie + folio


def generate_filtered_sheets(df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Genera las hojas filtradas con la estructura solicitada."""
    sheets: dict[str, pd.DataFrame] = {}

    for receptor, sheet_name in RECEPTOR_TO_SHEET.items():
        filtered = df[df["NOMBRE_RECEPTOR"].astype(str).str.strip() == receptor].copy()
        if filtered.empty:
            continue

        filtered["Folio_ABC"] = build_folio_abc(filtered)
        sheets[sheet_name] = filtered[FILTERED_COLUMNS]

    return sheets


def find_source_sheet_name(excel_file: pd.ExcelFile) -> str:
    """Busca la hoja fuente exacta o una variante equivalente sin guiones bajos."""
    if SOURCE_SHEET_NAME in excel_file.sheet_names:
        return SOURCE_SHEET_NAME

    normalized_target = SOURCE_SHEET_NAME.replace("_", "").lower()
    for sheet_name in excel_file.sheet_names:
        normalized_sheet = sheet_name.replace("_", "").replace(" ", "").lower()
        if normalized_sheet == normalized_target:
            return sheet_name

    available = ", ".join(excel_file.sheet_names)
    raise ValueError(
        f"No se encontró la hoja '{SOURCE_SHEET_NAME}'. Hojas disponibles: {available}"
    )


def process_workbook(input_path: Path, output_path: Path | None = None) -> Path:
    """Lee el Excel, separa por receptor y genera un nuevo archivo XLSX."""
    if not input_path.exists():
        raise FileNotFoundError(f"No se encontró el archivo de entrada: {input_path}")

    excel_file = pd.ExcelFile(input_path, engine="openpyxl")
    source_sheet = find_source_sheet_name(excel_file)
    df = pd.read_excel(input_path, sheet_name=source_sheet, engine="openpyxl")

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing_columns:
        raise ValueError(
            "Faltan columnas obligatorias en la hoja de entrada: "
            + ", ".join(missing_columns)
        )

    output_path = output_path or input_path.with_name(f"{input_path.stem}_separado.xlsx")

    # Mantener el archivo original en la primera hoja y agregar las hojas filtradas.
    filtered_sheets = generate_filtered_sheets(df)
    ordered_sheet_names = [OUTPUT_SHEET_NAME, "SPA", "AVA", "SME"]

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name=OUTPUT_SHEET_NAME, index=False)
        for sheet_name in ordered_sheet_names[1:]:
            sheet_df = filtered_sheets.get(sheet_name)
            if sheet_df is None:
                # Crear una hoja vacía con la estructura requerida si no hay coincidencias.
                pd.DataFrame(columns=FILTERED_COLUMNS).to_excel(
                    writer, sheet_name=sheet_name, index=False
                )
            else:
                sheet_df.to_excel(writer, sheet_name=sheet_name, index=False)

    return output_path


def main() -> None:
    """Lee el Excel, separa por receptor y genera un nuevo archivo XLSX."""
    input_path = Path(INPUT_FILE)

    try:
        output_path = process_workbook(input_path)
        print(f"Archivo generado correctamente: {output_path}")

    except Exception as exc:
        print(f"Error al procesar el archivo: {exc}")
        raise


if __name__ == "__main__":
    main()
