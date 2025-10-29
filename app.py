from flask import Flask, jsonify, request, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import os
import mercadopago
# Imports de e-mail foram mantidos, mas a função em si é um placeholder, o worker é o responsável.
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import hmac
import hashlib
import redis
from rq import Queue
from sqlalchemy.orm import declarative_base

# Inicialização do Flask
app = Flask(__name__, static_folder='static')

# Configuração de CORS
# Em app.py, substitua a linha do CORS

# Defina explicitamente as origens que você confia
NETLIFY_ORIGIN = "https://rread.netlify.app"
RENDER_ORIGIN = "https://mercadopago-final.onrender.com" 
# (Adicione http://localhost:5500 ou similar se for testar localmente)

# Inicializa o CORS permitindo *apenas* esses domínios
CORS(app, origins=[NETLIFY_ORIGIN, RENDER_ORIGIN])

# ---------- CONFIGURAÇÃO DO BANCO DE DADOS E EXTENSÕES ----------
db_url = os.environ.get("DATABASE_URL", "sqlite:///cobrancas.db")

if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "asdf#FGSgvasgf$5$WGT")

app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True, 
    "pool_recycle": 3600
}

db = SQLAlchemy(app)

# Configuração do Redis e RQ
redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
redis_conn = redis.from_url(redis_url)
q = Queue(connection=redis_conn)

# ---------- MODELO DE DADOS (CORRIGIDO PARA PLANO A) ----------
class Cobranca(db.Model):
    __tablename__ = "cobrancas"
    id = db.Column(db.Integer, primary_key=True)
    external_reference = db.Column(db.String(100), unique=True, nullable=False)
    cliente_nome = db.Column(db.String(200), nullable=False)
    cliente_email = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default="pending", nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # --- ADIÇÃO CORRETA ---
    product_id = db.Column(db.Integer, db.ForeignKey('produtos.id'), nullable=True)
    produto = db.relationship('Produto')
    # --- FIM DA ADIÇÃO ---
    
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

# --- NOVO MODELO PRODUTO ---
class Produto(db.Model):
    __tablename__ = "produtos"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    preco = db.Column(db.Float, nullable=False)
    link_download = db.Column(db.String(500), nullable=False)


# Criação das tabelas
with app.app_context():
    db.create_all()

# --- FUNÇÕES AUXILIARES (Sem mudanças) ---

def enviar_email_confirmacao(destinatario, nome_cliente, valor, link_produto):
    pass 

