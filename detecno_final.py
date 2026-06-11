#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Descarga semanal de facturas del portal DETECNO y envío por correo.

Fusiona la robustez de Playwright/ExtJS con el envío de correo SMTP.

Requisitos:
    Python 3.11+
    Microsoft Edge instalado
    pip install playwright
    python -m playwright install chromium

Variables de entorno obligatorias:
    export DETECNO_USER="usuario"
    export DETECNO_PASSWORD="password"
    export DETECNO_EMAIL_SENDER="tu_correo@gmail.com"
    export DETECNO_EMAIL_PASSWORD="contraseña_de_aplicacion"

Variables opcionales:
    export DETECNO_EMAIL_RECIPIENT="administracion@abcsc.mx"
    export DETECNO_DOWNLOAD_DIR="./descargas"
    export DETECNO_TIMEOUT_MS="60000"
    export DETECNO_HEADLESS="false"
    export DETECNO_SMTP_SERVER="smtp.gmail.com"
    export DETECNO_SMTP_PORT="587"

Cron — todos los lunes a las 18:00:
    0 18 * * 1 cd /home/christian/Documentos/PORTALES && \\
        DETECNO_USER="usuario" DETECNO_PASSWORD="password" \\
        DETECNO_EMAIL_SENDER="correo@gmail.com" \\
        DETECNO_EMAIL_PASSWORD="contraseña_app" \\
        /usr/bin/python3 detecno_unified.py >> cron_detecno.log 2>&1
"""

from __future__ import annotations

import logging
import os
import re
import smtplib
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Iterable

from playwright.sync_api import (
    Browser,
    BrowserContext,
    Error as PlaywrightError,
    Locator,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    sync_playwright,
)

# ─── CONSTANTES ──────────────────────────────────────────────────────────────

PORTAL_URL = (
    "https://detecnorecepcion.mx:447/Recepcion/Sanofi/"
    "cfdiWebRecepcion_Sanofi_Biopharma/asp/Start.aspx"
)

BASE_DIR        = Path(__file__).resolve().parent
LOG_FILE        = BASE_DIR / "detecno_extractor.log"
SCREENSHOT_DIR  = BASE_DIR / "screenshots"
DEFAULT_DOWNLOAD_DIR = BASE_DIR / "descargas"

# ─── CONFIGURACIÓN ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Settings:
    """Toda la configuración runtime leída desde variables de entorno."""

    # Portal
    username: str
    password: str
    download_dir: Path
    timeout_ms: int
    headless: bool

    # Correo
    email_sender: str
    email_password: str
    email_recipient: str
    smtp_server: str
    smtp_port: int


def load_settings() -> Settings:
    """Lee configuración desde variables de entorno con valores por defecto seguros."""

    username = os.getenv("DETECNO_USER", "").strip()
    password = os.getenv("DETECNO_PASSWORD", "").strip()
    if not username or not password:
        raise RuntimeError(
            "Faltan credenciales del portal: define DETECNO_USER y DETECNO_PASSWORD."
        )

    email_sender   = os.getenv("DETECNO_EMAIL_SENDER", "").strip()
    email_password = os.getenv("DETECNO_EMAIL_PASSWORD", "").strip()
    if not email_sender or not email_password:
        raise RuntimeError(
            "Faltan credenciales de correo: define DETECNO_EMAIL_SENDER "
            "y DETECNO_EMAIL_PASSWORD."
        )

    return Settings(
        username=username,
        password=password,
        download_dir=Path(
            os.getenv("DETECNO_DOWNLOAD_DIR", str(DEFAULT_DOWNLOAD_DIR))
        ).expanduser().resolve(),
        timeout_ms=int(os.getenv("DETECNO_TIMEOUT_MS", "60000")),
        headless=os.getenv("DETECNO_HEADLESS", "false").strip().lower()
            in {"1", "true", "yes", "si"},
        email_sender=email_sender,
        email_password=email_password,
        email_recipient=os.getenv(
            "DETECNO_EMAIL_RECIPIENT", "administracion@abcsc.mx"
        ).strip(),
        smtp_server=os.getenv("DETECNO_SMTP_SERVER", "smtp.gmail.com").strip(),
        smtp_port=int(os.getenv("DETECNO_SMTP_PORT", "587")),
    )


# ─── LOGGING ─────────────────────────────────────────────────────────────────

def setup_logging() -> logging.Logger:
    """Configura logging hacia consola y archivo rotativo."""
    logger = logging.getLogger("detecno")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


logger = setup_logging()


# ─── UTILIDADES GENERALES ────────────────────────────────────────────────────

def calculate_previous_week(today: date | None = None) -> tuple[str, str]:
    """Devuelve lunes y domingo de la semana anterior en formato dd/mm/yyyy."""
    current_day    = today or date.today()
    current_monday = current_day - timedelta(days=current_day.weekday())
    prev_monday    = current_monday - timedelta(days=7)
    prev_sunday    = prev_monday + timedelta(days=6)
    return prev_monday.strftime("%d/%m/%Y"), prev_sunday.strftime("%d/%m/%Y")


def ensure_directories(settings: Settings) -> None:
    """Crea carpetas necesarias si no existen."""
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def safe_name(value: str) -> str:
    """Normaliza texto para usarlo como nombre de archivo."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")


