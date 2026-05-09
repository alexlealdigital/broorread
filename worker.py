#!/usr/bin/env python3
"""
Worker RQ – BrooStore
Processa webhooks do Mercado Pago, entrega produtos e registra vendas no Supabase.
"""

import os
import mercadopago
import smtplib
import redis
import requests
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from rq import Worker, Queue 
from datetime import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# ============================================
# CONFIGURAÇÃO DO FLASK / DB LOCAL
# ============================================
app = Flask(__name__)

db_url = os.environ.get("DATABASE_URL", "sqlite:///cobrancas.db")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif db_url and db_url.startswith("postgresql://"):
    db_url = db_url.replace("postgresql://", "postgresql+psycopg://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 300}

db = SQLAlchemy(app)

# ============================================
# CONFIGURAÇÃO SUPABASE
# ============================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://gyepvrzkwesohbagpgfa.supabase.co")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

# ============================================
# MODELOS DE DADOS (DB LOCAL)
# ============================================
class Cobranca(db.Model):
    __tablename__ = "cobrancas"
    id = db.Column(db.Integer, primary_key=True)
    external_reference = db.Column(db.String(100), nullable=False)
    cliente_nome = db.Column(db.String(200), nullable=False)
    cliente_email = db.Column(db.String(200), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default="pending", nullable=False)
    data_criacao = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('produtos.id'), nullable=True)
    produto = db.relationship('Produto')
    chave_usada = db.relationship('ChaveLicenca', backref='cobranca_rel', uselist=False)

class Produto(db.Model):
    __tablename__ = "produtos"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    preco = db.Column(db.Float, nullable=False)
    link_download = db.Column(db.String(500), nullable=False)
    tipo = db.Column(db.String(50), default="ebook", nullable=False)
    moedas_equivalentes = db.Column(db.Integer, nullable=True)

class ChaveLicenca(db.Model):
    __tablename__ = "chaves_licenca"
    id = db.Column(db.Integer, primary_key=True)
    chave_serial = db.Column(db.String(100), unique=True, nullable=False)
    produto_id = db.Column(db.Integer, db.ForeignKey('produtos.id'), nullable=False)
    produto = db.relationship('Produto', backref=db.backref('chaves', lazy=True))
    vendida = db.Column(db.Boolean, default=False, nullable=False)
    vendida_em = db.Column(db.DateTime, nullable=True)
    cobranca_id = db.Column(db.Integer, db.ForeignKey('cobrancas.id'), unique=True, nullable=True)
    cliente_email = db.Column(db.String(200), nullable=True)

