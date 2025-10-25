#!/usr/bin/env python3
"""
Worker RQ – ARQUITETURA "PLANO A"
Ouve a fila por jobs (contendo o payment_id) enviados pelo webhook.
Se o pagamento estiver aprovado, busca os dados no DB e envia o produto correto.
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

# --- CONFIGURAÇÃO DO FLASK / DB ---
app = Flask(__name__)

db_url = os.environ.get("DATABASE_URL", "sqlite:///cobrancas.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 300}

db = SQLAlchemy(app) 

# --- MODELOS DE DADOS (AGORA SINCRONIZADOS COM APP.PY) ---

class Cobranca(db.Model):
    __tablename__ = "cobrancas"
    id = db.Column(db.Integer, primary_key=True)
    external_reference = db.Column(db.String(100), nullable=False)
    cliente_nome = db.Column(db.String(200), nullable=False)
    cliente_email = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default="pending", nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # --- ADIÇÃO (DEVE SER IGUAL AO APP.PY) ---
    product_id = db.Column(db.Integer, db.ForeignKey('produtos.id'), nullable=True)
    produto = db.relationship('Produto')
    # --- FIM DA ADIÇÃO ---

# --- ADIÇÃO (MODELO PRODUTO É NECESSÁRIO AQUI TAMBÉM) ---
class Produto(db.Model):
    __tablename__ = "produtos"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    preco = db.Column(db.Float, nullable=False)
    link_download = db.Column(db.String(500), nullable=False)
# --- FIM DA ADIÇÃO ---


# Criação das tabelas (vai criar 'produtos' e atualizar 'cobrancas')
with app.app_context():
    db.create_all()


# ---------- FUNÇÃO DE ENVIO DE E-MAIL (SEM MUDANÇAS) ----------
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
    
    # Definição da função
def enviar_email_confirmacao(destinatario, nome_cliente, valor, link_produto, cobranca, nome_produto): # <-- Adicione nome_produto
    # ... (try smtp_server, etc.) ...

    corpo_html = f"""
