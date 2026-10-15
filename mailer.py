"""HTTPS transactional email for Render Free; SMTP only for compatible hosts."""
import json,os,smtplib,ssl
from urllib.request import Request,urlopen
from email.message import EmailMessage


def configured():
    return bool(os.environ.get('MAIL_FROM') and (os.environ.get('BREVO_API_KEY') or (os.environ.get('SMTP_HOST') and os.environ.get('RENDER')!='true')))


def send_reset(email,text):
    sender=os.environ['MAIL_FROM']
    if os.environ.get('BREVO_API_KEY'):
        payload={'sender':{'name':'Lumina Signature','email':sender},'to':[{'email':email}],'subject':'Recuperar senha — Lumina Signature','textContent':text}
        req=Request('https://api.brevo.com/v3/smtp/email',data=json.dumps(payload).encode(),headers={'api-key':os.environ['BREVO_API_KEY'],'content-type':'application/json','accept':'application/json'},method='POST')
        with urlopen(req,timeout=20) as response:
            if response.status!=201:raise RuntimeError('Envio não confirmado pelo provedor.')
        return
    if os.environ.get('RENDER')=='true':raise RuntimeError('Render Free requer serviço de email HTTPS.')
    mail=EmailMessage();mail['From']=sender;mail['To']=email;mail['Subject']='Recuperar senha — Lumina Signature';mail.set_content(text)
    with smtplib.SMTP(os.environ['SMTP_HOST'],int(os.environ.get('SMTP_PORT','587')),timeout=15) as server:
        server.starttls(context=ssl.create_default_context())
        if os.environ.get('SMTP_USER'):server.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD'])
        server.send_message(mail)
