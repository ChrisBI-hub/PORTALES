from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path

import pandas as pd


# Hoja que contiene toda la información descargada del portal (sin filtrar).
SOURCE_SHEET_NAME = "Facturas_Seleccionadas"

# Tabla destino en la base BI (ver detecno.sql para su definición).
TARGET_TABLE = "dbo.detecno_portal"

# Conexión por defecto: mismo servidor que ped_detecno.py, base de datos BI,
# reutilizando el usuario ConsultaBD ya usado por el resto del flujo.
DEFAULT_ODBC_DRIVER = "ODBC Driver 17 for SQL Server"
DEFAULT_ODBC_SERVER = "150.1.1.152"
DEFAULT_ODBC_DATABASE = "BI"
DEFAULT_ODBC_UID = "ConsultaBD"
DEFAULT_ODBC_PWD = "5D$bc#kM&5W2T8J40?s%"

# Columnas del portal que se respaldan, en el mismo orden que detecno_portal.
DATE_COLUMNS = {
    "FECHA",
    "FECHA_RECEPCION",
    "FECHATIMBRADO",
    "FECHA_VALIDACION_LISTAS_NEGRAS",
}
INT_COLUMNS = {
    "ID",
    "USUARIO",
    "estatusPagoEncId",
    "ESTATUSIDLN",
    "ESTATUSIDIMAGEN",
}
DECIMAL_COLUMNS = {
    "TOTAL",
    "TOTALIMPUESTO_TRASLADADO",
    "TOTALIMPUESTO_RETENIDO",
    "peTotalAcumulado",
    "peTotalCompensado",
    "peTotalInsoluto",
}

TARGET_COLUMNS = [
    "ID",
    "SERIE",
    "FOLIO",
    "VERSION",
    "RFC_EMISOR",
    "NOMBRE_EMISOR",
    "RFC_RECEPTOR",
    "NOMBRE_RECEPTOR",
    "FECHA",
    "FECHA_RECEPCION",
    "TOTAL",
    "USUARIO",
    "METODOPAGO",
    "UUID",
    "MOTIVORECHAZO",
    "ESTATUS",
    "TIPOCOMPROBANTE",
    "MONEDA",
    "FECHATIMBRADO",
    "TOTALIMPUESTO_TRASLADADO",
    "TOTALIMPUESTO_RETENIDO",
    "estatusPagoEncId",
    "estatusPagoEncDesc",
    "peTotalAcumulado",
    "peTotalCompensado",
    "peTotalInsoluto",
    "ESTATUS SAT",
    "ESTATUSIDLN",
    "ESTATUS_LISTAS_NEGRA",
    "FECHA_VALIDACION_LISTAS_NEGRAS",
    "ESTATUSIDIMAGEN",
    "NUM_ORDEN",
    "CORREO_SANOFI",
    "Pedimento",
]


def build_connection_string() -> str:
    """Construye la cadena de conexión ODBC hacia la base BI desde variables de entorno."""
    direct_connection_string = os.getenv("DETECNO_BI_ODBC_CONNECTION_STRING", "").strip()
    if direct_connection_string:
        return direct_connection_string

    dsn = os.getenv("DETECNO_BI_ODBC_DSN", "").strip()
    if dsn:
        return f"DSN={dsn};"

    driver = os.getenv("DETECNO_BI_ODBC_DRIVER", DEFAULT_ODBC_DRIVER).strip()
    server = os.getenv("DETECNO_BI_ODBC_SERVER", DEFAULT_ODBC_SERVER).strip()
    database = os.getenv("DETECNO_BI_ODBC_DATABASE", DEFAULT_ODBC_DATABASE).strip()
    uid = os.getenv("DETECNO_BI_ODBC_UID", DEFAULT_ODBC_UID).strip()
    pwd = os.getenv("DETECNO_BI_ODBC_PWD", DEFAULT_ODBC_PWD).strip()

    parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={server}",
        f"DATABASE={database}",
    ]
    if uid:
        parts.append(f"UID={uid}")
    if pwd:
        parts.append(f"PWD={pwd}")
    if not uid:
        parts.append("Trusted_Connection=yes")

    return ";".join(parts) + ";"


def parse_date(value: object) -> date | None:
    """Convierte texto 'AAAA/MM/DD' (ya normalizado por fechas.py) a date."""
    text = str(value).strip()
    if not text:
        return None
    return datetime.strptime(text, "%Y/%m/%d").date()


def clean_value(column: str, value: object) -> object:
    """Convierte un valor de Excel al tipo Python esperado por detecno_portal."""
    if pd.isna(value):
        return None

    if column in DATE_COLUMNS:
        return parse_date(value)

    if column in INT_COLUMNS:
        return int(value)

    if column in DECIMAL_COLUMNS:
        return float(value)

    text = str(value).strip()
    if text.endswith(".0") and text[:-2].lstrip("-").isdigit():
        text = text[:-2]
    return text


