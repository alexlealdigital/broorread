#!/usr/bin/env python3
"""
Módulo principal do Web Service (API Flask).
Responsável por receber requisições de checkout, criar a cobrança no Mercado Pago
e enfileirar o Job de processamento no RQ/Redis.
"""

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
import time # Necessário para a rota de debug

import redis
from rq import Queue

# Inicialização do Flask
app = Flask(__name__, static_folder='static')

# Configuração de CORS para acesso frontend
CORS(app, origins='*')

# ---------- CONFIGURAÇÃO DO BANCO DE DADOS ----------
db_url = os.environ.get("DATABASE_URL", "sqlite:///cobrancas.db")

# Lógica para corrigir o esquema da URL do PostgreSQL (para compatibilidade com psycopg)
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)

# Se ainda for o esquema antigo do Render (sem o driver):
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)
    
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "asdf#FGSgvasgf$5$WGT")

# Inicialização do SQLAlchemy
db = SQLAlchemy(app)

# ---------- CONFIGURAÇÃO DO REDIS E RQ ----------
redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379')
redis_conn = redis.from_url(redis_url)
# Fila 'default' para onde os Jobs serão enviados
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

# Criação das tabelas (executado ao iniciar a aplicação)
with app.app_context():
    db.create_all()

# --- FUNÇÕES AUXILIARES (APENAS EXEMPLOS, ENVIADAS PELO WORKER) ---

def enviar_email_confirmacao(destinatario, nome_cliente, valor, link_produto):
    """(Função dummy - O envio real é feito pelo worker.py)"""
    # Esta função está definida aqui apenas para ilustrar, mas o código real deve estar no worker.py
    # Sua inclusão completa aqui foi mantida para integridade do código anterior
    pass 

def validar_assinatura_webhook(request):
    """
    Valida a assinatura do webhook do Mercado Pago (HMAC-SHA256)
    """
    # Código de validação HMAC (mantido por integridade)
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
            print("Secret key do Webhook não configurada")
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
        # Logs detalhados para debug (essenciais)
        print(f"Headers: {dict(request.headers)}")
        print(f"Query params: {dict(request.args)}")
        print(f"Body: {request.get_json()}")
        print("=" * 50)
        
        # Validar a assinatura do webhook (segurança)
        if not validar_assinatura_webhook(request):
            return jsonify({"status": "error", "message": "Assinatura inválida"}), 401
        
        dados = request.get_json()
        
        if dados.get("type") != "payment":
            print(f"Tipo de notificação ignorado: {dados.get('type')}")
            return jsonify({"status": "success", "message": "Notificação ignorada"}), 200
        
        # Enfileirar o job para processamento assíncrono
        # O Worker vai buscar os detalhes do pagamento no MP
        payment_id = dados.get("data", {}).get("id")
        
        # Importante: o job a ser enfileirado precisa estar no arquivo 'worker.py'
        if payment_id:
            q.enqueue('worker.process_mercado_pago_webhook', payment_id)
            print(f"Job para payment_id {payment_id} enfileirado com sucesso.")
        else:
            print("ID do pagamento não encontrado na notificação.")

        # Retorno 200 é crucial para que o Mercado Pago não tente novamente imediatamente
        return jsonify({"status": "success", "message": "Webhook recebido e processamento enfileirado"}), 200
        
    except Exception as e:
        print(f"Erro ao processar webhook: {str(e)}")
        return jsonify({"status": "error", "message": f"Erro interno ao processar webhook: {str(e)}"}), 200

