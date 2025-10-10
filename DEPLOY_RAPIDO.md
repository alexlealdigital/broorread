# 🚀 Guia Rápido de Deploy no Render.com

## Resumo: 5 Passos Simples

### 1️⃣ Enviar para o GitHub

```bash
git init
git add .
git commit -m "Projeto adaptado para Render"
git remote add origin https://github.com/SEU-USUARIO/SEU-REPO.git
git push -u origin main
```

### 2️⃣ Criar Banco de Dados

1. Entre em https://dashboard.render.com/
2. **New +** → **PostgreSQL**
3. Nome: `mercadopago-db`
4. Plano: **Free**
5. **Create Database**
6. ⚠️ **COPIE** a **Internal Database URL**

### 3️⃣ Criar Web Service

1. **New +** → **Web Service**
2. Conecte seu repositório GitHub
3. Configurações:
   - Nome: `mercadopago-api`
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
   - Plano: **Free**

### 4️⃣ Adicionar Variáveis de Ambiente

Clique em **"Advanced"** → **"Add Environment Variable"**

**OBRIGATÓRIAS:**
```
DATABASE_URL = [Cole a URL do passo 2]
MERCADOPAGO_ACCESS_TOKEN = [Seu token]
WEBHOOK_SECRET = [Seu secret]
EMAIL_USER = [Seu e-mail]
EMAIL_PASSWORD = [Sua senha]
```

**OPCIONAIS (use estes valores):**
```
SMTP_SERVER = smtp.zoho.com
SMTP_PORT = 465
LINK_PRODUTO = https://drive.google.com/file/d/1HlMExRRjV5Wn5SUNZktc46ragh8Zj8uQ/view?usp=sharing
```

### 5️⃣ Configurar Webhook no Mercado Pago

1. Acesse: https://www.mercadopago.com.br/developers/panel
2. Suas integrações → Sua aplicação → **Webhooks**
3. URL: `https://SEU-APP.onrender.com/api/webhook`
4. Eventos: **Pagamentos** ✅
5. Salve e copie o **Secret** (adicione nas variáveis de ambiente)

---

## ✅ Pronto! Seu Sistema Está no Ar!

Acesse: `https://seu-app.onrender.com`

## 🧪 Como Testar

1. Abra seu site
2. Preencha o formulário
3. Gere o QR Code
4. Pague com PIX
5. Verifique o e-mail de confirmação

## 📊 Ver Logs

Dashboard → Seu Web Service → **Logs**

Você verá:
- ✅ Webhooks recebidos
- ✅ Pagamentos processados
- ✅ E-mails enviados

---

## ⚠️ Problemas Comuns

### Webhook não funciona
- Verifique a URL no Mercado Pago
- Confirme o WEBHOOK_SECRET
- Veja os logs no Render

### E-mail não envia
- Use **App Password** se for Gmail
- Verifique EMAIL_USER e EMAIL_PASSWORD
- Confirme SMTP_SERVER e SMTP_PORT

### Erro de banco
- Confirme que DATABASE_URL está correta
- Aguarde o banco ficar "Available"
- Reinicie o Web Service

---

## 🔄 Fazer Atualizações

```bash
# Edite seus arquivos
git add .
git commit -m "Atualização"
git push

# Deploy automático! 🎉
```

---

## 📞 Links Úteis

- Dashboard Render: https://dashboard.render.com/
- Mercado Pago: https://www.mercadopago.com.br/developers/panel
- Documentação: Ver README.md completo

---

**Muito mais simples que Vercel para Flask!** 💪
