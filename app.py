# Importações existentes (e 'func' do SQLAlchemy para contar)
from flask import Flask, jsonify, request, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime, date
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
from sqlalchemy import func
import resend
import requests as http_requests
 
# Inicialização do Flask
app = Flask(__name__, static_folder='static')
 
# Configuração de CORS
NETLIFY_ORIGIN_PROD  = "https://rread.netlify.app"
RENDER_ORIGIN        = "https://mercadopago-final.onrender.com"
NETLIFY_ORIGIN_TEST  = "https://rankedsale.netlify.app"
BROOSTORE_ORIGIN     = "https://broostore.netlify.app"
CORS(app, origins=[NETLIFY_ORIGIN_PROD, RENDER_ORIGIN, NETLIFY_ORIGIN_TEST, BROOSTORE_ORIGIN])
 
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
try:
    redis_conn = redis.from_url(redis_url, socket_connect_timeout=3)
    redis_conn.ping()
    q = Queue(connection=redis_conn)
except Exception as _redis_err:
    print(f"[REDIS] Indisponível na inicialização: {_redis_err}")
    redis_conn = None
    q = None
 
# ---------- MODELOS DE DADOS ----------
 
class Vendedor(db.Model):
    __tablename__ = "vendedores"
    codigo_ranking = db.Column(db.String(50), primary_key=True) 
    nome_vendedor = db.Column(db.String(200), nullable=False)
    email_contato = db.Column(db.String(200), nullable=True)
 
    def to_dict(self):
        return {
            "codigo_ranking": self.codigo_ranking,
            "nome_vendedor": self.nome_vendedor
        }
 
# NOVO: Modelo de Cupom
class Cupom(db.Model):
    __tablename__ = "cupons"
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    tipo = db.Column(db.String(20), nullable=False, default='percentual')  # 'percentual' ou 'valor_fixo'
    valor = db.Column(db.Float, nullable=False)  # 70 (%) ou 10 (R$)
    produto_id = db.Column(db.Integer, db.ForeignKey('produtos.id'), nullable=True)  # NULL = todos
    produto = db.relationship('Produto')
    valido_de = db.Column(db.Date, default=date.today)
    valido_ate = db.Column(db.Date, nullable=True)
    usos_maximos = db.Column(db.Integer, nullable=True)  # NULL = ilimitado
    usos_atuais = db.Column(db.Integer, default=0)
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)
 
    def to_dict(self):
        return {
            "id": self.id,
            "codigo": self.codigo,
            "tipo": self.tipo,
            "valor": self.valor,
            "produto_id": self.produto_id,
            "valido_ate": self.valido_ate.isoformat() if self.valido_ate else None,
            "usos_maximos": self.usos_maximos,
            "usos_atuais": self.usos_atuais,
            "ativo": self.ativo
        }
 
    def esta_valido(self):
        """Verifica se o cupom está ativo e dentro da validade"""
        if not self.ativo:
            return False, "Cupom inativo"
        
        hoje = date.today()
        if self.valido_de and hoje < self.valido_de:
            return False, "Cupom ainda não está válido"
        if self.valido_ate and hoje > self.valido_ate:
            return False, "Cupom expirado"
        
        if self.usos_maximos is not None and self.usos_atuais >= self.usos_maximos:
            return False, "Limite de usos atingido"
        
        return True, "Válido"
 
    def calcular_desconto(self, valor_original):
        """Calcula o valor com desconto aplicado"""
        if self.tipo == 'percentual':
            desconto = valor_original * (self.valor / 100)
        else:  # valor_fixo
            desconto = min(self.valor, valor_original)  # Não permite valor negativo
        
        valor_final = max(0, valor_original - desconto)
        return {
            "valor_original": valor_original,
            "desconto": desconto,
            "valor_final": valor_final,
            "percentual_aplicado": self.valor if self.tipo == 'percentual' else (desconto / valor_original * 100)
        }
 
 
