import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import streamlit as st

# Chargement des identifiants depuis st.secrets (jamais commité)
EMAIL_ADDRESS = st.secrets["email"]["address"]
APP_PASSWORD = st.secrets["email"]["app_password"]


def send_email(to_email, subject, html_content):
    """Envoie un email HTML sécurisé via SMTP Google."""
    msg = MIMEMultipart("alternative")
    msg["From"] = EMAIL_ADDRESS
    msg["To"] = to_email
    msg["Subject"] = subject

    part = MIMEText(html_content, "html")
    msg.attach(part)

    context = ssl.create_default_context()

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(EMAIL_ADDRESS, APP_PASSWORD)
            server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
        return True
    except Exception as e:
        print("❌ Email error:", e)
        return False