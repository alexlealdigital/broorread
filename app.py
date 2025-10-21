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



# Configuração do Banco de Dados

db_url = os.environ.get("DATABASE_URL", "sqlite:///cobrancas.db")

if db_url and db_url.startswith("postgres://"):

    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)

    

# Fix para PostgreSQL URL (Render usa postgresql://)

if db_url.startswith("postgres://"):

    db_url = db_url.replace("postgres://", "postgresql://", 1)



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



# Função para enviar e-mail de confirmação (agora será chamada pelo worker)

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



# A função processar_webhook_background será movida para um worker separado

# e adaptada para ser executada de forma assíncrona pelo RQ.

# Por enquanto, vamos manter uma versão simplificada para o worker.py



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

        

        # Enfileirar o job para processamento assíncrono

        # Passamos o payment_id para o worker buscar os detalhes do pagamento

        payment_id = dados.get("data", {}).get("id")

        if payment_id:

            q.enqueue('worker.process_mercado_pago_webhook', payment_id)

            print(f"Job para payment_id {payment_id} enfileirado com sucesso.")

        else:

            print("ID do pagamento não encontrado na notificação. Não foi possível enfileirar.")



        return jsonify({"status": "success", "message": "Webhook recebido e processamento enfileirado"}), 200

        

    except Exception as e:

        print(f"Erro ao processar webhook: {str(e)}")

        return jsonify({"status": "error", "message": f"Erro interno ao processar webhook: {str(e)}"}), 200



@app.route("/api/cobrancas", methods=["POST"])
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
            
            # ⚠️ CORREÇÃO CRÍTICA: Força a liberação do dado para o Worker
            db.session.expire_all() 
            
            print(f"Cobrança {payment['id']} SALVA COM SUCESSO e liberada para o Worker.")
        
        except Exception as db_error:
            # Em caso de falha de DB (ex: unique constraint), faz rollback
            db.session.rollback() 
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
        # ⚠️ Garante que qualquer falha geral faça o rollback e limpe a sessão
        db.session.rollback() 
        print(f"Erro ao criar cobrança: {str(e)}")
        return jsonify({"status": "error", "message": f"Erro ao criar cobrança: {str(e)}"}), 500


@app.route("/api/cobrancas", methods=["POST"])
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
            
            # ⚠️ CORREÇÃO CRÍTICA: Força a liberação do dado para o Worker
            db.session.expire_all() 
            
            print(f"Cobrança {payment['id']} SALVA COM SUCESSO e liberada para o Worker.")
        
        except Exception as db_error:
            # Em caso de falha de DB (ex: unique constraint), faz rollback
            db.session.rollback() 
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
        # ⚠️ Garante que qualquer falha geral faça o rollback e limpe a sessão
        db.session.rollback() 
        print(f"Erro ao criar cobrança: {str(e)}")
        return jsonify({"status": "error", "message": f"Erro ao criar cobrança: {str(e)}"}), 500

            

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

# NO SEU app.py (Web Service)

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
