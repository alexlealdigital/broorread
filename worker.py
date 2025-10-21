#!/usr/bin/env python3
"""
Worker RQ – processa webhooks do Mercado Pago
Dependências: rq, redis, psycopg, flask-sqlalchemy, mercadopago
"""

import os
import mercadopago
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import redis
from rq import Worker, Queue
from datetime import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# ---------- CONFIGURAÇÃO DO FLASK / DB ----------
app = Flask(__name__)

# Corrige o esquema da URL em 1 linha apenas
db_url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"]        = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"]      = {"pool_pre_ping": True, "pool_recycle": 300}

db = SQLAlchemy(app)

# ---------- MODELO ----------
class Cobranca(db.Model):
    __tablename__ = "cobrancas"
    id               = db.Column(db.Integer, primary_key=True)
    external_reference = db.Column(db.String(100), unique=True, nullable=False)
    cliente_nome     = db.Column(db.String(200), nullable=False)
    cliente_email    = db.Column(db.String(200), nullable=False)
    valor            = db.Column(db.Float, nullable=False)
    status           = db.Column(db.String(50), default="pending", nullable=False)
    data_criacao     = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

# ---------- E-MAIL ----------
def enviar_email_confirmacao(destinatario, nome_cliente, valor, link_produto):
    try:
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.zoho.com")
        smtp_port   = int(os.environ.get("SMTP_PORT", 465))
        email_user  = os.environ["EMAIL_USER"]
        email_pass  = os.environ["EMAIL_PASSWORD"]
    except KeyError:
        raise RuntimeError("EMAIL_USER ou EMAIL_PASSWORD não configurados")

    msg            = MIMEMultipart("alternative")
    msg["Subject"] = "Pagamento Confirmado - Seu E-book está pronto!"
    msg["From"]    = email_user
    msg["To"]      = destinatario

    text_body = f"""
    Pagamento Confirmado!

    Olá, {nome_cliente}!
    Seu pagamento de R$ {valor:.2f} foi aprovado.
    Acesse seu e-book: {link_produto}
    """
    html_body = f"""
    <!doctype html>
    <html>
      <head><meta charset="utf-8"></head>
      <body style="font-family:Arial, sans-serif;">
        <div style="max-width:600px;margin:0 auto;padding:20px;background:#f9f9f9;">
          <div style="background:#27ae60;color:white;padding:20px;text-align:center;">
            <h1>✅ Pagamento Confirmado!</h1>
          </div>
          <div style="background:white;padding:30px;">
            <p>Olá, <strong>{nome_cliente}</strong>!</p>
            <p>Seu pagamento de <strong>R$ {valor:.2f}</strong> foi aprovado.</p>
            <p><a href="{link_produto}" style="display:inline-block;padding:15px 30px;background:#27ae60;color:white;text-decoration:none;border-radius:5px;">📥 BAIXAR MEU E-BOOK</a></p>
            <p>Atenciosamente,<br><strong>Equipe Lab Leal</strong></p>
          </div>
        </div>
      </body>
    </html>
    """

    msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
        server.login(email_user, email_pass)
        server.send_message(msg)

    print(f"[WORKER] E-mail enviado para {destinatario}")
    return True

# ---------- JOB ----------
def process_mercado_pago_webhook(payment_id):
    """
    Executado pelo RQ. Re-lança exceções para que o RQ re-tente automaticamente.
    """
    with app.app_context():
        if not payment_id:
            raise ValueError("payment_id vazio")

        access_token = os.environ["MERCADOPAGO_ACCESS_TOKEN"]
        sdk          = mercadopago.SDK(access_token)
        resp         = sdk.payment().get(payment_id)

        if resp["status"] != 200:
            raise RuntimeError(f"MercadoPago respondeu {resp['status']}: {resp}")

        payment       = resp["response"]
        payment_status = payment.get("status")
        print(f"[WORKER] Status do pagamento {payment_id}: {payment_status}")

        # ---------- ATUALIZA BANCO ----------
        cobranca = Cobranca.query.filter_by(external_reference=str(payment_id)).first()
        if not cobranca:
            raise RuntimeError(f"Cobrança não encontrada para payment_id={payment_id}")

        cobranca.status = payment_status
        db.session.commit()
        print(f"[WORKER] Cobrança {payment_id} atualizada para {payment_status}")

        # ---------- E-MAIL (apenas se aprovado) ----------
        if payment_status == "approved":
            link = os.environ.get(
                "LINK_PRODUTO",
                "https://drive.google.com/file/d/1HlMExRRjV5Wn5SUNZktc46ragh8Zj8uQ/view?usp=sharing"
            )
            enviar_email_confirmacao(
                destinatario=cobranca.cliente_email,
                nome_cliente=cobranca.cliente_nome,
                valor=cobranca.valor,
                link_produto=link
            )

# ---------- INICIALIZAÇÃO DO WORKER ----------
if __name__ == "__main__":
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    conn      = redis.from_url(redis_url)
    queues    = [Queue("default", connection=conn)]
    
    # CRIA AS TABELAS SE NECESSÁRIO (boa prática para workers)
    with app.app_context():
        db.create_all()

    worker    = Worker(queues, connection=conn)
    print("[WORKER] Iniciando worker RQ...")
    
    # ENVOLVA worker.work() NO CONTEXTO DA APLICAÇÃO
    with app.app_context(): 
        worker.work()