def load_rows(input_path: Path) -> list[tuple]:
    """Lee la hoja completa del portal y arma las filas listas para cargar."""
    df = pd.read_excel(input_path, sheet_name=SOURCE_SHEET_NAME, engine="openpyxl")

    missing_columns = [column for column in TARGET_COLUMNS if column not in df.columns]
    if missing_columns:
        raise ValueError(
            "Faltan columnas requeridas para el respaldo en BI: "
            + ", ".join(missing_columns)
        )

    return [
        tuple(clean_value(column, row[column]) for column in TARGET_COLUMNS)
        for _, row in df.iterrows()
    ]


def build_staging_ddl() -> str:
    """DDL de la tabla temporal usada para el MERGE (mismas columnas, sin auditoría)."""
    type_by_column = {
        "ID": "INT",
        "SERIE": "NVARCHAR(10)",
        "FOLIO": "NVARCHAR(20)",
        "VERSION": "NVARCHAR(10)",
        "RFC_EMISOR": "NVARCHAR(20)",
        "NOMBRE_EMISOR": "NVARCHAR(200)",
        "RFC_RECEPTOR": "NVARCHAR(20)",
        "NOMBRE_RECEPTOR": "NVARCHAR(200)",
        "FECHA": "DATE",
        "FECHA_RECEPCION": "DATE",
        "TOTAL": "DECIMAL(18, 2)",
        "USUARIO": "INT",
        "METODOPAGO": "NVARCHAR(10)",
        "UUID": "NVARCHAR(50)",
        "MOTIVORECHAZO": "NVARCHAR(500)",
        "ESTATUS": "NVARCHAR(50)",
        "TIPOCOMPROBANTE": "NVARCHAR(5)",
        "MONEDA": "NVARCHAR(5)",
        "FECHATIMBRADO": "DATE",
        "TOTALIMPUESTO_TRASLADADO": "DECIMAL(18, 2)",
        "TOTALIMPUESTO_RETENIDO": "DECIMAL(18, 2)",
        "estatusPagoEncId": "INT",
        "estatusPagoEncDesc": "NVARCHAR(50)",
        "peTotalAcumulado": "DECIMAL(18, 2)",
        "peTotalCompensado": "DECIMAL(18, 2)",
        "peTotalInsoluto": "DECIMAL(18, 2)",
        "ESTATUS SAT": "NVARCHAR(50)",
        "ESTATUSIDLN": "INT",
        "ESTATUS_LISTAS_NEGRA": "NVARCHAR(50)",
        "FECHA_VALIDACION_LISTAS_NEGRAS": "DATE",
        "ESTATUSIDIMAGEN": "INT",
        "NUM_ORDEN": "NVARCHAR(50)",
        "CORREO_SANOFI": "NVARCHAR(200)",
        "Pedimento": "NVARCHAR(50)",
    }
    columns_ddl = ",\n        ".join(
        f"[{column}] {type_by_column[column]}" for column in TARGET_COLUMNS
    )
    return f"CREATE TABLE #DetecnoPortalStaging (\n        {columns_ddl}\n    );"


def build_merge_sql() -> str:
    """MERGE que hace upsert de #DetecnoPortalStaging hacia detecno_portal por ID."""
    update_columns = [column for column in TARGET_COLUMNS if column != "ID"]
    update_clause = ",\n    ".join(f"target.[{c}] = source.[{c}]" for c in update_columns)
    insert_columns = ", ".join(f"[{c}]" for c in TARGET_COLUMNS)
    insert_values = ", ".join(f"source.[{c}]" for c in TARGET_COLUMNS)

    return f"""
MERGE {TARGET_TABLE} AS target
USING #DetecnoPortalStaging AS source
    ON target.ID = source.ID
WHEN MATCHED THEN UPDATE SET
    {update_clause},
    target.FECHA_ACTUALIZACION_BI = SYSDATETIME()
WHEN NOT MATCHED THEN INSERT (
    {insert_columns}
) VALUES (
    {insert_values}
);
"""


def upsert_rows(connection_string: str, rows: list[tuple]) -> int:
    """Carga las filas en una tabla temporal y hace MERGE hacia detecno_portal."""
    try:
        import pyodbc  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "No está instalado 'pyodbc'. Instálalo para poder respaldar en BI."
        ) from exc

    if not rows:
        return 0

    insert_columns = ", ".join(f"[{c}]" for c in TARGET_COLUMNS)
    placeholders = ", ".join("?" for _ in TARGET_COLUMNS)

    connection = pyodbc.connect(connection_string)
    connection.autocommit = False
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(build_staging_ddl())
            cursor.fast_executemany = True
            cursor.executemany(
                f"INSERT INTO #DetecnoPortalStaging ({insert_columns}) VALUES ({placeholders})",
                rows,
            )
            cursor.execute(build_merge_sql())
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()

    return len(rows)


def process_workbook(input_path: Path) -> int:
    """Respalda en la base BI toda la información del portal contenida en input_path."""
    rows = load_rows(input_path)
    connection_string = build_connection_string()
    return upsert_rows(connection_string, rows)


def main() -> None:
    """Punto de entrada del script."""
    import sys

    input_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("detecno_pedimento.xlsx")
    try:
        loaded = process_workbook(input_path)
        print(f"Respaldo en BI completado: {loaded} filas cargadas/actualizadas en {TARGET_TABLE}.")
    except Exception as exc:
        print(f"Error al respaldar en BI: {exc}")
        raise


if __name__ == "__main__":
    main()
