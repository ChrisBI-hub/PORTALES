from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Iterable

import pandas as pd


# Archivos por defecto.
BASE_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_FILE = BASE_DIR / "Facturas_2026-06-29T121106_separado.xlsx"
DEFAULT_SQL_FILE = BASE_DIR / "prueba.sql"

# Nombres de hojas que el flujo anterior genera.
TARGET_SHEETS = ["Facturas_Seleccionadas", "SPA", "AVA", "SME"]

# Nombre de la nueva columna a agregar.
PEDIMENTO_COLUMN = "Pedimento"

# Conexión por defecto para ejecución local cuando no se definan variables de entorno.
DEFAULT_ODBC_DRIVER = "ODBC Driver 17 for SQL Server"
DEFAULT_ODBC_SERVER = "150.1.1.152"
DEFAULT_ODBC_DATABASE = "SIR"
DEFAULT_ODBC_UID = "ConsultaBD"
DEFAULT_ODBC_PWD = "5D$bc#kM&5W2T8J40?s%"


def resolve_input_file() -> Path:
    """Resuelve el archivo de entrada a procesar."""
    configured_path = os.getenv("PED_DETECNO_INPUT_FILE", "").strip()
    if configured_path:
        input_path = Path(configured_path).expanduser().resolve()
        if input_path.exists():
            return input_path
        raise FileNotFoundError(f"No existe el archivo de entrada: {input_path}")

    if DEFAULT_INPUT_FILE.exists():
        return DEFAULT_INPUT_FILE

    candidates = sorted(
        BASE_DIR.glob("*_separado.xlsx"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0]

    raise FileNotFoundError(
        "No se encontró un archivo de entrada. "
        "Define PED_DETECNO_INPUT_FILE o genera primero el archivo separado."
    )


def read_sql_template(sql_path: Path) -> str:
    """Lee la consulta base desde `prueba.sql`."""
    if not sql_path.exists():
        raise FileNotFoundError(f"No se encontró la consulta SQL: {sql_path}")
    return sql_path.read_text(encoding="utf-8")


def normalize_text_value(value: object) -> str:
    """Convierte valores de Excel a texto estable sin perder IDs numéricos."""
    if pd.isna(value):
        return ""

    if isinstance(value, str):
        cleaned = value.strip()
        if re.fullmatch(r"\d+\.0+", cleaned):
            return cleaned.split(".", 1)[0]
        return cleaned

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    return str(value).strip()


def build_connection_string() -> str:
    """Construye la cadena de conexión ODBC desde variables de entorno."""
    direct_connection_string = os.getenv("PED_DETECNO_ODBC_CONNECTION_STRING", "").strip()
    if direct_connection_string:
        return direct_connection_string

    dsn = os.getenv("PED_DETECNO_ODBC_DSN", "").strip()
    if dsn:
        return f"DSN={dsn};"

    driver = os.getenv("PED_DETECNO_ODBC_DRIVER", DEFAULT_ODBC_DRIVER).strip()
    server = os.getenv("PED_DETECNO_ODBC_SERVER", DEFAULT_ODBC_SERVER).strip()
    database = os.getenv("PED_DETECNO_ODBC_DATABASE", DEFAULT_ODBC_DATABASE).strip()

    parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={server}",
        f"DATABASE={database}",
    ]

    uid = os.getenv("PED_DETECNO_ODBC_UID", DEFAULT_ODBC_UID).strip()
    pwd = os.getenv("PED_DETECNO_ODBC_PWD", DEFAULT_ODBC_PWD).strip()
    if uid:
        parts.append(f"UID={uid}")
    if pwd:
        parts.append(f"PWD={pwd}")

    trusted = os.getenv("PED_DETECNO_ODBC_TRUSTED_CONNECTION", "yes").strip().lower()
    if trusted in {"1", "true", "yes", "si"} and not uid:
        parts.append("Trusted_Connection=yes")

    return ";".join(parts) + ";"


def build_folio_abc(df: pd.DataFrame) -> pd.Series:
    """Construye Folio_ABC a partir de SERIE + FOLIO como texto limpio."""
    serie = df["SERIE"].map(normalize_text_value)
    folio = df["FOLIO"].map(normalize_text_value)
    return serie + folio


def normalize_folio(value: object) -> str:
    """Normaliza valores de folio para compararlos y consultarlos."""
    return normalize_text_value(value)