class Cobranca(db.Model):
    __tablename__ = "cobrancas"
    id = db.Column(db.Integer, primary_key=True)
    external_reference = db.Column(db.String(100), unique=True, nullable=False)
    cliente_nome = db.Column(db.String(200), nullable=False)
    cliente_email = db.Column(db.String(200), nullable=False)
    cliente_telefone = db.Column(db.String(20), nullable=True)
    valor = db.Column(db.Float, nullable=False)
    valor_original = db.Column(db.Float, nullable=True)  # NOVO: Valor antes do desconto
    status = db.Column(db.String(50), default="pending", nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    product_id = db.Column(db.Integer, db.ForeignKey('produtos.id'), nullable=True)
    produto = db.relationship('Produto')
    
    chave_usada = db.relationship('ChaveLicenca', backref='cobranca_rel', uselist=False) 
    
    vendedor_codigo = db.Column(db.String(50), db.ForeignKey('vendedores.codigo_ranking'), nullable=True)
    vendedor = db.relationship('Vendedor', backref='vendas')
    
    cupom_id = db.Column(db.Integer, db.ForeignKey('cupons.id'), nullable=True)  # NOVO
    cupom = db.relationship('Cupom')
 
    def to_dict(self):
        return {
            "id": self.id,
            "external_reference": self.external_reference,
            "cliente_nome": self.cliente_nome,
            "cliente_email": self.cliente_email,
            "cliente_telefone": self.cliente_telefone,
            "valor": self.valor,
            "valor_original": self.valor_original,
            "status": self.status,
            "data_criacao": self.data_criacao.isoformat() if self.data_criacao else None,
            "vendedor_codigo": self.vendedor_codigo,
            "cupom_id": self.cupom_id
        }
 
 
class Produto(db.Model):
    __tablename__ = "produtos"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    preco = db.Column(db.Float, nullable=False)
    link_download = db.Column(db.String(500), nullable=False)
    tipo = db.Column(db.String(50), default="ebook", nullable=False) 
 
 
class ChaveLicenca(db.Model):
    __tablename__ = "chaves_licenca"
    id = db.Column(db.Integer, primary_key=True)
    chave_serial = db.Column(db.String(100), unique=True, nullable=False)
    produto_id = db.Column(db.Integer, db.ForeignKey('produtos.id'), nullable=False)
    vendida = db.Column(db.Boolean, default=False, nullable=False)
    vendida_em = db.Column(db.DateTime, nullable=True)
    cobranca_id = db.Column(db.Integer, db.ForeignKey('cobrancas.id'), unique=True, nullable=True) 
    cliente_email = db.Column(db.String(200), nullable=True)
    ativa_no_app = db.Column(db.Boolean, default=False, nullable=False) 
 
 
# Criação das tabelas
with app.app_context():
    db.create_all()
 
# --- FUNÇÕES AUXILIARES ---
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
 
 
# ROTA DE GAMIFICAÇÃO
@app.route("/api/vendedores", methods=["GET"])
def get_vendedores():
    try:
        with app.app_context():
            vendedores = Vendedor.query.order_by(Vendedor.nome_vendedor).all()
            return jsonify([v.to_dict() for v in vendedores]), 200
    except Exception as e:
        print(f"ERRO (VENDEDORES): {str(e)}")
        return jsonify({"status": "error", "message": "Não foi possível carregar a lista de vendedores."}), 500
 
 
# NOVO: ROTA PARA VALIDAR CUPOM
@app.route("/api/validar-cupom", methods=["POST"])
def validar_cupom():
    """Valida um cupom de desconto e retorna o valor calculado"""
    try:
        dados = request.get_json()
        codigo = dados.get("codigo", "").strip().upper()
        produto_id = dados.get("produto_id")
        valor_original = dados.get("valor_original")
 
        if not codigo:
            return jsonify({"status": "error", "message": "Código do cupom é obrigatório"}), 400
        
        if not produto_id or not valor_original:
            return jsonify({"status": "error", "message": "ID do produto e valor original são obrigatórios"}), 400
        
        cupom = Cupom.query.filter_by(codigo=codigo).first()
        
        if not cupom:
            return jsonify({"status": "error", "message": "Cupom não encontrado"}), 404
            
        valido, motivo = cupom.esta_valido()
        if not valido:
            return jsonify({"status": "error", "message": motivo}), 400
            
        # Verifica se o cupom é específico para um produto
        if cupom.produto_id is not None and cupom.produto_id != int(produto_id):
            return jsonify({"status": "error", "message": "Este cupom não é válido para este produto"}), 400
            
        # Calcula o desconto
        calculo = cupom.calcular_desconto(float(valor_original))
        
        return jsonify({
            "status": "success",
            "cupom": cupom.to_dict(),
            "calculo": calculo
        }), 200
        
    except Exception as e:
        print(f"Erro ao validar cupom: {str(e)}")
        return jsonify({"status": "error", "message": f"Erro interno: {str(e)}"}), 500
 
 
# WEBHOOK DO MERCADO PAGO
@app.route("/api/webhook", methods=["POST"])
def webhook():
    try:
        # if not validar_assinatura_webhook(request):
        #    return jsonify({"status": "error", "message": "Assinatura inválida"}), 401
 
        dados = request.get_json()
        payment_id = dados.get("data", {}).get("id")
        
        if payment_id:
            q.enqueue('worker.process_mercado_pago_webhook', payment_id)
 
        return jsonify({"status": "success", "message": "Webhook recebido e processamento enfileirado"}), 200
        
    except Exception as e:
        print(f"Erro ao processar webhook: {str(e)}")
        return jsonify({"status": "error", "message": f"Erro interno ao processar webhook: {str(e)}"}), 500
 
 
# ROTA DE CRIAÇÃO DE COBRANÇA (com Cupom e Telefone)
@app.route("/api/cobrancas", methods=["POST"])
def create_cobranca():
    try:
        dados = request.get_json()
        
        if not dados:
            return jsonify({"status": "error", "message": "Nenhum dado foi enviado."}), 400
            
        email_cliente = dados.get("email")
        nome_cliente = dados.get("nome", "Cliente")
        telefone_cliente = dados.get("telefone")
        product_id_recebido = dados.get("product_id")
        vendedor_codigo_recebido = dados.get("vendedor_codigo")
        cupom_id_recebido = dados.get("cupom_id")
        usuario_id = dados.get("usuario_id")  # NOVO
 
        if not product_id_recebido:
            return jsonify({"status": "error", "message": "ID do produto é obrigatório."}), 400
        
        if not email_cliente or "@" not in email_cliente or "." not in email_cliente:
            return jsonify({"status": "error", "message": "Por favor, insira um email válido e obrigatório."}), 400
        
        if telefone_cliente:
            telefone_limpo = ''.join(filter(str.isdigit, telefone_cliente))
            if len(telefone_limpo) < 10:
                return jsonify({"status": "error", "message": "Telefone inválido."}), 400
 
        if vendedor_codigo_recebido:
            vendedor_existente = Vendedor.query.get(vendedor_codigo_recebido)
            if not vendedor_existente:
                 print(f"ALERTA: Código de vendedor inválido: {vendedor_codigo_recebido}. Prosseguindo sem afiliação.")
                 vendedor_codigo_recebido = None
        else:
            vendedor_codigo_recebido = None
 
        produto = db.session.get(Produto, int(product_id_recebido))
 
        # Sempre sincroniza preço e dados com o Supabase (evita cache desatualizado)
        try:
            sb_url  = os.environ.get("SUPABASE_URL", "https://gyepvrzkwesohbagpgfa.supabase.co")
            sb_key  = os.environ.get("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd5ZXB2cnprd2Vzb2hiYWdwZ2ZhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjEzMDk5OTAsImV4cCI6MjA3Njg4NTk5MH0.ePwzEE8FjikLiTyjbtJXUtIIwFRlaSf5RYe7iKMDnTA")
            resp = http_requests.get(
                f"{sb_url}/rest/v1/products?id=eq.{product_id_recebido}&select=id,title,price,link_pdf",
                headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}
            )
            rows = resp.json()
            if rows:
                p = rows[0]
                if not produto:
                    # Produto novo: cria localmente
                    produto = Produto(
                        id=p["id"],
                        nome=p["title"],
                        preco=float(p["price"]),
                        link_download=p.get("link_pdf") or "",
                        tipo="ebook"
                    )
                    db.session.add(produto)
                else:
                    # Produto existente: sempre atualiza preço e link_pdf do Supabase
                    produto.preco         = float(p["price"])
                    produto.nome          = p["title"]
                    produto.link_download = p.get("link_pdf") or produto.link_download
                db.session.commit()
        except Exception as e:
            print(f"Erro ao sincronizar produto com Supabase: {e}")
 
        if not produto:
            return jsonify({"status": "error", "message": "Produto não encontrado."}), 404
 
        valor_original = produto.preco
        valor_final = valor_original
        cupom_obj = None
 
        if cupom_id_recebido:
            cupom_obj = Cupom.query.get(int(cupom_id_recebido))
            if cupom_obj:
                valido, _ = cupom_obj.esta_valido()
                if valido and (cupom_obj.produto_id is None or cupom_obj.produto_id == int(product_id_recebido)):
                    resultado = cupom_obj.calcular_desconto(valor_original)
                    valor_final = resultado["valor_final"]
                    cupom_obj.usos_atuais += 1
                    db.session.add(cupom_obj)
 
        descricao_correta = produto.nome
        if cupom_obj:
            descricao_correta += f" (Cupom: {cupom_obj.codigo})"
 
        # --- GERAÇÃO DO EXTERNAL_REFERENCE (CORRIGIDA) ---
        import uuid
        unique_id = str(uuid.uuid4())  # Identificador único para esta cobrança
 
        # Define o external_reference conforme o produto
        if usuario_id and int(product_id_recebido) == 7:  # produto de moedas
            external_reference = f"{usuario_id}:{unique_id}"
        else:
            external_reference = unique_id
 
        # --- CRIAÇÃO DO PAGAMENTO NO MERCADO PAGO ---
        access_token = os.environ.get("MERCADOPAGO_ACCESS_TOKEN")
        if not access_token:
            return jsonify({"status": "error", "message": "Token do Mercado Pago não configurado."}), 500
 
        sdk = mercadopago.SDK(access_token)
 
        payment_data = {
            "transaction_amount": round(valor_final, 2),
            "description": descricao_correta,
            "payment_method_id": "pix",
            "external_reference": external_reference,  # AGORA DEFINIDA
            "payer": {
                "email": email_cliente,
            }
        }
 
        payment_response = sdk.payment().create(payment_data)
        
        if payment_response["status"] != 201:
            error_msg = payment_response.get("response", {}).get("message", "Erro desconhecido do Mercado Pago")
            return jsonify({"status": "error", "message": f"Erro do Mercado Pago: {error_msg}"}), 500
            
        payment = payment_response["response"]
 
        qr_code_base64 = payment["point_of_interaction"]["transaction_data"]["qr_code_base64"]
        qr_code_text = payment["point_of_interaction"]["transaction_data"]["qr_code"]
 
        # --- CRIAÇÃO DA COBRANÇA NO BANCO (USA O MESMO external_reference) ---
        nova_cobranca = Cobranca(
            external_reference=external_reference,  # MESMO VALOR ENVIADO AO MP
            cliente_nome=nome_cliente,
            cliente_email=email_cliente,
            cliente_telefone=telefone_cliente,
            valor=round(valor_final, 2),
            valor_original=round(valor_original, 2),
            status=payment["status"],
            product_id=produto.id,
            vendedor_codigo=vendedor_codigo_recebido,
            cupom_id=cupom_obj.id if cupom_obj else None
        )
        
        cobranca_dict = nova_cobranca.to_dict()
 
        db.session.add(nova_cobranca)
        db.session.commit()
        
        # Prepara resposta
        resposta = {
            "status": "success",
            "message": "Cobrança PIX criada com sucesso!",
            "qr_code_base64": qr_code_base64,
            "qr_code_text": qr_code_text,
            "payment_id": payment["id"],
            "cobranca": cobranca_dict
        }
        
        if cupom_obj:
            resposta["desconto_aplicado"] = {
                "cupom_codigo": cupom_obj.codigo,
                "tipo": cupom_obj.tipo,
                "valor_desconto": round(valor_original - valor_final, 2),
                "valor_original": round(valor_original, 2),
                "valor_final": round(valor_final, 2)
            }
        
        return jsonify(resposta), 201
        
    except Exception as e:
        db.session.rollback()
        print(f"ERRO CRÍTICO GERAL (CREATE): {str(e)}")
        return jsonify({"status": "error", "message": f"Falha ao criar cobrança: {str(e)}"}), 500


