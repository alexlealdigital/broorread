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
import time  # <--- Necessário para a lógica de re-tentativa

# ---------- CONFIGURAÇÃO DO FLASK / DB ----------
app = Flask(__name__)

# Corrige o esquema da URL para compatibilidade com psycopg (versão 3)
db_url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 300}

db = SQLAlchemy(app)

# ---------- MODELO ----------
class Cobranca(db.Model):
    __tablename__ = "cobrancas"
    id = db.Column(db.Integer, primary_key=True)
    external_reference = db.Column(db.String(100), unique=True, nullable=False)
    cliente_nome = db.Column(db.String(200), nullable=False)
    cliente_email = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default="pending", nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

# ---------- E-MAIL (Código de envio omitido para brevidade, mas deve estar completo no seu arquivo) ----------
def enviar_email_confirmacao(destinatario, nome_cliente, valor, link_produto):
    # Seu código de envio de e-mail completo aqui
    try:
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.zoho.com")
        # ... (restante da lógica de e-mail) ...
        print(f"[WORKER] E-mail enviado para {destinatario}")
        return True
    except Exception as e:
        print(f"Erro ao enviar e-mail: {str(e)}")
        return False
        
# ---------- JOB COM LÓGICA DE RE-TENTATIVA (RETRY LOOP) ----------
def process_mercado_pago_webhook(payment_id):
    """
    Executado pelo RQ. Implementa lógica de re-tentativa para garantir a leitura do DB.
    """
    with app.app_context():
        if not payment_id:
            raise ValueError("payment_id vazio")

        # --- LÓGICA DE RE-TENTATIVA (RETRY LOOP) ---
        cobranca = None
        MAX_TRIES = 5     # Tenta ler o DB no máximo 5 vezes
        WAIT_SECONDS = 1  # Espera 1 segundo entre as tentativas
        
        for attempt in range(MAX_TRIES):
            # Tenta ler o dado do DB
            cobranca = Cobranca.query.filter_by(external_reference=str(payment_id)).first()
            
            if cobranca:
                print(f"[WORKER] Cobrança {payment_id} encontrada na tentativa {attempt + 1}.")
                break  # Sai do loop, o registro foi encontrado
            
            print(f"[WORKER] Cobrança {payment_id} não encontrada na tentativa {attempt + 1}. Aguardando {WAIT_SECONDS}s...")
            time.sleep(WAIT_SECONDS) # Se não encontrou, espera 1s e tenta de novo

        # --- VERIFICAÇÃO FINAL APÓS O LOOP ---
        if not cobranca:
            # Se a leitura falhar após 5 tentativas, lança o erro (o RQ tentará o Job novamente mais tarde)
            raise RuntimeError(f"Cobrança não encontrada após {MAX_TRIES} tentativas para payment_id={payment_id}")
            
        # O restante do código só será executado se 'cobranca' for encontrado.

        access_token = os.environ["MERCADOPAGO_ACCESS_TOKEN"]
        sdk = mercadopago.SDK(access_token)
        resp = sdk.payment().get(payment_id)

        if resp["status"] != 200:
            raise RuntimeError(f"MercadoPago respondeu {resp['status']}: {resp}")

        payment = resp["response"]
        payment_status = payment.get("status")
        print(f"[WORKER] Status do pagamento {payment_id}: {payment_status}")

        # ---------- ATUALIZA BANCO ----------
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
    conn = redis.from_url(redis_url)
    queues = [Queue("default", connection=conn)]
    
    # CRIA AS TABELAS E GARANTE O CONTEXTO DE INICIALIZAÇÃO
    with app.app_context():
        db.create_all()

    worker = Worker(queues, connection=conn)
    print("[WORKER] Iniciando worker RQ...")
    
    # ENVOLVE worker.work() NO CONTEXTO DA APLICAÇÃO
    with app.app_context(): 
        worker.work()