<!doctype html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: 'Lato', Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f4f4f4; }}
    .email-wrapper {{ background-color: #f4f4f4; padding: 20px 0; }}
    .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; }}
    .header {{ background-color: #14213d; padding: 20px; text-align: center; }}
    .header h1 {{ color: #ffffff; font-family: 'Poppins', sans-serif; font-size: 1.8em; margin: 0; }}
    .content {{ padding: 30px; }}
    h2 {{ color: #fca311; font-family: 'Poppins', sans-serif; font-size: 1.5em; margin: 25px 0 15px 0; text-align: center; }}
    p {{ margin-bottom: 15px; font-size: 1em; color: #555; }}
    strong {{ color: #14213d; }}
    .button-container {{ text-align: center; margin: 25px 0; }}
    .button {{ 
        background-color: #fca311;
        color: #14213d !important;
        padding: 14px 28px; 
        text-decoration: none !important;
        border-radius: 25px; 
        font-weight: bold; 
        display: inline-block; 
        font-family: 'Poppins', sans-serif;
        font-size: 1.1em;
        border: none;
        cursor: pointer;
        text-align: center;
        transition: background-color 0.3s ease, transform 0.2s ease;
    }}
    .button:hover {{ background-color: #e0900b; transform: scale(1.03); }}
    .footer-text {{ font-size: 0.9em; color: #777; margin-top: 25px; border-top: 1px solid #e5e5e5; padding-top: 20px; text-align: center; }}
    .link-copy {{ word-break: break-all; font-family: monospace; font-size: 0.85em; background-color: #f0f0f0; padding: 5px; border-radius: 4px; display: block; margin-top: 5px; }}
    .brand-dot {{ color: #fca311; font-weight: bold; }}
    a {{ color: #fca311; text-decoration: underline; }}
  </style>
</head>
<body>
  <div class="email-wrapper">
    <div class="container">
      <div class="header">
        <h1>✅ Parabéns pela sua compra!</h1>
      </div>
      <div class="content">
        <p>Olá, {nome_cliente},</p>
        
        <p>Agradecemos por escolher a <strong>R·READ</strong>! Seu pagamento de <strong>R$ {valor:.2f}</strong> referente ao e-book "<strong>{nome_produto}</strong>" foi confirmado.</p>
        
        <h2>Agora é hora de devorar o conteúdo!</h2>
        
        <p>Clique no nosso <span class="brand-dot">·</span> (micro-portal!) abaixo para acessar seu e-book:</p>
        
        <div class="button-container"> 
          <a href="{link_produto}" class="button" target="_blank">[·] Baixar Meu E-book Agora</a>
        </div>

        <p style="font-size: 0.9em; color: #777;">Se o botão não funcionar, copie e cole o link abaixo no seu navegador:</p>
        <code class="link-copy">{link_produto}</code>
        
        <div class="footer-text">
          Boas leituras!<br>
          Equipe <strong>R·READ / B·ROO banca digital</strong>
          <br><br>
          Pedido ID: {cobranca.id} <br> 
          Lembre-se: nosso <span class="brand-dot">·</span> não é só um ponto, é uma experiência! A interação é o nosso DNA. <br>
          Em caso de dúvidas, responda a este e-mail.
        </div>
      </div>
    </div>
  </div>
</body>
</html>
"""
    # Restante da função de envio de e-mail...
    msg.attach(MIMEText(corpo_html, "html"))
    # ... try enviar email ...
    # Restante da função...
def enviar_email_confirmacao(destinatario, nome_cliente, valor, link_produto, cobranca, nome_produto): # <-- Adicione nome_produto
    # ... (try smtp_server, etc.) ...

    corpo_html = f"""
<!doctype html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    {/* ... (Estilos CSS com chaves duplicadas {{ }}) ... */}
  </style>
</head>
<body>
  <div class="email-wrapper">
    <div class="container">
      <div class="header">
        <h1>✅ Parabéns pela sua compra!</h1>
      </div>
      <div class="content">
        <p>Olá, {nome_cliente},</p>

        <p>Agradecemos por escolher a <strong>R·READ</strong>! Seu pagamento de <strong>R$ {valor:.2f}</strong> referente ao e-book "<strong>{nome_produto}</strong>" foi confirmado.</p> {/* <-- Use nome_produto aqui */}

        <h2>Agora é hora de devorar o conteúdo!</h2>

        <p>Clique no nosso <span class="brand-dot">·</span> (micro-portal!) abaixo para acessar seu e-book:</p>

        <div class="button-container"> 
          <a href="{link_produto}" class="button" target="_blank">[·] Baixar Meu E-book Agora</a>
        </div>

        <p style="font-size: 0.9em; color: #777;">Se o botão não funcionar, copie e cole o link abaixo no seu navegador:</p>
        <code class="link-copy">{link_produto}</code>

        <div class="footer-text">
          Boas leituras!<br>
          Equipe <strong>R·READ / B·ROO banca digital</strong>
          <br><br>
          Pedido ID: {cobranca.id} <br> 
          Lembre-se: nosso <span class="brand-dot">·</span> não é só um ponto, é uma experiência! A interação é o nosso DNA. <br>
          Em caso de dúvidas, responda a este e-mail.
        </div>
      </div>
    </div>
  </div>
</body>
</html>
"""
    msg.attach(MIMEText(corpo_html, "html"))
    # ... (Resto da função de envio) ...
   
    # Restante da função...

    # Restante da função...
    # Restante da função...
    msg.attach(MIMEText(corpo_html, "html"))
    
    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10) as server:
            server.login(email_user, email_pass)
            server.send_message(msg)
    except Exception as exc:
        print(f"[WORKER] Falha no envio SMTP: {exc}")
        return False
    
    print(f"[WORKER] E-mail DE ENTREGA enviado para {destinatario}")
    return True

# --- MODIFICAÇÃO CRÍTICA: LÓGICA DO "PLANO A" ---
# ---------- JOB DO "PLANO A" (USANDO O DB) ----------
def process_mercado_pago_webhook(payment_id):
    """
    PLANO A: Recebe o payment_id do webhook, consulta o MP, 
    e se APROVADO, busca os dados REAIS (email e produto) 
    no nosso DB para fazer a entrega.
    """
    with app.app_context():
        access_token = os.environ["MERCADOPAGO_ACCESS_TOKEN"]
        sdk = mercadopago.SDK(access_token)
        
        try:
            resp = sdk.payment().get(payment_id)
        except Exception as e:
            print(f"[WORKER] Falha ao consultar MP para o ID {payment_id}: {e}")
            return # Falha, o RQ tentará novamente

        if resp["status"] != 200:
            raise RuntimeError(f"MP respondeu {resp['status']} para o ID {payment_id}")

        payment = resp["response"]
        
        if payment.get("status") != "approved":
            print(f"[WORKER] Pagamento {payment_id} não aprovado ({payment.get('status')}). Ignorando.")
            return

        # 1. BUSCA A COBRANÇA NO NOSSO DB
        print(f"[WORKER] Pagamento {payment_id} APROVADO. Buscando no DB...")
        cobranca = Cobranca.query.filter_by(external_reference=str(payment_id)).first()

        if not cobranca:
            print(f"[WORKER] ERRO CRÍTICO: Cobrança {payment_id} aprovada, mas não encontrada no DB.")
            return

        # 2. BUSCA O PRODUTO CORRETO (usando o relationship)
        produto = cobranca.produto
        
        if not produto:
            print(f"[WORKER] ERRO CRÍTICO: Produto ID {cobranca.product_id} não encontrado no DB.")
            return

        # 3. USA OS DADOS REAIS DO BANCO DE DADOS
        destinatario = cobranca.cliente_email
        nome_cliente = cobranca.cliente_nome
        valor_real = cobranca.valor
        link_real = produto.link_download

        print(f"[WORKER] Enviando produto '{produto.nome}' para {destinatario}...")

        sucesso = enviar_email_confirmacao(destinatario=destinatario,
                                           nome_cliente=nome_cliente,
                                           valor=valor_real,
                                           link_produto=link_real)
        
        if sucesso:
            print(f"[WORKER] E-mail (Plano A) enviado com sucesso para {destinatario}.")
            # (Opcional) Atualiza o status no DB
            cobranca.status = "delivered" 
            db.session.commit()
        else:
            print(f"[WORKER] Falha no envio de e-mail (Plano A) para {destinatario}.")
# --- FIM DA MODIFICAÇÃO ---


# ---------- INICIALIZAÇÃO DO WORKER (SEM MUDANÇAS) ----------
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








