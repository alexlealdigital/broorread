# Importações existentes (e 'func' do SQLAlchemy para contar)
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
import redis
from rq import Queue
from sqlalchemy.orm import declarative_base
from sqlalchemy import func # <--- ADICIONADO PARA CONTAR VENDAS
import resend

# Inicialização do Flask
app = Flask(__name__, static_folder='static')

# Configuração de CORS - Inclui todos os seus domínios para evitar bloqueios
NETLIFY_ORIGIN_PROD = "https://rread.netlify.app"
RENDER_ORIGIN = "https://mercadopago-final.onrender.com" 
NETLIFY_ORIGIN_TEST = "https://rankedsale.netlify.app" 
# ADICIONA TODOS OS DOMÍNIOS CONHECIDOS
CORS(app, origins=[NETLIFY_ORIGIN_PROD, RENDER_ORIGIN, NETLIFY_ORIGIN_TEST])

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

# ---------- MODELOS DE DADOS (Gamificação Adicionada) ----------

# MODELO: VENDEDOR (Gamificação RKD)
class Vendedor(db.Model):
# ... (código do modelo Vendedor existente) ...
    __tablename__ = "vendedores"
    # Código único (Ex: NKD00101) que é a Chave Primária
    codigo_ranking = db.Column(db.String(50), primary_key=True) 
    nome_vendedor = db.Column(db.String(200), nullable=False)
    email_contato = db.Column(db.String(200), nullable=True)

    def to_dict(self):
        # Retorna apenas o que o dropdown precisa
        return {
            "codigo_ranking": self.codigo_ranking,
            "nome_vendedor": self.nome_vendedor
        }

class Cobranca(db.Model):
# ... (código do modelo Cobranca existente) ...
    __tablename__ = "cobrancas"
    id = db.Column(db.Integer, primary_key=True)
    external_reference = db.Column(db.String(100), unique=True, nullable=False)
    cliente_nome = db.Column(db.String(200), nullable=False)
    cliente_email = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default="pending", nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    product_id = db.Column(db.Integer, db.ForeignKey('produtos.id'), nullable=True)
    produto = db.relationship('Produto')
    
    chave_usada = db.relationship('ChaveLicenca', backref='cobranca_rel', uselist=False) 
    
    # ATUALIZADO: Chave Estrangeira para rastrear o vendedor
    vendedor_codigo = db.Column(db.String(50), db.ForeignKey('vendedores.codigo_ranking'), nullable=True)
    vendedor = db.relationship('Vendedor', backref='vendas') # Adiciona relacionamento para facilitar a consulta

    def to_dict(self):
        return {
            "id": self.id,
            "external_reference": self.external_reference,
            "cliente_nome": self.cliente_nome,
            "cliente_email": self.cliente_email,
            "valor": self.valor,
            "status": self.status,
            "data_criacao": self.data_criacao.isoformat() if self.data_criacao else None,
            "vendedor_codigo": self.vendedor_codigo # Inclui o código do vendedor no retorno
        }

class Produto(db.Model):
# ... (código do modelo Produto existente) ...
    __tablename__ = "produtos"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    preco = db.Column(db.Float, nullable=False)
    link_download = db.Column(db.String(500), nullable=False)
    tipo = db.Column(db.String(50), default="ebook", nullable=False) 


class ChaveLicenca(db.Model):
# ... (código do modelo ChaveLicenca existente) ...
    __tablename__ = "chaves_licenca"
    id = db.Column(db.Integer, primary_key=True)
    chave_serial = db.Column(db.String(100), unique=True, nullable=False)
    
    produto_id = db.Column(db.Integer, db.ForeignKey('produtos.id'), nullable=False)
    
    vendida = db.Column(db.Boolean, default=False, nullable=False)
    
    vendida_em = db.Column(db.DateTime, nullable=True)
    cobranca_id = db.Column(db.Integer, db.ForeignKey('cobrancas.id'), unique=True, nullable=True) 
    
    cliente_email = db.Column(db.String(200), nullable=True)
    
    # Campo preservado da funcionalidade anterior
    ativa_no_app = db.Column(db.Boolean, default=False, nullable=False) 


# Criação das tabelas
with app.app_context():
    db.create_all()

# --- FUNÇÕES AUXILIARES ---
# ... (código da função validar_assinatura_webhook existente) ...
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

