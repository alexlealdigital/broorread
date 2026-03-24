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
            # Se a API do MP falhar, lançamos erro para o RQ tentar de novo depois
            raise RuntimeError(f"MP respondeu {resp['status']} para o ID {payment_id}")

        payment = resp["response"]
        
        if payment.get("status") != "approved":
            print(f"[WORKER] Pagamento {payment_id} não aprovado ({payment.get('status')}). Ignorando.")
            return

        # 3. Buscar Cobrança no DB (COM RETRY E MÚLTIPLAS ESTRATÉGIAS)
        print(f"[WORKER] Pagamento {payment_id} APROVADO. Buscando no DB...")
        
        cobranca = None
        tentativas = 0
        max_tentativas = 5
        
        while tentativas < max_tentativas and not cobranca:
            # Estratégia 1: Buscar por external_reference (modo ideal)
            cobranca = Cobranca.query.filter_by(external_reference=str(payment_id)).first()
            
            if not cobranca:
                # Estratégia 2: Buscar por ID direto (caso o payment_id seja o ID da cobrança)
                try:
                    cobranca = Cobranca.query.get(int(payment_id))
                except (ValueError, TypeError):
                    pass
            
            if not cobranca:
                # Estratégia 3: Buscar nos metadados do payment (external_reference vem do MP)
                external_ref = payment.get("external_reference")
                if external_ref and str(external_ref) != str(payment_id):
                    cobranca = Cobranca.query.filter_by(external_reference=str(external_ref)).first()
            
            if not cobranca and tentativas < max_tentativas - 1:
                print(f"[WORKER] Cobrança não encontrada, tentando novamente em 3s... (tentativa {tentativas + 1}/{max_tentativas})")
                import time
                time.sleep(3)
                # Força refresh da sessão do SQLAlchemy para pegar dados atualizados
                db.session.expire_all()
                tentativas += 1
            else:
                tentativas += 1

        if not cobranca:
            print(f"[WORKER] ERRO CRÍTICO: Cobranca {payment_id} aprovada, mas não encontrada no DB local.")
            # Log adicional para debug
            ultimas_cobrancas = Cobranca.query.order_by(Cobranca.data_criacao.desc()).limit(5).all()
            if ultimas_cobrancas:
                print(f"[WORKER] Últimas cobranças no DB: {[f'ID:{c.id}/ExtRef:{c.external_reference}' for c in ultimas_cobrancas]}")
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
            
            # Lock de linha para evitar venda duplicada (concorrência)
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
                # Para games, o link de download é o instalador geral
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
        
        # 6. Finalizar Transação
        if sucesso:
            try:
                cobranca.status = "delivered" 
                db.session.add(cobranca) 
                db.session.commit()
                print(f"[WORKER] Sucesso total. Cobranca {cobranca.id} finalizada.")
            except Exception as db_exc:
                print(f"[WORKER] ALERTA: E-mail enviado, mas falha ao salvar DB: {db_exc}")
                db.session.rollback() 
        else:
            print(f"[WORKER] Falha no envio de e-mail. Fazendo Rollback do DB.")
            db.session.rollback() 
            raise Exception(f"Falha no envio SMTP para {destinatario}")
