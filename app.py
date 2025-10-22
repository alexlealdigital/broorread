@app.route("/api/cobrancas", methods=["POST"])
def create_cobranca():
    """Cria uma nova cobrança PIX no MP e salva o registro no DB."""
    
    # IMPORTANTE: Desativa o gerenciamento automático do Flask-SQLAlchemy para esta transação
    db.session.autoflush = False
    db.session.autocommit = False
    
    try:
        dados = request.get_json()
        print(f"Dados recebidos: {dados}")
        
        # --- (Resto das validações e criação do payment_response - MANTIDO) ---
        
        access_token = os.environ.get("MERCADOPAGO_ACCESS_TOKEN")
        # ... (SDK e pagamento)
        
        # Simulação do payment_response (já que o código completo não está aqui)
        # Substitua este bloco com sua lógica completa de MP
        payment_response = sdk.payment().create(payment_data) 
        
        if payment_response["status"] != 201:
            # ... (Tratamento de erro do Mercado Pago) ...
            
        payment = payment_response["response"]
        qr_code_base64 = payment["point_of_interaction"]["transaction_data"]["qr_code_base64"]
        qr_code_text = payment["point_of_interaction"]["transaction_data"]["qr_code"]
        
        # ---------- CRIAÇÃO E PERSISTÊNCIA NO DB ----------
        nova_cobranca = Cobranca(
            external_reference=str(payment["id"]),
            cliente_nome=dados.get("nome"),
            cliente_email=dados.get("email"),
            valor=float(dados.get("valor", 1.00)),
            status=payment["status"]
        )
        
        # Serialização ANTES do commit, para retorno seguro
        cobranca_dict = nova_cobranca.to_dict() 
        
        # 1. ESCRITA MANUAL NA SESSÃO
        db.session.add(nova_cobranca)
        db.session.commit()
        
        # 2. LIBERAÇÃO MÁXIMA
        db.session.expire_all()
        db.session.remove() # Força a desconexão do pool
        
        print(f"Cobrança {payment['id']} SALVA COM SUCESSO e liberada para o Worker.")
        
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