def validar_assinatura_webhook(request):
    try:
        x_signature = request.headers.get("x-signature")
        x_request_id = request.headers.get("x-request-id")
        
        if not x_signature or not x_request_id:
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
        
        secret_key = os.environ.get("WEBHOOK_SECRET")
        if not ts or not hash_signature or not secret_key:
            return False
        
        data_id = request.args.get("data.id", "")
        manifest = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
        calculated_hash = hmac.new(
            secret_key.encode(),
            manifest.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return calculated_hash == hash_signature
            
    except Exception as e:
        print(f"Erro ao validar assinatura: {str(e)}")
        return False


# ---------- ROTAS DA API ----------

@app.route("/")
def index():
    return send_from_directory('static', 'index.html')

@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory('static', path)

# --- [ROTA DO WEBHOOK CORRIGIDA] ---
@app.route("/api/webhook", methods=["POST"])
def webhook_mercadopago():
    
    try:
        dados = request.get_json()
        print("=" * 50)
        print("Webhook recebido do Mercado Pago")
        print(f"Body: {dados}")
        print("=" * 50)
        
        if not validar_assinatura_webhook(request):
            print("Assinatura do webhook inválida - Requisição rejeitada")
            return jsonify({"status": "error", "message": "Assinatura inválida"}), 401
        
        if dados.get("type") != "payment":
            return jsonify({"status": "success", "message": "Notificação ignorada"}), 200
        
        payment_id = dados.get("data", {}).get("id")
        
        if payment_id:
            # --- CORREÇÃO: Linha reativada ---
            # O Worker agora só recebe o ID e busca o resto no DB.
            q.enqueue('worker.process_mercado_pago_webhook', payment_id)
            # --- FIM DA CORREÇÃO ---

            print(f"Job (Plano A) para payment_id {payment_id} enfileirado pelo Webhook.")

        return jsonify({"status": "success", "message": "Webhook recebido e processamento enfileirado"}), 200
        
    except Exception as e:
        print(f"Erro ao processar webhook: {str(e)}")
        return jsonify({"status": "error", "message": f"Erro interno ao processar webhook: {str(e)}"}), 200


# --- [ROTA DE COBRANÇAS CORRIGIDA] ---
@app.route("/api/cobrancas", methods=["POST"])
def create_cobranca():
    
    db.session.autoflush = False
    db.session.autocommit = False
    
    try:
        dados = request.get_json()
        print(f"Dados recebidos: {dados}")
        
        if not dados:
            return jsonify({"status": "error", "message": "Nenhum dado foi enviado."}), 400
            
        email_cliente = dados.get("email")
        nome_cliente = dados.get("nome", "Cliente") # Mudado de "Cliente do E-book"

        # --- [CORREÇÃO 1] ---
        # Recebemos o 'product_id' do frontend
        product_id_recebido = dados.get("product_id")
        
        if not product_id_recebido:
            return jsonify({"status": "error", "message": "ID do produto é obrigatório."}), 400
        
        if not email_cliente or "@" not in email_cliente or "." not in email_cliente:
            return jsonify({"status": "error", "message": "Por favor, insira um email válido e obrigatório."}), 400

        # --- [CORREÇÃO 2] ---
        # Buscamos o produto e o preço no DB (Mais seguro!)
        produto = db.session.get(Produto, int(product_id_recebido))
        if not produto:
            return jsonify({"status": "error", "message": "Produto não encontrado."}), 404

        valor_correto = produto.preco
        descricao_correta = produto.nome
        # --- FIM DAS CORREÇÕES ---

        access_token = os.environ.get("MERCADOPAGO_ACCESS_TOKEN")
        if not access_token:
            return jsonify({"status": "error", "message": "Token do Mercado Pago não configurado."}), 500
            
        sdk = mercadopago.SDK(access_token)

        payment_data = {
            "transaction_amount": valor_correto,     # Usa o valor do DB
            "description": descricao_correta,        # Usa a descrição do DB
            "payment_method_id": "pix",
            "payer": {"email": email_cliente}
        }

        payment_response = sdk.payment().create(payment_data)
        
        if payment_response["status"] != 201:
            error_msg = payment_response.get("response", {}).get("message", "Erro desconhecido do Mercado Pago")
            return jsonify({"status": "error", "message": f"Erro do Mercado Pago: {error_msg}"}), 500
            
        payment = payment_response["response"]

        qr_code_base64 = payment["point_of_interaction"]["transaction_data"]["qr_code_base64"]
        qr_code_text = payment["point_of_interaction"]["transaction_data"]["qr_code"]

        # --- [CORREÇÃO 3] ---
        # Salva a cobrança LIGADA ao product_id
        nova_cobranca = Cobranca(
            external_reference=str(payment["id"]),
            cliente_nome=nome_cliente,
            cliente_email=email_cliente,
            valor=valor_correto,
            status=payment["status"],
            product_id=produto.id  # <-- A LIGAÇÃO IMPORTANTE!
        )
        
        cobranca_dict = nova_cobranca.to_dict() 

        db.session.add(nova_cobranca)
        db.session.commit()
        db.session.expire_all()
        db.session.remove()
        
        print(f"Cobrança {payment['id']} SALVA COM SUCESSO (Plano A).")
        
        # --- [CORREÇÃO 4] ---
        # A linha q.enqueue() foi REMOVIDA daqui.
        # O webhook é quem vai enfileirar o job agora.
        
        return jsonify({
            "status": "success",
            "message": "Cobrança PIX criada com sucesso!",
            "qr_code_base64": qr_code_base64,
            "qr_code_text": qr_code_text,
            "payment_id": payment["id"],
            "cobranca": cobranca_dict 
        }), 201
        
    except Exception as e:
        db.session.rollback()
        db.session.remove()
        print(f"ERRO CRÍTICO GERAL (CREATE): {str(e)}")
        return jsonify({"status": "error", "message": f"Falha ao criar cobrança: {str(e)}"}), 500


# --- [NOVA ROTA PARA FORMULÁRIO DE CONTATO] ---
@app.route("/api/contato", methods=["POST"])
def handle_contact_form():
    dados = request.get_json()

    nome = dados.get("nome")
    email_remetente = dados.get("email") # Email de quem preencheu o form
    assunto = dados.get("assunto")
    mensagem = dados.get("mensagem")

    # Validação básica no backend
    if not all([nome, email_remetente, assunto, mensagem]):
        return jsonify({"status": "error", "message": "Todos os campos são obrigatórios."}), 400
    if "@" not in email_remetente or "." not in email_remetente:
         return jsonify({"status": "error", "message": "Email do remetente inválido."}), 400

    # Configurações de envio (lidas das variáveis de ambiente)
    try:
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.zoho.com")
        smtp_port = int(os.environ.get("SMTP_PORT", 465))
        # USA AS MESMAS CREDENCIAIS DO WORKER (garanta que estão nas variáveis do app também)
        email_user = os.environ["EMAIL_USER"] 
        email_pass = os.environ["EMAIL_PASSWORD"] 
        
        # --- DESTINATÁRIO FINAL ---
        email_destinatario = "gameslizards@gmail.com" # Seu email de destino
        
    except KeyError:
        print("[CONTACT FORM] ERRO: Credenciais de e-mail (EMAIL_USER/EMAIL_PASSWORD) não configuradas.")
        return jsonify({"status": "error", "message": "Erro interno do servidor ao configurar e-mail."}), 500
    except Exception as config_err:
        print(f"[CONTACT FORM] ERRO GERAL CONFIG: {config_err}")
        return jsonify({"status": "error", "message": "Erro interno do servidor."}), 500

    # Monta o corpo do e-mail
    corpo_email_texto = f"""
Nova mensagem recebida do formulário de contato R·READ:

Nome: {nome}
Email: {email_remetente}
Assunto: {assunto}

Mensagem:
--------------------
{mensagem}
--------------------
"""

    msg = MIMEText(corpo_email_texto)
    msg["Subject"] = f"Contato R·READ: {assunto}" # Assunto do email recebido
    msg["From"] = email_user # Quem envia (seu email Zoho)
    msg["To"] = email_destinatario # Para onde vai (seu Gmail)
    msg["Reply-To"] = email_remetente # Para você poder responder diretamente ao cliente

    # Envia o e-mail
    try:
        print(f"[CONTACT FORM] Tentando enviar e-mail de {email_remetente} para {email_destinatario} via {email_user}...")
        # Usando SMTP_SSL para maior compatibilidade
        with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=15) as server: 
            server.login(email_user, email_pass)
            server.send_message(msg)
        print(f"[CONTACT FORM] E-mail enviado com sucesso!")
        return jsonify({"status": "success", "message": "Mensagem enviada com sucesso! Responderemos em breve."}), 200
    except smtplib.SMTPAuthenticationError:
         print(f"[CONTACT FORM] ERRO SMTP: Falha na autenticação com {email_user}. Verifique EMAIL_USER/EMAIL_PASSWORD.")
         return jsonify({"status": "error", "message": "Erro interno ao autenticar envio de e-mail."}), 500
    except Exception as e:
        print(f"[CONTACT FORM] ERRO SMTP GERAL: {e}")
        return jsonify({"status": "error", "message": f"Não foi possível enviar a mensagem no momento."}), 500
# --- FIM DA NOVA ROTA ---


@app.route("/health", methods=["GET"])
def health_check():
   
    try:
        redis_conn.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "error"

    try:
        with app.app_context():
            # Tenta consultar a nova tabela Produtos
            Produto.query.limit(1).all()
        db_status = "ok"
    except Exception:
        db_status = "error"
        
    status_code = 200 if redis_status == "ok" and db_status == "ok" else 503

    return jsonify({
        "status": "healthy" if status_code == 200 else "unhealthy", 
        "service": "mercadopago-api",
        "dependencies": {
            "redis": redis_status,
            "database": db_status
        }
    }), status_code

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
