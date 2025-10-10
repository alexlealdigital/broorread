from flask import Flask, jsonify, request, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import os
import mercadopago
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import hmac
import hashlib
import threading # Importar threading para processamento em segundo plano

# Inicialização do Flask
app = Flask(__name__, static_folder='static')

# Configuração de CORS
CORS(app, origins='*')

# Configuração do Banco de Dados
db_url = os.environ.get("DATABASE_URL", "sqlite:///cobrancas.db")

# Fix para PostgreSQL URL (Render usa postgresql://)
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "asdf#FGSgvasgf$5$WGT")

# Inicialização do SQLAlchemy
db = SQLAlchemy(app)

# Modelo de Dados
class Cobranca(db.Model):
    __tablename__ = "cobrancas"
    id = db.Column(db.Integer, primary_key=True)
    external_reference = db.Column(db.String(100), unique=True, nullable=False)
    cliente_nome = db.Column(db.String(200), nullable=False)
    cliente_email = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default="pending", nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    def to_dict(self):
        return {
            "id": self.id,
            "external_reference": self.external_reference,
            "cliente_nome": self.cliente_nome,
            "cliente_email": self.cliente_email,
            "valor": self.valor,
            "status": self.status,
            "data_criacao": self.data_criacao.isoformat() if self.data_criacao else None
        }

# Criação das tabelas
with app.app_context():
    db.create_all()

