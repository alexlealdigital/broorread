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

# Inicialização do Flask
app = Flask(__name__, static_folder='static')

# Configuração de CORS
NETLIFY_ORIGIN_PROD = "https://rread.netlify.app"
RENDER_ORIGIN = "https://mercadopago-final.onrender.com" 
NETLIFY_ORIGIN_TEST = "https://rankedsale.netlify.app" 
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
            return jsonify({"status": "error", "message": "Dados do produto incompletos"}), 400

        # Busca o cupom
        cupom = Cupom.query.filter_by(codigo=codigo).first()
        
        if not cupom:
            return jsonify({"status": "error", "message": "Cupom não encontrado"}), 404

        # Verifica validade
        valido, mensagem = cupom.esta_valido()
        if not valido:
            return jsonify({"status": "error", "message": mensagem}), 400

        # Verifica se é válido para este produto (se tiver restrição)
        if cupom.produto_id is not None and cupom.produto_id != int(produto_id):
            return jsonify({
                "status": "error", 
                "message": f"Este cupom não é válido para este produto"
            }), 400

        # Calcula o desconto
        resultado = cupom.calcular_desconto(float(valor_original))
        
        return jsonify({
            "status": "success",
            "cupom": {
                "id": cupom.id,
                "codigo": cupom.codigo,
                "tipo": cupom.tipo,
                "valor": cupom.valor,
                "descricao": f"{cupom.valor}{'%' if cupom.tipo == 'percentual' else ' R$ OFF'}"
            },
            "calculo": resultado
        }), 200

    except Exception as e:
        print(f"ERRO (VALIDAR CUPOM): {str(e)}")
        return jsonify({"status": "error", "message": f"Erro ao validar cupom: {str(e)}"}), 500


# ROTA DE VALIDAÇÃO DE CHAVE
@app.route("/api/validar_chave", methods=["POST"])
def validar_chave():
    dados = request.get_json()
    chave_serial = dados.get("chave_serial", "").strip().upper()
    product_id_app = dados.get("product_id") 
    
    if not chave_serial or not product_id_app:
        return jsonify({"status": "error", "message": "Chave serial e ID do produto incompletos."}), 400

    try:
        chave = ChaveLicenca.query.filter_by(chave_serial=chave_serial).with_for_update().first()
        
        if not chave:
            return jsonify({"status": "invalid", "message": "Chave não encontrada."}), 404

        if chave.produto_id != int(product_id_app):
            return jsonify({"status": "invalid", "message": "Chave válida, mas para um produto diferente."}), 403

        if not chave.vendida:
            return jsonify({"status": "invalid", "message": "Pagamento pendente ou chave não ativada."}), 403

        if chave.ativa_no_app:
             return jsonify({"status": "invalid", "message": "Chave já ativa em outro dispositivo."}), 403
        
        chave.ativa_no_app = True
        db.session.add(chave)
        db.session.commit()
        
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
        db.session.rollback()
        print(f"ERRO CRÍTICO (VALIDAR CHAVE): {str(e)}")
        return jsonify({"status": "error", "message": f"Erro interno na validação: {str(e)}"}), 500


# ROTA DE WEBHOOK
@app.route("/api/webhook", methods=["POST"])
def webhook_mercado_pago():
    
    try:
        dados = request.get_json()
        
        if not validar_assinatura_webhook(request):
            return jsonify({"status": "error", "message": "Assinatura inválida"}), 401
        
        if dados.get("type") != "payment":
            return jsonify({"status": "success", "message": "Notificação ignorada"}), 200
        
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
        cupom_id_recebido = dados.get("cupom_id")  # ID do cupom aplicado
        # NOVO: capturar usuario_id do payload
        usuario_id = dados.get("usuario_id")

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
        if not produto:
            return jsonify({"status": "error", "message": "Produto não encontrado."}), 404

        valor_original = produto.preco
        valor_final = valor_original
        cupom_obj = None

        # Se tiver cupom, valida e aplica desconto
        if cupom_id_recebido:
            cupom_obj = Cupom.query.get(int(cupom_id_recebido))
            if cupom_obj:
                valido, _ = cupom_obj.esta_valido()
                if valido and (cupom_obj.produto_id is None or cupom_obj.produto_id == int(product_id_recebido)):
                    resultado = cupom_obj.calcular_desconto(valor_original)
                    valor_final = resultado["valor_final"]
                    # Incrementa o contador de usos
                    cupom_obj.usos_atuais += 1
                    db.session.add(cupom_obj)

        descricao_correta = produto.nome
        if cupom_obj:
            descricao_correta += f" (Cupom: {cupom_obj.codigo})"

        access_token = os.environ.get("MERCADOPAGO_ACCESS_TOKEN")
        if not access_token:
            return jsonify({"status": "error", "message": "Token do Mercado Pago não configurado."}), 500
            
        sdk = mercadopago.SDK(access_token)

        payment_data = {
            "transaction_amount": round(valor_final, 2),
            "description": descricao_correta,
            "payment_method_id": "pix",
            "external_reference": external_reference,  # <--- ESSENCIAL
            "payer": {
                "email": email_cliente,
            }
        }

        payment_response = sdk.payment().create(payment_data)
        
        if payment_response["status"] != 201:
            error_msg = payment_response.get("response", {}).get("message", "Erro desconhecido do Mercado Pago")
            return jsonify({"status": "error", "message": f"Erro do Mercado Pago: {error_msg}"}), 500
            
        payment = payment_response["response"]

        # --- NOVO: Montar external_reference condicional ---
        if usuario_id and int(product_id_recebido) == 7:  # produto de moedas (ID 7)
            external_reference = f"{usuario_id}:{payment['id']}"
        else:
            external_reference = str(payment['id'])

        qr_code_base64 = payment["point_of_interaction"]["transaction_data"]["qr_code_base64"]
        qr_code_text = payment["point_of_interaction"]["transaction_data"]["qr_code"]

        nova_cobranca = Cobranca(
            external_reference=external_reference,  # AGORA USA A VARIÁVEL
            cliente_nome=nome_cliente,
            cliente_email=email_cliente,
            cliente_telefone=telefone_cliente,
            valor=round(valor_final, 2),
            valor_original=round(valor_original, 2),  # Salva valor original
            status=payment["status"],
            product_id=produto.id,
            vendedor_codigo=vendedor_codigo_recebido,
            cupom_id=cupom_obj.id if cupom_obj else None
        )
        
        cobranca_dict = nova_cobranca.to_dict() 

        db.session.add(nova_cobranca)
        db.session.commit()
        
        # Prepara resposta com informações do desconto
        resposta = {
            "status": "success",
            "message": "Cobrança PIX criada com sucesso!",
            "qr_code_base64": qr_code_base64,
            "qr_code_text": qr_code_text,
            "payment_id": payment["id"],
            "cobranca": cobranca_dict
        }
        
        # Adiciona info do desconto se houver
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
            "from": "RREAD <onboarding@resend.dev>",
            "to": "gameslizards@gmail.com",
            "reply_to": email_remetente,
            "subject": f"Contato R·READ: {assunto}",
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
@app.route("/health", methods=["GET"])
def health_check():
   
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


# ROTA DA API DE RANKING
@app.route("/api/ranking", methods=["GET"])
def get_ranking():
    try:
        PRECO_BASE_EBOOK = 15.90
        META_VENDAS_DIA = 1000
        
        COMISSOES = {
            0: 0.25,
            1: 0.10,
            2: 0.05
        }

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


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
