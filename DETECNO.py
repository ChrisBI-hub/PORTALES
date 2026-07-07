#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import smtplib
import logging
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('detecno_extractor.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Configuración de rutas y credenciales
DOWNLOAD_DIR = os.path.join(os.getcwd(), 'descargas')
EMAIL_SENDER = 'reportes.bi@abcsc.mx'          # Cambiar por correo emisor
EMAIL_PASSWORD = 'jwvjdrvmprzrwzxy'          # Usar contraseña de aplicación
EMAIL_RECIPIENT = ["sgonzalez@abcsc.mx", "administracion@abcsc.mx", "cxc@abcsc.mx"]
SMTP_SERVER = 'smtp.gmail.com'
SMTP_PORT = 587

# Credenciales del portal
PORTAL_USER = '0100537273'
PORTAL_PASSWORD = 'Abcspa3942$'
PORTAL_URL = 'https://detecnorecepcion.mx:447/Recepcion/Sanofi/cfdiWebRecepcion_Sanofi_Biopharma/asp/Start.aspx'

def setup_driver():
    """Configura el driver de Chrome para manejar descargas y certificados."""
    chrome_options = Options()
    chrome_options.add_argument('--ignore-certificate-errors')
    chrome_options.add_argument('--allow-insecure-localhost')
    chrome_options.add_argument('--disable-web-security')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    
    # Crear carpeta de descarga si no existe
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)
    
    prefs = {
        'download.default_directory': DOWNLOAD_DIR,
        'download.prompt_for_download': False,
        'download.directory_upgrade': True,
        'safebrowsing.enabled': True
    }
    chrome_options.add_experimental_option('prefs', prefs)
    
    driver = webdriver.Chrome(options=chrome_options)
    driver.maximize_window()
    return driver

def get_last_week_dates():
    """Calcula las fechas de la semana pasada (lunes a domingo)."""
    today = datetime.now()
    days_since_monday = today.weekday()  # lunes=0, domingo=6
    this_monday = today - timedelta(days=days_since_monday)
    last_monday = this_monday - timedelta(days=7)
    last_sunday = last_monday + timedelta(days=6)
    
    # Formato día/mes/año (observado en el placeholder)
    start_date = last_monday.strftime('%d/%m/%Y')
    end_date = last_sunday.strftime('%d/%m/%Y')
    return start_date, end_date

def login(driver, username, password):
    """Realiza login con los campos txtUsuario y txtPass."""
    logger.info("Cargando página de login...")
    driver.get(PORTAL_URL)
    time.sleep(3)
    
    try:
        # Campo usuario
        user_input = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "txtUsuario"))
        )
        user_input.clear()
        user_input.send_keys(username)
        logger.info("Usuario ingresado")
        
        # Campo contraseña
        pwd_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "txtPass"))
        )
        pwd_input.clear()
        pwd_input.send_keys(password)
        logger.info("Contraseña ingresada")
        
        # Botón de login (intentamos varios selectores)
        try:
            login_btn = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Ingresar') or contains(text(),'Aceptar') or contains(@id,'btnIngresar')]"))
            )
        except:
            # Si no, buscar cualquier botón dentro del formulario
            login_btn = driver.find_element(By.XPATH, "//form//button")
        
        driver.execute_script("arguments[0].click();", login_btn)
        logger.info("Login enviado")
        time.sleep(5)
        
        # Verificar éxito: esperar el radio button (imagen radio2.png)
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//img[contains(@src,'radio2.png')]"))
        )
        logger.info("Login exitoso")
        return True
        
    except Exception as e:
        logger.error(f"Error en login: {e}")
        driver.save_screenshot("login_error.png")
        return False

def select_radio_button(driver):
    """Selecciona el botón de radio con la imagen radio2.png."""
    try:
        radio_img = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//img[contains(@src,'radio2.png')]"))
        )
        driver.execute_script("arguments[0].click();", radio_img)
        logger.info("Radio button seleccionado")
        time.sleep(1)
        return True
    except Exception as e:
        logger.error(f"Error seleccionando radio button: {e}")
        return False

def set_dates(driver, start_date, end_date):
    """Ingresa las fechas en los campos fechaInicio y fechaFinal."""
    try:
        # Fecha inicio
        fecha_inicio = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "fechaInicio"))
        )
        driver.execute_script("arguments[0].value = arguments[1];", fecha_inicio, start_date)
        driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", fecha_inicio)
        
        # Fecha final
        fecha_final = driver.find_element(By.ID, "fechaFinal")
        driver.execute_script("arguments[0].value = arguments[1];", fecha_final, end_date)
        driver.execute_script("arguments[0].dispatchEvent(new Event('change'));", fecha_final)
        
        logger.info(f"Fechas ingresadas: {start_date} - {end_date}")
        return True
    except Exception as e:
        logger.error(f"Error al ingresar fechas: {e}")
        return False

def click_buscar(driver):
    """Hace clic en el botón Buscar."""
    try:
        buscar_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Buscar')]"))
        )
        driver.execute_script("arguments[0].click();", buscar_btn)
        logger.info("Clic en Buscar")
        time.sleep(5)
        return True
    except Exception as e:
        logger.error(f"Error al hacer clic en Buscar: {e}")
        return False

