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
from rq import Worker, Queue # Correção: Removido 'Connection'
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


# ---------- FUNÇÃO DE ENVIO DE E-MAIL (CORRIGIDA PARA PROTOCOLO SSL) ----------
def enviar_email_confirmacao(destinatario, nome_cliente, valor, link_produto):
    """ Envia e-mail, usando SMTP_SSL para máxima compatibilidade. """
    try:
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.zoho.com")
        smtp_port = int(os.environ.get("SMTP_PORT", 465))
        email_user = os.environ["EMAIL_USER"]
        email_pass = os.environ["EMAIL_PASSWORD"]
    except KeyError:
        # Se as variáveis de ambiente não estiverem configuradas, falha com log
        print("[WORKER] ERRO: Credenciais de e-mail não configuradas.")
        return False
        
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Produto APROVADO - Seu E-book está pronto!"
    msg["From"] = email_user
    msg["To"] = destinatario
    
    # [Corpo do e-mail omitido para brevidade, mas deve estar completo no seu arquivo]
    html_body = f"""
        <!doctype html><html><body>
        <h1>✅ Pagamento Aprovado!</h1>
        <p>Olá, {nome_cliente}! Seu pagamento de R$ {valor:.2f} foi aprovado.</p>
        <p><a href="{link_produto}">📥 BAIXAR MEU E-BOOK</a></p>
        </body></html>
        """
    msg.attach(MIMEText(html_body, "html"))
    
    # 🔑 CORREÇÃO SMTP: Usando SMTP_SSL na porta 465 (mais robusto)
    with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
        server.login(email_user, email_pass)
        server.send_message(msg)
    
    print(f"[WORKER] E-mail DE ENTREGA enviado para {destinatario}")
    return True

# ---------- JOB DE CONTORNO (IGNORANDO O DB) ----------
def process_mercado_pago_webhook(payment_id):
    """
    CONTORNO: Verifica o status no MP para entrega, IGNORANDO a busca no DB.
    """
    with app.app_context():
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

        # 2. Se aprovado, faz a entrega com dados mockados (para a emergência)
        if payment_status == "approved":
            # ⚠️ DADOS MOCKADOS: Usamos dados de teste, pois a busca no DB falhou.
            destinatario_mock = "profalexleal@gmail.com" # Substitua pelo email de teste real
            nome_mock = "Alex Leal (Cliente Emergencial)"
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


# ---------- INICIALIZAÇÃO DO WORKER ----------
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
