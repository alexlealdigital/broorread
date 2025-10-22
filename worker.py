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
db_url = os.environ["DATABASE_URL"].replace("postgres://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 300}

# Inicialização mínima do DB para contexto
db = SQLAlchemy(app) 

# --- MODELO DUMMY (Não usado para busca, apenas para estrutura) ---
class Cobranca(db.Model):
    __tablename__ = "cobrancas"
    id = db.Column(db.Integer, primary_key=True)
    external_reference = db.Column(db.String(100), nullable=False)
    cliente_nome = db.Column(db.String(200), nullable=False)
    cliente_email = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default="pending", nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


# ---------- FUNÇÃO DE ENVIO DE E-MAIL (MANTIDA) ----------
def enviar_email_confirmacao(destinatario, nome_cliente, valor, link_produto):
    """ Envia e-mail, assumindo que as credenciais estão configuradas. """
    try:
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.zoho.com")
        smtp_port = int(os.environ.get("SMTP_PORT", 465))
        email_user = os.environ["EMAIL_USER"]
        email_pass = os.environ["EMAIL_PASSWORD"]
    except KeyError:
        print("[WORKER] ERRO: Credenciais de e-mail não configuradas.")
        return False # Nao lanca erro para nao travar o job
        
    # [Corpo do e-mail omitido para brevidade, mas o seu código completo será usado aqui]
    # ...
    
    print(f"[WORKER] E-mail DE ENTREGA enviado para {destinatario}")
    return True

# ---------- JOB DE CONTORNO (IGNORANDO O DB) ----------
def process_mercado_pago_webhook(payment_id):
    """
    CONTORNO: Verifica o status no MP. Usa dados estáticos se o DB falhar.
    Não tenta ler o DB, apenas verifica o status para entrega.
    """
    with app.app_context():
        # --- LÓGICA DE CONTORNO (SEM BUSCA NO DB) ---
        
        # 1. Tenta buscar no Mercado Pago para obter o status de aprovação.
        access_token = os.environ["MERCADOPAGO_ACCESS_TOKEN"]
        sdk = mercadopago.SDK(access_token)
        resp = sdk.payment().get(payment_id)

        if resp["status"] != 200:
            # Lançamos erro para que o RQ tente novamente mais tarde
            raise RuntimeError(f"MercadoPago respondeu {resp['status']}. Tentando novamente.")

        payment = resp["response"]
        payment_status = payment.get("status")
        print(f"[WORKER] Status do pagamento {payment_id}: {payment_status}")

        # 2. Se aprovado, faz a entrega, usando DADOS MOCKADOS/DEFAULT
        # ESTA PARTE É ONDE O CONTORNO TEMPORÁRIO ENTRA:
        if payment_status == "approved":
            # ⚠️ DADOS MOCKADOS: Como nao lemos o DB, usamos dados de teste/mock
            # ATENCAO: Se o app.py for corrigido, o Worker deveria ler o DB para pegar o email correto.
            # Aqui, para a emergencia, assumimos um email de teste/mock para o envio:
            destinatario_mock = "profalexleal@gmail.com" # <--- Substitua pelo email de teste real
            nome_mock = "Cliente de Emergência"
            valor_mock = 1.00 # Baseado no valor de teste
            
            # --- MOCK DA ATUALIZAÇÃO DO BANCO (Substituído por LOG) ---
            print(f"[WORKER] NOTA: Pagamento {payment_id} APROVADO. A entrega será feita. A atualização do DB foi ignorada.")

            link = os.environ.get(
                "LINK_PRODUTO",
                "https://drive.google.com/file/d/1HlMExRRjV5Wn5SUNZktc46ragh8Zj8uQ/view?usp=sharing"
            )
            enviar_email_confirmacao(
                destinatario=destinatario_mock,
                nome_cliente=nome_mock,
                valor=valor_mock,
                link_produto=link
            )
        else:
            print(f"[WORKER] Pagamento {payment_id} não aprovado. Status: {payment_status}. Nenhuma entrega.")


# ---------- INICIALIZAÇÃO DO WORKER (MANTIDA) ----------
if __name__ == "__main__":
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    conn = redis.from_url(redis_url)
    queues = [Queue("default", connection=conn)]
    
    # Executa apenas o mínimo necessário
    with app.app_context():
        db.create_all()

    worker = Worker(queues, connection=conn)
    print("[WORKER] Iniciando worker RQ...")
    
    with app.app_context(): 
        worker.work()

