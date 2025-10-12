import os
import mercadopago
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import redis
from rq import Worker, Queue
from datetime import datetime  # <--- CORREÇÃO 1: Importação adicionada

# Configuração do Banco de Dados (sem alterações)
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
db_url = os.environ.get("DATABASE_URL", "sqlite:///cobrancas.db")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
    

if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Modelo Cobranca (sem alterações)
class Cobranca(db.Model):
    __tablename__ = "cobrancas"
    id = db.Column(db.Integer, primary_key=True)
    external_reference = db.Column(db.String(100), unique=True, nullable=False)
    cliente_nome = db.Column(db.String(200), nullable=False)
    cliente_email = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default="pending", nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

# Função para enviar e-mail (sem alterações)
def enviar_email_confirmacao(destinatario, nome_cliente, valor, link_produto):
    """
    Envia e-mail de confirmação de pagamento com link do produto
    """
    try:
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.zoho.com")
        smtp_port = int(os.environ.get("SMTP_PORT", 465))
        email_user = os.environ.get("EMAIL_USER")
        email_password = os.environ.get("EMAIL_PASSWORD")
        
        if not email_user or not email_password:
            print("Erro: Credenciais de e-mail não configuradas")
            return False
        
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "Pagamento Confirmado - Seu E-book está pronto!"
        msg["From"] = email_user
        msg["To"] = destinatario
        
        # ... (corpo do e-mail sem alterações) ...
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .container {{ max-width: 600px; margin: 0 auto; padding: 20px; background-color: #f9f9f9; }}
                .header {{ background-color: #27ae60; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ background-color: white; padding: 30px; border-radius: 0 0 5px 5px; }}
                .button {{ display: inline-block; padding: 15px 30px; background-color: #27ae60; color: white; text-decoration: none; border-radius: 5px; margin: 20px 0; font-weight: bold; }}
                .footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header"><h1>✅ Pagamento Confirmado!</h1></div>
                <div class="content">
                    <p>Olá, <strong>{nome_cliente}</strong>!</p>
                    <p>Temos uma ótima notícia! Seu pagamento no valor de <strong>R$ {valor:.2f}</strong> foi confirmado com sucesso.</p>
                    <p>Agora você já pode acessar seu e-book clicando no botão abaixo:</p>
                    <div style="text-align: center;"><a href="{link_produto}" class="button">📥 BAIXAR MEU E-BOOK</a></div>
                    <p><strong>Link direto:</strong>  
<a href="{link_produto}">{link_produto}</a></p>
                    <p>Aproveite sua leitura e qualquer dúvida, estamos à disposição!</p>
                    <p>Atenciosamente,  
<strong>Equipe Lab Leal</strong></p>
                </div>
                <div class="footer"><p>Este é um e-mail automático. Por favor, não responda.</p></div>
            </div>
        </body>
        </html>
        """
        text_body = f"Pagamento Confirmado!\n\nOlá, {nome_cliente}!\n\nSeu pagamento no valor de R$ {valor:.2f} foi confirmado com sucesso.\n\nAcesse seu e-book através do link abaixo:\n{link_produto}\n\nAtenciosamente,\nEquipe Lab Leal"
        
        part1 = MIMEText(text_body, "plain")
        part2 = MIMEText(html_body, "html")
        msg.attach(part1)
        msg.attach(part2)
        
        with smtplib.SMTP_SSL(smtp_server, smtp_port) as server:
            server.login(email_user, email_password)
            server.send_message(msg)
        
        print(f"E-mail de confirmação enviado para {destinatario}")
        return True
        
    except Exception as e:
        print(f"Erro ao enviar e--mail: {str(e)}")
        return False

# Função do worker (sem alterações)
def process_mercado_pago_webhook(payment_id):
    with app.app_context():
        try:
            if not payment_id:
                print("ID do pagamento não encontrado na notificação de background")
                return
            
            access_token = os.environ.get("MERCADOPAGO_ACCESS_TOKEN")
            if not access_token:
                print("Token do Mercado Pago não configurado para processamento em background")
                return
            
            sdk = mercadopago.SDK(access_token)
            payment_info = sdk.payment().get(payment_id)
            
            if payment_info["status"] != 200:
                print(f"Erro ao consultar pagamento em background: {payment_info}")
                return
            
            payment = payment_info["response"]
            payment_status = payment.get("status")
            
            print(f"[WORKER] Status do pagamento {payment_id}: {payment_status}")
            
            cobranca = Cobranca.query.filter_by(external_reference=str(payment_id)).first()
            
            if not cobranca:
                print(f"[WORKER] Cobrança não encontrada para o payment_id: {payment_id}")
                return
            
            cobranca.status = payment_status
            db.session.commit()
            
            print(f"[WORKER] Status da cobrança atualizado para: {payment_status}")
            
            if payment_status == "approved":
                print(f"[WORKER] Pagamento aprovado! Enviando e-mail para {cobranca.cliente_email}")
                
                link_produto = os.environ.get("LINK_PRODUTO", "https://drive.google.com/file/d/1HlMExRRjV5Wn5SUNZktc46ragh8Zj8uQ/view?usp=sharing" )
                
                email_enviado = enviar_email_confirmacao(
                    destinatario=cobranca.cliente_email,
                    nome_cliente=cobranca.cliente_nome,
                    valor=cobranca.valor,
                    link_produto=link_produto
                )
                
                if email_enviado:
                    print("[WORKER] E-mail de confirmação enviado com sucesso!")
                else:
                    print("[WORKER] Falha ao enviar e-mail de confirmação")
            
        except Exception as e:
            print(f"[WORKER] Erro ao processar webhook: {str(e)}")

# --- CORREÇÃO 2: Bloco de inicialização do worker ---
# --- BLOCO CORRIGIDO ---
if __name__ == '__main__':
    listen = ['default']
    redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    conn = redis.from_url(redis_url)

    print(f"Iniciando worker para as filas: {listen}")

    # Cria uma lista de objetos Queue, passando a conexão para cada um
    queues = [Queue(name, connection=conn) for name in listen]
    
    # Passa a lista de filas e a conexão para o Worker
    worker = Worker(queues, connection=conn)
    
    worker.work()