class Sale(db.Model):
    __tablename__ = "sales"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('produtos.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

# ============================================
# FUNÇÃO: REGISTRAR VENDA NO SUPABASE
# ============================================
def registrar_venda_no_supabase(product_id, customer_email, amount, payment_id):
    """Insere a venda na tabela sales do Supabase para o dashboard atualizar."""
    if not SUPABASE_SERVICE_ROLE_KEY:
        print("[WORKER] ❌ ERRO: SUPABASE_SERVICE_ROLE_KEY não configurada!")
        return False
    
    try:
        url = f"{SUPABASE_URL}/rest/v1/sales"
        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
        
        payload = {
            "product_id": int(product_id),
            "customer_email": str(customer_email),
            "amount": float(amount),
            "payment_id": str(payment_id),
            "status": "paid"
        }
        
        # Busca author_id do produto no Supabase para preencher corretamente
        try:
            prod_url = f"{SUPABASE_URL}/rest/v1/products?id=eq.{product_id}&select=author_id"
            prod_resp = requests.get(prod_url, headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
            }, timeout=5)
            prod_rows = prod_resp.json()
            if prod_rows and prod_rows[0].get("author_id"):
                payload["author_id"] = prod_rows[0]["author_id"]
        except Exception as e:
            print(f"[WORKER] Aviso: não conseguiu buscar author_id: {e}")
        
        print(f"[WORKER] Inserindo no Supabase: Produto {product_id}, Valor {amount}")
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        
        print(f"[WORKER] Resposta Supabase: Status {response.status_code}")
        
        if response.status_code in [200, 201]:
            print(f"[WORKER] ✅ Venda registrada no Supabase!")
            return True
        else:
            print(f"[WORKER] ❌ Erro Supabase: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"[WORKER] ❌ Exceção ao conectar no Supabase: {e}")
        return False

# ============================================
# FUNÇÃO: ENVIAR EMAIL DE CONFIRMAÇÃO
# ============================================
def enviar_email_confirmacao(destinatario, nome_cliente, valor, link_produto, cobranca, nome_produto, chave_acesso=None):
    """Envia email de entrega do produto."""
    try:
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.zoho.com")
        email_user = os.environ["EMAIL_USER"]
        email_pass = os.environ["EMAIL_PASSWORD"]
    except KeyError:
        print("[WORKER] ERRO: Credenciais de email não configuradas.")
        return False
    
    if chave_acesso:
        assunto = f"BrooStore: Sua chave de acesso para \"{nome_produto}\" chegou! 🚀"
        instrucoes_entrega = f"""
            <p>Agradecemos por escolher a <strong>BrooStore</strong>! Seu pagamento de <strong>R$ {valor:.2f}</strong> foi confirmado.</p>
            <h2 style="color: #27ae60;">Sua Chave de Acesso está aqui! 🔑</h2>
            <div style="background-color: #e0f2f1; padding: 15px; border-radius: 8px; text-align: center; margin: 20px 0; border: 2px dashed #27ae60;">
                <code style="font-size: 1.5em; font-weight: bold; color: #14213d; display: block; word-break: break-all;">{chave_acesso}</code>
            </div>
            <p>Copie a chave acima e use-a no instalador. Se precisar baixar:</p>
            <div style="text-align: center; margin: 25px 0;">
                <a href="{link_produto}" style="background-color: #27ae60; color: white; padding: 14px 28px; text-decoration: none; border-radius: 25px; font-weight: bold;">[·] Baixar o Instalador</a>
            </div>
        """
    else:
        assunto = f"BrooStore: Seu e-book \"{nome_produto}\" está pronto! 🎉"
        instrucoes_entrega = f"""
            <p>Agradecemos por escolher a <strong>BrooStore</strong>! Seu pagamento de <strong>R$ {valor:.2f}</strong> foi confirmado.</p>
            <h2>Agora é hora de devorar o conteúdo!</h2>
            <div style="text-align: center; margin: 25px 0;">
                <a href="{link_produto}" style="background-color: #f59e0b; color: #14213d; padding: 14px 28px; text-decoration: none; border-radius: 25px; font-weight: bold;">[·] Baixar Meu E-book</a>
            </div>
        """
    
    corpo_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f4f4f4; }}
    .container {{ max-width: 600px; margin: 20px auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
    .header {{ background-color: #3B82F6; padding: 30px; text-align: center; color: white; }}
    .header h1 {{ margin: 0; font-size: 1.8em; }}
    .content {{ padding: 30px; }}
    .footer {{ background-color: #f9fafb; padding: 20px; text-align: center; font-size: 0.9em; color: #6b7280; border-top: 1px solid #e5e7eb; }}
    code {{ font-family: monospace; background-color: #f3f4f6; padding: 2px 5px; border-radius: 3px; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header"><h1>✅ Parabéns pela sua compra!</h1></div>
    <div class="content">
      <p>Olá, {nome_cliente},</p>
      {instrucoes_entrega}
    </div>
    <div class="footer">
      <strong>BrooStore</strong><br>
      Pedido ID: {cobranca.id}<br>
      Em caso de dúvidas, responda este e-mail.
    </div>
  </div>
</body>
</html>"""
    
    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"] = email_user
    msg["To"] = destinatario
    msg.attach(MIMEText(corpo_html, "html"))
    
    try:
        smtp_port = int(os.environ.get("SMTP_PORT", 587))
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(email_user, email_pass)
            server.send_message(msg)
        print(f"[WORKER] Email enviado para {destinatario}")
        return True
    except Exception as exc:
        print(f"[WORKER] Falha no envio SMTP: {exc}")
        return False

def enviar_email_recibo_moedas(destinatario, nome_cliente, valor, quantidade, link_jogo, cobranca):
    """Envia email de recibo para compra de moedas."""
    try:
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.zoho.com")
        email_user = os.environ["EMAIL_USER"]
        email_pass = os.environ["EMAIL_PASSWORD"]
    except KeyError:
        print("[WORKER] ERRO: Credenciais de email não configuradas.")
        return False

    assunto = f"🪙 Suas {quantidade} moedas já estão na sua conta - Broo Store"
    instrucoes_entrega = f"""
        <p>Agradecemos por escolher a <strong>Broo Store</strong>! Seu pagamento de <strong>R$ {valor:.2f}</strong> referente à compra de <strong>{quantidade} moedas</strong> foi confirmado.</p>
        <div style="text-align: center; margin: 25px 0;">
            <a href="{link_jogo}" style="background-color: #fca311; color: #14213d; padding: 14px 28px; text-decoration: none; border-radius: 25px; font-weight: bold;">🎮 Jogar Agora</a>
        </div>
    """

    corpo_html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f4f4f4; }}
    .container {{ max-width: 600px; margin: 20px auto; background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
    .header {{ background-color: #14213d; padding: 30px; text-align: center; color: white; }}
    .header h1 {{ margin: 0; font-size: 1.8em; }}
    .content {{ padding: 30px; }}
    .footer {{ background-color: #f9fafb; padding: 20px; text-align: center; font-size: 0.9em; color: #6b7280; border-top: 1px solid #e5e7eb; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header"><h1>✅ Compra confirmada!</h1></div>
    <div class="content">
      <p>Olá, {nome_cliente},</p>
      {instrucoes_entrega}
    </div>
    <div class="footer">
      <strong>Broo Store</strong><br>
      Pedido ID: {cobranca.id}
    </div>
  </div>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"] = email_user
    msg["To"] = destinatario
    msg.attach(MIMEText(corpo_html, "html"))

    try:
        smtp_port = int(os.environ.get("SMTP_PORT", 587))
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(email_user, email_pass)
            server.send_message(msg)
        print(f"[WORKER] Email de moedas enviado para {destinatario}")
        return True
    except Exception as exc:
        print(f"[WORKER] Falha no envio SMTP (moedas): {exc}")
        return False

# ============================================
# JOB PRINCIPAL: PROCESSAR WEBHOOK
# ============================================
def process_mercado_pago_webhook(payment_id):
    """Processa pagamento aprovado do Mercado Pago."""
    with app.app_context():
        # 1. Verificar token
        access_token = os.environ.get("MERCADOPAGO_ACCESS_TOKEN")
        if not access_token:
            print("[WORKER] ERRO: MERCADOPAGO_ACCESS_TOKEN não configurado.")
            return
        
        # 2. Consultar Mercado Pago
        sdk = mercadopago.SDK(access_token)
        try:
            resp = sdk.payment().get(payment_id)
        except Exception as e:
            print(f"[WORKER] Falha ao consultar MP: {e}")
            return
        
        if resp["status"] != 200:
            print(f"[WORKER] MP respondeu {resp['status']}")
            raise RuntimeError(f"Erro na API do MP: {resp['status']}")
        
        payment = resp["response"]
        
        if payment.get("status") != "approved":
            print(f"[WORKER] Pagamento {payment_id} não aprovado ({payment.get('status')}).")
            return
        
        # 3. Buscar cobrança pelo EXTERNAL_REFERENCE
        external_ref = payment.get("external_reference")
        if not external_ref:
            print(f"[WORKER] ERRO: Pagamento {payment_id} sem external_reference.")
            return
        
        # Retry com delay
        cobranca = None
        for tentativa in range(5):
            cobranca = Cobranca.query.filter_by(external_reference=str(external_ref)).first()
            if cobranca:
                break
            if tentativa < 4:
                print(f"[WORKER] Tentativa {tentativa+1}: cobrança não encontrada, aguardando 2s...")
                time.sleep(2)
                db.session.expire_all()
        
        if not cobranca:
            print(f"[WORKER] ERRO: Cobrança {external_ref} não encontrada.")
            return
        
        if cobranca.status == "delivered":
            print(f"[WORKER] Cobrança {cobranca.id} já foi entregue. Ignorando.")
            return
        
        # 4. Buscar produto
        produto = cobranca.produto
        if not produto:
            print(f"[WORKER] ERRO: Produto não encontrado.")
            return
        
        # 5. Lógica de Entrega
        link_entrega = produto.link_download
        chave_entregue = None
        sucesso_entrega = False
        
        if produto.tipo == 'moedas':
            # Extrair usuario_id do external_reference (formato "usuario_id:unique_id")
            usuario_id = None
            if ':' in str(external_ref):
                usuario_id = str(external_ref).split(':')[0]
            
            if usuario_id:
                # Chamar Edge Function do Supabase para creditar moedas
                edge_function_url = f"{SUPABASE_URL}/functions/v1/creditar-moedas"
                payload = {
                    "usuario_id": usuario_id,
                    "quantidade": produto.moedas_equivalentes or 0,
                    "valor_pago": cobranca.valor,
                    "mp_id": str(payment_id)
                }
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"
                }
                
                try:
                    resp_edge = requests.post(edge_function_url, json=payload, headers=headers, timeout=15)
                    if resp_edge.status_code == 200:
                        print(f"[WORKER] ✅ Moedas creditadas para {usuario_id}")
                        sucesso_entrega = enviar_email_recibo_moedas(
                            destinatario=cobranca.cliente_email,
                            nome_cliente=cobranca.cliente_nome,
                            valor=cobranca.valor,
                            quantidade=produto.moedas_equivalentes or 0,
                            link_jogo="https://broo.games",
                            cobranca=cobranca
                        )
                    else:
                        print(f"[WORKER] ❌ Erro ao creditar moedas: {resp_edge.status_code} - {resp_edge.text}")
                except Exception as e:
                    print(f"[WORKER] ❌ Exceção ao chamar Edge Function: {e}")
            else:
                print("[WORKER] ⚠️ Compra de moedas sem usuario_id.")
        else:
            # Entrega normal (Ebook ou Game)
            if produto.tipo in ["game", "app"]:
                print(f"[WORKER] Reservando chave para {produto.nome}...")
                chave_obj = ChaveLicenca.query.filter(
                    ChaveLicenca.produto_id == produto.id,
                    ChaveLicenca.vendida == False
                ).order_by(ChaveLicenca.id.asc()).with_for_update().first()
                
                if chave_obj:
                    chave_obj.vendida = True
                    chave_obj.vendida_em = datetime.utcnow()
                    chave_obj.cobranca_id = cobranca.id
                    chave_obj.cliente_email = cobranca.cliente_email
                    chave_entregue = chave_obj.chave_serial
                    db.session.add(chave_obj)
                    print(f"[WORKER] Chave reservada: {chave_entregue[:10]}...")
                else:
                    print(f"[WORKER] ERRO: Estoque esgotado!")
                    db.session.rollback()
                    raise Exception(f"Estoque esgotado: {produto.id}")
            
            sucesso_entrega = enviar_email_confirmacao(
                destinatario=cobranca.cliente_email,
                nome_cliente=cobranca.cliente_nome,
                valor=cobranca.valor,
                link_produto=link_entrega,
                cobranca=cobranca,
                nome_produto=produto.nome,
                chave_acesso=chave_entregue
            )
        
        # 6. Finalizar transação e registrar no Supabase
        if sucesso_entrega:
            try:
                # Salva localmente
                cobranca.status = "delivered"
                db.session.add(cobranca)
                
                # Salva na tabela local (backup)
                nova_venda = Sale(
                    product_id=produto.id,
                    amount=cobranca.valor
                )
                db.session.add(nova_venda)
                db.session.commit()
                
                print(f"[WORKER] ✅ Venda salva no banco local.")
                
                # REGISTRA NO SUPABASE (para o dashboard)
                supabase_ok = registrar_venda_no_supabase(
                    product_id=produto.id,
                    customer_email=cobranca.cliente_email,
                    amount=cobranca.valor,
                    payment_id=payment_id
                )
                
                if supabase_ok:
                    print(f"[WORKER] ✅ SUCESSO TOTAL: Entrega + Dashboard atualizado!")
                else:
                    print(f"[WORKER] ⚠️ Entrega feita, mas dashboard NÃO atualizado.")
                
            except Exception as e:
                print(f"[WORKER] ERRO ao salvar: {e}")
                db.session.rollback()
        else:
            print(f"[WORKER] ERRO: Falha na entrega (email não enviado ou erro em moedas).")
            db.session.rollback()

# ============================================
# INICIALIZAÇÃO DO WORKER
# ============================================
if __name__ == "__main__":
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        raise ValueError("REDIS_URL não configurada.")
    
    # Conectar Redis
    try:
        redis_conn = redis.from_url(redis_url)
        redis_conn.ping()
        print("[WORKER] ✅ Redis conectado.")
    except Exception as e:
        print(f"[WORKER] ❌ Falha no Redis: {e}")
        exit(1)
    
    # Criar tabelas se necessário
    with app.app_context():
        db.create_all()
        print("[WORKER] ✅ Tabelas verificadas.")
    
    # Iniciar worker
    try:
        worker = Worker(["default"], connection=redis_conn)
        print("[WORKER] 🚀 Worker iniciado...")
        worker.work()
    except Exception as e:
        print(f"[WORKER] ❌ Erro fatal: {e}")
