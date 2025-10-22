import os
import sys
import mercadopago
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import time
import redis
from rq import Worker, Connection, Queue

# Este módulo é executado pelo RQ (Redis Queue).
# Ele precisa de uma configuração de DB e do modelo para buscar os dados.

# ---------- CONFIGURAÇÃO DO BANCO DE DADOS (FORA DO CONTEXTO FLASK) ----------
# O Worker precisa acessar o DB de forma independente (usando SQLAlchemy nativo).
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

db_url = os.environ.get("DATABASE_URL", "sqlite:///cobrancas.db")

# Lógica para compatibilidade com driver PostgreSQL (psycopg) no Render
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

# Inicialização do SQLAlchemy sem Flask-SQLAlchemy
Engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=3600)
Base = declarative_base()
Session = sessionmaker(bind=Engine)

# ---------- MODELO DE DADOS (REPLICADO) ----------
class Cobranca(Base):
    """Modelo de dados para a tabela 'cobrancas'."""
    __tablename__ = "cobrancas"
    id = Column(Integer, primary_key=True)
    external_reference = Column(String(100), unique=True, nullable=False)
    cliente_nome = Column(String(200), nullable=False)
    cliente_email = Column(String(200), nullable=False)
    valor = Column(Float, nullable=False)
    status = Column(String(50), default="pending", nullable=False)
    data_criacao = Column(DateTime, default=datetime.utcnow, nullable=False)

# --- FUNÇÃO DE ENVIO DE E-MAIL (AGORA COMPLETA) ---

def enviar_email_confirmacao(destinatario, nome_cliente, valor, link_produto):
    """Envia o e-mail de entrega do e-book (ou qualquer produto digital)."""
    
    # 1. Obtenção Segura das Variáveis de Ambiente
    try:
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.zoho.com")
        smtp_port = int(os.environ.get("SMTP_PORT", 465))
        # Estas devem ser as variáveis com sync: false no Render
        email_user = os.environ["EMAIL_USER"]
        email_pass = os.environ["EMAIL_PASSWORD"]
        
        if not destinatario or not link_produto:
            print("[WORKER] Erro: Email do cliente ou Link do Produto estão vazios.")
            return False

    except KeyError as exc:
        print(f"[WORKER] ERRO: Variável de ambiente essencial faltando → {exc}")
        return False
    except ValueError:
        print("[WORKER] ERRO: SMTP_PORT não é um número válido.")
        return False

    # 2. Montagem do E-mail
    assunto = "Seu e-book chegou! 🎉"
    corpo_html = f"""
    <html>
      <body style="font-family:Arial, sans-serif; background-color: #f4f4f4; padding: 20px; text-align: center;">
        <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 20px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
            <h2 style="color: #27ae60;">Obrigado pela sua compra!</h2>
            <p style="font-size: 16px;">Olá <strong>{nome_cliente}</strong>,</p>
            <p style="font-size: 16px;">O seu pagamento foi confirmado. Segue o link exclusivo para download do seu e-book:</p>
            
            <a href="{link_produto}" target="_blank" style="display: inline-block; padding: 10px 20px; margin: 20px 0; background-color: #3498db; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">
                CLIQUE AQUI E BAIXE SEU PRODUTO
            </a>
            
            <p style="font-size: 14px; color: #555;">Valor pago: R$ {valor:.2f}</p>
            <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
            <small style="color: #888;">Se tiver qualquer dúvida, responda este e-mail. Esta é uma mensagem automática de confirmação de entrega.</small>
        </div>
      </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"] = email_user
    msg["To"] = destinatario
    msg.attach(MIMEText(corpo_html, "html"))

    # 3. Conexão e Envio SMTPLIB
    try:
        # Usa SMTP_SSL para a porta 465 (Conexão SSL imediata)
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(email_user, email_pass)
            server.sendmail(email_user, destinatario, msg.as_string())
        
        print(f"[WORKER] E-mail DE ENTREGA enviado para {destinatario}")
        return True
    
    except smtplib.SMTPAuthenticationError:
        print("[WORKER] Erro de Autenticação SMTP. Verifique EMAIL_USER/PASSWORD.")
        return False
    except Exception as exc:
        print(f"[WORKER] Falha ao enviar e-mail (Exceção Geral): {exc}")
        return False

# --- FUNÇÃO PRINCIPAL DO RQ JOB ---

def process_mercado_pago_webhook(payment_id):
    """
    Processa a notificação, verifica o status no DB (ou MP) e envia o produto.
    """
    print(f"[WORKER] Processando payment_id: {payment_id}")
    
    session = Session()
    try:
        # 1. BUSCAR DADOS DA COBRANÇA DO DB
        cobranca = session.query(Cobranca).filter(
            Cobranca.external_reference == str(payment_id)
        ).first()

        if not cobranca:
            print(f"[WORKER] Cobrança {payment_id} não encontrada no DB. Pulando.")
            session.close()
            return

        # 2. VERIFICAR STATUS (Assumindo que o status no DB está atualizado pelo webhook)
        payment_status = cobranca.status 
        
        # 3. LÓGICA DE ENTREGA
        if payment_status == "approved":
            # 3.1. Busca dados para o E-mail
            destinatario = cobranca.cliente_email
            nome_cliente = cobranca.cliente_nome
            valor = cobranca.valor

            # 3.2. Busca o link do produto no ambiente
            link = os.environ.get(
                "LINK_PRODUTO",
                # Fallback, caso a variável não esteja setada
                "https://drive.google.com/file/d/1HlMExRRjV5Wn5SUNZktc46ragh8Zj8uQ/view?usp=sharing"
            )

            # 3.3. Chama a função de envio
            ok = enviar_email_confirmacao(
                destinatario=destinatario,
                nome_cliente=nome_cliente,
                valor=valor,
                link_produto=link
            )

            # 3.4. Se o envio falhou, forçar re-tentativa
            if not ok:
                # ESSENCIAL: Lança erro para que o RQ re-enfileire o job
                raise RuntimeError("E-mail não foi enviado – job será re-enfileirado pelo RQ")
            
            # Opcional: Marcar no DB que o produto foi entregue (evita re-envio se o webhook for chamado novamente)
            # cobranca.status = "delivered"
            # session.commit()
            
            print(f"[WORKER] Entrega concluída para {destinatario}.")

        else:
            print(f"[WORKER] Pagamento {payment_id} não aprovado ou status: {payment_status}. Nenhuma entrega.")
            
        session.close()

    except Exception as e:
        session.rollback()
        session.close()
        # Re-lança o erro para que o RQ o capture e re-enfileire o job
        raise e

# --- INICIALIZAÇÃO DO WORKER (SETUP RQ) ---

if __name__ == '__main__':
    # Configuração do Redis (mesma do app.py)
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    try:
        redis_conn = redis.from_url(redis_url)
    except Exception as e:
        print(f"Erro ao conectar ao Redis: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"[*] Worker pronto para rodar na fila default (Redis: {redis_url}).")
    
    # Executa o Worker
    with Connection(redis_conn):
        worker = Worker(['default'], connection=redis_conn)
        worker.work()
