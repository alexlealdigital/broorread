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

# --- FUNÇÕES AUXILIARES (Definições simplificadas para integridade) ---
def enviar_email_confirmacao(destinatario, nome_cliente, valor, link_produto):
    # Conteúdo da função omitido. O código completo deve estar no worker.py
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
    Endpoint para receber notificações de pagamento do Mercado Pago
    Apenas enfileira o Job de processamento assíncrono
    """
    try:
        print("=" * 50)
        print("Webhook recebido do Mercado Pago")
        print(f"Headers: {dict(request.headers)}")
        print(f"Query params: {dict(request.args)}")
        print(f"Body: {request.get_json()}")
        print("=" * 50)
        
        if not validar_assinatura_webhook(request):
            print("Assinatura do webhook inválida - Requisição rejeitada")
            return jsonify({"status": "error", "message": "Assinatura inválida"}), 401
        
        dados = request.get_json()
        
        if dados.get("type") != "payment":
            print(f"Tipo de notificação ignorado: {dados.get('type')}")
            return jsonify({"status": "success", "message": "Notificação ignorada"}), 200
        
        # Enfileirar o job para processamento assíncrono
        payment_id = dados.get("data", {}).get("id")
        if payment_id:
            # Enfileira a tarefa para o worker.py
            q.enqueue('worker.process_mercado_pago_webhook', payment_id)
            print(f"Job para payment_id {payment_id} enfileirado com sucesso.")

        return jsonify({"status": "success", "message": "Webhook recebido e processamento enfileirado"}), 200
        
    except Exception as e:
        print(f"Erro ao processar webhook: {str(e)}")
        return jsonify({"status": "error", "message": f"Erro interno ao processar webhook: {str(e)}"}), 200

@app.route("/api/cobrancas", methods=["GET"])
def get_cobrancas():
    """Lista todas as cobranças salvas no DB"""
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

def create_cobranca():
    """Cria uma nova cobrança PIX no MP e salva o registro no DB."""
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
        
        try:
            db.session.add(nova_cobranca)
            db.session.commit()
            
            # 🔑 PASSO CRÍTICO: Serializa o objeto para Dicionário *ANTES* de invalidar a sessão.
            cobranca_dict = nova_cobranca.to_dict() 
            
            # 1. CORREÇÃO DE VISIBILIDADE: Força a liberação do dado para o Worker
            db.session.expire_all()
            
            # 2. CORREÇÃO DE SEGURANÇA: Remove a sessão do pool para evitar o erro de 'not bound'
            db.session.remove() 
            
            print(f"Cobrança {payment['id']} SALVA COM SUCESSO e liberada para o Worker.")
        
        except Exception as db_error:
            # Em caso de falha de DB, faz rollback e remove a sessão
            db.session.rollback()
            db.session.remove() 
            print(f"!!! ERRO CRÍTICO DB: FALHA AO SALVAR COBRANÇA: {str(db_error)}")
            return jsonify({"status": "error", "message": "Falha interna ao registrar a cobrança (DB)."}, 500)
        
        # O retorno 201 agora usa o dicionário serializado (cobranca_dict),
        # que é independente da sessão do DB.
        return jsonify({
            "status": "success",
            "message": "Cobrança PIX criada com sucesso!",
            "qr_code_base64": qr_code_base64,
            "qr_code_text": qr_code_text,
            "payment_id": payment["id"],
            "cobranca": cobranca_dict # <--- Usa o dicionário seguro
        }), 201
        
    except Exception as e:
        db.session.rollback()
        db.session.remove()
        print(f"Erro ao criar cobrança: {str(e)}")
        return jsonify({"status": "error", "message": f"Erro ao criar cobrança: {str(e)}"}), 500

            
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
        
        # Bloco aninhado para tratar falhas no commit
        try:
            db.session.add(nova_cobranca)
            db.session.commit()
            
            # 🔑 CORREÇÃO CRÍTICA: Força a liberação do dado para o Worker (Resolve visibilidade)
            db.session.expire_all()
            
            # 🔑 CORREÇÃO DE SEGURANÇA: Remove a sessão do pool para garantir o fim da transação.
            db.session.remove() 
            
            print(f"Cobrança {payment['id']} SALVA COM SUCESSO e liberada para o Worker.")
        
        except Exception as db_error:
            # Em caso de falha de DB, faz rollback e remove a sessão
            db.session.rollback()
            db.session.remove() 
            print(f"!!! ERRO CRÍTICO DB: FALHA AO SALVAR COBRANÇA: {str(db_error)}")
            return jsonify({"status": "error", "message": "Falha interna ao registrar a cobrança (DB)."}, 500)
        
        # O retorno 201 ocorre somente após a persistência bem-sucedida
        return jsonify({
            "status": "success",
            "message": "Cobrança PIX criada com sucesso!",
            "qr_code_base64": qr_code_base64,
            "qr_code_text": qr_code_text,
            "payment_id": payment["id"],
            "cobranca": nova_cobranca.to_dict()
        }), 201
        
    except Exception as e:
        # Garante que qualquer falha geral faça o rollback e limpe a sessão
        db.session.rollback()
        db.session.remove()
        print(f"Erro ao criar cobrança: {str(e)}")
        return jsonify({"status": "error", "message": f"Erro ao criar cobrança: {str(e)}"}), 500


@app.route("/health", methods=["GET"])
def health_check():
    """Endpoint de health check para o Render"""
    return jsonify({"status": "healthy", "service": "mercadopago-api"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
