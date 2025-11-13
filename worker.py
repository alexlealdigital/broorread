#!/usr/bin/env python3
"""
Worker RQ – ARQUITETURA "PLANO A"
Ouve a fila por jobs (contendo o payment_id) enviados pelo webhook.
Se o pagamento estiver aprovado, busca os dados no DB e envia o produto correto.
"""

import os
import mercadopago
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import redis
from rq import Worker, Queue 
from datetime import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.ext.declarative import declarative_base

# --- CONFIGURAÇÃO DO FLASK / DB ---
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

# --- MODELOS DE DADOS (SINCRONIZADOS COM APP.PY) ---

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


# NOVO MODELO CHAVE_LICENCA
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

# Criação das tabelas
with app.app_context():
    db.create_all()


# ---------- FUNÇÃO DE ENVIO DE E-MAIL (CORRIGIDA) ----------

def enviar_email_confirmacao(destinatario, nome_cliente, valor, link_produto, cobranca, nome_produto, chave_acesso=None):
    """ Envia e-mail, usando SMTP_SSL para máxima compatibilidade. Suporta link (e-book) ou chave (game/app). """
    try:
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.zoho.com")
        smtp_port = int(os.environ.get("SMTP_PORT", 465))
        email_user = os.environ["EMAIL_USER"]
        email_pass = os.environ["EMAIL_PASSWORD"]
    except KeyError:
        print("[WORKER] ERRO: Credenciais de e-mail não configuradas.")
        return False
    
    # 1. Configuração do Assunto e Conteúdo Dinâmico
    if chave_acesso:
        assunto = f"R·READ: Sua chave de acesso para \"{nome_produto}\" chegou! 🚀"
        
        # Conteúdo para Game/App (Com bloco de chave serial)
        instrucoes_entrega = f"""
            <p>Agradecemos por escolher a <strong>R·READ</strong>! Seu pagamento de <strong>R$ {valor:.2f}</strong> referente ao produto "<strong>{nome_produto}</strong>" foi confirmado.</p>
            
            <h2 style="color: #27ae60;">Sua Chave de Acesso está aqui! 🔑</h2>
            
            <p>Sua chave de acesso (Serial Key) para o jogo/app é:</p>
            <div style="background-color: #e0f2f1; padding: 15px; border-radius: 8px; text-align: center; margin: 20px 0; border: 2px dashed #27ae60;">
                <code style="font-size: 1.5em; font-weight: bold; color: #14213d; display: block; word-break: break-all;">{chave_acesso}</code>
            </div>
            
            <p>Copie a chave acima e use-a no instalador. Se precisar baixar o instalador, clique abaixo:</p>
            
            <div class="button-container"> 
                <a href="{link_produto}" class="button" target="_blank" style="background-color: #27ae60;">[·] Baixar o Instalador</a>
            </div>
        """

    else:
        assunto = f"R·READ: Seu e-book \"{nome_produto}\" está pronto para devorar! 🎉"
        
        # Conteúdo para E-book (Com bloco de link de download)
        instrucoes_entrega = f"""
            <p>Agradecemos por escolher a <strong>R·READ</strong>! Seu pagamento de <strong>R$ {valor:.2f}</strong> referente ao e-book "<strong>{nome_produto}</strong>" foi confirmado.</p>
            
            <h2>Agora é hora de devorar o conteúdo!</h2>
            
            <p>Clique no nosso <span class="brand-dot">·</span> (micro-portal!) abaixo para acessar seu e-book:</p>
            
            <div class="button-container"> 
                <a href="{link_produto}" class="button" target="_blank">[·] Baixar Meu E-book Agora</a>
            </div>
        """
        
    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"] = email_user
    msg["To"] = destinatario
    
    # Bloco corpo_html (Usando o conteúdo dinâmico)
    corpo_html = f"""
<!doctype html>
<html>
<head>
  <meta charset="UTF-8">
  <style>
    body {{ font-family: 'Lato', Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f4f4f4; }}
    .email-wrapper {{ background-color: #f4f4f4; padding: 20px 0; }}
    .container {{ max-width: 600px; margin: 0 auto; background-color: #ffffff; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; }}
    .header {{ background-color: #14213d; padding: 20px; text-align: center; }}
    .header h1 {{ color: #ffffff; font-family: 'Poppins', sans-serif; font-size: 1.8em; margin: 0; }}
    .content {{ padding: 30px; }}
    h2 {{ color: #fca311; font-family: 'Poppins', sans-serif; font-size: 1.5em; margin: 25px 0 15px 0; text-align: center; }}
    p {{ margin-bottom: 15px; font-size: 1em; color: #555; }}
    strong {{ color: #14213d; }}
    .button-container {{ text-align: center; margin: 25px 0; }}
    /* ESTILOS PADRÃO DO BOTÃO (Laranja para E-book) */
    .button {{ 
        background-color: #fca311;
        color: #14213d !important;
        padding: 14px 28px; 
        text-decoration: none !important;
        border-radius: 25px; 
        font-weight: bold; 
        display: inline-block; 
        font-family: 'Poppins', sans-serif;
        font-size: 1.1em;
        border: none;
        cursor: pointer;
        text-align: center;
        transition: background-color 0.3s ease, transform 0.2s ease;
    }}
    .button:hover {{ background-color: #e0900b; transform: scale(1.03); }}
    .footer-text {{ font-size: 0.9em; color: #777; margin-top: 25px; border-top: 1px solid #e5e5e5; padding-top: 20px; text-align: center; }}
    .link-copy {{ word-break: break-all; font-family: monospace; font-size: 0.85em; background-color: #f0f0f0; padding: 5px; border-radius: 4px; display: block; margin-top: 5px; }}
    .brand-dot {{ color: #fca311; font-weight: bold; }}
    a {{ color: #fca311; text-decoration: underline; }}
  </style>
</head>
<body>
  <div class="email-wrapper">
    <div class="container">
      <div class="header">
        <h1>✅ Parabéns pela sua compra!</h1>
      </div>
      <div class="content">
        <p>Olá, {nome_cliente},</p>
        
        {instrucoes_entrega}
        
        <p style="font-size: 0.9em; color: #777; margin-top: 30px;">Se o link do botão não funcionar, copie e cole este link no seu navegador:</p>
        <code class="link-copy">{link_produto}</code>
        
        <div class="footer-text">
          Boas leituras / Bom jogo!<br>
          Equipe <strong>R·READ / B·ROO banca digital</strong>
          <br><br>
          Pedido ID: {cobranca.id} <br> 
          Lembre-se: nosso <span class="brand-dot">·</span> não é só um ponto, é uma experiência! A interação é o nosso DNA. <br>
          Em caso de dúvidas, responda a este e-mail.
        </div>
      </div>
    </div>
  </div>
</body>
</html>
"""
    msg.attach(MIMEText(corpo_html, "html"))
    
    try:
        with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=10) as server:
            server.login(email_user, email_pass)
            server.send_message(msg)
    except Exception as exc:
        print(f"[WORKER] Falha no envio SMTP: {exc}")
        return False
    
    print(f"[WORKER] E-mail DE ENTREGA enviado para {destinatario}")
    return True

