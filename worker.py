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
from datetime import datetime, timedelta
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
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 300, "connect_args": {"prepare_threshold": None}}

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
    observacoes = db.Column(db.Text, nullable=True)  # JSON com endereco/frete do pedido fisico
    produto = db.relationship('Produto')
    chave_usada = db.relationship('ChaveLicenca', backref='cobranca_rel', uselist=False)

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
    produto = db.relationship('Produto', backref=db.backref('chaves', lazy=True))
    vendida = db.Column(db.Boolean, default=False, nullable=False)
    vendida_em = db.Column(db.DateTime, nullable=True)
    cobranca_id = db.Column(db.Integer, db.ForeignKey('cobrancas.id'), unique=True, nullable=True)
    cliente_email = db.Column(db.String(200), nullable=True)

# REMOVIDO: supabase_synced - essa coluna não existe no banco local
class Sale(db.Model):
    __tablename__ = "sales"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('produtos.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

# ============================================
# ASSINATURA / LICENÇA (BrooStock)
# Tabelas NOVAS — criadas pelo db.create_all() no deploy, sem ALTER.
# ============================================
class PlanoAssinatura(db.Model):
    __tablename__ = "planos_assinatura"
    produto_id = db.Column(db.Integer, db.ForeignKey('produtos.id'), primary_key=True)
    dias = db.Column(db.Integer, nullable=False)            # 30, 365...
    rotulo = db.Column(db.String(50), nullable=True)        # 'mensal' / 'anual'

class Licenca(db.Model):
    __tablename__ = "licencas"
    id = db.Column(db.Integer, primary_key=True)
    cliente_email = db.Column(db.String(200), nullable=False, index=True)
    plano = db.Column(db.String(50), nullable=True)         # 'mensal' / 'anual'
    status = db.Column(db.String(30), default="ativa", nullable=False)
    inicia_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expira_em = db.Column(db.DateTime, nullable=False)
    ultimo_pagamento_em = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    cobranca_id = db.Column(db.Integer, db.ForeignKey('cobrancas.id'), nullable=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('produtos.id'), nullable=True)

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
        
        # Verifica se payment_id já existe antes de inserir (proteção anti-duplicata)
        check_url = f"{SUPABASE_URL}/rest/v1/sales?payment_id=eq.{payment_id}&select=id"
        check_resp = requests.get(check_url, headers=headers, timeout=10)
        if check_resp.status_code == 200 and check_resp.json():
            print(f"[WORKER] ⚠️ Venda {payment_id} já registrada no Supabase. Ignorando duplicata.")
            return True

        payload = {
            "product_id": int(product_id),
            "customer_email": str(customer_email),
            "amount": float(amount),
            "payment_id": str(payment_id),
            "status": "paid"
        }
        
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
def enviar_email_produto_fisico(destinatario, nome_cliente, valor, nome_produto, cobranca):
    """Envia email de confirmação de pedido para produto físico."""
    try:
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.zoho.com")
        email_user  = os.environ["EMAIL_USER"]
        email_pass  = os.environ["EMAIL_PASSWORD"]
    except KeyError:
        print("[WORKER] ERRO: Credenciais de email não configuradas.")
        return False

    assunto = f'BrooStore: Pedido "{nome_produto}" confirmado! 📦'

    # Tenta recuperar endereço do campo observacoes ou metadados da cobrança
    endereco_html = ""
    try:
        import json as _json
        meta = _json.loads(cobranca.observacoes or "{}")
        end = meta.get("endereco", {})
        if end:
            endereco_html = f"""
            <div style="background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:15px;margin:20px 0;">
                <h3 style="margin:0 0 10px;color:#374151;">📍 Endereço de Entrega</h3>
                <p style="margin:3px 0;color:#374151;">{end.get('rua','')} {end.get('numero','')}{', '+end.get('complemento','') if end.get('complemento') else ''}</p>
                <p style="margin:3px 0;color:#374151;">{end.get('bairro','')} — {end.get('cidade','')} / {end.get('estado','')}</p>
                <p style="margin:3px 0;color:#374151;">CEP: {end.get('cep','')}</p>
            </div>"""
    except Exception:
        pass

    instrucoes = f"""
        <p>Agradecemos por escolher a <strong>BrooStore</strong>! Seu pagamento de <strong>R$ {valor:.2f}</strong> foi confirmado.</p>
        <h2 style="color:#27ae60;">Pedido recebido com sucesso! 🎉</h2>
        <p>Seu pedido de <strong>{nome_produto}</strong> foi confirmado e está sendo preparado.</p>
        {endereco_html}
        <div style="background:#fef3c7;border:1px solid #f59e0b;border-radius:8px;padding:15px;margin:20px 0;">
            <p style="margin:0;color:#92400e;"><strong>⏱️ Próximos passos:</strong><br>
            Entraremos em contato em breve para confirmar os detalhes do envio e o prazo de entrega.</p>
        </div>
        <p style="color:#6b7280;font-size:0.9em;">Em caso de dúvidas, responda este e-mail.</p>
    """

    corpo_html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><style>
body{{font-family:Arial,sans-serif;line-height:1.6;color:#333;margin:0;padding:0;background:#f4f4f4;}}
.container{{max-width:600px;margin:20px auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,.1);}}
.header{{background:#3B82F6;padding:30px;text-align:center;color:white;}}
.content{{padding:30px;}}
.footer{{background:#f9fafb;padding:20px;text-align:center;font-size:.9em;color:#6b7280;border-top:1px solid #e5e7eb;}}
</style></head><body>
<div class="container">
  <div class="header"><h1>✅ Parabéns pela sua compra!</h1></div>
  <div class="content">
    <p>Olá, {nome_cliente},</p>
    {instrucoes}
  </div>
  <div class="footer">
    <strong>BrooStore</strong><br>
    Pedido ID: {cobranca.id}<br>
    Em caso de dúvidas, responda este e-mail.
  </div>
</div>
</body></html>"""

    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText
        msg = MIMEMultipart("alternative")
        msg["Subject"] = assunto
        msg["From"]    = email_user
        msg["To"]      = destinatario
        msg.attach(MIMEText(corpo_html, "html"))
        smtp_port = int(os.environ.get("SMTP_PORT", 587))
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10) as server:
                server.login(email_user, email_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(email_user, email_pass)
                server.send_message(msg)
        print(f"[WORKER] Email físico enviado para {destinatario}")
        return True
    except Exception as e:
        print(f"[WORKER] Erro ao enviar email físico: {e}")
        return False


def enviar_email_confirmacao(destinatario, nome_cliente, valor, link_produto, cobranca, nome_produto, chave_acesso=None):
    """Envia email de entrega do produto."""
    try:
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.zoho.com")
        email_user = os.environ["EMAIL_USER"]
        email_pass = os.environ["EMAIL_PASSWORD"]
    except KeyError:
        print("[WORKER] ERRO: Credenciais de email não configuradas.")
        return False
    
    if chave_acesso and nome_produto == "Compressão de PDF":
        assunto = f"BrooStore: Seu código de compressão de PDF chegou! 🗜️"
        instrucoes_entrega = f"""
            <p>Agradecemos por escolher a <strong>BrooStore</strong>! Seu pagamento de <strong>R$ {valor:.2f}</strong> foi confirmado.</p>
            <h2 style="color: #fca311;">Seu código de liberação está aqui! 🔑</h2>
            <p>Cole este código na página de compressão para baixar seu PDF reduzido:</p>
            <div style="background-color: #1a1400; padding: 15px; border-radius: 8px; text-align: center; margin: 20px 0; border: 2px dashed #fca311;">
                <code style="font-size: 1.1em; font-weight: bold; color: #fca311; display: block; word-break: break-all;">{chave_acesso}</code>
            </div>
            <div style="text-align: center; margin: 25px 0;">
                <a href="https://mercadopago-final.onrender.com/comprimir-pdf.html" style="background-color: #fca311; color: #000; padding: 14px 28px; text-decoration: none; border-radius: 25px; font-weight: bold;">[·] Ir para o Compressor</a>
            </div>
            <p style="font-size:0.85em; color:#888;">Este código é de uso único e válido por 24 horas.</p>
        """
    elif chave_acesso:
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

# ============================================
# E-MAIL DE CONFIRMAÇÃO DE LICENÇA (ASSINATURA)
# ============================================
def enviar_email_licenca(destinatario, nome_cliente, rotulo_plano, expira_em):
    """Envia e-mail confirmando a ativação/renovação da licença do BrooStock."""
    try:
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.zoho.com")
        email_user = os.environ["EMAIL_USER"]
        email_pass = os.environ["EMAIL_PASSWORD"]
    except KeyError:
        print("[WORKER] ERRO: Credenciais de email não configuradas.")
        return False

    validade_str = expira_em.strftime("%d/%m/%Y")
    plano_str = (rotulo_plano or "assinatura").capitalize()
    assunto = "BrooStock: Sua licença está ativa! 🚀"
    corpo_html = f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;background:#0d1b2a;color:#e0e6ed;padding:24px;">
  <div style="max-width:560px;margin:0 auto;background:#14213d;border-radius:12px;padding:28px;">
    <h2 style="color:#48cae4;margin-top:0;">Licença BrooStock ativada ✅</h2>
    <p>Olá, {nome_cliente or 'cliente'}!</p>
    <p>Recebemos seu pagamento e sua licença do <strong>BrooStock</strong> já está ativa.</p>
    <div style="background:#0d1b2a;border:1px solid #2a3b55;border-radius:8px;padding:16px;margin:16px 0;">
      <p style="margin:4px 0;">Plano: <strong>{plano_str}</strong></p>
      <p style="margin:4px 0;">Válida até: <strong>{validade_str}</strong></p>
    </div>
    <p>Acesse o BrooStock com o <strong>mesmo e-mail desta compra</strong> ({destinatario}) para usar a ferramenta liberada.</p>
    <p style="font-size:0.85em;color:#9fb0c3;">Quando a licença estiver perto de expirar, avisaremos por e-mail para você renovar.</p>
  </div>
</body></html>"""

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
        print(f"[WORKER] Email de licença enviado para {destinatario}")
        return True
    except Exception as exc:
        print(f"[WORKER] Falha no envio SMTP (licença): {exc}")
        return False


def ativar_ou_renovar_licenca(produto, cobranca):
    """Cria ou estende a licença do cliente (renovação manual).
    Retorna (licenca, rotulo_plano) ou (None, None) se não houver plano configurado."""
    plano = db.session.get(PlanoAssinatura, produto.id)
    if not plano:
        print(f"[WORKER] ERRO: produto {produto.id} é 'assinatura' mas não tem plano em planos_assinatura.")
        return None, None

    email = (cobranca.cliente_email or "").strip().lower()
    agora = datetime.utcnow()

    licenca = (Licenca.query
               .filter_by(cliente_email=email)
               .order_by(Licenca.id.desc())
               .first())

    # Renovação: se ainda está válida, soma a partir da data de expiração;
    # caso contrário, conta a partir de agora.
    base = licenca.expira_em if (licenca and licenca.expira_em and licenca.expira_em > agora) else agora
    nova_expira = base + timedelta(days=plano.dias)

    if licenca:
        licenca.plano = plano.rotulo
        licenca.status = "ativa"
        licenca.expira_em = nova_expira
        licenca.ultimo_pagamento_em = agora
        licenca.cobranca_id = cobranca.id
        licenca.produto_id = produto.id
    else:
        licenca = Licenca(
            cliente_email=email,
            plano=plano.rotulo,
            status="ativa",
            inicia_em=agora,
            expira_em=nova_expira,
            ultimo_pagamento_em=agora,
            cobranca_id=cobranca.id,
            produto_id=produto.id,
        )
        db.session.add(licenca)

    db.session.flush()
    print(f"[WORKER] Licença {plano.rotulo} de {email} válida até {nova_expira.date()}")
    return licenca, plano.rotulo


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
        
        print(f"[WORKER] Processando pagamento {payment_id} | ExtRef: {external_ref}")
        
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
        
        # 5. Gerenciar estoque
        link_entrega = produto.link_download
        chave_entregue = None
        licenca_ativa = None
        rotulo_plano = None

        # Produto 99 = Compressão de PDF: envia o external_reference como código de liberação
        if produto.id == 99:
            chave_entregue = cobranca.external_reference
            print(f"[WORKER] Produto PDF Compressão — enviando código: {chave_entregue}")

        elif produto.tipo == "assinatura":
            print(f"[WORKER] Ativando/renovando licença para {produto.nome}...")
            licenca_ativa, rotulo_plano = ativar_ou_renovar_licenca(produto, cobranca)
            if not licenca_ativa:
                db.session.rollback()
                raise Exception(f"Plano de assinatura não configurado para produto {produto.id}")

        elif produto.tipo in ["game", "app"]:
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
        
        # 6. Enviar email
        # Produto físico: envia confirmação de pedido com endereço (sem link de download)
        tipo_produto = getattr(produto, 'tipo', 'digital') or 'digital'

        if tipo_produto == 'fisico':
            sucesso = enviar_email_produto_fisico(
                destinatario=cobranca.cliente_email,
                nome_cliente=cobranca.cliente_nome,
                valor=cobranca.valor,
                nome_produto=produto.nome,
                cobranca=cobranca,
            )
        elif tipo_produto == 'assinatura':
            sucesso = enviar_email_licenca(
                destinatario=cobranca.cliente_email,
                nome_cliente=cobranca.cliente_nome,
                rotulo_plano=rotulo_plano,
                expira_em=licenca_ativa.expira_em,
            )
        else:
            sucesso = enviar_email_confirmacao(
                destinatario=cobranca.cliente_email,
                nome_cliente=cobranca.cliente_nome,
                valor=cobranca.valor,
                link_produto=link_entrega,
                cobranca=cobranca,
                nome_produto=produto.nome,
                chave_acesso=chave_entregue
            )
        
        # 7. Finalizar transação e registrar no Supabase
        if sucesso:
            # 7a. PRIMEIRO commit o essencial: cobrança entregue + licença
            #     (a licença já foi adicionada/flushada na ativação). Isso NÃO
            #     pode depender do registro de venda.
            try:
                cobranca.status = "delivered"
                db.session.add(cobranca)
                db.session.commit()
                print(f"[WORKER] ✅ Cobrança/licença salvas.")
            except Exception as e:
                print(f"[WORKER] ERRO ao salvar cobrança/licença: {e}")
                db.session.rollback()
                return

            # 7b. Registro de venda — best-effort, NÃO derruba a licença.
            #     Assinatura: os planos vivem em 'produtos', não em 'products'
            #     (a FK de 'sales' aponta para 'products'), então pulamos.
            if produto.tipo == "assinatura":
                print(f"[WORKER] (assinatura) registro em 'sales' ignorado.")
            else:
                try:
                    db.session.add(Sale(product_id=produto.id, amount=cobranca.valor))
                    db.session.commit()
                    print(f"[WORKER] ✅ Venda salva no banco local.")
                except Exception as e:
                    print(f"[WORKER] ⚠️ Não foi possível salvar em 'sales': {e}")
                    db.session.rollback()

                supabase_ok = registrar_venda_no_supabase(
                    product_id=produto.id,
                    customer_email=cobranca.cliente_email,
                    amount=cobranca.valor,
                    payment_id=payment_id
                )
                if supabase_ok:
                    print(f"[WORKER] ✅ Dashboard atualizado!")
                else:
                    print(f"[WORKER] ⚠️ Dashboard NÃO atualizado.")
        else:
            print(f"[WORKER] ERRO: Falha no envio de email.")
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
