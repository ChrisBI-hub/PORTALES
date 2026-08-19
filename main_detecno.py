from __future__ import annotations

import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import fechas
import ped_detecno
import separacion


# Archivo base que debe procesar todo el flujo.
INPUT_FILE = Path("detecno.xlsx")

# Configuración de correo.
CORREOS_DESTINO = ["cxc@abcsc.mx"]
#CORREOS_DESTINO = ["ccarbajal@abcsc.mx"]
CORREOS_CC = [
    "administracion@abcsc.mx",
    "sgonzalez@abcsc.mx",
    #"ymontoya@abcsc.mx",
    #"contraloria@abcsc.mx",
    "facturacion3@abcsc.mx",
    "administracion2@abcsc.mx",
    "gerenteadmin@abcsc.mx",
]
CORREO_REMITE = "reportes.bi@abcsc.mx"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "reportes.bi@abcsc.mx"
SMTP_PASSWORD = "jwvjdrvmprzrwzxy"


def send_email(file_path: Path) -> None:
    """Envía el archivo generado por correo."""
    subject = "Reporte DETECNO generado"
    body = (
        "Se adjunta el archivo final generado por el flujo DETECNO.\n\n"
        f"Archivo: {file_path.name}"
    )

    message = MIMEMultipart()
    message["From"] = CORREO_REMITE
    message["To"] = ", ".join(CORREOS_DESTINO)
    message["Cc"] = ", ".join(CORREOS_CC)
    message["Subject"] = subject
    message.attach(MIMEText(body, "plain", "utf-8"))

    with open(file_path, "rb") as attachment:
        part = MIMEBase("application", "octet-stream")
        part.set_payload(attachment.read())
    encoders.encode_base64(part)
    part.add_header("Content-Disposition", f"attachment; filename={file_path.name}")
    message.attach(part)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(SMTP_USER, SMTP_PASSWORD)
        recipients = CORREOS_DESTINO + CORREOS_CC
        server.sendmail(CORREO_REMITE, recipients, message.as_string())


def main() -> None:
    """Ejecuta fechas, separación y enriquecimiento con Pedimento sobre detecno.xlsx."""
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"No se encontró el archivo de entrada: {INPUT_FILE}")

    try:
        fechas_path = INPUT_FILE.with_name(f"{INPUT_FILE.stem}_fechas.xlsx")
        separated_path = INPUT_FILE.with_name(f"{INPUT_FILE.stem}_separado.xlsx")
        final_path = INPUT_FILE.with_name(f"{INPUT_FILE.stem}_pedimento.xlsx")

        # Paso 1: normalizar fechas.
        fechas.process_workbook(INPUT_FILE, fechas_path)

        # Paso 2: separar por receptor.
        separacion.process_workbook(fechas_path, separated_path)

        # Paso 3: agregar Pedimento desde la consulta SQL.
        ped_detecno.process_workbook(separated_path, final_path)

        # Paso 4: enviar el archivo final por correo.
        send_email(final_path)

        print(f"Archivo final generado correctamente: {final_path}")
        print("Correo enviado correctamente.")

    except Exception as exc:
        print(f"Error en el flujo DETECNO: {exc}")
        raise


if __name__ == "__main__":
    main()
