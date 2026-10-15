"""Request lifecycle, CSRF, authorization, abuse limits, and safe error responses."""
import hashlib,hmac,secrets,os
from urllib.parse import urlparse
from flask import g,request,session,jsonify
from werkzeug.exceptions import HTTPException
import psycopg


def install(app,db,require_admin,require_customer):
    @app.teardown_appcontext
    def close_database(error=None):
        c=g.pop('database',None)
        if c and not c.closed:
            c.rollback();c.close()

    @app.get('/api/csrf')
    def csrf_token():
        token=session.setdefault('csrf_token',secrets.token_urlsafe(32))
        return jsonify({'token':token})

    @app.get('/healthz')
    def health():return jsonify({'ok':True})

    @app.get('/readyz')
    def ready():
        try:
            db().execute('SELECT 1 FROM schema_migrations WHERE version=1').fetchone()
            return jsonify({'ok':True})
        except psycopg.Error:return jsonify({'error':'Banco indisponível.'}),503

    @app.before_request
    def guard():
        if os.environ.get('STAGING_MODE')=='1' and request.path not in ('/admin','/api/admin/login','/api/me','/api/csrf','/healthz') and not request.path.startswith('/static/'):
            if not require_admin():return jsonify({'error':'Ambiente de validação restrito à administração.'}),401
        if not request.path.startswith('/api/'):return
        if request.method not in ('GET','HEAD','OPTIONS'):
            if request.is_json and not isinstance(request.get_json(),dict):return jsonify({'error':'Envie um objeto JSON válido.'}),400
            origin=request.headers.get('Origin')
            if origin and urlparse(origin).netloc!=request.host:return jsonify({'error':'Origem não autorizada.'}),403
            received=request.headers.get('X-CSRF-Token','');expected=session.get('csrf_token','')
            if not expected or not hmac.compare_digest(expected,received):return jsonify({'error':'Sessão expirada. Atualize a página e tente novamente.','code':'csrf'}),403
        if request.path.startswith('/api/admin/') and request.path not in ('/api/admin/login','/api/admin/accept-invite'):
            if not require_admin():return jsonify({'error':'Faça login como administradora.'}),401
            row=db().execute('SELECT role FROM admins WHERE id=%s',(session['admin_id'],)).fetchone()
            if request.method not in ('GET','HEAD') and row['role']!='owner':return jsonify({'error':'Esta conta permite somente visualização.'}),403
        if request.path in ('/api/login','/api/admin/login','/api/register','/api/password/forgot','/api/password/reset','/api/admin/accept-invite') and request.method=='POST':
            key=hmac.new(app.secret_key.encode(),(request.remote_addr+':'+request.path).encode(),hashlib.sha256).hexdigest()
            c=db();row=c.execute("INSERT INTO login_attempts(bucket,attempts,expires_at) VALUES(%s,1,now()+interval '15 minutes') ON CONFLICT(bucket) DO UPDATE SET attempts=CASE WHEN login_attempts.expires_at<now() THEN 1 ELSE login_attempts.attempts+1 END,expires_at=CASE WHEN login_attempts.expires_at<now() THEN now()+interval '15 minutes' ELSE login_attempts.expires_at END RETURNING attempts",(key,)).fetchone();c.commit()
            if row['attempts']>8:return jsonify({'error':'Muitas tentativas. Aguarde 15 minutos.'}),429

    @app.after_request
    def response_headers(response):
        if os.environ.get('STAGING_MODE')=='1':response.headers['X-Robots-Tag']='noindex, nofollow, noarchive'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
        # Existing approved UI uses inline handlers. Values inserted in those handlers are encoded or numeric.
        response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' blob: data: https://res.cloudinary.com; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        if request.is_secure:response.headers['Strict-Transport-Security']='max-age=31536000'
        if request.path.startswith('/api/') or request.path in ('/admin','/account','/cart'):
            response.headers['Cache-Control']='no-store'
        return response

    @app.errorhandler(Exception)
    def api_error(error):
        if isinstance(error,HTTPException):
            status=error.code
            message={400:'Solicitação inválida.',404:'Não encontrado.',413:'A imagem excede o limite de 20 MB.',415:'Envie os dados no formato correto.'}.get(status,'Solicitação não permitida.')
        elif isinstance(error,(ValueError,TypeError,OverflowError)):
            status=400;message=str(error) if isinstance(error,ValueError) and len(str(error))<250 else 'Dados inválidos.'
        elif isinstance(error,psycopg.IntegrityError):status=409;message='Os dados conflitam com um registro existente. Atualize a página.'
        elif isinstance(error,psycopg.OperationalError):status=503;message='Banco temporariamente indisponível. Tente novamente.'
        else:
            status=500;message='Não foi possível concluir a operação. Tente novamente.'
            app.logger.error('request_failed class=%s endpoint=%s',type(error).__name__,request.endpoint)
        return jsonify({'error':message}),status
