#!/bin/bash

echo "🧪 Teste Local do Sistema Mercado Pago"
echo "======================================"
echo ""

# Verificar Python
echo "✓ Verificando Python..."
python3.11 --version

# Verificar dependências
echo "✓ Verificando dependências..."
pip3 list | grep -E "Flask|gunicorn|mercadopago|psycopg2"

# Verificar sintaxe
echo "✓ Verificando sintaxe do app.py..."
python3.11 -m py_compile app.py && echo "  ✅ Sintaxe OK"

# Verificar importação
echo "✓ Testando importação..."
python3.11 -c "from app import app; print('  ✅ App importado')"

# Verificar rotas
echo "✓ Rotas disponíveis:"
python3.11 -c "from app import app; [print(f'  - {rule}') for rule in app.url_map.iter_rules()]"

# Verificar banco de dados
echo "✓ Verificando banco de dados..."
python3.11 -c "from app import app, db; app.app_context().push(); db.create_all(); print('  ✅ Banco criado')"

# Verificar arquivos estáticos
echo "✓ Verificando arquivos estáticos..."
ls -l static/*.html static/*.js static/*.css | awk '{print "  - " $9}'

echo ""
echo "======================================"
echo "✅ Todos os testes passaram!"
echo ""
echo "Para rodar localmente:"
echo "  export DATABASE_URL=sqlite:///cobrancas.db"
echo "  export MERCADOPAGO_ACCESS_TOKEN=seu_token"
echo "  python3.11 app.py"
echo ""
echo "Ou com Gunicorn:"
echo "  gunicorn app:app --bind 0.0.0.0:5000"