# ROTA DE CONTATO
@app.route("/api/contato", methods=["POST"])
def handle_contact_form():
    dados = request.get_json()
    nome = dados.get("nome")
    email_remetente = dados.get("email")
    assunto = dados.get("assunto")
    mensagem = dados.get("mensagem")
 
    if not all([nome, email_remetente, assunto, mensagem]):
        return jsonify({"status": "error", "message": "Todos os campos são obrigatórios."}), 400
 
    try:
        resend.api_key = os.environ.get("RESEND_API_KEY")
        if not resend.api_key:
             return jsonify({"status": "error", "message": "API de email não configurada."}), 500
 
        params = {
            "from": "BrooStore <onboarding@resend.dev>",
            "to": "profalexleal@gmail.com",
            "reply_to": email_remetente,
            "subject": f"Contato BrooStore: {assunto}",
            "html": f"<p>De: {nome} ({email_remetente})</p><hr><p>{mensagem}</p>"
        }
        
        email = resend.Emails.send(params)
        
        if email.get("id"):
            return jsonify({"status": "success", "message": "Mensagem enviada com sucesso!"}), 200
        else:
            return jsonify({"status": "error", "message": "Falha ao enviar e-mail."}), 500
 
    except Exception as e:
        print(f"[CONTACT FORM] ERRO RESEND: {e}")
        return jsonify({"status": "error", "message": "Não foi possível enviar a mensagem no momento."}), 500
 
 