def cleanup_old_files(download_dir: Path, days: int = 7) -> None:
    """Elimina archivos descargados con más de `days` días de antigüedad."""
    cutoff = time.time() - days * 86400
    for filepath in download_dir.iterdir():
        if filepath.is_file() and filepath.stat().st_ctime < cutoff:
            filepath.unlink()
            logger.info("Archivo antiguo eliminado: %s", filepath)


# ─── UTILIDADES PLAYWRIGHT ───────────────────────────────────────────────────

def take_error_screenshot(page: Page | None, label: str) -> Path | None:
    """Captura el estado de la página ante un error."""
    if page is None:
        return None
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{safe_name(label)}.png"
    try:
        page.screenshot(path=str(path), full_page=True)
        logger.info("Screenshot guardado: %s", path)
        return path
    except PlaywrightError as exc:
        logger.warning("No se pudo guardar screenshot: %s", exc)
        return None


def wait_for_app(page: Page) -> None:
    """Espera carga base de la página."""
    page.wait_for_load_state("domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=15_000)
    except PlaywrightTimeoutError:
        logger.info("App con actividad de red continua; prosiguiendo.")


def wait_for_extjs_ready(page: Page, timeout_ms: int = 30_000) -> None:
    """Espera a que desaparezcan las máscaras de carga de ExtJS."""
    deadline = datetime.now().timestamp() + timeout_ms / 1000
    while datetime.now().timestamp() < deadline:
        try:
            if page.locator(".ext-el-mask:visible").count() == 0:
                return
        except Exception:
            return
        time.sleep(0.25)
    logger.info("Continuando aunque ExtJS todavía muestra máscara de carga.")


def first_visible(locators: Iterable[Locator], timeout_ms: int) -> Locator:
    """Retorna el primer locator visible de una lista de candidatos."""
    deadline = datetime.now().timestamp() + timeout_ms / 1000
    last_error: Exception | None = None
    while datetime.now().timestamp() < deadline:
        for locator in locators:
            try:
                candidate = locator.first
                if candidate.count() > 0 and candidate.is_visible(timeout=1000):
                    return candidate
            except Exception as exc:
                last_error = exc
        time.sleep(0.25)
    raise PlaywrightTimeoutError(
        f"No se encontró elemento visible. Último error: {last_error}"
    )


def click_first_visible(
    page: Page,
    locators: Iterable[Locator],
    timeout_ms: int,
    *,
    force: bool = False,
) -> Locator:
    """Hace clic en el primer elemento visible y habilitado."""
    target = first_visible(locators, timeout_ms)
    target.scroll_into_view_if_needed()
    target.click(force=force)
    return target


def fill_readonly_extjs_date(page: Page, selector: str, value: str) -> None:
    """Asigna una fecha a un input readonly de ExtJS notificando todos los eventos."""
    page.locator(selector).wait_for(state="attached")
    page.evaluate(
        """([selector, value]) => {
            const input = document.querySelector(selector);
            if (!input) throw new Error(`No existe el campo ${selector}`);

            input.removeAttribute('readonly');
            input.value = value;
            input.setAttribute('value', value);

            for (const ev of ['input', 'change', 'keyup', 'blur']) {
                input.dispatchEvent(new Event(ev, { bubbles: true }));
            }

            if (window.Ext) {
                const cmp = Ext.getCmp(input.id);
                if (cmp) {
                    if (typeof cmp.setRawValue === 'function') cmp.setRawValue(value);
                    cmp.value    = value;
                    cmp.rawValue = value;
                    if (typeof cmp.fireEvent === 'function') {
                        cmp.fireEvent('change', cmp, value);
                        cmp.fireEvent('blur', cmp);
                    }
                }
            }
            input.setAttribute('readonly', '');
        }""",
        [selector, value],
    )


def click_extjs_text(page: Page, text: str) -> bool:
    """Clic en controles ExtJS buscando por texto visible exacto."""
    return page.evaluate(
        """(text) => {
            const isVisible = el => {
                const s = window.getComputedStyle(el);
                const r = el.getBoundingClientRect();
                return s.visibility !== 'hidden' && s.display !== 'none'
                    && r.width > 0 && r.height > 0;
            };
            const matches = [...document.querySelectorAll('button, a, span, div, td')]
                .filter(el => el.textContent.trim() === text && isVisible(el));
            for (const el of matches.reverse()) {
                const clickable = el.closest('button, a, .x-btn, .x-btn-text, .x-btn-noicon') || el;
                clickable.scrollIntoView({ block: 'center', inline: 'center' });
                clickable.click();
                return true;
            }
            return false;
        }""",
        text,
    )


# ─── FLUJO DE SESIÓN ─────────────────────────────────────────────────────────

def complete_previous_session_check(page: Page, settings: Settings) -> bool:
    """Completa el formulario de validación de cierre de sesión previa."""
    try:
        page.locator("#txtUsuario2").wait_for(
            state="visible", timeout=min(settings.timeout_ms, 15_000)
        )
    except Exception:
        return False

    logger.info("Formulario de sesión previa detectado.")
    page.locator("#txtUsuario2").fill(settings.username)
    page.locator("#txtPass2").fill(settings.password)
    page.locator("#txtPass3").fill(settings.password)

    if not click_extjs_text(page, "Aceptar"):
        click_first_visible(
            page,
            [
                page.locator("button.x-btn-text:has-text('Aceptar')"),
                page.get_by_role("button", name=re.compile(r"^Aceptar$", re.I)),
            ],
            min(settings.timeout_ms, 15_000),
            force=True,
        )

    wait_for_app(page)
    wait_for_extjs_ready(page, min(settings.timeout_ms, 30_000))
    return True


def finalize_existing_session(page: Page, settings: Settings) -> bool:
    """Cierra una sesión previa detectada en la pantalla de login."""
    if complete_previous_session_check(page, settings):
        return True

    candidates = [
        page.get_by_text(re.compile(r"Finalizar Sesi[oó]n", re.I)),
        page.locator("button:has-text('Finalizar Sesion')"),
        page.locator("button:has-text('Finalizar Sesión')"),
    ]
    try:
        target = first_visible(candidates, min(settings.timeout_ms, 5_000))
    except Exception:
        return False

    logger.info("Sesión previa detectada; finalizándola.")
    try:
        target.click(force=True)
        wait_for_app(page)
        wait_for_extjs_ready(page, min(settings.timeout_ms, 30_000))
        complete_previous_session_check(page, settings)
        page.locator("#txtUsuario").wait_for(
            state="visible", timeout=min(settings.timeout_ms, 15_000)
        )
        return True
    except Exception as exc:
        logger.warning("No se pudo finalizar sesión previa: %s", exc)
        return False


def login(page: Page, settings: Settings) -> None:
    """Inicia sesión en el portal DETECNO."""
    logger.info("Abriendo portal DETECNO.")
    page.goto(PORTAL_URL, wait_until="domcontentloaded")
    wait_for_app(page)
    finalize_existing_session(page, settings)
    wait_for_extjs_ready(page, min(settings.timeout_ms, 30_000))

    page.locator("#txtUsuario").wait_for(state="visible")
    page.locator("#txtUsuario").fill(settings.username)
    page.locator("#txtPass").fill(settings.password)
    logger.info("Credenciales capturadas.")

    click_first_visible(
        page,
        [
            page.get_by_text("siguiente", exact=True),
            page.locator("div:has-text('siguiente')"),
        ],
        settings.timeout_ms,
        force=True,
    )
    wait_for_app(page)
    wait_for_extjs_ready(page, min(settings.timeout_ms, 30_000))

    try:
        page.get_by_text("Buscar Factura", exact=True).wait_for(
            state="visible", timeout=settings.timeout_ms
        )
    except PlaywrightTimeoutError:
        # Segundo intento si había sesión activa que requirió interacción
        if finalize_existing_session(page, settings):
            page.locator("#txtUsuario").fill(settings.username)
            page.locator("#txtPass").fill(settings.password)
            click_first_visible(
                page,
                [
                    page.get_by_text("siguiente", exact=True),
                    page.locator("div:has-text('siguiente')"),
                ],
                settings.timeout_ms,
                force=True,
            )
            wait_for_app(page)
            wait_for_extjs_ready(page, min(settings.timeout_ms, 30_000))
            page.get_by_text("Buscar Factura", exact=True).wait_for(
                state="visible", timeout=settings.timeout_ms
            )
        else:
            raise

    logger.info("Sesión iniciada correctamente.")


def logout(page: Page, settings: Settings) -> None:
    """Cierra la sesión en el portal."""
    logger.info("Cerrando sesión.")
    try:
        click_first_visible(
            page,
            [
                page.locator("button.imgkey:has-text('Cerrar Sesion')"),
                page.locator("button.imgkey:has-text('Cerrar Sesión')"),
                page.get_by_role("button", name=re.compile(r"Cerrar Sesi[oó]n", re.I)),
                page.get_by_text(re.compile(r"Cerrar Sesi[oó]n", re.I)),
                page.locator(".imgkey"),
            ],
            min(settings.timeout_ms, 15_000),
            force=True,
        )
        wait_for_app(page)
        logger.info("Sesión cerrada.")
    except Exception as exc:
        logger.warning("Clic normal de cierre falló; intentando con dispatch JS: %s", exc)
        try:
            target = first_visible(
                [
                    page.locator("button.imgkey:has-text('Cerrar Sesion')"),
                    page.locator("button.imgkey:has-text('Cerrar Sesión')"),
                    page.get_by_text(re.compile(r"Cerrar Sesi[oó]n", re.I)),
                    page.locator(".imgkey"),
                ],
                5_000,
            )
            target.dispatch_event("click")
            wait_for_app(page)
            logger.info("Sesión cerrada con dispatch JS.")
        except Exception as dispatch_exc:
            logger.warning("No se confirmó cierre de sesión: %s", dispatch_exc)
            take_error_screenshot(page, "logout_error")


# ─── FLUJO DE DESCARGA ────────────────────────────────────────────────────────

def open_buscar_factura(page: Page, settings: Settings) -> None:
    """Abre el módulo Buscar Factura desde el árbol lateral."""
    logger.info("Abriendo módulo Buscar Factura.")
    click_first_visible(
        page,
        [
            page.get_by_text("Buscar Factura", exact=True),
            page.locator("a.x-tree-node-anchor:has-text('Buscar Factura')"),
            page.locator("span:has-text('Buscar Factura')"),
        ],
        settings.timeout_ms,
    )
    page.locator("#fechaInicio").wait_for(state="attached", timeout=settings.timeout_ms)
    page.locator("#fechaFinal").wait_for(state="attached", timeout=settings.timeout_ms)


def set_dates(page: Page, start_date: str, end_date: str) -> None:
    """Captura Fecha Inicial y Fecha Final en campos readonly de ExtJS."""
    logger.info("Asignando fechas: %s - %s.", start_date, end_date)
    fill_readonly_extjs_date(page, "#fechaInicio", start_date)
    fill_readonly_extjs_date(page, "#fechaFinal", end_date)


def search_invoices(page: Page, settings: Settings) -> None:
    """Ejecuta la búsqueda de facturas."""
    logger.info("Buscando facturas.")
    click_first_visible(
        page,
        [
            page.locator("button.imgfind:has-text('Buscar')"),
            page.get_by_role("button", name=re.compile(r"^Buscar$", re.I)),
            page.locator("button:has-text('Buscar')"),
            page.locator(".imgfind"),
        ],
        settings.timeout_ms,
    )
    wait_for_app(page)


def export_excel(page: Page, settings: Settings) -> None:
    """Abre el diálogo de exportación a Excel."""
    logger.info("Abriendo exportación a Excel.")
    if not click_extjs_text(page, "Exportar a Excel"):
        click_first_visible(
            page,
            [
                page.get_by_text("Exportar a Excel", exact=True),
                page.get_by_role("button", name=re.compile(r"Exportar a Excel", re.I)),
                page.locator("button:has-text('Exportar a Excel')"),
                page.locator(".imgexcel"),
            ],
            settings.timeout_ms,
            force=True,
        )
    # Esperar que aparezca el diálogo de confirmación
    first_visible(
        [
            page.locator(".x-window:visible button.x-btn-text:not(.imgaceptar):has-text('Aceptar')"),
            page.locator(".x-window:visible button:has-text('Aceptar')"),
            page.locator("button.x-btn-text:not(.imgaceptar):has-text('Aceptar')"),
        ],
        settings.timeout_ms,
    )


def select_reporte_comprobantes(page: Page, settings: Settings) -> None:
    """Selecciona 'Reporte Comprobantes' en el combo del diálogo."""
    logger.info("Seleccionando tipo de reporte.")
    click_first_visible(
        page,
        [
            page.locator(".x-window .x-form-arrow-trigger"),
            page.locator("img.x-form-arrow-trigger"),
            page.locator(".x-form-arrow-trigger"),
        ],
        settings.timeout_ms,
    )
    click_first_visible(
        page,
        [
            page.locator(".x-combo-list-item", has_text="Reporte Comprobantes"),
            page.get_by_text("Reporte Comprobantes", exact=True),
        ],
        settings.timeout_ms,
    )


def download_report(page: Page, settings: Settings) -> Path:
    """Acepta el diálogo y guarda el archivo descargado con su nombre original."""
    select_reporte_comprobantes(page, settings)
    logger.info("Confirmando exportación y esperando descarga.")

    with page.expect_download(timeout=settings.timeout_ms) as download_info:
        click_first_visible(
            page,
            [
                page.locator(".x-window:visible button.x-btn-text:not(.imgaceptar):has-text('Aceptar')"),
                page.locator(".x-window button:has-text('Aceptar')"),
                page.get_by_role("button", name=re.compile(r"^Aceptar$", re.I)),
                page.get_by_text("Aceptar", exact=True),
            ],
            settings.timeout_ms,
        )

    download = download_info.value
    target   = settings.download_dir / download.suggested_filename
    download.save_as(str(target))

    if not target.exists() or target.stat().st_size == 0:
        raise RuntimeError(f"La descarga no se guardó correctamente: {target}")

    logger.info("Archivo descargado: %s", target)
    return target


# ─── CORREO ───────────────────────────────────────────────────────────────────

def send_email(
    settings: Settings,
    file_path: Path,
    start_date: str,
    end_date: str,
) -> bool:
    """Envía el reporte descargado como adjunto por correo SMTP."""
    subject = f"Facturas DETECNO — Semana {start_date} al {end_date}"

    body_html = f"""
    <div style="font-family:Arial,sans-serif;max-width:600px;color:#333;">
      <div style="background:#2c5f8a;padding:20px 24px;border-radius:6px 6px 0 0;">
        <h2 style="margin:0;color:#fff;font-size:18px;">📄 Facturas DETECNO</h2>
        <p style="margin:6px 0 0;color:#cce0f5;font-size:13px;">
          Semana del {start_date} al {end_date}
        </p>
      </div>
      <div style="background:#f9f9f9;padding:24px;border:1px solid #ddd;
                  border-top:none;border-radius:0 0 6px 6px;">
        <p>Estimados,</p>
        <p>Les hacemos llegar el estado de cuenta del portal <strong>DETECNO</strong>
           con las facturas de la semana pasada ({start_date} – {end_date}).</p>
        <p>El archivo Excel se encuentra adjunto a este correo.</p>
        <hr style="border:none;border-top:1px solid #ddd;margin:20px 0;"/>
        <p style="font-size:11px;color:#999;margin:0;">
          Correo generado automáticamente. No es necesario responder.
        </p>
      </div>
    </div>
    """

    msg              = MIMEMultipart("alternative")
    msg["From"]      = settings.email_sender
    msg["To"]        = settings.email_recipient
    msg["Subject"]   = subject
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    # Adjunto
    try:
        with open(file_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={file_path.name}",
            )
            msg.attach(part)
    except OSError as exc:
        logger.error("No se pudo adjuntar el archivo: %s", exc)
        return False

    # Envío
    try:
        with smtplib.SMTP(settings.smtp_server, settings.smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.email_sender, settings.email_password)
            server.send_message(msg)
        logger.info("Correo enviado a: %s", settings.email_recipient)
        return True
    except smtplib.SMTPException as exc:
        logger.error("Error al enviar correo: %s", exc)
        return False


# ─── NAVEGADOR ────────────────────────────────────────────────────────────────

def create_browser(
    settings: Settings,
) -> tuple[Playwright, Browser, BrowserContext, Page]:
    """Inicia Microsoft Edge con descargas habilitadas."""
    playwright = sync_playwright().start()
    browser    = playwright.chromium.launch(
        channel="msedge", headless=settings.headless
    )
    context = browser.new_context(
        accept_downloads=True,
        ignore_https_errors=True,
        viewport={"width": 1366, "height": 768},
    )
    context.set_default_timeout(settings.timeout_ms)
    page = context.new_page()
    page.set_default_timeout(settings.timeout_ms)
    return playwright, browser, context, page


def close_browser(
    playwright: Playwright | None,
    browser: Browser | None,
    context: BrowserContext | None,
) -> None:
    """Cierra contexto, navegador y Playwright sin dejar procesos colgados."""
    try:
        if context:
            context.close()
    finally:
        if browser:
            browser.close()
        if playwright:
            playwright.stop()


# ─── PUNTO DE ENTRADA ────────────────────────────────────────────────────────

def main() -> int:
    """Orquesta login → búsqueda → descarga → correo → logout."""
    logger.info("=== INICIANDO EXTRACCIÓN DETECNO ===")

    settings = load_settings()
    ensure_directories(settings)

    start_date, end_date = calculate_previous_week()
    logger.info("Período semanal: %s - %s", start_date, end_date)

    playwright: Playwright | None = None
    browser: Browser | None      = None
    context: BrowserContext | None = None
    page: Page | None            = None
    downloaded_file: Path | None = None

    try:
        playwright, browser, context, page = create_browser(settings)

        login(page, settings)
        open_buscar_factura(page, settings)
        set_dates(page, start_date, end_date)
        search_invoices(page, settings)
        export_excel(page, settings)
        downloaded_file = download_report(page, settings)

        logger.info("Descarga completada: %s", downloaded_file)

        if send_email(settings, downloaded_file, start_date, end_date):
            logger.info("Correo enviado exitosamente.")
        else:
            logger.error("Fallo en el envío del correo.")

        cleanup_old_files(settings.download_dir)
        logger.info("=== PROCESO DETECNO COMPLETADO ===")
        return 0

    except Exception as exc:
        logger.exception("Error inesperado en el proceso DETECNO: %s", exc)
        take_error_screenshot(page, "detecno_error")
        return 1

    finally:
        if page:
            logout(page, settings)
        close_browser(playwright, browser, context)
        logger.info("Fin del proceso. Archivo: %s", downloaded_file or "N/A")


if __name__ == "__main__":
    sys.exit(main())