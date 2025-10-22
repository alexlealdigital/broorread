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
import time
import redis
from rq import Queue

# Inicialização do Flask
app = Flask(__name__, static_folder='static')

# Configuração de CORS
CORS(app, origins='*')

# ---------- CONFIGURAÇÃO DO BANCO DE DADOS ----------
db_url = os.environ.get("DATABASE_URL", "sqlite:///cobrancas.db")

# Lógica para compatibilidade com driver PostgreSQL (psycopg) no Render
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "asdf#FGSgvasgf$5$WGT")
# Pool de conexões robusto
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 3600}

# Inicialização do SQLAlchemy
db = SQLAlchemy(app)

# Configuração do Redis e RQ
redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
redis_conn = redis.from_url(redis_url)
q = Queue(connection=redis_conn)

# ---------- MODELO DE DADOS ----------
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

# --- FUNÇÕES AUXILIARES ---

def enviar_email_confirmacao(destinatario, nome_cliente, valor, link_produto):
    """Placeholder: O envio real é feito pelo worker.py"""
    pass 

def validar_assinatura_webhook(request):
    """
    Valida a assinatura do webhook do Mercado Pago
    """
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
    """Serve a página principal"""
    return send_from_directory('static', 'index.html')

@app.route("/<path:path>")
def serve_static(path):
    """Serve arquivos estáticos"""
    return send_from_directory('static', path)

@app.route("/api/webhook", methods=["POST"])
def webhook_mercadopago():
    """
    Endpoint para receber notificações de pagamento do Mercado Pago.
    Extrai o e-mail do payload para enviá-lo ao Worker.
    """
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
        
        # 🔑 CORREÇÃO CRÍTICA: Extrai o email do cliente do objeto JSON do webhook.
        # Nota: O Mercado Pago envia o ID do usuário, mas o email de contato é o mais confiável para entrega.
        # Vamos usar um valor de fallback para o email, pois o webhook não garante o email do payer no payload simples.
        # No modo contorno, precisamos que o Web Service passe pelo menos o ID.
        
        # Como o Webhook não envia o email do payer no payload simples, esta é uma falha de design do MP.
        # Vamos garantir que o ID do pagamento seja passado, e o Worker terá que usar um email default.
        
        if payment_id:
            # Não temos o email real do cliente aqui, o que é a origem do problema.
            # O Web Service deve ter guardado o email do cliente em algum lugar. 
            # Como ele não está no objeto JSON do webhook, teremos que contornar, MAS O SEU APP.PY ESTAVA COM ESSA LINHA:
            # q.enqueue('worker.process_mercado_pago_webhook', payment_id)

            # Para resolver o problema de forma definitiva, voltaremos à lógica que funciona:
            # A rota /api/cobrancas deve enfileirar o Job com o email.
            
            # Vamos supor que o email esteja armazenado na sessão do pagamento.
            
            # O Webhook envia apenas o ID. A responsabilidade de passar o email é da rota create_cobranca.
            
            
            # -----------------------------------------------------
            # A ÚNICA FORMA DE RESOLVER ISTO É MUDANDO A ROTA /api/COBRANCAS
            # -----------------------------------------------------
            
            # Vamos garantir que o Worker aceite apenas o ID, e a rota /api/cobrancas envie o email.
            
            # Para o webhook, o Worker deve ser capaz de lidar com o ID.
            q.enqueue('worker.process_mercado_pago_webhook', payment_id)

            print(f"Job para payment_id {payment_id} enfileirado com sucesso.")

        return jsonify({"status": "success", "message": "Webhook recebido e processamento enfileirado"}), 200
        
    except Exception as e:
        print(f"Erro ao processar webhook: {str(e)}")
        return jsonify({"status": "error", "message": f"Erro interno ao processar webhook: {str(e)}"}), 200

### O Diagnóstico Final

**O `app.py` tem o e-mail, mas enfileira o Job apenas na rota `/api/cobrancas`.**

A rota `/api/cobrancas` deve ser corrigida para **enviar o e-mail junto com o `payment_id`**.

Você tem que garantir que a sua rota **`create_cobranca`** (que tem o e-mail) chame o `q.enqueue` com o e-mail:

```python
# NO SEU app.py, dentro de create_cobranca:
q.enqueue('worker.process_mercado_pago_webhook', payment['id'], nova_cobranca.cliente_email) 


@app.route("/api/cobrancas", methods=["GET"])
def get_cobrancas():
    """Lista todas as cobranças salvas no DB"""
    try:
        cobrancas_db = Cobranca.query.order_by(Cobranca.data_criacao.desc()).all()
        # Corrigido: Usar 'cobranca' singular no loop para serialização
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
    """Cria uma nova cobrança PIX no MP e salva o registro no DB."""
    
    # IMPORTANTE: Desativa o gerenciamento automático do Flask-SQLAlchemy para esta transação
    db.session.autoflush = False
    db.session.autocommit = False
    
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
            "payer": {"email": email_cliente}
        }

        payment_response = sdk.payment().create(payment_data)
        
        # --- Verificação de status do Mercado Pago ---
        if payment_response["status"] != 201:
            error_msg = payment_response.get("response", {}).get("message", "Erro desconhecido do Mercado Pago")
            return jsonify({"status": "error", "message": f"Erro do Mercado Pago: {error_msg}"}), 500
            
        payment = payment_response["response"]

        qr_code_base64 = payment["point_of_interaction"]["transaction_data"]["qr_code_base64"]
        qr_code_text = payment["point_of_interaction"]["transaction_data"]["qr_code"]

        # ---------- CRIAÇÃO E PERSISTÊNCIA NO DB ----------
        nova_cobranca = Cobranca(
            external_reference=str(payment["id"]),
            cliente_nome=nome_cliente,
            cliente_email=email_cliente,
            valor=valor_ebook,
            status=payment["status"]
        )
        
        # Serialização ANTES do commit/limpeza, para retorno seguro
        cobranca_dict = nova_cobranca.to_dict() 

        # 1. ESCRITA MANUAL NA SESSÃO
        db.session.add(nova_cobranca)
        db.session.commit()
        
        # 2. LIBERAÇÃO MÁXIMA
        db.session.expire_all()
        db.session.remove() # Força a desconexão do pool
        
       print(f"Cobrança {payment['id']} SALVA COM SUCESSO e liberada para o Worker.")
        
        # ✅ ADIÇÃO DA CORREÇÃO: Enfileira o job com o e-mail para envio das instruções PIX.
        # Isso garante que o e-mail real seja usado na primeira comunicação.
        q.enqueue('worker.send_pix_instruction_email', payment["id"], nova_cobranca.cliente_email) 
        
               
        # Retorno de sucesso
        return jsonify({
            "status": "success",
            "message": "Cobrança PIX criada com sucesso!",
            "qr_code_base64": qr_code_base64,
            "qr_code_text": qr_code_text,
            "payment_id": payment["id"],
            "cobranca": cobranca_dict 
        }), 201
        
    except Exception as e:
        # Tenta reverter e remover a sessão em caso de qualquer falha
        db.session.rollback()
        db.session.remove()
        print(f"ERRO CRÍTICO GERAL (CREATE): {str(e)}")
        return jsonify({"status": "error", "message": f"Falha ao criar cobrança: {str(e)}"}), 500

@app.route("/health", methods=["GET"])
def health_check():
    """Endpoint de health check para o Render"""
    return jsonify({"status": "healthy", "service": "mercadopago-api"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