@app.route("/api/cobrancas", methods=["GET"])
def get_cobrancas():
    """Lista todas as cobranças salvas no DB"""
    try:
        cobrancas_db = Cobranca.query.order_by(Cobranca.data_criacao.desc()).all()
        # Necessário list comprehension para resolver o erro no código original
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
    """Cria uma nova cobrança PIX no MP e salva o registro no DB"""
    try:
        dados = request.get_json()
        
        # ... (Validações de email e dados) ...

        access_token = os.environ.get("MERCADOPAGO_ACCESS_TOKEN")
        # ... (Inicialização do SDK) ...

        valor_ebook = float(dados.get("valor", 1.00))
        descricao_ebook = dados.get("titulo", "Seu E-book Incrível")

        # ... (Criação do payment_data) ...

        payment_response = sdk.payment().create(payment_data)
        
        if payment_response["status"] != 201:
            # Tratamento de erro do MP
            error_msg = payment_response.get("response", {}).get("message", "Erro desconhecido do Mercado Pago")
            return jsonify({"status": "error", "message": f"Erro do Mercado Pago: {error_msg}"}), 500
            
        payment = payment_response["response"]

        # ... (Extração de QR Code) ...

        # ---------- CRIAÇÃO E PERSISTÊNCIA NO DB ----------
        nova_cobranca = Cobranca(
            external_reference=str(payment["id"]),
            cliente_nome=nome_cliente,
            cliente_email=email_cliente,
            valor=valor_ebook,
            status=payment["status"]
        )
        
        # Uso de try/except/rollback para DEBUG: Garante que o erro de persistência seja capturado
        try:
            db.session.add(nova_cobranca)
            db.session.commit()
            print(f"Cobrança {payment['id']} SALVA COM SUCESSO no DB.")
        except Exception as db_error:
            db.session.rollback()
            # Este log é fundamental para vermos o erro que impede a persistência
            print(f"!!! ERRO CRÍTICO DB: FALHA AO SALVAR COBRANÇA: {str(db_error)}") 
            return jsonify({"status": "error", "message": "Falha interna ao registrar a cobrança (DB)."}, 500)
        
        # ... (Retorno dos dados para o cliente) ...

        return jsonify({
            # ... dados de retorno (QR codes, etc.)
            "status": "success",
            "message": "Cobrança PIX criada com sucesso!",
            "payment_id": payment["id"],
            "cobranca": nova_cobranca.to_dict()
        }), 201
        
    except Exception as e:
        print(f"Erro ao criar cobrança: {str(e)}")
        # Garante que qualquer sessão aberta seja revertida em caso de erro
        db.session.rollback() 
        return jsonify({"status": "error", "message": f"Erro ao criar cobrança: {str(e)}"}), 500

# ---------- ÁREA DE TESTE DE DEBUG (WRITE/READ ISOLADO) ----------

@app.route("/api/debug_db", methods=["POST"])
def debug_db_route():
    """
    TESTE DE COMUNICAÇÃO DB (ESCRITA E LEITURA ISOLADA)
    Simula o fluxo de escrita do app.py e leitura imediata do worker.py para
    testar a visibilidade da transação.
    """
    test_id = "TEST_FLAG_" + datetime.now().strftime("%H%M%S")
    
    try:
        # --- 1. ESCRITA (Simula o Commit do Web Service) ---
        cobranca_teste = Cobranca(
            external_reference=test_id,
            cliente_nome="DEBUG TEST",
            cliente_email="debug@test.com",
            valor=0.01
        )
        db.session.add(cobranca_teste)
        db.session.commit()
        
        print(f"DEBUG: Escrita/Commit SUCESSO para ID: {test_id}")
        
        # --- 2. FORÇA NOVA SESSÃO, PAUSA E LEITURA (Simula o Worker) ---
        db.session.close() # Fecha a sessão atual
        time.sleep(1)      # Pausa de 1s para latência de concorrência
        
        cobranca_lida = Cobranca.query.filter_by(external_reference=test_id).first()
        
        # --- 3. VERIFICAÇÃO E LIMPEZA ---
        if cobranca_lida:
            # SUCESSO: Os dados são visíveis!
            db.session.delete(cobranca_lida)
            db.session.commit()
            db.session.close()
            
            print(f"DEBUG: Escrita/Leitura SUCESSO. Dado {test_id} visível e deletado.")
            return jsonify({"success": True, "message": "Comunicação DB Write/Read OK."}), 200
        else:
            # FALHA: O dado não foi lido (problema de transação/visibilidade)
            db.session.rollback()
            print(f"DEBUG: Escrita/Leitura FALHA. Dado {test_id} não encontrado.")
            return jsonify({"success": False, "message": "Dado não visível na nova sessão após commit."}), 500

    except Exception as e:
        db.session.rollback()
        print(f"DEBUG: ERRO CRÍTICO NA CONEXÃO: {str(e)}")
        return jsonify({"success": False, "message": f"Erro fatal de DB: {str(e)}"}), 500


@app.route("/health", methods=["GET"])
def health_check():
    """Endpoint de health check para o Render"""
    return jsonify({"status": "healthy", "service": "mercadopago-api"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