def unique_non_empty(values: Iterable[object]) -> list[str]:
    """Devuelve valores únicos, conservando el orden y descartando vacíos."""
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = normalize_folio(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def extract_pedimento_value(result_df: pd.DataFrame) -> str | None:
    """Obtiene el primer valor válido de la columna Pedimento."""
    if result_df.empty:
        return None
    if PEDIMENTO_COLUMN not in result_df.columns:
        raise KeyError(
            f"La consulta no devolvió la columna '{PEDIMENTO_COLUMN}'. "
            f"Columnas recibidas: {list(result_df.columns)}"
        )

    values = (
        result_df[PEDIMENTO_COLUMN]
        .dropna()
        .astype(str)
        .str.strip()
    )
    values = values[values != ""]
    if values.empty:
        return None
    return values.iloc[0]


def normalize_column_name(column_name: str) -> str:
    """Normaliza nombres de columna para comparaciones tolerantes."""
    return re.sub(r"\s+", "", column_name).lower()


def fetch_pedimento_map(
    connection_string: str,
    sql_template: str,
    folios: Iterable[object],
) -> dict[str, str | None]:
    """Consulta Pedimento para cada Folio_ABC y devuelve un mapa por folio."""
    try:
        import pyodbc  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "No está instalado 'pyodbc'. Instálalo para poder consultar la base de datos."
        ) from exc

    folio_list = unique_non_empty(folios)
    pedimento_map: dict[str, str | None] = {}

    if not folio_list:
        return pedimento_map

    connection = pyodbc.connect(connection_string)
    connection.autocommit = True

    try:
        cursor = connection.cursor()
        try:
            cursor.execute(
                "CREATE TABLE #Folios "
                "([FOLIO_ ABC] NVARCHAR(100) COLLATE DATABASE_DEFAULT NOT NULL PRIMARY KEY)"
            )
            cursor.fast_executemany = True
            cursor.executemany(
                "INSERT INTO #Folios ([FOLIO_ ABC]) VALUES (?)",
                [(folio,) for folio in folio_list],
            )
            cursor.execute(sql_template)
            rows = cursor.fetchall()

            if not rows:
                return pedimento_map

            column_names = [column[0] for column in cursor.description]
            pedimento_index = None
            folio_index = None
            for index, column_name in enumerate(column_names):
                normalized = normalize_column_name(column_name)
                if normalized == "pedimento":
                    pedimento_index = index
                elif normalized in {"folio_abc", "folioabc"} or "folio" in normalized:
                    folio_index = index

            if pedimento_index is None:
                raise KeyError(
                    f"La consulta no devolvió la columna '{PEDIMENTO_COLUMN}'. "
                    f"Columnas recibidas: {column_names}"
                )
            if folio_index is None:
                raise KeyError(
                    "La consulta no devolvió la columna de folio esperada. "
                    f"Columnas recibidas: {column_names}"
                )

            for row in rows:
                folio_value = normalize_folio(row[folio_index])
                if not folio_value:
                    continue
                pedimento_value = normalize_folio(row[pedimento_index]) or None
                pedimento_map[folio_value] = pedimento_value
        finally:
            cursor.close()
    finally:
        connection.close()

    return pedimento_map


def add_pedimento_column(df: pd.DataFrame, pedimento_map: dict[str, str | None]) -> pd.DataFrame:
    """Agrega la columna Pedimento a un DataFrame usando Folio_ABC o SERIE+FOLIO."""
    enriched = df.copy()

    if "Folio_ABC" in enriched.columns:
        folios = enriched["Folio_ABC"].map(normalize_text_value)
    elif "SERIE" in enriched.columns and "FOLIO" in enriched.columns:
        folios = build_folio_abc(enriched)
    else:
        return enriched

    enriched[PEDIMENTO_COLUMN] = folios.map(lambda value: pedimento_map.get(normalize_folio(value)))
    return enriched


def process_workbook(
    input_path: Path,
    output_path: Path,
    sql_path: Path = DEFAULT_SQL_FILE,
) -> None:
    """Enriquece todas las hojas del workbook con la columna Pedimento."""
    sql_template = read_sql_template(sql_path)
    connection_string = build_connection_string()

    excel_file = pd.ExcelFile(input_path, engine="openpyxl")
    sheets_data = {
        sheet_name: pd.read_excel(input_path, sheet_name=sheet_name, engine="openpyxl")
        for sheet_name in excel_file.sheet_names
    }

    # Recolectar todos los folios presentes para consultar una sola vez por valor.
    all_folios: list[object] = []
    for sheet_name in TARGET_SHEETS:
        if sheet_name not in sheets_data:
            continue
        df = sheets_data[sheet_name]
        if "Folio_ABC" in df.columns:
            all_folios.extend(df["Folio_ABC"].tolist())
        elif "SERIE" in df.columns and "FOLIO" in df.columns:
            all_folios.extend(build_folio_abc(df).tolist())
        else:
            raise ValueError(
                f"La hoja '{sheet_name}' no contiene Folio_ABC ni SERIE/FOLIO."
            )

    pedimento_map = fetch_pedimento_map(connection_string, sql_template, all_folios)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet_name in excel_file.sheet_names:
            df = sheets_data[sheet_name]
            if "Folio_ABC" in df.columns or ("SERIE" in df.columns and "FOLIO" in df.columns):
                df = add_pedimento_column(df, pedimento_map)
            df.to_excel(writer, sheet_name=sheet_name, index=False)


def main() -> None:
    """Punto de entrada del script."""
    try:
        input_path = resolve_input_file()
        output_path = input_path.with_name(f"{input_path.stem}_pedimento.xlsx")
        process_workbook(input_path=input_path, output_path=output_path)
        print(f"Archivo generado correctamente: {output_path}")
    except Exception as exc:
        print(f"Error al agregar Pedimento: {exc}")
        raise


if __name__ == "__main__":
    main()
