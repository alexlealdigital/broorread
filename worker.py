#!/usr/bin/env python3
"""
Worker RQ – CONTORNO DE EMERGÊNCIA
IGNORA O BANCO DE DADOS (DB) PARA PRIORIZAR A ENTREGA IMEDIATA DO PRODUTO.
Apenas verifica o status do pagamento no MP e envia o e-mail se aprovado.
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
import time

# --- CONFIGURAÇÃO DO FLASK / DB (MANTIDA, MAS NÃO USADA PARA BUSCA) ---
app = Flask(__name__)

# URL deve ser a mesma do app.py
db_url = os.environ.get("DATABASE_URL", "sqlite:///cobrancas.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 300}

# Inicialização mínima do DB para contexto
db = SQLAlchemy(app) 

# --- MODELO CORRIGIDO (Usando tipos do db.Column) ---
class Cobranca(db.Model):
    __tablename__ = "cobrancas"
    # CORREÇÃO: Usando db.Integer, db.String, etc., que são definidos pelo Flask-SQLAlchemy
    id = db.Column(db.Integer, primary_key=True)
    external_reference = db.Column(db.String(100), nullable=False)
    cliente_nome = db.Column(db.String(200), nullable=False)
    cliente_email = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default="pending", nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# Criação das tabelas (necessário para inicialização)
with app.app_context():
    db.create_all()


# ---------- FUNÇÃO DE ENVIO DE E-MAIL (CORRIGIDA PARA PROTOCOLO SSL) ----------
def enviar_email_confirmacao(destinatario, nome_cliente, valor, link_produto):
    """ Envia e-mail, usando SMTP_SSL para máxima compatibilidade. """
    try:
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.zoho.com")
        smtp_port = int(os.environ.get("SMTP_PORT", 465))
        email_user = os.environ["EMAIL_USER"]
        email_pass = os.environ["EMAIL_PASSWORD"]
    except KeyError:
        print("[WORKER] ERRO: Credenciais de e-mail não configuradas.")
        return False
        
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Produto APROVADO - Seu E-book está pronto! 🎉"
    msg["From"] = email_user
    msg["To"] = destinatario
    
    corpo_html = f"""
        <!doctype html><html><body>
        <h1>✅ Pagamento Aprovado!</h1>
        <p>Olá, {nome_cliente}! Seu pagamento de R$ {valor:.2f} foi aprovado.</p>
        <p><a href="{link_produto}">📥 BAIXAR MEU E-BOOK</a></p>
        </body></html>
        """
    msg.attach(MIMEText(corpo_html, "html"))
    
    # 🔑 CORREÇÃO SMTP: Usando SMTP_SSL na porta 465 (mais robusto)
    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10) as server:
            server.login(email_user, email_pass)
            server.send_message(msg)
    except Exception as exc:
        print(f"[WORKER] Falha no envio SMTP: {exc}")
        return False
    
    print(f"[WORKER] E-mail DE ENTREGA enviado para {destinatario}")
    return True

# ---------- JOB DE CONTORNO (IGNORANDO O DB) ----------
def process_mercado_pago_webhook(payment_id, email_cliente=None):
	    """
	    PLANO B: Recebe o e-mail real pelo Job (enfileirado pelo app.py) e ignora o DB.
	    """
    with app.app_context():
        access_token = os.environ["MERCADOPAGO_ACCESS_TOKEN"]
        sdk = mercadopago.SDK(access_token)
        resp = sdk.payment().get(payment_id)

        if resp["status"] != 200:
            raise RuntimeError(f"MP respondeu {resp['status']}")

	        payment = resp["response"]
	        if payment.get("status") != "approved":
	            print(f"[WORKER] Pagamento {payment_id} não aprovado.")
	            return
	
	        # 🔑 CORREÇÃO: Usa o e-mail que veio do Job. Se não vier, levanta um erro, pois o app.py deve fornecê-lo.
	        if not email_cliente:
	            print(f"[WORKER] ERRO CRÍTICO: E-mail do cliente não fornecido para o job {payment_id}.")
	            return
	            
	        destinatario = email_cliente
	        nome_mock    = "Cliente" # Mantém o mock, pois o DB é ignorado
	        valor_mock   = 1.00    # Mantém o mock, pois o DB é ignorado
	        link         = os.environ.get("LINK_PRODUTO",
	                       "https://drive.google.com/file/d/1HlMExRRjV5Wn5SUNZktc46ragh8Zj8uQ/view?usp=sharing")
	
	        enviar_email_confirmacao(destinatario=destinatario,
	                                 nome_cliente=nome_mock,
	                                 valor=valor_mock,
	                                 link_produto=link)
	        print(f"[WORKER] E-mail enviado para {destinatario}")


# ---------- INICIALIZAÇÃO DO WORKER ----------
if __name__ == "__main__":
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    redis_conn = redis.from_url(redis_url)

    with app.app_context():
    db.create_all()

    # Todas estas linhas devem ter o mesmo nível de indentação (4 espaços)
    worker = Worker(["default"], connection=redis_conn)
    print("[WORKER] Worker iniciado – aguardando jobs...")
    
    with app.app_context(): 
    worker.work()

