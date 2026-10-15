"""Administrative metadata, subcategories, invites, and email-based password recovery."""
import hashlib,json,os,re,secrets,smtplib,ssl
from email.message import EmailMessage
from datetime import datetime,timedelta,timezone
from flask import request,jsonify,session,render_template,abort
from werkzeug.security import generate_password_hash
from media import normalize_image,store_image
from mailer import configured as mail_configured,send_reset


def install(app,db,now,safe_media):
    @app.get('/api/subcategories')
    def subcategories():return jsonify([dict(r) for r in db().execute('SELECT * FROM subcategories ORDER BY position,id')])

    @app.post('/api/admin/subcategory')
    def add_subcategory():
        d=request.get_json() or {};name=str(d.get('name','')).strip();cat=int(d.get('category_id',0));c=db()
        if not name or len(name)>80:raise ValueError('Nome de subcategoria inválido.')
        if not c.execute('SELECT 1 FROM categories WHERE id=%s',(cat,)).fetchone():raise ValueError('Categoria inválida.')
        c.execute('INSERT INTO subcategories(category_id,name,position) VALUES(%s,%s,999)',(cat,name));c.commit();return jsonify({'ok':True})

    @app.post('/api/admin/media')
    def upload_store_media():
        f=request.files.get('photo')
        if not f:raise ValueError('Selecione uma imagem.')
        c=db();path=store_image(c,normalize_image(f.stream));c.commit();return jsonify({'ok':True,'url':path})

    @app.get('/api/admin/revenue')
    def revenue():
        year=int(request.args.get('year',datetime.now().year));month=request.args.get('month','')
        if not 2020<=year<=2100:raise ValueError('Ano inválido.')
        if month and not 1<=int(month)<=12:raise ValueError('Mês inválido.')
        prefix=str(year)+(('-'+str(int(month)).zfill(2)) if month else '')
        row=db().execute("SELECT count(*) AS orders,coalesce(sum(total),0) AS total FROM orders WHERE status='Confirmado' AND created_at LIKE %s",(prefix+'%',)).fetchone()
        return jsonify({'orders':row['orders'],'total':float(row['total'])})

    @app.get('/api/admin/admins')
    def admins():return jsonify([dict(r) for r in db().execute('SELECT id,email,role,created_at FROM admins ORDER BY id')])

    @app.post('/api/admin/invites')
    def invite():
        d=request.get_json() or {};email=str(d.get('email','')).strip().lower();role=d.get('role','viewer')
        if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email) or role not in ('owner','viewer'):raise ValueError('Email ou permissão inválidos.')
        c=db()
        if c.execute('SELECT 1 FROM admins WHERE email=%s',(email,)).fetchone():raise ValueError('Esta administradora já tem acesso.')
        token=secrets.token_urlsafe(32)
        c.execute("INSERT INTO admin_invites(token_hash,email,role,expires_at) VALUES(%s,%s,%s,now()+interval '48 hours')",(hashlib.sha256(token.encode()).hexdigest(),email,role));c.commit()
        return jsonify({'ok':True,'url':request.host_url+'admin/invite#'+token,'expires_hours':48})

    @app.get('/admin/invite')
    def invite_page():return render_template('invite.html')

    @app.post('/api/admin/accept-invite')
    def accept_invite():
        d=request.get_json() or {};token=str(d.get('token',''));pw=d.get('password','')
        if not 12<=len(pw)<=128 or pw!=d.get('confirm'):raise ValueError('Use pelo menos 12 caracteres e confirme a senha.')
        c=db();row=c.execute('SELECT * FROM admin_invites WHERE token_hash=%s AND expires_at>now() AND used_at IS NULL FOR UPDATE',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if not row:raise ValueError('Convite inválido ou expirado.')
        c.execute('INSERT INTO admins(email,password_hash,created_at,role) VALUES(%s,%s,%s,%s)',(row['email'],generate_password_hash(pw),now(),row['role']))
        c.execute('UPDATE admin_invites SET used_at=now() WHERE token_hash=%s',(row['token_hash'],));c.commit();return jsonify({'ok':True})

    @app.get('/reset-password')
    def reset_page():return render_template('reset.html')

    @app.post('/api/password/forgot')
    def forgot():
        # No token is returned to the browser, logs, or administrator.
        if not mail_configured():
            return jsonify({'error':'Recuperação por email ainda não configurada. Entre em contato com a loja.'}),503
        d=request.get_json() or {};email=str(d.get('email','')).strip().lower();c=db();row=c.execute('SELECT id FROM customers WHERE email=%s',(email,)).fetchone()
        if row:
            token=secrets.token_urlsafe(32);hashed=hashlib.sha256(token.encode()).hexdigest()
            c.execute("INSERT INTO password_resets(token_hash,customer_id,expires_at) VALUES(%s,%s,now()+interval '30 minutes')",(hashed,row['id']))
            origin=os.environ.get('PUBLIC_BASE_URL','').rstrip('/')
            if not origin.startswith('https://'):raise RuntimeError('PUBLIC_BASE_URL HTTPS deve ser configurada para recuperação.')
            text='Para definir uma nova senha, abra o link em até 30 minutos:\n'+origin+'/reset-password#'+token+'\n\nSe você não solicitou, ignore esta mensagem.'
            try:
                send_reset(email,text)
            except Exception:
                c.rollback();return jsonify({'error':'O serviço de email está indisponível. Tente novamente mais tarde.'}),503
            c.commit()
        return jsonify({'ok':True,'message':'Se o email estiver cadastrado, você receberá um link de recuperação.'})

    @app.post('/api/password/reset')
    def reset():
        d=request.get_json() or {};pw=d.get('password','');token=str(d.get('token',''))
        if not 10<=len(pw)<=128 or pw!=d.get('confirm'):raise ValueError('Use pelo menos 10 caracteres e confirme a senha.')
        c=db();row=c.execute('SELECT * FROM password_resets WHERE token_hash=%s AND expires_at>now() AND used_at IS NULL FOR UPDATE',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        if not row:raise ValueError('Link inválido ou expirado.')
        c.execute('UPDATE customers SET password_hash=%s,session_version=session_version+1 WHERE id=%s',(generate_password_hash(pw),row['customer_id']))
        c.execute('UPDATE password_resets SET used_at=now() WHERE customer_id=%s',(row['customer_id'],));c.commit();session.clear();return jsonify({'ok':True})