# ... (código das rotas /, /<path>, /api/vendedores, /api/validar_chave, /api/webhook, /api/cobrancas, /api/contato existentes) ...
@app.route("/")
def index():
    return send_from_directory('static', 'index.html')

@app.route("/<path:path>")
def serve_static(path):
    return send_from_directory('static', path)


# ROTA DE GAMIFICAÇÃO (Para o Dropdown)
@app.route("/api/vendedores", methods=["GET"])
def get_vendedores():
    """ Rota para o frontend buscar a lista de vendedores (para o dropdown) """
    try:
        with app.app_context():
            vendedores = Vendedor.query.order_by(Vendedor.nome_vendedor).all()
            # Retorna apenas o código e o nome do vendedor
            return jsonify([v.to_dict() for v in vendedores]), 200
    except Exception as e:
        print(f"ERRO (VENDEDORES): {str(e)}")
        return jsonify({"status": "error", "message": "Não foi possível carregar a lista de vendedores."}), 500


# ROTA DE VALIDAÇÃO DE CHAVE (PARA O SEU APP)
@app.route("/api/validar_chave", methods=["POST"])
def validar_chave():
    """ API chamada pelo App (Agenda_Estetica) para verificar se a chave é válida e ativá-la. """
    
    dados = request.get_json()
    chave_serial = dados.get("chave_serial", "").strip().upper()
    product_id_app = dados.get("product_id") 
    
    if not chave_serial or not product_id_app:
        return jsonify({"status": "error", "message": "Chave serial e ID do produto incompletos."}), 400

    try:
        # 1. Busca a chave no DB (com with_for_update para garantir o lock durante a modificação)
        chave = ChaveLicenca.query.filter_by(chave_serial=chave_serial).with_for_update().first()
        
        if not chave:
            return jsonify({"status": "invalid", "message": "Chave não encontrada."}), 404

        # 2. Verifica se a chave pertence ao produto
        if chave.produto_id != int(product_id_app):
            return jsonify({"status": "invalid", "message": "Chave válida, mas para um produto diferente."}), 403

        # 3. Verifica se a chave foi vendida 
        if not chave.vendida:
            return jsonify({"status": "invalid", "message": "Pagamento pendente ou chave não ativada."}), 403

        # 4. Verifica se a chave já está marcada como ativa (Controle de DRM)
        if chave.ativa_no_app:
             return jsonify({"status": "invalid", "message": "Chave já ativa em outro dispositivo."}), 403
        
        # --- Chave VÁLIDA e NUNCA USADA ANTES ---
        
        # 5. Marca a chave como ativa no App (Ativação da Licença)
        chave.ativa_no_app = True
        
        # 6. Commit final: Persiste a mudança de 'ativa_no_app' para TRUE
        db.session.add(chave) # Garante que a sessão rastreie a mudança
        db.session.commit()
        
        # 7. Retorna o sucesso.
        data_venda = chave.vendida_em or datetime.utcnow()

        return jsonify({
            "status": "valid",
            "message": "Chave de licença ativada com sucesso!",
            "licenca": {
                "chave": chave_serial,
                "cliente": chave.cliente_email,
                "data_ativacao": data_venda.isoformat(),
                "status_uso": "Ativa"
            }
        }), 200

    except Exception as e:
        # Garante que qualquer erro (incluindo o de sessão) reverta a transação
        db.session.rollback()
        print(f"ERRO CRÍTICO (VALIDAR CHAVE): {str(e)}")
        # Usamos 500 para erro interno do servidor
        return jsonify({"status": "error", "message": f"Erro interno na validação: {str(e)}"}), 500


# ROTA DE WEBHOOK
@app.route("/api/webhook", methods=["POST"])
def webhook_mercadopago():
    
    try:
        dados = request.get_json()
        
        if not validar_assinatura_webhook(request):
            return jsonify({"status": "error", "message": "Assinatura inválida"}), 401
        
        if dados.get("type") != "payment":
            return jsonify({"status": "success", "message": "Notificação ignorada"}), 200
        
        payment_id = dados.get("data", {}).get("id")
        
        if payment_id:
            # Enfileira o job para o worker 
            q.enqueue('worker.process_mercado_pago_webhook', payment_id)

        return jsonify({"status": "success", "message": "Webhook recebido e processamento enfileirado"}), 200
        
    except Exception as e:
        print(f"Erro ao processar webhook: {str(e)}")
        return jsonify({"status": "error", "message": f"Erro interno ao processar webhook: {str(e)}"}), 500