def click_exportar(driver):
    """Hace clic en el botón de exportar (puede tener texto 'Exportar' o ser el mismo que Buscar pero en otro estado)."""
    try:
        # Primero intentamos con el texto "Exportar"
        export_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Exportar')]"))
        )
        driver.execute_script("arguments[0].click();", export_btn)
        logger.info("Clic en Exportar")
        time.sleep(3)
        return True
    except TimeoutException:
        logger.warning("No se encontró botón 'Exportar', intentando con botón de imagen genérico...")
        try:
            # Buscar por clase o atributo común (ej: botón con clase 'imgfind')
            export_btn = driver.find_element(By.XPATH, "//button[contains(@class,'imgfind')]")
            driver.execute_script("arguments[0].click();", export_btn)
            logger.info("Clic en botón de exportación (selector imgfind)")
            time.sleep(3)
            return True
        except:
            logger.error("No se pudo localizar el botón de exportación")
            return False

def aceptar_dialogo(driver):
    """Acepta el diálogo que aparece después de exportar."""
    try:
        aceptar_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Aceptar')]"))
        )
        driver.execute_script("arguments[0].click();", aceptar_btn)
        logger.info("Diálogo aceptado")
        time.sleep(5)
        return True
    except TimeoutException:
        logger.info("No apareció diálogo de confirmación, continuando...")
        return True
    except Exception as e:
        logger.error(f"Error al aceptar diálogo: {e}")
        return False

def wait_for_download(timeout=60):
    """Espera a que se complete la descarga del archivo Excel."""
    logger.info("Esperando descarga...")
    end_time = time.time() + timeout
    downloaded_file = None
    while time.time() < end_time:
        files = [f for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.xlsx') and not f.endswith('.crdownload')]
        if files:
            downloaded_file = max([os.path.join(DOWNLOAD_DIR, f) for f in files], key=os.path.getctime)
            # Esperar un poco para que el archivo termine de escribirse
            time.sleep(2)
            if os.path.getsize(downloaded_file) > 0:
                logger.info(f"Archivo descargado: {downloaded_file}")
                return downloaded_file
        time.sleep(2)
    logger.error("Timeout esperando descarga")
    return None

def send_email(file_path, start_date, end_date):
    """Envía el archivo adjunto por correo."""
    subject = f"Facturas DETECNO - Semana {start_date} al {end_date}"
    body = f"""Estimados,

Te hacemos llegar los estados de cuenta del portal *DETECNO* con el estado de cuentas de las facturas de la semana pasada {start_date} a {end_date}.

Siempre tuyo,
Christian Carbajal
"""
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECIPIENT
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    # Adjuntar archivo
    try:
        with open(file_path, 'rb') as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
            encoders.encode_base64(part)
            part.add_header('Content-Disposition', f'attachment; filename={os.path.basename(file_path)}')
            msg.attach(part)
    except Exception as e:
        logger.error(f"Error al adjuntar archivo: {e}")
        return False

    # Enviar correo
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.send_message(msg)
        server.quit()
        logger.info("Correo enviado exitosamente")
        return True
    except Exception as e:
        logger.error(f"Error al enviar correo: {e}")
        return False

def cleanup_old_files(days=7):
    """Limpia archivos descargados antiguos (más de 'days' días)."""
    now = time.time()
    for filename in os.listdir(DOWNLOAD_DIR):
        filepath = os.path.join(DOWNLOAD_DIR, filename)
        if os.path.isfile(filepath) and (now - os.path.getctime(filepath)) > days * 86400:
            os.remove(filepath)
            logger.info(f"Archivo antiguo eliminado: {filepath}")

def main():
    logger.info("=== INICIANDO EXTRACCIÓN DETECNO ===")
    driver = None
    try:
        # Calcular fechas de la semana pasada
        start_date, end_date = get_last_week_dates()
        logger.info(f"Período a extraer: {start_date} - {end_date}")

        # Configurar driver
        driver = setup_driver()
        
        # Login
        if not login(driver, PORTAL_USER, PORTAL_PASSWORD):
            logger.error("Fallo en login, abortando")
            return False
        
        # Seleccionar radio button
        if not select_radio_button(driver):
            logger.error("No se pudo seleccionar el radio button")
            return False
        
        # Ingresar fechas
        if not set_dates(driver, start_date, end_date):
            logger.error("No se pudieron ingresar las fechas")
            return False
        
        # Buscar
        if not click_buscar(driver):
            logger.error("No se pudo hacer clic en Buscar")
            return False
        
        # Exportar
        if not click_exportar(driver):
            logger.error("No se pudo hacer clic en Exportar")
            return False
        
        # Aceptar diálogo (si aparece)
        aceptar_dialogo(driver)
        
        # Esperar descarga
        downloaded_file = wait_for_download()
        if not downloaded_file:
            logger.error("No se descargó ningún archivo")
            return False
        
        # Enviar por correo
        if send_email(downloaded_file, start_date, end_date):
            logger.info("Proceso completado con éxito")
        else:
            logger.error("Fallo en el envío de correo")
        
        # Limpieza opcional
        cleanup_old_files()
        
    except Exception as e:
        logger.error(f"Error inesperado: {e}")
        if driver:
            driver.save_screenshot("error_general.png")
    finally:
        if driver:
            driver.quit()
        logger.info("=== FIN DEL PROCESO ===")

if __name__ == "__main__":
    main()