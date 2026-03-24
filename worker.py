#!/usr/bin/env python3
"""
Worker RQ – ARQUITETURA "PLANO A"
Ouve a fila por jobs (contendo o payment_id) enviados pelo webhook.
Se o pagamento estiver aprovado, busca os dados no DB, envia o produto e REGISTRA A VENDA para o dashboard.
"""

import os
import mercadopago
import smtplib
import redis
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from rq import Worker, Queue 
from datetime import datetime
from flask import Flask
from flask_sqlalchemy import SQLAlchemy

# --- CONFIGURAÇÃO DO FLASK / DB ---
app = Flask(__name__)

db_url = os.environ.get("DATABASE_URL", "sqlite:///cobrancas.db")
# Ajuste para compatibilidade com SQLAlchemy versões recentes e Postgres
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
    # Assumindo que produtos têm author_id para vincular ao vendedor/autor
    author_id = db.Column(db.String(100), nullable=True)  # UUID do autor no Supabase

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

# NOVO MODELO: Registro de vendas para o dashboard dos autores
class Sale(db.Model):
    __tablename__ = "sales"
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('produtos.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)  # Valor bruto da venda
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Opcional: vincular ao autor diretamente para consultas mais rápidas
    author_id = db.Column(db.String(100), nullable=True)

# --- FUNÇÃO DE ENVIO DE E-MAIL ---

def enviar_email_confirmacao(destinatario, nome_cliente, valor, link_produto, cobranca, nome_produto, chave_acesso=None):
    """ Envia e-mail, usando SMTP_SSL/TLS. Suporta link (e-book) ou chave (game/app). """
    try:
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.zoho.com")
        email_user = os.environ["EMAIL_USER"]
        email_pass = os.environ["EMAIL_PASSWORD"]
    except KeyError:
        print("[WORKER] ERRO: Credenciais de e-mail não configuradas.")
        return False
    
    # Configuração do Assunto e Conteúdo Dinâmico
    if chave_acesso:
        assunto = f"BrooStore: Sua chave de acesso para \"{nome_produto}\" chegou! 🚀"
        instrucoes_entrega = f"""
            <p>Agradecemos por escolher a <strong>BrooStore</strong>! Seu pagamento de <strong>R$ {valor:.2f}</strong> referente ao produto "<strong>{nome_produto}</strong>" foi confirmado.</p>
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
        assunto = f"BrooStore: Seu e-book \"{nome_produto}\" está pronto para devorar! 🎉"
        instrucoes_entrega = f"""
            <p>Agradecemos por escolher a <strong>BrooStore</strong>! Seu pagamento de <strong>R$ {valor:.2f}</strong> referente ao e-book "<strong>{nome_produto}</strong>" foi confirmado.</p>
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
    .button {{ 
        background-color: #fca311; color: #14213d !important; padding: 14px 28px; 
        text-decoration: none !important; border-radius: 25px; font-weight: bold; 
        display: inline-block; font-family: 'Poppins', sans-serif; font-size: 1.1em;
        border: none; cursor: pointer; text-align: center;
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
      <div class="header"><h1>✅ Parabéns pela sua compra!</h1></div>
      <div class="content">
        <p>Olá, {nome_cliente},</p>
        {instrucoes_entrega}
        <p style="font-size: 0.9em; color: #777; margin-top: 30px;">Se o link do botão não funcionar, copie e cole este link no seu navegador:</p>
        <code class="link-copy">{link_produto}</code>
        <div class="footer-text">
          Boas leituras / Bom jogo!<br>Equipe <strong>BrooStore / B·ROO banca digital</strong>
          <br><br>Pedido ID: {cobranca.id} <br> 
          Lembre-se: nosso <span class="brand-dot">·</span> não é só um ponto, é uma experiência! <br>
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
        smtp_port = int(os.environ.get("SMTP_PORT", 587))
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(email_user, email_pass)
            server.send_message(msg)
    except Exception as exc:
        print(f"[WORKER] Falha no envio SMTP: {exc}")
        return False
        
    print(f"[WORKER] E-mail DE ENTREGA enviado para {destinatario}")
    return True

# --- JOB DO "PLANO A" ---

def process_mercado_pago_webhook(payment_id):
    """
    Recebe o payment_id do webhook, consulta o MP, 
    e se APROVADO, busca os dados REAIS no nosso DB para fazer a entrega.
    """
    # 1. Obter Contexto do App
    with app.app_context():
        access_token = os.environ.get("MERCADOPAGO_ACCESS_TOKEN")
        if not access_token:
            print("[WORKER] ERRO CRÍTICO: MERCADOPAGO_ACCESS_TOKEN não configurado.")
            return 

        sdk = mercadopago.SDK(access_token)
        
        # 2. Consultar Mercado Pago
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

        # 3. Buscar Cobrança no DB pelo EXTERNAL_REFERENCE
        external_ref = payment.get("external_reference")
        
        if not external_ref:
            print(f"[WORKER] ERRO CRÍTICO: Pagamento {payment_id} não tem external_reference.")
            return
            
        print(f"[WORKER] Pagamento {payment_id} APROVADO. Buscando external_reference: {external_ref}")
        
        cobranca = Cobranca.query.filter_by(external_reference=str(external_ref)).first()

        if not cobranca:
            print(f"[WORKER] ERRO CRÍTICO: Cobranca com external_reference {external_ref} não encontrada no DB.")
            ultimas = Cobranca.query.order_by(Cobranca.data_criacao.desc()).limit(3).all()
            for c in ultimas:
                print(f"[WORKER] DB Check: ID={c.id}, ExtRef={c.external_reference}, Status={c.status}")
            return

        # Verifica se já não foi processada (evita duplicatas)
        if cobranca.status == "delivered":
            print(f"[WORKER] Cobrança {cobranca.id} já foi entregue anteriormente. Ignorando.")
            return

        produto = cobranca.produto 
        if not produto:
            print(f"[WORKER] ERRO CRÍTICO: Produto não encontrado para a Cobranca ID {cobranca.id}.")
            return

        # 4. Lógica de Estoque (Chaves) vs Link Simples
        link_entrega = produto.link_download
        chave_entregue = None

        if produto.tipo in ["game", "app"] or produto.nome == "8 PERSONAGENS do Game Chinelo Voador":
            print(f"[WORKER] Produto '{produto.tipo}'. Buscando chave de licença...")
            
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
                link_entrega = produto.link_download 
                
                print(f"[WORKER] CHAVE reservada: {chave_entregue}")
                db.session.add(chave_obj) 
            else:
                print(f"[WORKER] ERRO CRÍTICO: Estoque esgotado para o produto {produto.nome}.")
                db.session.rollback() 
                raise Exception(f"FALHA DE ESTOQUE: Sem chaves para produto ID {produto.id}")
        
        # 5. Enviar E-mail
        destinatario = cobranca.cliente_email
        print(f"[WORKER] Enviando produto '{produto.nome}' para {destinatario}...")

        sucesso = enviar_email_confirmacao(
            destinatario=destinatario,
            nome_cliente=cobranca.cliente_nome,
            valor=cobranca.valor,
            link_produto=link_entrega,
            cobranca=cobranca, 
            nome_produto=produto.nome,
            chave_acesso=chave_entregue
        )
        
        # 6. Finalizar Transação e REGISTRAR VENDA NO DASHBOARD
        if sucesso:
            try:
                # Atualiza status da cobrança
                cobranca.status = "delivered" 
                db.session.add(cobranca)
                
                # NOVO: Registra a venda na tabela sales para o dashboard do autor
                nova_venda = Sale(
                    product_id=produto.id,
                    amount=cobranca.valor,  # Valor bruto da venda
                    author_id=produto.author_id  # Vincula ao autor do produto
                )
                db.session.add(nova_venda)
                print(f"[WORKER] VENDA REGISTRADA: Produto {produto.id}, Autor {produto.author_id}, Valor {cobranca.valor}")
                
                db.session.commit()
                print(f"[WORKER] Sucesso total. Cobranca {cobranca.id} finalizada e venda computada no dashboard.")
            except Exception as db_exc:
                print(f"[WORKER] ALERTA: E-mail enviado, mas falha ao salvar DB: {db_exc}")
                db.session.rollback() 
        else:
            print(f"[WORKER] Falha no envio de e-mail. Fazendo Rollback do DB.")
            db.session.rollback() 
            raise Exception(f"Falha no envio SMTP para {destinatario}")

# ---------- INICIALIZAÇÃO DO WORKER ----------
if __name__ == "__main__":
    redis_url = os.environ.get("REDIS_URL") 
    if not redis_url:
        raise ValueError("Variável de ambiente REDIS_URL não configurada.")

    # Conexão Redis
    try:
        redis_conn = redis.from_url(redis_url)
        redis_conn.ping()
        print("[WORKER] Conexão com Redis OK.")
    except Exception as redis_err:
        print(f"[WORKER] ERRO CRÍTICO: Falha ao conectar no Redis: {redis_err}")
        exit(1) 

    # Conexão DB e Criação de Tabelas
    try:
        with app.app_context():
            db.create_all()
            print("[WORKER] Tabelas do banco de dados verificadas (incluindo 'sales').")
    except Exception as db_err:
        print(f"[WORKER] ALERTA: Erro ao conectar/criar tabelas no DB: {db_err}")

    # Iniciar Worker
    worker_queues = ["default"]
    try:
        worker = Worker(worker_queues, connection=redis_conn)
        print(f"[WORKER] Monitorando filas: {', '.join(worker_queues)}...")
        worker.work()
    except Exception as e:
        print(f"[WORKER] Ocorreu um erro na execução do worker: {e}")
