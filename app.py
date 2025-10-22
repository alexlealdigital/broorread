
corrija o erro: 
pasted_content.txt
Text · 10.77 KB
pasted_content_2.txt
Text · 5.07 KB
pasted_content_3.txt
Text · 5.66 KB
Lite
Recebi os três arquivos de texto. Vou analisar o conteúdo de cada um para identificar e corrigir o erro que você mencionou.
Currently analyzing user files to identify the error; once found, I'll proceed with correction before delivering the results.

Found an error: the ORM instance was not properly bound to the session, causing a 'detached' state. Removed redundant job enqueuing after commit to prevent confusion.

I identified the ORM instance was not properly bound to the session, causing a 'detached' error. Next, I will analyze the code to find and fix the binding issue.

Lite
O erro foi identificado e corrigido no arquivo pasted_content.txt.
Análise do Erro
O log de erro (pasted_content_3.txt, linha 41) indicava:
Plain Text
ERRO CRÍTICO GERAL (CREATE): Instance <Cobranca at 0x7b37a6691ad0> is not bound to a Session; attribute refresh operation cannot proceed (Background on this error at: https://sqlalche.me/e/20/bhk3 )
Este erro ocorre na função create_cobranca (linha 173 do seu código) e é causado por duas ações conflitantes:
Chamar nova_cobranca.cliente_email após a linha db.session.remove().
Enfileirar um job desnecessário (linha 244 do código original).
Quando a linha db.session.remove() é executada, o objeto nova_cobranca (que é um objeto do SQLAlchemy) é "desanexado" da sessão do banco de dados. Qualquer tentativa subsequente de acessar um atributo (como nova_cobranca.cliente_email) faz com que o SQLAlchemy tente "atualizar" o objeto, o que falha porque a sessão já foi fechada/removida.
Além disso, a linha que enfileirava o job (q.enqueue('worker.process_mercado_pago_webhook', payment['id'], nova_cobranca.cliente_email)) era redundante, pois o webhook do Mercado Pago já aciona o mesmo worker logo em seguida, conforme visto nos seus logs.
Correção Aplicada
A correção consistiu em:
Remover a linha de enfileiramento redundante do worker na função create_cobranca (linhas 244-246 do código original).
Adicionar um comentário explicando o motivo da remoção e a redundância com o webhook.
O código corrigido está no anexo.
Resumo da Mudança no Arquivo pasted_content.txt:
Linhas
Código Original (Removido)
244-246
q.enqueue('worker.process_mercado_pago_webhook', payment['id'], nova_cobranca.cliente_email)
print(f"Job para pagamento {payment['id']} enfileirado com e-mail: {nova_cobranca.cliente_email}")
O arquivo corrigido pasted_content.txt foi anexado para sua conveniência.
pasted_content.txt
Text · 10.58 KB

View all files in this task
Task completed
How was this result?
Suggested follow-ups
Send message to Manus
pasted_content.txt
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
CORS(app, origins='*')

# ---------- CONFIGURAÇÃO DO BANCO DE DADOS E EXTENSÕES ----------
db_url = os.environ.get("DATABASE_URL", "sqlite:///cobrancas.db")

# Lógica para compatibilidade com driver PostgreSQL (psycopg) no Render
# Garante que a URL do banco de dados use o driver assíncrono psycopg
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "asdf#FGSgvasgf$5$WGT")

# Pool de conexões robusto (Essencial para serviços em cloud como Render)
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True, 
    "pool_recycle": 3600
}

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

# Mantido como um placeholder para clareza, mas o Worker fará o trabalho real.
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
        # O manifesto deve incluir 'ts' e 'request-id' do header e o 'id' do parâmetro
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
            # Enfileira o job de processamento do webhook. 
            # O Worker usará o payment_id para buscar detalhes do pagamento e o email no DB.
            q.enqueue('worker.process_mercado_pago_webhook', payment_id)

            print(f"Job para payment_id {payment_id} enfileirado com sucesso.")

        return jsonify({"status": "success", "message": "Webhook recebido e processamento enfileirado"}), 200
        
    except Exception as e:
        print(f"Erro ao processar webhook: {str(e)}")
        return jsonify({"status": "error", "message": f"Erro interno ao processar webhook: {str(e)}"}), 200


@app.route("/api/cobrancas", methods=["POST"])
def create_cobranca():
    """Cria uma nova cobrança PIX no MP e salva o registro no DB."""
    
    # IMPORTANTE: Desativa o gerenciamento automático da sessão para controle manual
    db.session.autoflush = False
    db.session.autocommit = False
    
    try:
        dados = request.get_json()
        print(f"Dados recebidos: {dados}")
        
        if not dados:
            return jsonify({"status": "error", "message": "Nenhum dado foi enviado."}), 400
            
        email_cliente = dados.get("email")
        nome_cliente = dados.get("nome", "Cliente do E-book")
        
        if not email_cliente or "@" not in email_cliente or "." not in email_cliente:
            return jsonify({"status": "error", "message": "Por favor, insira um email válido e obrigatório."}), 400

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
        
        # O job de notificação para o worker é desnecessário aqui, pois o webhook já o faz.
        # A linha abaixo foi removida para evitar redundância e confusão de fluxo.
        # q.enqueue('worker.process_mercado_pago_webhook', payment['id'], nova_cobranca.cliente_email)
        # print(f"Job para pagamento {payment['id']} enfileirado com e-mail: {nova_cobranca.cliente_email}")

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
   
    # Verifica a saúde da conexão do Redis
    try:
        redis_conn.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "error"

    # Verifica o status de uma tabela do DB (teste de conexão)
    try:
        with app.app_context():
            Cobranca.query.limit(1).all()
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
    # Em ambientes de produção (Render), gunicorn irá rodar o app:app
    # Este bloco é apenas para desenvolvimento local.
    app.run(host="0.0.0.0", port=port, debug=False)
Corrija o erro nos arquivos carregados - Manus
