"""
notificar_expiracao.py — Job diário (Render Cron) que envia e-mails de aviso:

  • Trial (teste grátis): avisa faltando até 2 dias e quando expira.
  • Assinatura paga: avisa faltando até 7 dias e quando expira.

Cada estágio é enviado UMA vez (controlado pela coluna licencas.ultimo_aviso).
Reaproveita o app/DB do BrooStore e o mesmo SMTP do worker.

Execução: python notificar_expiracao.py
"""
import os
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from app import app, db, Licenca  # usa o mesmo contexto/engine do BrooStore

BROOSTOCK_URL = os.environ.get("BROOSTOCK_URL", "https://brootechstock.netlify.app/login")


def _enviar(destinatario: str, assunto: str, corpo_html: str) -> bool:
    try:
        smtp_server = os.environ.get("SMTP_SERVER", "smtp.zoho.com")
        email_user = os.environ["EMAIL_USER"]
        email_pass = os.environ["EMAIL_PASSWORD"]
    except KeyError:
        print("[CRON] ERRO: credenciais de e-mail não configuradas.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"] = email_user
    msg["To"] = destinatario
    msg.attach(MIMEText(corpo_html, "html"))
    try:
        smtp_port = int(os.environ.get("SMTP_PORT", 587))
        with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as server:
            server.starttls()
            server.login(email_user, email_pass)
            server.send_message(msg)
        return True
    except Exception as exc:
        print(f"[CRON] Falha no envio SMTP para {destinatario}: {exc}")
        return False


def _html(titulo: str, paragrafo: str, cta_label: str) -> str:
    return f"""<!DOCTYPE html>
<html><body style="font-family:Arial,sans-serif;background:#0d1b2a;color:#e0e6ed;padding:24px;">
  <div style="max-width:560px;margin:0 auto;background:#14213d;border-radius:12px;padding:28px;">
    <h2 style="color:#48cae4;margin-top:0;">{titulo}</h2>
    <p>{paragrafo}</p>
    <p style="text-align:center;margin:24px 0;">
      <a href="{BROOSTOCK_URL}" style="background:#15bcd6;color:#012;text-decoration:none;font-weight:bold;padding:12px 22px;border-radius:8px;display:inline-block;">{cta_label}</a>
    </p>
    <p style="font-size:0.85em;color:#9fb0c3;">Se você já renovou ou assinou, pode ignorar este aviso.</p>
  </div>
</body></html>"""


def run():
    enviados = 0
    with app.app_context():
        agora = datetime.utcnow()
        licencas = Licenca.query.filter(Licenca.expira_em.isnot(None)).all()

        for lic in licencas:
            if not lic.expira_em:
                continue
            status = (lic.status or "").lower()
            if status not in ("trial", "ativa"):
                continue  # já expirada/cancelada: não reavisa

            email = (lic.cliente_email or "").strip()
            if not email:
                continue

            dias = (lic.expira_em - agora).days
            expira_str = lic.expira_em.strftime("%d/%m/%Y")
            venceu = lic.expira_em <= agora
            stage = assunto = corpo = None

            if status == "trial":
                if venceu and lic.ultimo_aviso != "expirado":
                    stage = "expirado"
                    assunto = "Seu teste grátis do BrooStock terminou"
                    corpo = _html(
                        "Seu teste grátis terminou",
                        "Esperamos que tenha gostado do BrooStock! Para voltar a acessar seu estoque e seu painel financeiro, escolha um plano e ative sua assinatura.",
                        "Assinar agora",
                    )
                elif (not venceu) and dias <= 2 and lic.ultimo_aviso not in ("2d", "expirado"):
                    stage = "2d"
                    quando = "hoje" if dias <= 0 else (f"em {dias} dia" + ("s" if dias > 1 else ""))
                    assunto = "Seu teste grátis do BrooStock está acabando ⏳"
                    corpo = _html(
                        "Seu teste está acabando",
                        f"Seu teste grátis termina <strong>{quando}</strong> ({expira_str}). Assine para não perder o acesso e continuar de onde parou.",
                        "Assinar e continuar",
                    )

            elif status == "ativa":
                if venceu and lic.ultimo_aviso != "expirado":
                    stage = "expirado"
                    assunto = "Sua licença do BrooStock expirou"
                    corpo = _html(
                        "Sua licença expirou",
                        "Sua assinatura do BrooStock chegou ao fim. Renove para reativar o acesso ao seu estoque e painel.",
                        "Renovar agora",
                    )
                elif (not venceu) and dias <= 7 and lic.ultimo_aviso not in ("7d", "expirado"):
                    stage = "7d"
                    quando = "hoje" if dias <= 0 else (f"em {dias} dia" + ("s" if dias > 1 else ""))
                    assunto = "Sua licença do BrooStock vai expirar"
                    corpo = _html(
                        "Sua licença vai expirar",
                        f"Sua assinatura expira <strong>{quando}</strong> ({expira_str}). Renove para manter o acesso sem interrupção.",
                        "Renovar agora",
                    )

            if not stage:
                continue

            if _enviar(email, assunto, corpo):
                lic.ultimo_aviso = stage
                if stage == "expirado":
                    lic.status = "expirado"
                try:
                    db.session.commit()
                    enviados += 1
                    print(f"[CRON] Aviso '{stage}' enviado para {email} (expira {expira_str}).")
                except Exception as e:
                    db.session.rollback()
                    print(f"[CRON] ERRO ao salvar aviso de {email}: {e}")
            else:
                db.session.rollback()

    print(f"[CRON] Concluído. {enviados} e-mail(s) enviado(s).")


if __name__ == "__main__":
    run()