# ---------- JOB DO "PLANO A" (ATUALIZADO) ----------
def process_mercado_pago_webhook(payment_id):
    """
    PLANO A: Recebe o payment_id do webhook, consulta o MP, 
    e se APROVADO, busca os dados REAIS no nosso DB para fazer a entrega (E-book ou Chave).
    """
    with app.app_context():
        access_token = os.environ.get("MERCADOPAGO_ACCESS_TOKEN")
        if not access_token:
             print("[WORKER] ERRO CRÍTICO: MERCADOPAGO_ACCESS_TOKEN não configurado.")
             return 

        sdk = mercadopago.SDK(access_token)
        
        try:
            resp = sdk.payment().get(payment_id)
        except Exception as e:
            print(f"[WORKER] Falha ao consultar MP para o ID {payment_id}: {e}")
            return 

        if resp["status"] != 200:
            print(f"[WORKER] MP respondeu {resp['status']} para o ID {payment_id}. Detalhes: {resp.get('response')}")
            raise RuntimeError(f"MP respondeu {resp['status']} para o ID {payment_id}")

        payment = resp["response"]
        
        if payment.get("status") != "approved":
            print(f"[WORKER] Pagamento {payment_id} não aprovado ({payment.get('status')}). Ignorando.")
            return

        print(f"[WORKER] Pagamento {payment_id} APROVADO. Buscando no DB...")
        cobranca = Cobranca.query.filter_by(external_reference=str(payment_id)).first()

        if not cobranca:
            print(f"[WORKER] ERRO CRÍTICO: Cobranca {payment_id} aprovada, mas não encontrada no DB.")
            return

        produto = cobranca.produto 
        
        if not produto:
            print(f"[WORKER] ERRO CRÍTICO: Produto não encontrado para a Cobranca ID {cobranca.id} (MP ID: {payment_id}).")
            return
            
        # --- LÓGICA DE ENTREGA DE PRODUTO/CHAVE ---
        link_entrega = produto.link_download
        chave_entregue = None
        
        if produto.tipo in ("game", "app"): # Verifica o novo campo 'tipo'
            print(f"[WORKER] Tipo de produto é '{produto.tipo}'. Buscando chave de licença...")

            # 1. Busca a primeira chave não vendida (usando with_for_update para lock)
            chave_obj = ChaveLicenca.query.filter(
              chave_obj = ChaveLicenca.query.filter(
	                ChaveLicenca.produto_id == produto.id,
	                ChaveLicenca.vendida == False
	            ).order_by(ChaveLicenca.id.asc()).with_for_update().first()

            if chave_obj:
                # 2. Marca a chave como vendida
                chave_obj.vendida = True
                chave_obj.vendida_em = datetime.utcnow()
                chave_obj.cobranca_id = cobranca.id
                chave_obj.cliente_email = cobranca.cliente_email
                chave_entregue = chave_obj.chave_serial
                link_entrega = produto.link_download # O link_download passa a ser o link do instalador
                print(f"[WORKER] CHAVE encontrada e marcada como vendida: {chave_entregue}")
                
                # --- NOVO: Adicionar à sessão explicitamente para garantir rastreamento ---
                db.session.add(chave_obj) 
                # --------------------------------------------------------------------------

            else:
                # 3. ERRO: Não há chaves disponíveis! O job será re-tentado.
                print(f"[WORKER] ERRO CRÍTICO: Produto '{produto.nome}' esgotou as chaves de licença.")
                db.session.rollback() 
                raise Exception(f"FALHA DE ESTOQUE: Chaves esgotadas para o produto {produto.id}")
        
        # Dados reais do banco
        destinatario = cobranca.cliente_email
        nome_cliente = cobranca.cliente_nome
        valor_real = cobranca.valor
        nome_produto = produto.nome

        print(f"[WORKER] Enviando produto '{nome_produto}' (Tipo: {produto.tipo}) para {destinatario}...")

        # Chama a função de envio, passando a chave se houver
        sucesso = enviar_email_confirmacao(
            destinatario=destinatario,
            nome_cliente=nome_cliente,
            valor=valor_real,
            link_produto=link_entrega,
            cobranca=cobranca, 
            nome_produto=nome_produto,
            chave_acesso=chave_entregue # Novo parâmetro
        )
        
        if sucesso:
            print(f"[WORKER] E-mail (Plano A) enviado com sucesso para {destinatario}.")
            try:
                cobranca.status = "delivered" 
                db.session.add(cobranca) # Adicionar explicitamente
                db.session.commit() # Commit final para Cobrança e, se for o caso, a Chave Licença
                print(f"[WORKER] Status da Cobranca {cobranca.id} atualizado para 'delivered'.")
            except Exception as db_exc:
                 print(f"[WORKER] ALERTA: Falha ao atualizar status da Cobranca {cobranca.id} para 'delivered': {db_exc}")
                 db.session.rollback() 
        else:
            print(f"[WORKER] Falha no envio de e-mail (Plano A) para {destinatario}. O job será re-tentado pelo RQ.")
            # Se o e-mail falhou, DESFAZ A MARCAÇÃO DA CHAVE.
            db.session.rollback() 
            raise Exception(f"Falha no envio SMTP para {destinatario}")

# ---------- INICIALIZAÇÃO DO WORKER ----------
if __name__ == "__main__":
    redis_url = os.environ.get("REDIS_URL") 
    if not redis_url:
        raise ValueError("Variável de ambiente REDIS_URL não configurada.")

    redis_conn = redis.from_url(redis_url)

    # Verifica conexão com Redis antes de iniciar
    try:
        redis_conn.ping()
        print("[WORKER] Conexão com Redis OK.")
    except redis.exceptions.ConnectionError as redis_err:
        print(f"[WORKER] ERRO CRÍTICO: Não foi possível conectar ao Redis em {redis_url}. Erro: {redis_err}")
        exit(1) 

    # Verifica conexão com DB antes de iniciar
    try:
        with app.app_context():
             db.session.execute(db.text('SELECT 1'))
        print("[WORKER] Conexão com Banco de Dados OK.")
    except Exception as db_init_err:
         print(f"[WORKER] ERRO CRÍTICO: Não foi possível conectar ao Banco de Dados. Verifique DATABASE_URL. Erro: {db_init_err}")
         exit(1) 

    # Cria tabelas (agora que sabemos que o DB conecta)
    with app.app_context():
        try:
            db.create_all()
            print("[WORKER] Tabelas verificadas/criadas no DB.")
        except Exception as create_err:
             print(f"[WORKER] ALERTA: Erro ao executar db.create_all(): {create_err}")

    # Inicia o worker
    worker_queues = ["default"]
    worker = Worker(worker_queues, connection=redis_conn)
    print(f"[WORKER] Worker iniciado – aguardando jobs nas filas: {', '.join(worker_queues)}...")
    
    worker.work()
