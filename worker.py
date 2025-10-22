#!/usr/bin/env python3
"""
Worker RQ – versão compatível com rq>=2.0
"""

import os
import redis
from rq import Worker, Queue
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base
from datetime import datetime
import mercadopago
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# ---------- DB ----------
db_url = os.environ.get("DATABASE_URL", "sqlite:///cobrancas.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)

engine = create_engine(db_url, pool_pre_ping=True, pool_recycle=3600)
Session = sessionmaker(bind=engine, expire_on_commit=False)
Base = declarative_base()

class Cobranca(Base):
    __tablename__ = "cobrancas"
    id = Column(Integer, primary_key=True)
    external_reference = Column(String(100), unique=True, nullable=False)
    cliente_nome = Column(String(200), nullable=False)
    cliente_email = Column(String(200), nullable=False)
    valor = Column(Float, nullable=False)
    status = Column(String(50), default="pending", nullable=False)
    data_criacao = Column(DateTime, default=datetime.utcnow, nullable=False)

# ---------- E-MAIL ----------
def enviar_email_confirmacao(destinatario, nome_cliente, valor, link_produto):
    try:
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.zoho.com")
        smtp_port = int(os.environ.get("SMTP_PORT", 465))
        email_user = os.environ["EMAIL_USER"]
        email_pass = os.environ["EMAIL_PASSWORD"]
    except (KeyError, ValueError) as exc:
        print(f"[WORKER] ERRO de configuração: {exc}")
        return False

    assunto = "Seu e-book chegou! 🎉"
    corpo_html = f"""
    <html>
      <body style="font-family:Arial,sans-serif;background:#f4f4f4;padding:20px;text-align:center;">
        <div style="max-width:600px;margin:0 auto;background:#fff;padding:30px;border-radius:8px;box-shadow:0 4px 8px rgba(0,0,0,.1);">
          <h2 style="color:#27ae60;">Obrigado pela sua compra!</h2>
          <p>Olá <strong>{nome_cliente}</strong>,</p>
          <p>Seu pagamento foi confirmado. Clique no botão abaixo para baixar:</p>
          <a href="{link_produto}" target="_blank" style="display:inline-block;padding:12px 24px;margin:20px 0;background:#3498db;color:#fff;text-decoration:none;border-radius:5px;font-weight:bold;">BAIXAR AGORA</a>
          <p style="font-size:14px;color:#555;">Valor pago: R$ {valor:.2f}</p>
          <hr><small style="color:#888;">Dúvidas? Responda este e-mail.</small>
        </div>
      </body>
    </html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"] = email_user
    msg["To"] = destinatario
    msg.attach(MIMEText(corpo_html, "html"))

    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10) as server:
            server.login(email_user, email_pass)
            server.sendmail(email_user, destinatario, msg.as_string())
        print(f"[WORKER] E-mail enviado para {destinatario}")
        return True
    except Exception as exc:
        print(f"[WORKER] Falha ao enviar e-mail: {exc}")
        return False

# ---------- JOB ----------
def process_mercado_pago_webhook(payment_id):
    session = Session()
    try:
        cobranca = session.query(Cobranca).filter_by(external_reference=str(payment_id)).first()
        if not cobranca:
            print(f"[WORKER] Cobrança {payment_id} não encontrada.")
            return
        if cobranca.status != "approved":
            print(f"[WORKER] Status {cobranca.status} ≠ approved. Nada a fazer.")
            return
        if cobranca.status == "delivered":
            print(f"[WORKER] Produto já entregue para {payment_id}.")
            return

        link = os.environ.get("LINK_PRODUTO",
                              "https://drive.google.com/file/d/1HlMExRRjV5Wn5SUNZktc46ragh8Zj8uQ/view?usp=sharing")

        ok = enviar_email_confirmacao(destinatario=cobranca.cliente_email,
                                      nome_cliente=cobranca.cliente_nome,
                                      valor=cobranca.valor,
                                      link_produto=link)
        if not ok:
            raise RuntimeError("E-mail não enviado – re-enfileirando.")

        cobranca.status = "delivered"
        session.commit()
        print(f"[WORKER] Entrega concluída para {cobranca.cliente_email}.")
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()

# ---------- WORKER ----------
if __name__ == "__main__":
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379")
    redis_conn = redis.from_url(redis_url)

    Base.metadata.create_all(engine)
    queue = Queue("default", connection=redis_conn)
    worker = Worker([queue], connection=redis_conn)
    print("[WORKER] Worker iniciado – aguardando jobs...")
    worker.work()