# ROTA DE CRIAÇÃO DE COBRANÇA (com Vendedor)
@app.route("/api/cobrancas", methods=["POST"])
def create_cobranca():
    
    try:
        dados = request.get_json()
        
        if not dados:
            return jsonify({"status": "error", "message": "Nenhum dado foi enviado."}), 400
            
        email_cliente = dados.get("email")
        nome_cliente = dados.get("nome", "Cliente") 
        product_id_recebido = dados.get("product_id")
        
        # NOVO CAMPO: Código do Vendedor (vem do dropdown)
        vendedor_codigo_recebido = dados.get("vendedor_codigo") 

        if not product_id_recebido:
            return jsonify({"status": "error", "message": "ID do produto é obrigatório."}), 400
        
        if not email_cliente or "@" not in email_cliente or "." not in email_cliente:
            return jsonify({"status": "error", "message": "Por favor, insira um email válido e obrigatório."}), 400
        
        # Opcional: Verifica se o código do vendedor existe (para integridade de dados)
        if vendedor_codigo_recebido: # Se o cliente selecionou algo (não é "")
            vendedor_existente = Vendedor.query.get(vendedor_codigo_recebido) # .get() é mais rápido para Chave Primária
            if not vendedor_existente:
                 # Avisa que o código é inválido, mas não impede a compra (não é crítico)
                 print(f"ALERTA: Código de vendedor inválido: {vendedor_codigo_recebido}. Prosseguindo sem afiliação.")
                 vendedor_codigo_recebido = None # Define como None se for inválido
        else:
            vendedor_codigo_recebido = None # Garante que "" (string vazia do dropdown) seja salvo como NULL

        produto = db.session.get(Produto, int(product_id_recebido))
        if not produto:
            return jsonify({"status": "error", "message": "Produto não encontrado."}), 404

        valor_correto = produto.preco
        descricao_correta = produto.nome

        access_token = os.environ.get("MERCADOPAGO_ACCESS_TOKEN")
        if not access_token:
            return jsonify({"status": "error", "message": "Token do Mercado Pago não configurado."}), 500
            
        sdk = mercadopago.SDK(access_token)

        payment_data = {
            "transaction_amount": valor_correto,
            "description": descricao_correta,
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

        nova_cobranca = Cobranca(
            external_reference=str(payment["id"]),
            cliente_nome=nome_cliente,
            cliente_email=email_cliente,
            valor=valor_correto,
            status=payment["status"],
            product_id=produto.id,
            vendedor_codigo=vendedor_codigo_recebido # NOVO: Salva o código do vendedor
        )
        
        cobranca_dict = nova_cobranca.to_dict() 

        db.session.add(nova_cobranca)
        db.session.commit()
        
        
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
        print(f"ERRO CRÍTICO GERAL (CREATE): {str(e)}")
        return jsonify({"status": "error", "message": f"Falha ao criar cobrança: {str(e)}"}), 500


# ROTA DE CONTATO
@app.route("/api/contato", methods=["POST"])
def handle_contact_form():
    dados = request.get_json()
    nome = dados.get("nome")
    email_remetente = dados.get("email") # Email do cliente
    assunto = dados.get("assunto")
    mensagem = dados.get("mensagem")

    if not all([nome, email_remetente, assunto, mensagem]):
        return jsonify({"status": "error", "message": "Todos os campos são obrigatórios."}), 400

    try:
        # 1. Pegue sua API Key do Render
        resend.api_key = os.environ.get("RESEND_API_KEY")
        if not resend.api_key:
             return jsonify({"status": "error", "message": "API de email não configurada."}), 500

        # 2. Formate o email
        params = {
            "from": "RREAD <contato@seu-dominio-verificado.com>", # Seu email verificado no Resend
            "to": "gameslizards@gmail.com", # Seu email de destino
            "reply_to": email_remetente, # Responde direto para o cliente
            "subject": f"Contato R·READ: {assunto}",
            "html": f"<p>De: {nome} ({email_remetente})</p><hr><p>{mensagem}</p>"
        }
        
        # 3. Envie!
        email = resend.Emails.send(params)
        
        if email.get("id"):
            return jsonify({"status": "success", "message": "Mensagem enviada com sucesso!"}), 200
        else:
            # Se o Resend retornar um erro
            return jsonify({"status": "error", "message": "Falha ao enviar e-mail."}), 500

    except Exception as e:
        print(f"[CONTACT FORM] ERRO RESEND: {e}")
        return jsonify({"status": "error", "message": "Não foi possível enviar a mensagem no momento."}), 500


# ROTA DE HEALTH CHECK
@app.route("/health", methods=["GET"])
def health_check():
# ... (código da função health_check existente) ...
   
    try:
        redis_conn.ping()
        redis_status = "ok"
    except Exception:
        redis_status = "error"

    try:
        with app.app_context():
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


# --- NOVA ROTA DA API DE RANKING ---
@app.route("/api/ranking", methods=["GET"])
def get_ranking():
    """
    Nova API para o dashboard de 'Ranked Sales'.
    Calcula pontos (vendas entregues) e comissões.
    """
    try:
        # Define suas regras de negócio
        PRECO_BASE_EBOOK = 15.90
        META_VENDAS_DIA = 1000 # Meta Diária
        
        # Define as comissões do Top 3
        # (índice 0 = 1º lugar, 1 = 2º lugar, 2 = 3º lugar)
        COMISSOES = {
            0: 0.25,  # 25%
            1: 0.10,  # 10%
            2: 0.05   # 5%
        }

        with app.app_context():
            
            # 1. Conta apenas vendas ENTREGUES (status == 'delivered')
            #    Agrupa por vendedor_codigo
            vendas_entregues_query = db.session.query(
                Cobranca.vendedor_codigo,
                func.count(Cobranca.id).label('pontos')
            ).filter(
                Cobranca.status == 'delivered',
                Cobranca.vendedor_codigo != None
            ).group_by(
                Cobranca.vendedor_codigo
            ).subquery() # Transforma em subconsulta

            # 2. Junta com a tabela de Vendedores para pegar os nomes
            #    Usa LEFT JOIN (outerjoin) para incluir vendedores com 0 pontos
            ranking_query = db.session.query(
                Vendedor.nome_vendedor,
                Vendedor.codigo_ranking,
                # Usa func.coalesce para tratar 0 vendas (pontos = NULL)
                func.coalesce(vendas_entregues_query.c.pontos, 0).label('pontos') 
            ).outerjoin(
                vendas_entregues_query,
                Vendedor.codigo_ranking == vendas_entregues_query.c.vendedor_codigo
            ).order_by(
                # Ordena por pontos (descendente)
                func.coalesce(vendas_entregues_query.c.pontos, 0).desc() 
            )
            
            ranking_db = ranking_query.all()

            # 3. Processa os dados em Python para calcular comissões
            ranking_final = []
            total_vendas_geral = 0

            for i, (nome, codigo, pontos) in enumerate(ranking_db):
                
                total_vendas_geral += pontos
                valor_vendido_bruto = pontos * PRECO_BASE_EBOOK
                
                # Pega a comissão (25, 10, 5) ou 0 se for 4º lugar ou abaixo
                percentual_comissao = COMISSOES.get(i, 0)
                valor_comissao_calculado = valor_vendido_bruto * percentual_comissao
                
                ranking_final.append({
                    "rank": i + 1,
                    "nome": nome,
                    "codigo": codigo,
                    "pontos": pontos,
                    # Formata os valores para exibição direta no frontend
                    "valor_comissao_brl": f"R$ {valor_comissao_calculado:,.2f}",
                    "percentual_comissao": f"{percentual_comissao * 100:.0f}%"
                })

            # 4. Prepara o JSON da Meta Diária
            meta = {
                "objetivo": META_VENDAS_DIA,
                "atual": total_vendas_geral,
                "percentual_meta": min((total_vendas_geral / META_VENDAS_DIA) * 100, 100) # Trava em 100%
            }

            # 5. Retorna o JSON completo
            return jsonify({
                "status": "success",
                "ranking": ranking_final,
                "meta_diaria": meta
            }), 200

    except Exception as e:
        db.session.rollback()
        print(f"ERRO CRÍTICO (RANKING): {str(e)}")
        return jsonify({"status": "error", "message": f"Erro interno ao calcular ranking: {str(e)}"}), 500


# --- FIM DA NOVA ROTA ---


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