# ROTA DE HEALTH CHECK
 
@app.route("/api/sync-produto", methods=["POST"])
def sync_produto():
    """Sincroniza preço e dados de um produto da tabela products (Supabase) para produtos (local).
    Chamado pelo painel do autor após salvar edições."""
    dados = request.get_json(silent=True) or {}
    product_id = dados.get("product_id")
 
    if not product_id:
        return jsonify({"status": "error", "message": "product_id obrigatório"}), 400
 
    try:
        sb_url = os.environ.get("SUPABASE_URL", "https://gyepvrzkwesohbagpgfa.supabase.co")
        sb_key = os.environ.get("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd5ZXB2cnprd2Vzb2hiYWdwZ2ZhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjEzMDk5OTAsImV4cCI6MjA3Njg4NTk5MH0.ePwzEE8FjikLiTyjbtJXUtIIwFRlaSf5RYe7iKMDnTA")
        resp = http_requests.get(
            f"{sb_url}/rest/v1/products?id=eq.{product_id}&select=id,title,price,link_pdf",
            headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}
        )
        rows = resp.json()
        if not rows:
            return jsonify({"status": "error", "message": "Produto não encontrado no Supabase"}), 404
 
        p = rows[0]
        produto = db.session.get(Produto, int(p["id"]))
        if produto:
            produto.preco         = float(p["price"])
            produto.nome          = p["title"]
            produto.link_download = p.get("link_pdf") or produto.link_download
        else:
            produto = Produto(
                id=p["id"],
                nome=p["title"],
                preco=float(p["price"]),
                link_download=p.get("link_pdf") or "",
                tipo="ebook"
            )
            db.session.add(produto)
 
        db.session.commit()
        print(f"[sync-produto] id={p['id']} nome={p['title']} preco={p['price']}")
        return jsonify({"status": "ok", "preco": float(p["price"]), "nome": p["title"]})
 
    except Exception as e:
        print(f"[sync-produto] Erro: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500
 

# ─────────────────────────────────────────────
# PAGAMENTO COM CARTÃO DE CRÉDITO
# ─────────────────────────────────────────────
@app.route("/api/cobrancas-cartao", methods=["POST"])
def create_cobranca_cartao():
    try:
        dados = request.get_json()
        if not dados:
            return jsonify({"status": "error", "message": "Nenhum dado enviado."}), 400

        token           = dados.get("token")
        payment_method  = dados.get("payment_method_id")
        installments    = dados.get("installments", 1)
        email_cliente   = dados.get("email")
        nome_cliente    = dados.get("nome", "Cliente")
        cpf_cliente     = dados.get("cpf", "")
        product_id_rec  = dados.get("product_id")
        cupom_id_rec    = dados.get("cupom_id")
        issuer_id       = dados.get("issuer_id")

        if not token:
            return jsonify({"status": "error", "message": "Token do cartão é obrigatório."}), 400
        if not email_cliente or "@" not in email_cliente:
            return jsonify({"status": "error", "message": "E-mail inválido."}), 400
        if not product_id_rec:
            return jsonify({"status": "error", "message": "ID do produto é obrigatório."}), 400

        # Busca/sincroniza produto
        produto = db.session.get(Produto, int(product_id_rec))
        try:
            sb_url = os.environ.get("SUPABASE_URL", "https://gyepvrzkwesohbagpgfa.supabase.co")
            sb_key = os.environ.get("SUPABASE_ANON_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imd5ZXB2cnprd2Vzb2hiYWdwZ2ZhIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjEzMDk5OTAsImV4cCI6MjA3Njg4NTk5MH0.ePwzEE8FjikLiTyjbtJXUtIIwFRlaSf5RYe7iKMDnTA")
            resp = http_requests.get(
                f"{sb_url}/rest/v1/products?id=eq.{product_id_rec}&select=id,title,price,link_pdf",
                headers={"apikey": sb_key, "Authorization": f"Bearer {sb_key}"}
            )
            rows = resp.json()
            if rows:
                p = rows[0]
                if not produto:
                    produto = Produto(id=p["id"], nome=p["title"], preco=float(p["price"]),
                                      link_download=p.get("link_pdf") or "", tipo="ebook")
                    db.session.add(produto)
                else:
                    produto.preco         = float(p["price"])
                    produto.nome          = p["title"]
                    produto.link_download = p.get("link_pdf") or produto.link_download
                db.session.commit()
        except Exception as e:
            print(f"[CARTAO] Erro ao sincronizar produto: {e}")

        if not produto:
            return jsonify({"status": "error", "message": "Produto não encontrado."}), 404

        valor_original = produto.preco
        valor_final    = valor_original
        cupom_obj      = None

        if cupom_id_rec:
            cupom_obj = Cupom.query.get(int(cupom_id_rec))
            if cupom_obj:
                valido, _ = cupom_obj.esta_valido()
                if valido and (cupom_obj.produto_id is None or cupom_obj.produto_id == int(product_id_rec)):
                    resultado   = cupom_obj.calcular_desconto(valor_original)
                    valor_final = resultado["valor_final"]
                    cupom_obj.usos_atuais += 1
                    db.session.add(cupom_obj)

        import uuid
        external_reference = str(uuid.uuid4())

        access_token = os.environ.get("MERCADOPAGO_ACCESS_TOKEN")
        if not access_token:
            return jsonify({"status": "error", "message": "Token do Mercado Pago não configurado."}), 500

        sdk = mercadopago.SDK(access_token)

        payment_data = {
            "transaction_amount": round(valor_final, 2),
            "token":              token,
            "description":        produto.nome,
            "installments":       int(installments),
            "payment_method_id":  payment_method,
            "external_reference": external_reference,
            "payer": {
                "email": email_cliente,
                "first_name": nome_cliente.split()[0] if nome_cliente else "Cliente",
                "last_name":  " ".join(nome_cliente.split()[1:]) if len(nome_cliente.split()) > 1 else ".",
                "identification": {
                    "type":   "CPF",
                    "number": cpf_cliente.replace(".", "").replace("-", "")
                }
            }
        }
        if issuer_id:
            payment_data["issuer_id"] = int(issuer_id)

        import uuid as _uuid
        from mercadopago.config import RequestOptions
        request_options = RequestOptions(custom_headers={"X-Idempotency-Key": str(_uuid.uuid4())})

        payment_response = sdk.payment().create(payment_data, request_options)

        print(f"[CARTAO] Resposta MP status={payment_response.get('status')} response={payment_response.get('response')}")

        if payment_response["status"] not in [200, 201]:
            resp_body = payment_response.get("response") or {}
            error_msg = (
                resp_body.get("message")
                or resp_body.get("error")
                or str(resp_body)
                or "Erro desconhecido do Mercado Pago"
            )
            print(f"[CARTAO] ERRO MP completo: {payment_response}")
            return jsonify({"status": "error", "message": f"Erro MP: {error_msg}"}), 500

        payment    = payment_response["response"]
        status_mp  = payment.get("status")
        status_detail = payment.get("status_detail", "")

        nova_cobranca = Cobranca(
            external_reference=external_reference,
            cliente_nome=nome_cliente,
            cliente_email=email_cliente,
            cliente_telefone=None,
            valor=round(valor_final, 2),
            valor_original=round(valor_original, 2),
            status=status_mp,
            product_id=produto.id,
            cupom_id=cupom_obj.id if cupom_obj else None
        )
        db.session.add(nova_cobranca)
        db.session.commit()

        if status_mp == "approved":
            try:
                from rq import Queue as RQueue
                rq = RQueue(connection=redis_conn)
                rq.enqueue("worker.process_mercado_pago_webhook", payment["id"])
            except Exception as _rq_err:
                print(f"[CARTAO] Redis indisponível, webhook não enfileirado: {_rq_err}")
            mensagem = "Pagamento aprovado! Você receberá o produto por e-mail em instantes."
        elif status_mp == "in_process":
            mensagem = "Pagamento em análise. Você receberá o produto assim que aprovado."
        else:
            mensagem = f"Pagamento não aprovado ({status_detail}). Verifique os dados do cartão."

        resposta = {
            "status":        status_mp,
            "status_detail": status_detail,
            "payment_id":    payment["id"],
            "mensagem":      mensagem,
        }
        if cupom_obj:
            resposta["desconto_aplicado"] = {
                "cupom_codigo": cupom_obj.codigo,
                "tipo": cupom_obj.tipo,
                "valor_desconto": round(valor_original - valor_final, 2),
                "valor_original": round(valor_original, 2),
                "valor_final": round(valor_final, 2)
            }

        return jsonify(resposta), 201

    except Exception as e:
        db.session.rollback()
        print(f"ERRO CRÍTICO GERAL (CARTÃO): {str(e)}")
        return jsonify({"status": "error", "message": f"Falha ao criar cobrança com cartão: {str(e)}"}), 500


# ROTA DE RANKING / DASHBOARD
@app.route("/api/ranking", methods=["GET"])
def get_ranking():
    try:
        # Configurações de metas e comissões
        META_VENDAS_DIA = 100
        PRECO_BASE_EBOOK = 15.90
        COMISSOES = {0: 0.15, 1: 0.10, 2: 0.05} 

        with app.app_context():
            vendas_entregues_query = db.session.query(
                Cobranca.vendedor_codigo,
                func.count(Cobranca.id).label('pontos')
            ).filter(
                Cobranca.status == 'delivered',
                Cobranca.vendedor_codigo != None
            ).group_by(
                Cobranca.vendedor_codigo
            ).subquery()
 
            ranking_query = db.session.query(
                Vendedor.nome_vendedor,
                Vendedor.codigo_ranking,
                func.coalesce(vendas_entregues_query.c.pontos, 0).label('pontos') 
            ).outerjoin(
                vendas_entregues_query,
                Vendedor.codigo_ranking == vendas_entregues_query.c.vendedor_codigo
            ).order_by(
                func.coalesce(vendas_entregues_query.c.pontos, 0).desc() 
            )
            
            ranking_db = ranking_query.all()
 
            ranking_final = []
            total_vendas_geral = 0
 
            for i, (nome, codigo, pontos) in enumerate(ranking_db):
                
                total_vendas_geral += pontos
                valor_vendido_bruto = pontos * PRECO_BASE_EBOOK
                
                percentual_comissao = COMISSOES.get(i, 0)
                valor_comissao_calculado = valor_vendido_bruto * percentual_comissao
                
                ranking_final.append({
                    "rank": i + 1,
                    "nome": nome,
                    "codigo": codigo,
                    "pontos": pontos,
                    "valor_comissao_brl": f"R$ {valor_comissao_calculado:,.2f}",
                    "percentual_comissao": f"{percentual_comissao * 100:.0f}%"
                })
 
            meta = {
                "objetivo": META_VENDAS_DIA,
                "atual": total_vendas_geral,
                "percentual_meta": min((total_vendas_geral / META_VENDAS_DIA) * 100, 100)
            }
 
            return jsonify({
                "status": "success",
                "ranking": ranking_final,
                "meta_diaria": meta
            }), 200
 
    except Exception as e:
        db.session.rollback()
        print(f"ERRO CRÍTICO (RANKING): {str(e)}")
        return jsonify({"status": "error", "message": f"Erro interno ao calcular ranking: {str(e)}"}), 500
 
 


# ═══════════════════════════════════════════════════════════
# COMPRESSOR DE PDF — validação de código + compressão
# ═══════════════════════════════════════════════════════════

@app.route("/api/validar-codigo-compressao", methods=["POST"])
def validar_codigo_compressao():
    """Verifica se o external_reference corresponde a um pagamento
    aprovado do produto 99 (compressão de PDF)."""
    try:
        dados  = request.get_json()
        codigo = (dados.get("codigo") or "").strip()
        if not codigo:
            return jsonify({"status": "erro", "message": "Código não informado."}), 400

        cobranca = Cobranca.query.filter_by(
            external_reference=codigo,
            product_id=99,
            status="approved"
        ).first()

        if not cobranca:
            return jsonify({"status": "erro",
                            "message": "Código inválido ou pagamento ainda não confirmado."}), 404

        # Verifica se o código já foi usado para uma compressão
        if getattr(cobranca, "compressao_usada", False):
            return jsonify({"status": "erro",
                            "message": "Este código já foi utilizado."}), 400

        return jsonify({"status": "ok", "message": "Código válido."}), 200

    except Exception as e:
        print(f"ERRO validar_codigo_compressao: {e}")
        return jsonify({"status": "erro", "message": str(e)}), 500


@app.route("/api/comprimir-pdf", methods=["POST"])
def comprimir_pdf():
    """Recebe o PDF e o código de liberação, comprime e devolve o arquivo."""
    import subprocess, tempfile, os as _os

    try:
        codigo = (request.form.get("codigo") or "").strip()
        pdf    = request.files.get("pdf")

        if not codigo:
            return jsonify({"status": "erro", "message": "Código não informado."}), 400
        if not pdf:
            return jsonify({"status": "erro", "message": "Nenhum arquivo enviado."}), 400

        # Valida código novamente (segurança)
        cobranca = Cobranca.query.filter_by(
            external_reference=codigo,
            product_id=99,
            status="approved"
        ).first()

        if not cobranca:
            return jsonify({"status": "erro",
                            "message": "Código inválido ou pagamento não confirmado."}), 403

        if getattr(cobranca, "compressao_usada", False):
            return jsonify({"status": "erro",
                            "message": "Este código já foi utilizado."}), 400

        # Salva o PDF recebido em arquivo temporário
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_in:
            pdf.save(tmp_in.name)
            tmp_in_path = tmp_in.name

        tmp_out_path = tmp_in_path.replace(".pdf", "_out.pdf")

        try:
            result = subprocess.run([
                "gs",
                "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.4",
                "-dPDFSETTINGS=/ebook",
                "-dNOPAUSE", "-dQUIET", "-dBATCH",
                f"-sOutputFile={tmp_out_path}",
                tmp_in_path
            ], capture_output=True, timeout=120)

            if result.returncode != 0 or not _os.path.exists(tmp_out_path):
                raise Exception("Ghostscript falhou: " + result.stderr.decode()[:200])

            # Marca código como usado
            try:
                cobranca.compressao_usada = True
                db.session.commit()
            except Exception:
                pass  # campo pode não existir ainda; não bloqueia a entrega

            # Retorna o PDF comprimido
            from flask import send_file
            return send_file(
                tmp_out_path,
                mimetype="application/pdf",
                as_attachment=True,
                download_name="comprimido.pdf"
            )

        finally:
            for p in [tmp_in_path]:
                try: _os.unlink(p)
                except: pass

    except Exception as e:
        print(f"ERRO comprimir_pdf: {e}")
        return jsonify({"status": "erro", "message": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