# Função para enviar e-mail de confirmação
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
        
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    color: #333;
                }}
                .container {{
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #f9f9f9;
                }}
                .header {{
                    background-color: #27ae60;
                    color: white;
                    padding: 20px;
                    text-align: center;
                    border-radius: 5px 5px 0 0;
                }}
                .content {{
                    background-color: white;
                    padding: 30px;
                    border-radius: 0 0 5px 5px;
                }}
                .button {{
                    display: inline-block;
                    padding: 15px 30px;
                    background-color: #27ae60;
                    color: white;
                    text-decoration: none;
                    border-radius: 5px;
                    margin: 20px 0;
                    font-weight: bold;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 20px;
                    color: #666;
                    font-size: 12px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>✅ Pagamento Confirmado!</h1>
                </div>
                <div class="content">
                    <p>Olá, <strong>{nome_cliente}</strong>!</p>
                    
                    <p>Temos uma ótima notícia! Seu pagamento no valor de <strong>R$ {valor:.2f}</strong> foi confirmado com sucesso.</p>
                    
                    <p>Agora você já pode acessar seu e-book clicando no botão abaixo:</p>
                    
                    <div style="text-align: center;">
                        <a href="{link_produto}" class="button">📥 BAIXAR MEU E-BOOK</a>
                    </div>
                    
                    <p><strong>Link direto:</strong><br>
                    <a href="{link_produto}">{link_produto}</a></p>
                    
                    <p>Aproveite sua leitura e qualquer dúvida, estamos à disposição!</p>
                    
                    <p>Atenciosamente,<br>
                    <strong>Equipe Lab Leal</strong></p>
                </div>
                <div class="footer">
                    <p>Este é um e-mail automático. Por favor, não responda.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        text_body = f"""
        Pagamento Confirmado!
        
        Olá, {nome_cliente}!
        
        Seu pagamento no valor de R$ {valor:.2f} foi confirmado com sucesso.
        
        Acesse seu e-book através do link abaixo:
        {link_produto}
        
        Atenciosamente,
        Equipe Lab Leal
        """
        
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
        print(f"Erro ao enviar e-mail: {str(e)}")
        return False

# Função para validar a assinatura do webhook
def validar_assinatura_webhook(request):
    """
    Valida a assinatura do webhook do Mercado Pago
    """
    try:
        x_signature = request.headers.get("x-signature")
        x_request_id = request.headers.get("x-request-id")
        
        if not x_signature or not x_request_id:
            print("Cabeçalhos de assinatura ausentes")
            return False
        
        parts = x_signature.split(",")
        ts = None
        hash_signature = None
        
        for part in parts:
            key_value = part.split("=", 1)
            if len(key_value) == 2:
                key = key_value[0].strip()
                value = key_value[1].strip()
                if key == "ts":
                    ts = value
                elif key == "v1":
                    hash_signature = value
        
        if not ts or not hash_signature:
            print("Timestamp ou hash ausentes na assinatura")
            return False
        
        data_id = request.args.get("data.id", "")
        secret_key = os.environ.get("WEBHOOK_SECRET")
        
        if not secret_key:
            print("Secret key não configurada")
            return False
        
        manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
        calculated_hash = hmac.new(
            secret_key.encode(),
            manifest.encode(),
            hashlib.sha256
        ).hexdigest()
        
        if calculated_hash == hash_signature:
            print("Assinatura validada com sucesso")
            return True
        else:
            print(f"Assinatura inválida. Esperado: {hash_signature}, Calculado: {calculated_hash}")
            return False
            
    except Exception as e:
        print(f"Erro ao validar assinatura: {str(e)}")
        return False

# Função para processar o webhook em segundo plano
def processar_webhook_background(dados_webhook, app_context):
    with app_context:
        try:
            payment_id = dados_webhook.get("data", {}).get("id")
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
            
            print(f"[BACKGROUND] Status do pagamento {payment_id}: {payment_status}")
            
            cobranca = Cobranca.query.filter_by(external_reference=str(payment_id)).first()
            
            if not cobranca:
                print(f"[BACKGROUND] Cobrança não encontrada para o payment_id: {payment_id}")
                return
            
            cobranca.status = payment_status
            db.session.commit()
            
            print(f"[BACKGROUND] Status da cobrança atualizado para: {payment_status}")
            
            if payment_status == "approved":
                print(f"[BACKGROUND] Pagamento aprovado! Enviando e-mail para {cobranca.cliente_email}")
                
                link_produto = os.environ.get("LINK_PRODUTO", "https://drive.google.com/file/d/1HlMExRRjV5Wn5SUNZktc46ragh8Zj8uQ/view?usp=sharing")
                
                email_enviado = enviar_email_confirmacao(
                    destinatario=cobranca.cliente_email,
                    nome_cliente=cobranca.cliente_nome,
                    valor=cobranca.valor,
                    link_produto=link_produto
                )
                
                if email_enviado:
                    print("[BACKGROUND] E-mail de confirmação enviado com sucesso!")
                else:
                    print("[BACKGROUND] Falha ao enviar e-mail de confirmação")
            
        except Exception as e:
            print(f"[BACKGROUND] Erro ao processar webhook em background: {str(e)}")

# ROTAS DA API

@app.route("/")
def index():
    """Serve a página principal"""
    return send_from_directory('static', 'index.html')

@app.route("/<path:path>")
def serve_static(path):
    """Serve arquivos estáticos"""
    return send_from_directory('static', path)

@app.route("/api/webhook", methods=["POST"])
def webhook_mercadopago():
    """
    Endpoint para receber notificações de pagamento do Mercado Pago
    """
    try:
        print("=" * 50)
        print("Webhook recebido do Mercado Pago")
        print(f"Headers: {dict(request.headers)}")
        print(f"Query params: {dict(request.args)}")
        print(f"Body: {request.get_json()}")
        print("=" * 50)
        
        # Validar a assinatura do webhook
        if not validar_assinatura_webhook(request):
            print("Assinatura do webhook inválida - Requisição rejeitada")
            return jsonify({"status": "error", "message": "Assinatura inválida"}), 401
        
        dados = request.get_json()
        
        if dados.get("type") != "payment":
            print(f"Tipo de notificação ignorado: {dados.get('type')}")
            return jsonify({"status": "success", "message": "Notificação ignorada"}), 200
        
        # Iniciar o processamento em segundo plano e retornar imediatamente
        thread = threading.Thread(target=processar_webhook_background, args=(dados, app.app_context()))
        thread.start()
        
        return jsonify({"status": "success", "message": "Webhook recebido e processamento iniciado em segundo plano"}), 200
        
    except Exception as e:
        print(f"Erro ao processar webhook: {str(e)}")
        # Em caso de erro na recepção ou validação, ainda é melhor retornar 200 OK
        # para evitar reenvios excessivos e tratar o erro internamente.
        return jsonify({"status": "error", "message": f"Erro interno ao processar webhook: {str(e)}"}), 200

@app.route("/api/cobrancas", methods=["GET"])
def get_cobrancas():
    """Lista todas as cobranças"""
    try:
        cobrancas_db = Cobranca.query.order_by(Cobranca.data_criacao.desc()).all()
        cobrancas_list = [cobranca.to_dict() for cobranca in cobrancas_db]
        return jsonify({
            "status": "success",
            "message": "Cobranças recuperadas com sucesso!",
            "data": cobrancas_list
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": f"Erro ao acessar o banco de dados: {str(e)}"}), 500

@app.route("/api/cobrancas", methods=["POST"])
def create_cobranca():
    """Cria uma nova cobrança PIX"""
    try:
        dados = request.get_json()
        print(f"Dados recebidos: {dados}")
        
        if not dados:
            return jsonify({"status": "error", "message": "Nenhum dado foi enviado."}), 400
            
        email_cliente = dados.get("email")
        nome_cliente = dados.get("nome", "Cliente do E-book")
        
        if not email_cliente:
            return jsonify({"status": "error", "message": "O email é obrigatório."}), 400

        if "@" not in email_cliente or "." not in email_cliente:
            return jsonify({"status": "error", "message": "Por favor, insira um email válido."}), 400

        access_token = os.environ.get("MERCADOPAGO_ACCESS_TOKEN")
        if not access_token:
            return jsonify({"status": "error", "message": "Token do Mercado Pago não configurado."}), 500
            
        sdk = mercadopago.SDK(access_token)

        valor_ebook = float(dados.get("valor", 1.00))
        descricao_ebook = dados.get("titulo", "Seu E-book Incrível")

        payment_data = {
            "transaction_amount": valor_ebook,
            "description": descricao_ebook,
            "payment_method_id": "pix",
            "payer": {
                "email": email_cliente
            }
        }

        payment_response = sdk.payment().create(payment_data)
        
        if payment_response["status"] != 201:
            error_msg = payment_response.get("response", {}).get("message", "Erro desconhecido do Mercado Pago")
            return jsonify({"status": "error", "message": f"Erro do Mercado Pago: {error_msg}"}), 500
            
        payment = payment_response["response"]

        qr_code_base64 = payment["point_of_interaction"]["transaction_data"]["qr_code_base64"]
        qr_code_text = payment["point_of_interaction"]["transaction_data"]["qr_code"]

        nova_cobranca = Cobranca(
            external_reference=str(payment["id"]),
            cliente_nome=nome_cliente,
            cliente_email=email_cliente,
            valor=valor_ebook,
            status=payment["status"]
        )
        db.session.add(nova_cobranca)
        db.session.commit()

        return jsonify({
            "status": "success",
            "message": "Cobrança PIX criada com sucesso!",
            "qr_code_base64": qr_code_base64,
            "qr_code_text": qr_code_text,
            "payment_id": payment["id"],
            "cobranca": nova_cobranca.to_dict()
        }), 201
        
    except Exception as e:
        print(f"Erro ao criar cobrança: {str(e)}")
        return jsonify({"status": "error", "message": f"Erro ao criar cobrança: {str(e)}"}), 500

@app.route("/health", methods=["GET"])
def health_check():
    """Endpoint de health check para o Render"""
    return jsonify({"status": "healthy", "service": "mercadopago-api"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
