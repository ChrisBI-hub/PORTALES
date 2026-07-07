from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


# Columnas que deben normalizarse a formato AAAA/MM/DD.
DATE_COLUMNS = [
    "FECHA",
    "FECHA_RECEPCION",
    "FECHA_VALIDACION_LISTAS_NEGRAS",
    "FECHATIMBRADO",
]


def normalize_date_value(value: object) -> object:
    """Convierte valores tipo AAAAMMDD a AAAA/MM/DD sin tocar otros formatos."""
    if pd.isna(value):
        return value

    text = str(value).strip()

    if "/" in text:
        return text

    if text.endswith(".0"):
        text = text[:-2]

    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}/{text[4:6]}/{text[6:8]}"

    return value


def format_dataframe_dates(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica el formato de fecha a las columnas existentes en el DataFrame."""
    updated = df.copy()
    for column in DATE_COLUMNS:
        if column in updated.columns:
            updated[column] = updated[column].map(normalize_date_value)
    return updated


def resolve_input_path(argv: list[str]) -> Path:
    """Resuelve el archivo de entrada a partir de argumentos o valores por defecto."""
    if len(argv) > 1:
        input_path = Path(argv[1]).expanduser().resolve()
        if not input_path.exists():
            raise FileNotFoundError(f"No se encontró el archivo de entrada: {input_path}")
        return input_path

    for candidate_name in ("detecno_pedimento.xlsx", "detecno_separado.xlsx", "detecno.xlsx"):
        candidate = Path(candidate_name)
        if candidate.exists():
            return candidate.resolve()

    candidates = sorted(
        Path(".").glob("*.xlsx"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0].resolve()

    raise FileNotFoundError("No se encontró ningún archivo XLSX para procesar.")


def resolve_output_path(input_path: Path, argv: list[str]) -> Path:
    """Resuelve el archivo de salida."""
    if len(argv) > 2:
        return Path(argv[2]).expanduser().resolve()
    return input_path.with_name(f"{input_path.stem}_fechas.xlsx")


def process_workbook(input_path: Path, output_path: Path) -> None:
    """Normaliza columnas de fecha en todas las hojas del libro."""
    excel_file = pd.ExcelFile(input_path, engine="openpyxl")

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(input_path, sheet_name=sheet_name, engine="openpyxl")
            format_dataframe_dates(df).to_excel(writer, sheet_name=sheet_name, index=False)


def main(argv: list[str] | None = None) -> None:
    """Punto de entrada del script."""
    args = argv or sys.argv
    try:
        input_path = resolve_input_path(args)
        output_path = resolve_output_path(input_path, args)
        process_workbook(input_path, output_path)
        print(f"Archivo generado correctamente: {output_path}")
    except Exception as exc:
        print(f"Error al formatear fechas: {exc}")
        raise


if __name__ == "__main__":
    main()
