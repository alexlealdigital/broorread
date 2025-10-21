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
import time # [NOVO] Adicionado para a rota de debug

import redis
from rq import Queue

# Inicialização do Flask
app = Flask(__name__, static_folder='static')

# Configuração de CORS
CORS(app, origins='*')

# ---------- CONFIGURAÇÃO DO BANCO DE DADOS ----------
db_url = os.environ.get("DATABASE_URL", "sqlite:///cobrancas.db")

# Lógica para corrigir o esquema da URL do PostgreSQL (para compatibilidade com psycopg)
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
# Trata o caso de 'postgresql://' sem o driver:
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

# --- FUNÇÕES AUXILIARES ---

# Funções enviar_email_confirmacao e validar_assinatura_webhook (mantidas inalteradas)
def enviar_email_confirmacao(destinatario, nome_cliente, valor, link_produto):
    # Conteúdo da função omitido para brevidade, mas está no seu código
    pass 

def validar_assinatura_webhook(request):
    # Conteúdo da função omitido para brevidade, mas está no seu código
    pass 


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
        # ... (Log e validação da assinatura)
        if not validar_assinatura_webhook(request):
            return jsonify({"status": "error", "message": "Assinatura inválida"}), 401
        
        # ... (Enfileiramento do job no RQ)
        dados = request.get_json()
        payment_id = dados.get("data", {}).get("id")
        if payment_id:
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
        # [CORREÇÃO] Corrigido o loop para usar 'cobranca' e não 'cobrancas'
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
        print(f"Dados recebidos: {dados}")
        
        if not dados or not dados.get("email"):
            return jsonify({"status": "error", "message": "O email é obrigatório."}), 400
            
        email_cliente = dados.get("email")
        nome_cliente = dados.get("nome", "Cliente do E-book")
        
        # ... (Validação de e-mail e outros dados) ...

        access_token = os.environ.get("MERCADOPAGO_ACCESS_TOKEN")
        if not access_token:
            return jsonify({"status": "error", "message": "Token do Mercado Pago não configurado."}), 500
            
        # [CORREÇÃO DE SDK] Variável 'sdk' definida no escopo da função
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
            print(f"Cobrança {payment['id']} SALVA COM SUCESSO no DB.")
        except Exception as db_error:
            db.session.rollback()
            # Este log é fundamental para vermos o erro que impede a persistência
            print(f"!!! ERRO CRÍTICO DB: FALHA AO SALVAR COBRANÇA: {str(db_error)}") 
            return jsonify({"status": "error", "message": "Falha interna ao registrar a cobrança (DB)."}, 500)
        
        # ... (Retorno dos dados para o cliente) ...

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
        db.session.rollback() 
        return jsonify({"status": "error", "message": f"Erro ao criar cobrança: {str(e)}"}), 500

# ---------- ÁREA DE TESTE DE DEBUG (WRITE/READ ISOLADO) ----------

@app.route("/api/debug_db", methods=["POST"])
def debug_db_route():
    """
    [ROTA DE DEBUG]: Cria um registro, comita e tenta lê-lo imediatamente em uma nova sessão.
    Retorna True/False para verificar a visibilidade da transação.
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
