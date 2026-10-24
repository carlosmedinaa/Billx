import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import os

def enviar_email(remitente, password, destinatario, asunto, cuerpo, ruta_adjunto=None):
    # 1. Limpiar espacios que se hayan colado sin querer
    password_limpia = password.replace(" ", "").strip()
    remitente_limpio = remitente.strip()
    
    # 2. Detectar el servidor (Cambiado al servidor global y moderno de Microsoft)
    dominio = remitente_limpio.split('@')[-1].lower()
    
    if dominio in ['hotmail.com', 'hotmail.es', 'outlook.com', 'outlook.es', 'live.com']:
        smtp_server = "smtp.office365.com"  # <-- Servidor moderno y más permisivo
        smtp_port = 587
    elif dominio == 'gmail.com':
        smtp_server = "smtp.gmail.com"
        smtp_port = 587
    else:
        smtp_server = f"smtp.{dominio}"
        smtp_port = 587

    # 3. Construir el correo
    msg = MIMEMultipart()
    msg['From'] = remitente_limpio
    msg['To'] = destinatario.strip()
    msg['Subject'] = asunto
    msg.attach(MIMEText(cuerpo, 'plain', 'utf-8'))

    # 4. Adjuntar el PDF
    if ruta_adjunto and os.path.exists(ruta_adjunto):
        with open(ruta_adjunto, "rb") as f:
            adjunto = MIMEApplication(f.read(), _subtype="pdf")
            nombre_archivo = os.path.basename(ruta_adjunto)
            adjunto.add_header('Content-Disposition', 'attachment', filename=nombre_archivo)
            msg.attach(adjunto)

    # 5. Conectar y enviar
    try:
        server = smtplib.SMTP(smtp_server, smtp_port, timeout=15)
        server.ehlo()
        server.starttls() # Iniciar conexión segura
        server.ehlo() # Refrescar la conexión segura (obligatorio para Office365)
        server.login(remitente_limpio, password_limpia)
        server.send_message(msg)
        server.quit()
    except smtplib.SMTPAuthenticationError as e:
        # Extraer el mensaje exacto que nos devuelve Microsoft
        error_msg = e.smtp_error.decode('utf-8') if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
        raise Exception(f"Microsoft ha bloqueado la conexión.\n\nMensaje técnico del servidor:\n{error_msg}")
    except Exception as e:
        raise Exception(f"No se pudo conectar al servidor {smtp_server}.\n\nDetalles:\n{str(e)}")