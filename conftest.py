import os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
os.environ.setdefault('LUMINA_SECRET','local-test-secret-not-for-production')
assert '127.0.0.1' in os.environ.get('DATABASE_URL',''), 'Tests require isolated localhost PostgreSQL.'
import pytest,psycopg
from werkzeug.security import generate_password_hash
from app import app,db,init,now

@pytest.fixture(scope='session',autouse=True)
def prepare():
    with app.app_context():
        init();c=db();c.execute('DELETE FROM login_attempts')
        c.execute("INSERT INTO categories(name,position) VALUES('AUDIT categoria',998) ON CONFLICT(name) DO NOTHING")
        for color in ['Dourado','Prata']:
            c.execute('INSERT INTO colors(name,position) VALUES(%s,998) ON CONFLICT(name) DO NOTHING',(color,))
        if not c.execute('SELECT 1 FROM products').fetchone():
            category=c.execute("SELECT id FROM categories WHERE name='AUDIT categoria'").fetchone()['id']
            c.execute('INSERT INTO products(code,name,description,category_id,care,modality,price,status,photos,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',('AUDIT-SEED','AUDIT sample','Seed for isolated tests only',category,'Care','Pronta entrega',10,'published','["/static/placeholder.svg"]',now(),now()))
        for role,email in [('owner','audit-owner@example.invalid'),('viewer','audit-viewer@example.invalid')]:
            c.execute('INSERT INTO admins(email,password_hash,created_at,role) VALUES(%s,%s,%s,%s) ON CONFLICT(email) DO NOTHING',(email,generate_password_hash('test-password-only-12345'),now(),role))
        c.commit()
    app.config.update(TESTING=True)

@pytest.fixture
def client():return app.test_client()

@pytest.fixture
def owner():
    c=app.test_client()
    with app.app_context():
        row=db().execute('SELECT * FROM admins WHERE email=%s',('audit-owner@example.invalid',)).fetchone()
    with c.session_transaction() as s:s['admin_id']=row['id'];s['admin_version']=row['session_version']
    return c

@pytest.fixture
def customer():
    c=app.test_client()
    with app.app_context():
        conn=db();row=conn.execute('INSERT INTO customers(email,password_hash,whatsapp,created_at) VALUES(%s,%s,%s,%s) ON CONFLICT(email) DO UPDATE SET email=excluded.email RETURNING id,session_version',('audit-customer@example.invalid',generate_password_hash('test-password-only-12345'),'5584999999999',now())).fetchone();conn.commit()
    with c.session_transaction() as s:s['customer_id']=row['id'];s['customer_version']=row['session_version']
    return c

def mutate(client,url,method='POST',**kwargs):
    csrf=client.get('/api/csrf').json['token'];headers=kwargs.pop('headers',{});headers['X-CSRF-Token']=csrf
    return client.open(url,method=method,headers=headers,**kwargs)

@pytest.fixture
def product(owner):
    import io,secrets
    from PIL import Image
    with app.app_context():cat=db().execute("SELECT id FROM categories WHERE name<>'Sem categoria' ORDER BY id LIMIT 1").fetchone()['id']
    data={'name':'AUDITORIA '+secrets.token_hex(4),'description':'Descrição inicial','care':'Guardar em local seco.','category_id':cat,'material':'Aço','modality':'Pronta entrega','price':120,'promo_percent':10,'status':'draft','photos':[],'sizes':['17 cm','19 cm'],'colors':['Dourado']}
    r=mutate(owner,'/api/admin/product',json=data);assert r.status_code==200,r.json
    pid=r.json['id'];buf=io.BytesIO();Image.new('RGB',(50,50),'red').save(buf,'PNG');buf.seek(0)
    r=mutate(owner,f'/api/admin/product/{pid}/photo',data={'photo':(buf,'print.png')});assert r.status_code==200,r.json
    data.update(id=pid,photos=r.json['photos'],status='published')
    r=mutate(owner,'/api/admin/product',json=data);assert r.status_code==200,r.json
    return r.json
