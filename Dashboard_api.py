# -*- coding: utf-8 -*-
"""
dashboard_api.py
================
Blueprint Flask AUTOSUFICIENTE para a Central Financeira da BrooStore.

Por que um arquivo separado?
  - Mantém o app.py intocado (apenas 2 linhas de registro + 1 origem no CORS).
  - Tem a própria conexão com o banco (não importa nada do app.py -> sem
    risco de import circular).
  - Somente LEITURA. Não cria tabelas, não altera dados.

Segurança:
  - Todo acesso exige o header  X-Admin-Token  igual à variável de ambiente
    ADMIN_TOKEN (comparação em tempo constante).
  - CORS liberado apenas para a origem do dashboard (env DASHBOARD_ORIGIN).

Endpoint:
  GET /api/admin/dashboard?periodo=7d|30d|90d|todos
"""

import os
import json
import hmac
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import create_engine, text

# ----------------------------------------------------------------------
# Configuração
# ----------------------------------------------------------------------
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
# O CORS (origem do painel + header X-Admin-Token) é configurado no app.py.

# Status que contam como venda paga (faturamento real).
STATUS_PAGOS = ("approved", "delivered")

# Normaliza a URL do banco igual ao app.py (psycopg3 + pooler do Supabase).
def _db_url():
    url = os.environ.get("DATABASE_URL", "sqlite:///cobrancas.db")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url

# Engine lazy (criado na primeira requisição, reaproveitado depois).
_engine = None
def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            _db_url(),
            pool_pre_ping=True,
            pool_recycle=3600,
            connect_args={"prepare_threshold": None},
        )
    return _engine


dashboard_bp = Blueprint("dashboard_admin", __name__)


# ----------------------------------------------------------------------
# Autenticação
# ----------------------------------------------------------------------
# Obs.: o CORS é tratado pelo flask-cors no app.py (origem do painel +
# header X-Admin-Token liberados lá). Não duplicamos headers aqui.
def _token_ok():
    enviado = request.headers.get("X-Admin-Token", "")
    if not ADMIN_TOKEN or not enviado:
        return False
    # Comparação em tempo constante (evita ataque de timing).
    return hmac.compare_digest(enviado, ADMIN_TOKEN)


# ----------------------------------------------------------------------
# Helpers de cálculo
# ----------------------------------------------------------------------
def _categoria(tipo):
    """
    Classifica o produto numa das 3 categorias de comissão da BrooStore.
    Ajuste aqui se surgirem novos 'tipo' no catálogo.
      - fisico                       -> produtos físicos
      - game / app                   -> jogos e aplicativos
      - ebook / digital / assinatura -> produtos digitais (default)
    """
    t = (tipo or "").strip().lower()
    if t == "fisico":
        return "fisico"
    if t in ("game", "app", "jogo", "aplicativo"):
        return "jogos_apps"
    return "digital"


def _parse_obs(raw):
    """Lê o JSON da coluna observacoes com segurança. Retorna dict."""
    if not raw:
        return {}
    try:
        return json.loads(raw) if isinstance(raw, str) else dict(raw)
    except Exception:
        return {}


def _split_valores(row):
    """
    Decompõe o valor de uma cobrança em (subtotal_produto, frete).
    - 'frete' e 'subtotal_produto' vêm de observacoes quando existirem.
    - Pedidos antigos/digitais podem não ter: usa fallback seguro.
    """
    valor = float(row["valor"] or 0)
    obs = _parse_obs(row["observacoes"])
    frete = float(obs.get("frete") or 0)
    subtotal = obs.get("subtotal_produto")
    if subtotal is None:
        subtotal = max(0.0, valor - frete)
    return round(float(subtotal), 2), round(frete, 2)


def _intervalo(periodo):
    """Retorna (inicio, fim) do período e do período anterior (p/ comparação)."""
    agora = datetime.utcnow()
    dias = {"7d": 7, "30d": 30, "90d": 90}.get(periodo)
    if dias is None:  # 'todos'
        return None, None, None, None
    inicio = agora - timedelta(days=dias)
    inicio_ant = inicio - timedelta(days=dias)
    return inicio, agora, inicio_ant, inicio


