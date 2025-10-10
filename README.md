# Sistema de Cobrança Mercado Pago - Render.com

Sistema completo de geração de cobranças PIX via Mercado Pago, com recebimento de webhooks e envio automático de e-mails de confirmação.

## 🚀 Por que Render.com?

O **Render.com** é muito mais adequado para aplicações Flask do que o Vercel porque:

- ✅ Suporte nativo completo para Flask e Python
- ✅ Webhooks funcionam perfeitamente (conexões persistentes)
- ✅ Banco de dados PostgreSQL integrado
- ✅ Logs em tempo real para debugging
- ✅ Plano gratuito robusto
- ✅ Deploy automático via Git

## 📋 Pré-requisitos

1. Conta no [Render.com](https://render.com) (gratuita)
2. Conta no [Mercado Pago](https://www.mercadopago.com.br) com credenciais de produção
3. Conta de e-mail configurada (Zoho, Gmail, etc.)
4. Repositório Git (GitHub, GitLab ou Bitbucket)

## 🔧 Configuração Passo a Passo

### 1. Preparar o Repositório

```bash
# Inicializar repositório Git
git init

# Adicionar todos os arquivos
git add .

# Fazer o primeiro commit
git commit -m "Projeto adaptado para Render.com"

# Conectar com seu repositório remoto (GitHub, GitLab, etc.)
git remote add origin https://github.com/seu-usuario/seu-repositorio.git

# Enviar para o repositório
git push -u origin main
```

### 2. Criar Banco de Dados no Render

1. Acesse [Render Dashboard](https://dashboard.render.com/)
2. Clique em **"New +"** → **"PostgreSQL"**
3. Configure:
   - **Name**: `mercadopago-db`
   - **Database**: `mercadopago`
   - **User**: `mercadopago_user`
   - **Region**: Escolha a mais próxima (ex: Ohio - US East)
   - **Plan**: Free
4. Clique em **"Create Database"**
5. **IMPORTANTE**: Copie a **Internal Database URL** (será usada no próximo passo)

### 3. Criar Web Service no Render

1. No Dashboard, clique em **"New +"** → **"Web Service"**
2. Conecte seu repositório Git
3. Configure:
   - **Name**: `mercadopago-api`
   - **Region**: Mesma do banco de dados
   - **Branch**: `main`
   - **Root Directory**: deixe em branco
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn app:app`
   - **Plan**: Free

### 4. Configurar Variáveis de Ambiente

Na seção **"Environment Variables"**, adicione:

#### Obrigatórias:

```
DATABASE_URL = [Cole a Internal Database URL do passo 2]
MERCADOPAGO_ACCESS_TOKEN = [Seu token do Mercado Pago]
WEBHOOK_SECRET = [Seu webhook secret do Mercado Pago]
EMAIL_USER = [Seu e-mail completo]
EMAIL_PASSWORD = [Sua senha de e-mail ou app password]
```

#### Opcionais (já têm valores padrão):

```
SMTP_SERVER = smtp.zoho.com
SMTP_PORT = 465
LINK_PRODUTO = https://drive.google.com/file/d/1HlMExRRjV5Wn5SUNZktc46ragh8Zj8uQ/view?usp=sharing
SECRET_KEY = [Será gerado automaticamente]
```

### 5. Deploy

1. Clique em **"Create Web Service"**
2. O Render iniciará o build automaticamente
3. Aguarde o deploy (leva 2-5 minutos)
4. Quando aparecer **"Live"** em verde, seu sistema está no ar! 🎉

### 6. Configurar Webhook no Mercado Pago

1. Acesse o [Painel do Mercado Pago](https://www.mercadopago.com.br/developers/panel)
2. Vá em **"Suas integrações"** → Selecione sua aplicação
3. Clique em **"Webhooks"**
4. Configure:
   - **URL de notificação**: `https://seu-app.onrender.com/api/webhook`
   - **Eventos**: Marque **"Pagamentos"**
5. Salve e copie o **Webhook Secret** (cole nas variáveis de ambiente)

## 🧪 Testar o Sistema

### Teste Local (Opcional)

```bash
# Instalar dependências
pip install -r requirements.txt

# Criar arquivo .env com suas credenciais
cp .env.example .env
# Edite o .env com suas credenciais reais

# Rodar localmente
python app.py
```

Acesse: `http://localhost:5000`

### Teste em Produção

1. Acesse: `https://seu-app.onrender.com`
2. Preencha o formulário de cobrança
3. Gere o QR Code PIX
4. Faça um pagamento de teste
5. Verifique:
   - Logs no Render Dashboard
   - E-mail de confirmação enviado
   - Status atualizado no banco de dados

## 📊 Monitoramento

### Ver Logs em Tempo Real

1. Acesse o Render Dashboard
2. Clique no seu Web Service
3. Vá na aba **"Logs"**
4. Você verá todos os webhooks recebidos e processados

### Verificar Banco de Dados

1. No Dashboard, clique no seu Database
2. Use o **"Connect"** para acessar via psql ou ferramentas como DBeaver
3. Query de exemplo:
```sql
SELECT * FROM cobrancas ORDER BY data_criacao DESC;
```

## 🔒 Segurança

- ✅ Validação de assinatura de webhook implementada
- ✅ HTTPS automático (certificado SSL gratuito)
- ✅ Variáveis de ambiente protegidas
- ✅ Banco de dados com autenticação

## 🐛 Troubleshooting

### Webhook não está funcionando

1. Verifique os logs no Render Dashboard
2. Confirme que a URL do webhook no Mercado Pago está correta
3. Verifique se o `WEBHOOK_SECRET` está configurado corretamente
4. Teste a validação de assinatura

### E-mail não está sendo enviado

1. Verifique as credenciais de e-mail
2. Para Gmail, use **App Password** ao invés da senha normal
3. Verifique se a porta SMTP está correta (465 para SSL)
4. Veja os logs para mensagens de erro específicas

### Erro de conexão com banco de dados

1. Verifique se a `DATABASE_URL` está correta
2. Confirme que o banco de dados está "Available" no Dashboard
3. Reinicie o Web Service

### Deploy falhou

1. Verifique os logs de build
2. Confirme que o `requirements.txt` está correto
3. Verifique se o Python 3.11 está disponível
4. Tente fazer um novo deploy manual

## 📝 Estrutura do Projeto

```
mercadopago-render/
├── app.py                 # Aplicação Flask principal
├── requirements.txt       # Dependências Python
├── Procfile              # Configuração de processo
├── render.yaml           # Configuração do Render (opcional)
├── .env.example          # Exemplo de variáveis de ambiente
├── .gitignore            # Arquivos ignorados pelo Git
├── README.md             # Este arquivo
└── static/               # Arquivos frontend
    ├── index.html        # Página principal
    ├── script.js         # Lógica do frontend
    └── styles.css        # Estilos
```

## 🔄 Atualizações Futuras

Para fazer alterações no sistema:

```bash
# Fazer suas modificações nos arquivos

# Commit
git add .
git commit -m "Descrição da alteração"

# Push
git push origin main

# O Render fará deploy automático!
```

## 📞 Suporte

- [Documentação do Render](https://render.com/docs)
- [API do Mercado Pago](https://www.mercadopago.com.br/developers/pt/docs)
- [Webhooks do Mercado Pago](https://www.mercadopago.com.br/developers/pt/docs/your-integrations/notifications/webhooks)

## ✅ Checklist de Deploy

- [ ] Repositório Git criado e enviado
- [ ] Banco de dados PostgreSQL criado no Render
- [ ] Web Service criado no Render
- [ ] Todas as variáveis de ambiente configuradas
- [ ] Deploy concluído com sucesso (status "Live")
- [ ] Webhook configurado no Mercado Pago
- [ ] Teste de criação de cobrança realizado
- [ ] Teste de pagamento PIX realizado
- [ ] Webhook recebido e processado
- [ ] E-mail de confirmação enviado

---

**Desenvolvido para funcionar perfeitamente no Render.com** 🚀
