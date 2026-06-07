# seed_chave_broostock.py
# ---------------------------------------------------------------------------
# Cria o produto "Chave BrooStock" (tipo "app") e gera chaves de licença.
#
# Onde rodar: no painel do Render do serviço broorread, aba "Shell":
#     python seed_chave_broostock.py
# (ou como One-Off Job, com o mesmo comando)
#
# Usa a conexão de banco que o próprio backend já tem (DATABASE_URL),
# então NÃO precisa descobrir host/senha do banco. Pode apagar este
# arquivo depois de rodar uma vez.
# ---------------------------------------------------------------------------

import uuid
from app import app, db, Produto, ChaveLicenca

NOME  = "Chave BrooStock — Licença de Uso"
PRECO = 99.90        # ajuste o preço (tem que bater com o front)
QTD   = 50           # quantas chaves gerar agora


def gerar_serial():
    h = uuid.uuid4().hex.upper()
    return f"BROO-{h[0:4]}-{h[4:8]}-{h[8:12]}"


with app.app_context():
    # 1) Produto. tipo="app" faz o worker reservar uma chave e enviar por e-mail.
    produto = Produto(nome=NOME, preco=PRECO, link_download="", tipo="app")
    db.session.add(produto)
    db.session.flush()  # garante que produto.id já exista

    # 2) Estoque inicial de chaves (formato BROO-XXXX-XXXX-XXXX)
    for _ in range(QTD):
        db.session.add(ChaveLicenca(
            chave_serial=gerar_serial(),
            produto_id=produto.id,
            vendida=False,
            ativa_no_app=False,
        ))

    db.session.commit()

    disponiveis = ChaveLicenca.query.filter_by(
        produto_id=produto.id, vendida=False
    ).count()

    print("====================================================")
    print(f"  Produto criado: id = {produto.id}")
    print(f"  Preco: R$ {PRECO:.2f}")
    print(f"  Chaves disponiveis: {disponiveis}")
    print(f"  >>> Coloque {produto.id} em BROOSTOCK_LICENSE_PRODUCT_ID (broostore.ts)")
    print("====================================================")