# ----------------------------------------------------------------------
# Endpoint principal
# ----------------------------------------------------------------------
@dashboard_bp.route("/api/admin/dashboard", methods=["GET"])
def dashboard():
    if not _token_ok():
        return jsonify({"erro": "Não autorizado"}), 401

    periodo = request.args.get("periodo", "30d")
    inicio, fim, inicio_ant, fim_ant = _intervalo(periodo)

    # Busca o conjunto de linhas necessário em UMA query.
    # Para comparação de período, puxamos desde o início do período anterior.
    desde = inicio_ant if inicio_ant else None

    sql = """
        SELECT c.id, c.valor, c.status, c.data_criacao,
               c.cliente_nome, c.cliente_email, c.cliente_telefone,
               c.observacoes, c.product_id,
               p.nome AS produto_nome, p.tipo AS produto_tipo,
               cup.codigo AS cupom_codigo
        FROM cobrancas c
        LEFT JOIN produtos p ON p.id = c.product_id
        LEFT JOIN cupons  cup ON cup.id = c.cupom_id
        {filtro}
        ORDER BY c.data_criacao DESC
    """
    params = {}
    if desde:
        sql = sql.format(filtro="WHERE c.data_criacao >= :desde")
        params["desde"] = desde
    else:
        sql = sql.format(filtro="")

    try:
        with get_engine().connect() as conn:
            rows = [dict(r._mapping) for r in conn.execute(text(sql), params)]
    except Exception as e:
        return jsonify({"erro": f"Falha ao consultar o banco: {e}"}), 500

    # ---- Separa período atual x anterior ---------------------------------
    def no_periodo(r, ini, fi):
        if ini is None:
            return True
        dt = r["data_criacao"]
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt)
            except Exception:
                return True
        return (ini <= dt) if fi is None else (ini <= dt < fi)

    atuais = [r for r in rows if no_periodo(r, inicio, None)]
    anteriores = [r for r in rows if (inicio_ant and no_periodo(r, inicio_ant, inicio))]

    # ---- Agrega métricas do período atual --------------------------------
    def agrega(lista):
        bruto = frete_total = produtos_total = 0.0
        n_pagos = 0
        for r in lista:
            if r["status"] in STATUS_PAGOS:
                sub, fr = _split_valores(r)
                bruto += float(r["valor"] or 0)
                frete_total += fr
                produtos_total += sub
                n_pagos += 1
        return {
            "bruto": round(bruto, 2),
            "frete": round(frete_total, 2),
            "produtos": round(produtos_total, 2),
            "pedidos": n_pagos,
            "ticket_medio": round(bruto / n_pagos, 2) if n_pagos else 0.0,
        }

    metricas = agrega(atuais)
    metricas_ant = agrega(anteriores) if anteriores else None

    def variacao(atual, anterior):
        if not anterior or anterior == 0:
            return None
        return round((atual - anterior) / anterior * 100, 1)

    comparacao = None
    if metricas_ant:
        comparacao = {
            "bruto":   variacao(metricas["bruto"],   metricas_ant["bruto"]),
            "pedidos": variacao(metricas["pedidos"], metricas_ant["pedidos"]),
        }

    # ---- Série temporal diária (faturamento bruto por dia) ---------------
    serie = {}
    for r in atuais:
        if r["status"] in STATUS_PAGOS:
            dt = r["data_criacao"]
            if isinstance(dt, str):
                try:
                    dt = datetime.fromisoformat(dt)
                except Exception:
                    continue
            dia = dt.strftime("%Y-%m-%d")
            serie[dia] = round(serie.get(dia, 0) + float(r["valor"] or 0), 2)
    serie_ordenada = [{"data": d, "valor": v} for d, v in sorted(serie.items())]

    # ---- Top produtos ----------------------------------------------------
    top = {}
    for r in atuais:
        if r["status"] in STATUS_PAGOS:
            nome = r["produto_nome"] or f"Produto #{r['product_id']}"
            if nome not in top:
                top[nome] = {"nome": nome, "qtd": 0, "valor": 0.0}
            top[nome]["qtd"] += 1
            top[nome]["valor"] = round(top[nome]["valor"] + float(r["valor"] or 0), 2)
    top_produtos = sorted(top.values(), key=lambda x: x["valor"], reverse=True)[:8]

    # ---- Faturamento real por categoria (base p/ comissão) ---------------
    # Devolve o SUBTOTAL de produto (sem frete) por categoria. A alíquota de
    # comissão (ex.: 30%) é aplicada no frontend, onde é editável.
    por_categoria = {
        "digital":    {"subtotal": 0.0, "pedidos": 0},
        "fisico":     {"subtotal": 0.0, "pedidos": 0},
        "jogos_apps": {"subtotal": 0.0, "pedidos": 0},
    }
    for r in atuais:
        if r["status"] in STATUS_PAGOS:
            cat = _categoria(r["produto_tipo"])
            sub, _fr = _split_valores(r)
            por_categoria[cat]["subtotal"] = round(por_categoria[cat]["subtotal"] + sub, 2)
            por_categoria[cat]["pedidos"] += 1

    # ---- Distribuição por status (todos, não só pagos) -------------------
    por_status = {}
    for r in atuais:
        s = r["status"] or "desconhecido"
        por_status[s] = por_status.get(s, 0) + 1

    # ---- Últimas vendas pagas (para o feed de notificações) --------------
    ultimas = []
    for r in atuais:
        if r["status"] in STATUS_PAGOS:
            sub, fr = _split_valores(r)
            ultimas.append({
                "id": r["id"],
                "cliente": r["cliente_nome"],
                "email": r["cliente_email"],
                "produto": r["produto_nome"] or f"#{r['product_id']}",
                "valor": float(r["valor"] or 0),
                "frete": fr,
                "status": r["status"],
                "cupom": r["cupom_codigo"],
                "data": r["data_criacao"].isoformat() if hasattr(r["data_criacao"], "isoformat") else str(r["data_criacao"]),
            })
    ultimas = ultimas[:25]

    # ---- Envios pendentes (etiquetas): produtos físicos pagos ------------
    envios = []
    for r in atuais:
        if r["status"] in STATUS_PAGOS and (r["produto_tipo"] or "").lower() == "fisico":
            obs = _parse_obs(r["observacoes"])
            end = obs.get("endereco") or {}
            sub, fr = _split_valores(r)
            envios.append({
                "id": r["id"],
                "cliente": r["cliente_nome"],
                "email": r["cliente_email"],
                "telefone": r["cliente_telefone"],
                "produto": r["produto_nome"] or f"#{r['product_id']}",
                "transportadora": obs.get("transportadora"),
                "frete": fr,
                "endereco": end,
                "data": r["data_criacao"].isoformat() if hasattr(r["data_criacao"], "isoformat") else str(r["data_criacao"]),
            })

    payload = {
        "periodo": periodo,
        "gerado_em": datetime.utcnow().isoformat(),
        "metricas": metricas,
        "comparacao": comparacao,
        "serie": serie_ordenada,
        "top_produtos": top_produtos,
        "por_categoria": por_categoria,
        "por_status": por_status,
        "ultimas_vendas": ultimas,
        "envios_pendentes": envios,
    }
    return jsonify(payload), 200
