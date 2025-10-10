# ✅ Checklist Completo de Deploy no Render.com

Use este checklist para garantir que cada etapa foi concluída corretamente.

---

## 📦 FASE 1: Preparação do Código

- [ ] Baixei o arquivo `mercadopago-render.zip`
- [ ] Extraí os arquivos em uma pasta local
- [ ] Revisei o arquivo `.env.example` para entender as variáveis necessárias
- [ ] Tenho em mãos:
  - [ ] Token do Mercado Pago (`MERCADOPAGO_ACCESS_TOKEN`)
  - [ ] Credenciais de e-mail (`EMAIL_USER` e `EMAIL_PASSWORD`)
  - [ ] Link do produto/e-book (`LINK_PRODUTO`)

---

## 🔐 FASE 2: Configuração do Mercado Pago

- [ ] Acessei o [Painel do Mercado Pago](https://www.mercadopago.com.br/developers/panel)
- [ ] Copiei o **Access Token** de produção
- [ ] Guardei o token em local seguro (vou precisar no Render)

---

## 📂 FASE 3: Repositório Git

- [ ] Criei um repositório no GitHub/GitLab/Bitbucket
- [ ] Inicializei o Git na pasta do projeto:
  ```bash
  git init
  git add .
  git commit -m "Projeto adaptado para Render.com"
  ```
- [ ] Conectei ao repositório remoto:
  ```bash
  git remote add origin https://github.com/MEU-USUARIO/MEU-REPO.git
  git push -u origin main
  ```
- [ ] Confirmei que os arquivos estão no repositório online

---

## 🗄️ FASE 4: Banco de Dados no Render

- [ ] Acessei [Render Dashboard](https://dashboard.render.com/)
- [ ] Cliquei em **"New +"** → **"PostgreSQL"**
- [ ] Configurei:
  - [ ] Name: `mercadopago-db`
  - [ ] Database: `mercadopago`
  - [ ] User: `mercadopago_user`
  - [ ] Region: Escolhi a mais próxima
  - [ ] Plan: **Free**
- [ ] Cliquei em **"Create Database"**
- [ ] Aguardei o status mudar para **"Available"** (1-2 minutos)
- [ ] Copiei a **Internal Database URL** (começa com `postgresql://`)
- [ ] Salvei a URL em local seguro

---

## 🌐 FASE 5: Web Service no Render

- [ ] No Dashboard, cliquei em **"New +"** → **"Web Service"**
- [ ] Selecionei **"Build and deploy from a Git repository"**
- [ ] Conectei meu repositório (GitHub/GitLab/Bitbucket)
- [ ] Selecionei o repositório correto
- [ ] Configurei:
  - [ ] Name: `mercadopago-api` (ou outro nome de sua escolha)
  - [ ] Region: **Mesma do banco de dados**
  - [ ] Branch: `main`
  - [ ] Root Directory: (deixei em branco)
  - [ ] Runtime: **Python 3**
  - [ ] Build Command: `pip install -r requirements.txt`
  - [ ] Start Command: `gunicorn app:app`
  - [ ] Plan: **Free**

---

## 🔧 FASE 6: Variáveis de Ambiente

Na seção **"Environment Variables"**, cliquei em **"Add Environment Variable"** e adicionei:

### Obrigatórias:

- [ ] `DATABASE_URL`
  - Valor: (colei a Internal Database URL da FASE 4)

- [ ] `MERCADOPAGO_ACCESS_TOKEN`
  - Valor: (colei o token da FASE 2)

- [ ] `WEBHOOK_SECRET`
  - Valor: (vou pegar depois de configurar o webhook - por enquanto coloquei "temporario")

- [ ] `EMAIL_USER`
  - Valor: meu e-mail completo (ex: contato@meudominio.com)

- [ ] `EMAIL_PASSWORD`
  - Valor: minha senha de e-mail ou app password

### Opcionais (recomendadas):

- [ ] `SMTP_SERVER`
  - Valor: `smtp.zoho.com` (ou smtp.gmail.com, etc.)

- [ ] `SMTP_PORT`
  - Valor: `465`

- [ ] `LINK_PRODUTO`
  - Valor: URL do meu e-book/produto

---

## 🚀 FASE 7: Deploy

- [ ] Cliquei em **"Create Web Service"**
- [ ] Aguardei o build começar (aparece "In Progress")
- [ ] Acompanhei os logs de build
- [ ] Aguardei até aparecer **"Live"** em verde (3-5 minutos)
- [ ] Copiei a URL do serviço (ex: `https://mercadopago-api.onrender.com`)
- [ ] Acessei a URL no navegador para confirmar que a página carrega

---

## 🔗 FASE 8: Configurar Webhook no Mercado Pago

- [ ] Voltei ao [Painel do Mercado Pago](https://www.mercadopago.com.br/developers/panel)
- [ ] Fui em **"Suas integrações"** → Selecionei minha aplicação
- [ ] Cliquei em **"Webhooks"** ou **"Notificações"**
- [ ] Cliquei em **"Configurar notificações"** ou **"Adicionar webhook"**
- [ ] Configurei:
  - [ ] URL: `https://MEU-APP.onrender.com/api/webhook`
  - [ ] Eventos: Marquei **"Pagamentos"** ou **"payment"**
- [ ] Cliquei em **"Salvar"**
- [ ] Copiei o **Webhook Secret** que foi gerado
- [ ] Voltei ao Render Dashboard
- [ ] Editei a variável `WEBHOOK_SECRET` com o valor correto
- [ ] Salvei as alterações
- [ ] Aguardei o serviço reiniciar automaticamente (30 segundos)

---

## 🧪 FASE 9: Teste Completo

- [ ] Acessei meu site: `https://meu-app.onrender.com`
- [ ] Preenchi o formulário de cobrança com:
  - [ ] E-mail válido (que tenho acesso)
  - [ ] Nome
  - [ ] Outros dados necessários
- [ ] Cliquei em **"Gerar Cobrança"** ou botão similar
- [ ] Recebi o QR Code PIX
- [ ] Fiz um pagamento de teste (pode ser R$ 1,00)
- [ ] Aguardei alguns segundos

---

## 📧 FASE 10: Verificação

- [ ] Recebi o e-mail de confirmação
- [ ] O e-mail contém o link do produto
- [ ] Consegui acessar o produto pelo link
- [ ] Voltei ao Render Dashboard → Logs
- [ ] Vi a mensagem de webhook recebido
- [ ] Vi a mensagem de pagamento aprovado
- [ ] Vi a mensagem de e-mail enviado

---

## 📊 FASE 11: Monitoramento

- [ ] Salvei a URL do Render Dashboard nos favoritos
- [ ] Testei acessar os logs em tempo real
- [ ] Verifiquei que o banco de dados está funcionando:
  - [ ] No Dashboard do PostgreSQL, cliquei em "Connect"
  - [ ] Usei uma ferramenta como DBeaver ou psql
  - [ ] Executei: `SELECT * FROM cobrancas;`
  - [ ] Vi minha cobrança de teste registrada

---

## 🎉 CONCLUSÃO

Se todos os itens acima estão marcados, **PARABÉNS!** 🎊

Seu sistema está:
- ✅ Funcionando perfeitamente
- ✅ Recebendo webhooks
- ✅ Processando pagamentos
- ✅ Enviando e-mails
- ✅ Pronto para produção!

---

## 🔄 Próximas Ações

### Para fazer atualizações:
```bash
# Editar arquivos localmente
git add .
git commit -m "Descrição da mudança"
git push origin main
# Deploy automático no Render!
```

### Para ver logs:
1. Render Dashboard
2. Seu Web Service
3. Aba "Logs"

### Para backup do banco:
1. Dashboard do PostgreSQL
2. Aba "Backups"
3. Download manual ou automático

---

## 🆘 Se Algo Não Funcionar

### Webhook não chega:
- [ ] Verifiquei a URL no Mercado Pago
- [ ] Confirmei que o WEBHOOK_SECRET está correto
- [ ] Vi os logs no Render para mensagens de erro

### E-mail não envia:
- [ ] Verifiquei EMAIL_USER e EMAIL_PASSWORD
- [ ] Usei App Password se for Gmail
- [ ] Confirmei SMTP_SERVER e SMTP_PORT
- [ ] Vi os logs para erro específico

### Erro 500 ou 502:
- [ ] Vi os logs de erro no Render
- [ ] Verifiquei se todas as variáveis estão configuradas
- [ ] Confirmei que o banco está "Available"
- [ ] Tentei reiniciar o serviço manualmente

---

## 📞 Recursos Úteis

- [Render Docs](https://render.com/docs)
- [Mercado Pago Webhooks](https://www.mercadopago.com.br/developers/pt/docs/your-integrations/notifications/webhooks)
- [Gunicorn Docs](https://docs.gunicorn.org/)
- [Flask Docs](https://flask.palletsprojects.com/)

---

**Data:** ___/___/______  
**Status:** [ ] Em andamento  [ ] Concluído  
**URL do Sistema:** _________________________________  
**Observações:** ___________________________________
