from flask import g, abort, Flask, render_template, request, jsonify, session, send_from_directory, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import os, json, secrets, re, io
from dotenv import load_dotenv
load_dotenv()
import psycopg
from psycopg.rows import dict_row
from PIL import Image, ImageOps
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from urllib.parse import urlparse
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.exceptions import HTTPException
from migrations import migrate
from media import normalize_image, store_image

BASE=os.path.dirname(os.path.abspath(__file__))
DATABASE_URL=os.environ.get('DATABASE_URL','').strip()
UPLOAD=os.path.join(BASE,'static','uploads')
os.makedirs(UPLOAD,exist_ok=True)
app=Flask(__name__)
app.secret_key=os.environ.get('LUMINA_SECRET')
if not app.secret_key:
    raise RuntimeError('LUMINA_SECRET não configurada.')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.environ.get('RENDER') == 'true')
app.config['MAX_CONTENT_LENGTH']=21*1024*1024
app.config['PERMANENT_SESSION_LIFETIME']=timedelta(hours=12)
app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=1)

SCHEMA='''
CREATE TABLE IF NOT EXISTS uploaded_images(name TEXT PRIMARY KEY,data BYTEA NOT NULL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS admins(id SERIAL PRIMARY KEY,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS customers(id SERIAL PRIMARY KEY,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,whatsapp TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS categories(id SERIAL PRIMARY KEY,name TEXT UNIQUE NOT NULL,position INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS subcategories(id SERIAL PRIMARY KEY,category_id INTEGER NOT NULL,name TEXT NOT NULL,position INTEGER NOT NULL DEFAULT 0,UNIQUE(category_id,name));
CREATE TABLE IF NOT EXISTS colors(id SERIAL PRIMARY KEY,name TEXT UNIQUE NOT NULL,position INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS products(id SERIAL PRIMARY KEY,code TEXT UNIQUE NOT NULL,name TEXT NOT NULL,description TEXT NOT NULL,category_id INTEGER NOT NULL,subcategory_id INTEGER,material TEXT,sizes TEXT NOT NULL DEFAULT '[]',colors TEXT NOT NULL DEFAULT '[]',care TEXT NOT NULL,modality TEXT NOT NULL,price REAL NOT NULL,promo_percent REAL NOT NULL DEFAULT 0,highlighted INTEGER NOT NULL DEFAULT 0,status TEXT NOT NULL DEFAULT 'draft',photos TEXT NOT NULL DEFAULT '[]',variation_photos TEXT NOT NULL DEFAULT '{}',created_at TEXT NOT NULL,updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS carts(customer_id INTEGER PRIMARY KEY,items TEXT NOT NULL DEFAULT '[]',updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS orders(id SERIAL PRIMARY KEY,code TEXT UNIQUE NOT NULL,customer_id INTEGER NOT NULL,status TEXT NOT NULL,items TEXT NOT NULL,subtotal REAL NOT NULL,total REAL NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS order_changes(id SERIAL PRIMARY KEY,order_id INTEGER NOT NULL,action TEXT NOT NULL,details TEXT NOT NULL,created_at TEXT NOT NULL);
'''

def db():
    if not DATABASE_URL: raise RuntimeError('DATABASE_URL não configurada.')
    if 'database' not in g:
        g.database=psycopg.connect(DATABASE_URL,row_factory=dict_row,connect_timeout=15,prepare_threshold=None)
    if g.database.closed:
        g.database=psycopg.connect(DATABASE_URL,row_factory=dict_row,connect_timeout=15,prepare_threshold=None)
    return g.database

def safe_media(url,c):
    if not isinstance(url,str):return False
    if url=='/static/placeholder.svg':return True
    if url.startswith('/uploads/'):
        name=url.removeprefix('/uploads/')
        return bool(re.fullmatch(r'[a-f0-9]{24,32}\.jpg',name) and (c.execute('SELECT 1 FROM uploaded_images WHERE name=%s',(name,)).fetchone() or os.path.isfile(os.path.join(UPLOAD,name))))
    if url.startswith('/static/uploads/'):
        name=url.removeprefix('/static/uploads/')
        return bool(re.fullmatch(r'[a-f0-9]{24,32}\.jpg',name) and os.path.isfile(os.path.join(UPLOAD,name)))
    return False

def now(): return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec='seconds')
def money(v):
    return float(Decimal(str(v)).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP))
def clean_digits(v): return ''.join(ch for ch in str(v or '') if ch.isdigit())

def init():
    # Explicit deployment command only. No demo data and no writes during import.
    c=db()
    migrate(c,SCHEMA)
    defaults={'store_name':'Lumina Signature','whatsapp':'','instagram':'','footer_phrase':'Brilhe do seu jeito. ✨','above_footer':'','contact_email':'','contact_extra':'','admin_email':'admin@lumina.local'}
    for k,v in defaults.items():
        c.execute('INSERT INTO settings(key,value) VALUES(%s,%s) ON CONFLICT(key) DO NOTHING',(k,v))
    c.commit()
    c.close()

def settings():
    c=db(); s={r['key']:r['value'] for r in c.execute('SELECT * FROM settings')}; c.close(); return s

def product_dict(r):
    d=dict(r)
    d['price']=float(d['price']);d['promo_percent']=float(d['promo_percent'])
    for k in ('photos','sizes','colors'):
        try:d[k]=json.loads(d[k] or '[]')
        except:d[k]=[]
    try:d['variation_photos']=json.loads(d['variation_photos'] or '{}')
    except:d['variation_photos']={}
    d['final_price']=money(d['price']*(1-d['promo_percent']/100))
    d['highlighted']=bool(d['highlighted'])
    return d

def require_admin():
    aid=session.get('admin_id')
    if not aid:return None
    c=db();r=c.execute('SELECT id,role,session_version FROM admins WHERE id=%s',(aid,)).fetchone()
    if not r or r['session_version']!=session.get('admin_version'):
        session.clear();return None
    return aid
def require_customer():
    cid=session.get('customer_id')
    if not cid:return None
    c=db();r=c.execute('SELECT id,session_version FROM customers WHERE id=%s',(cid,)).fetchone()
    if not r or r['session_version']!=session.get('customer_version'):
        session.clear();return None
    return cid

def categories_data():
    c=db(); out=[dict(r) for r in c.execute('SELECT * FROM categories ORDER BY position,id')]; c.close(); return out

@app.route('/')
def home(): return render_template('index.html')
@app.route('/product/<int:pid>')
def product(pid): return render_template('product.html',pid=pid)
@app.route('/cart')
def cart(): return render_template('cart.html')
@app.route('/account')
def account(): return render_template('account.html')
@app.route('/admin')
def admin(): return render_template('admin.html')
@app.route('/uploads/<path:name>')
def uploads(name):
    if not re.fullmatch(r'[a-f0-9]{24,32}\.jpg',name):abort(404)
    c=db();image=c.execute('SELECT data,mime_type FROM uploaded_images WHERE name=%s',(name,)).fetchone();c.close()
    if image:
        import hashlib
        return send_file(io.BytesIO(bytes(image['data'])),mimetype=image['mime_type'],etag=hashlib.sha256(bytes(image['data'])).hexdigest(),max_age=86400,conditional=True)
    return send_from_directory(UPLOAD,name)

@app.get('/api/settings')
def api_settings(): return jsonify(settings())
@app.get('/api/categories')
def api_categories(): return jsonify(categories_data())

@app.get('/api/colors')
def api_colors():
    c=db(); rows=[dict(r) for r in c.execute('SELECT * FROM colors ORDER BY position,id')]; c.close(); return jsonify(rows)

@app.get('/api/products')
def api_products():
    c=db(); q=request.args.get('q','').strip(); cat=request.args.get('category'); color=request.args.get('color'); size=request.args.get('size'); material=request.args.get('material'); promo=request.args.get('promo'); modality=request.args.get('modality'); sort=request.args.get('sort','recent')
    sql="SELECT p.*,c.name category_name FROM products p LEFT JOIN categories c ON c.id=p.category_id WHERE p.status='published' AND p.deleted_at IS NULL"; args=[]
    if q: sql+=' AND lower(p.name) LIKE lower(%s)'; args.append('%'+q+'%')
    if cat: sql+=' AND p.category_id=%s'; args.append(int(cat))
    sub=request.args.get('subcategory')
    if sub:sql+=' AND p.subcategory_id=%s';args.append(int(sub))
    if promo=='1': sql+=' AND p.promo_percent>0'
    if modality: sql+=' AND p.modality=%s'; args.append(modality)
    sql += {'price_asc':' ORDER BY (p.price*(1-p.promo_percent/100)) ASC','price_desc':' ORDER BY (p.price*(1-p.promo_percent/100)) DESC','az':' ORDER BY lower(p.name) ASC','za':' ORDER BY lower(p.name) DESC'}.get(sort,' ORDER BY p.created_at DESC')
    rows=[product_dict(r) for r in c.execute(sql,args)]
    c.close()
    if color: rows=[p for p in rows if color in p['colors']]
    if size: rows=[p for p in rows if size in p['sizes']]
    if material: rows=[p for p in rows if material.lower() in (p['material'] or '').lower()]
    return jsonify(rows)

@app.get('/api/featured')
def api_featured():
    cutoff=(datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(days=30)).isoformat(timespec='seconds')
    c=db(); rows=c.execute("SELECT items FROM orders WHERE status='Confirmado' AND created_at>=%s",(cutoff,)).fetchall(); totals={}
    for row in rows:
        try: items=json.loads(row['items'] or '[]')
        except: items=[]
        for item in items:
            pid=item.get('product_id'); qty=max(0,int(item.get('qty',0)))
            if pid: totals[int(pid)]=totals.get(int(pid),0)+qty
    ids=sorted(totals,key=lambda pid:(-totals[pid],pid))[:10]
    manual=[r['id'] for r in c.execute("SELECT id FROM products WHERE highlighted=1 AND status='published' AND deleted_at IS NULL ORDER BY created_at DESC")]
    ids=list(dict.fromkeys(manual+ids))[:10]
    if not ids: c.close(); return jsonify([])
    ph=','.join(['%s']*len(ids)); found={r['id']:product_dict(r) for r in c.execute(f'SELECT p.*,c.name category_name FROM products p LEFT JOIN categories c ON c.id=p.category_id WHERE p.status=\'published\' AND p.deleted_at IS NULL AND p.id IN ({ph})',ids)}; c.close()
    return jsonify([{**found[pid],'units_sold_30d':totals.get(pid,0)} for pid in ids if pid in found])

@app.get('/api/product/<int:pid>')
def api_product(pid):
    c=db();r=c.execute("SELECT p.*,c.name category_name FROM products p LEFT JOIN categories c ON c.id=p.category_id WHERE p.id=%s AND p.status='published' AND p.deleted_at IS NULL",(pid,)).fetchone();c.close()
    return jsonify(product_dict(r)) if r else (jsonify({'error':'Produto não encontrado.'}),404)

@app.post('/api/register')
def register():
    d=request.json or {}; email=d.get('email','').strip().lower(); pw=d.get('password',''); conf=d.get('confirm',''); wa=d.get('whatsapp','').strip()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+',email) or not 10<=len(pw)<=128 or pw!=conf or not 10<=len(clean_digits(wa))<=15:return jsonify({'error':'Preencha e confirme todos os campos.'}),400
    c=db()
    try:
        cur=c.execute('INSERT INTO customers(email,password_hash,whatsapp,created_at) VALUES(%s,%s,%s,%s) RETURNING id',(email,generate_password_hash(pw),wa,now())); cid=cur.fetchone()['id']; c.execute('INSERT INTO carts(customer_id,items,updated_at) VALUES(%s,%s,%s)',(cid,'[]',now())); c.commit()
    except psycopg.IntegrityError:
        c.rollback(); c.close(); return jsonify({'error':'Este e-mail já possui uma conta.'}),400
    c.close(); session.clear();session['customer_id']=cid;session['customer_version']=1;session.permanent=True;return jsonify({'ok':True})

@app.post('/api/login')
def login():
    d=request.json or {}; email=d.get('email','').strip().lower(); c=db(); r=c.execute('SELECT * FROM customers WHERE email=%s',(email,)).fetchone(); c.close()
    if not r or not check_password_hash(r['password_hash'],d.get('password','')):return jsonify({'error':'E-mail ou senha inválidos.'}),401
    session.clear();session['customer_id']=r['id'];session['customer_version']=r['session_version'];session.permanent=True;return jsonify({'ok':True})
@app.post('/api/logout')
def logout(): session.clear(); return jsonify({'ok':True})
@app.get('/api/me')
def me():
    c=db(); out={'customer':None,'admin':None}
    if require_customer():
        r=c.execute('SELECT id,email,whatsapp FROM customers WHERE id=%s',(require_customer(),)).fetchone(); out['customer']=dict(r) if r else None
    if require_admin():
        r=c.execute('SELECT id,email,role FROM admins WHERE id=%s',(require_admin(),)).fetchone(); out['admin']=dict(r) if r else None
    c.close(); return jsonify(out)

@app.post('/api/customer/password')
def customer_password():
    cid=require_customer(); d=request.json or {}; c=db(); r=c.execute('SELECT password_hash FROM customers WHERE id=%s',(cid,)).fetchone()
    if not r or not check_password_hash(r['password_hash'],d.get('current','')): c.close(); return jsonify({'error':'Senha atual incorreta.'}),400
    if not 10<=len(d.get('new',''))<=128 or d.get('new')!=d.get('confirm'): c.close(); return jsonify({'error':'As novas senhas não coincidem.'}),400
    c.execute('UPDATE customers SET password_hash=%s,session_version=session_version+1 WHERE id=%s',(generate_password_hash(d['new']),cid)); c.commit(); c.close(); return jsonify({'ok':True})
@app.post('/api/customer/whatsapp')
def customer_whatsapp():
    cid=require_customer(); wa=(request.json or {}).get('whatsapp','').strip()
    if not cid:return jsonify({'error':'Faça login.'}),401
    if not wa:return jsonify({'error':'Informe o WhatsApp.'}),400
    c=db(); c.execute('UPDATE customers SET whatsapp=%s WHERE id=%s',(wa,cid)); c.commit(); c.close(); return jsonify({'ok':True})

@app.get('/api/cart')
def get_cart():
    cid=require_customer()
    if not cid:return jsonify({'items':[]})
    c=db(); r=c.execute('SELECT items FROM carts WHERE customer_id=%s',(cid,)).fetchone(); c.close(); return jsonify({'items':json.loads(r['items']) if r else []})


@app.get('/api/orders')
def orders():
    cid=require_customer();
    if not cid:return jsonify({'error':'login'}),401
    c=db(); rows=c.execute('SELECT * FROM orders WHERE customer_id=%s ORDER BY created_at DESC',(cid,)).fetchall(); out=[]; changed=False
    for r in rows:
        d=dict(r)
        if d['status']=='Aguardando confirmação' and datetime.fromisoformat(d['expires_at'])<datetime.now(timezone.utc).replace(tzinfo=None):
            c.execute("UPDATE orders SET status='Cancelado',updated_at=%s WHERE id=%s",(now(),d['id'])); c.execute('INSERT INTO order_changes(order_id,action,details,created_at) VALUES(%s,%s,%s,%s)',(d['id'],'Cancelamento automático','Pedido passou 30 dias sem confirmação',now())); d['status']='Cancelado'; changed=True
        d['total']=float(d['total']);d['subtotal']=float(d['subtotal']);d['items']=json.loads(d['items']);out.append(d)
    if changed:c.commit()
    c.close(); return jsonify(out)

# ADMIN
@app.post('/api/admin/login')
def admin_login():
    d=request.json or {}; c=db(); r=c.execute('SELECT * FROM admins WHERE email=%s',(d.get('email','').strip().lower(),)).fetchone(); c.close()
    if not r or not check_password_hash(r['password_hash'],d.get('password','')):return jsonify({'error':'Acesso administrativo inválido.'}),401
    session.clear();session['admin_id']=r['id'];session['admin_version']=r['session_version'];session.permanent=True;return jsonify({'ok':True})
@app.get('/api/admin/stats')
def admin_stats():
    if not require_admin():return jsonify({'error':'forbidden'}),403
    c=db(); confirmed=c.execute("SELECT COUNT(*) n,COALESCE(SUM(total),0) s FROM orders WHERE status='Confirmado'").fetchone(); pending=c.execute("SELECT COUNT(*) n FROM orders WHERE status='Aguardando confirmação'").fetchone()['n']; canceled=c.execute("SELECT COUNT(*) n FROM orders WHERE status='Cancelado'").fetchone()['n']; products=0
    for row in c.execute("SELECT items FROM orders WHERE status='Confirmado'"):
        try: products += sum(max(0,int(x.get('qty',0))) for x in json.loads(row['items'] or '[]'))
        except: pass
    c.close(); return jsonify({'sales':money(confirmed['s']),'confirmed_orders':confirmed['n'],'pending':pending,'canceled':canceled,'products_sold':products,'ticket':money(confirmed['s']/confirmed['n']) if confirmed['n'] else 0})

@app.get('/api/admin/top-products')
def admin_top_products():
    if not require_admin():return jsonify({'error':'forbidden'}),403
    try: days=max(1,min(365,int(request.args.get('days',30))))
    except: days=30
    cutoff=(datetime.now(timezone.utc).replace(tzinfo=None)-timedelta(days=days)).isoformat(timespec='seconds')
    c=db(); rows=c.execute("SELECT items FROM orders WHERE status='Confirmado' AND created_at>=%s",(cutoff,)).fetchall(); stats={}
    for row in rows:
        try: items=json.loads(row['items'] or '[]')
        except: items=[]
        for item in items:
            pid=item.get('product_id'); qty=max(0,int(item.get('qty',0)))
            if not pid: continue
            rec=stats.setdefault(int(pid),{'units':0,'orders':0,'revenue':0}); rec['units']+=qty; rec['orders']+=1; rec['revenue']+=float(item.get('unit_price',0))*qty
    ids=sorted(stats,key=lambda pid:(-stats[pid]['units'],-stats[pid]['orders'],pid))[:10]
    if not ids:c.close();return jsonify([])
    ph=','.join(['%s']*len(ids)); products={r['id']:dict(r) for r in c.execute(f'SELECT id,name,code FROM products WHERE id IN ({ph})',ids)}; c.close()
    return jsonify([{'product_id':pid,'name':products.get(pid,{}).get('name','Produto removido'),'code':products.get(pid,{}).get('code',''),'units':stats[pid]['units'],'orders':stats[pid]['orders'],'revenue':money(stats[pid]['revenue'])} for pid in ids])

@app.get('/api/admin/orders')
def admin_orders():
    if not require_admin():return jsonify({'error':'forbidden'}),403
    c=db(); rows=c.execute('SELECT o.*,c.email,c.whatsapp FROM orders o JOIN customers c ON c.id=o.customer_id ORDER BY o.created_at DESC').fetchall(); out=[]
    for r in rows:
        d=dict(r);d['total']=float(d['total']);d['subtotal']=float(d['subtotal']);d['items']=json.loads(d['items']);out.append(d)
    c.close(); return jsonify(out)
@app.get('/api/admin/order/<int:oid>/history')
def order_history(oid):
    if not require_admin():return jsonify({'error':'forbidden'}),403
    c=db(); rows=[dict(r) for r in c.execute('SELECT * FROM order_changes WHERE order_id=%s ORDER BY created_at DESC',(oid,))]; c.close(); return jsonify(rows)
@app.post('/api/admin/order/<int:oid>/status')
def admin_status(oid):
    if not require_admin():return jsonify({'error':'forbidden'}),403
    status=(request.json or {}).get('status');
    if status not in ['Aguardando confirmação','Confirmado','Cancelado']:return jsonify({'error':'Status inválido.'}),400
    c=db(); r=c.execute('SELECT status FROM orders WHERE id=%s FOR UPDATE',(oid,)).fetchone()
    if not r:c.close();return jsonify({'error':'Pedido não encontrado.'}),404
    old=r['status']
    if old==status:c.close();return jsonify({'ok':True})
    # Reopening is allowed only when currently cancelled.
    if old!='Cancelado' and old!='Aguardando confirmação' and status=='Aguardando confirmação': c.close(); return jsonify({'error':'Só pedidos cancelados podem ser reabertos.'}),400
    if old=='Confirmado' and status=='Cancelado': pass
    c.execute('UPDATE orders SET status=%s,updated_at=%s WHERE id=%s',(status,now(),oid)); c.execute('INSERT INTO order_changes(order_id,action,details,created_at) VALUES(%s,%s,%s,%s)',(oid,'Status alterado',f'{old} → {status}',now())); c.commit(); c.close(); return jsonify({'ok':True})

@app.get('/api/admin/products')
def admin_products():
    if not require_admin():return jsonify({'error':'forbidden'}),403
    c=db(); rows=[product_dict(r) for r in c.execute('SELECT * FROM products WHERE deleted_at IS NULL ORDER BY created_at DESC')]; c.close(); return jsonify(rows)

@app.post('/api/admin/product')
def admin_product_save():
    d=request.get_json() or {};c=db();ts=now()
    for key in ('name','description','care'):
        if not isinstance(d.get(key),str) or not d[key].strip():raise ValueError('Preencha nome, descrição e cuidados.')
        if len(d[key])>(200 if key=='name' else 8000):raise ValueError('Texto maior que o permitido.')
    status=d.get('status','draft')
    if status not in ('published','draft'):raise ValueError('Status inválido.')
    cat=int(d.get('category_id',0))
    if not c.execute('SELECT 1 FROM categories WHERE id=%s',(cat,)).fetchone():raise ValueError('Selecione uma categoria cadastrada.')
    sub=d.get('subcategory_id') or None
    if sub and not c.execute('SELECT 1 FROM subcategories WHERE id=%s AND category_id=%s',(sub,cat)).fetchone():raise ValueError('Subcategoria incompatível.')
    price=Decimal(str(d.get('price',0)));promo=Decimal(str(d.get('promo_percent',0)))
    if not price.is_finite() or not promo.is_finite() or price<=0 or price>9999999 or not 0<=promo<=100:raise ValueError('Preço ou desconto inválido.')
    def choices(key):
        value=d.get(key,[])
        if not isinstance(value,list) or len(value)>50 or any(not isinstance(v,str) or not v.strip() or len(v)>80 for v in value):raise ValueError('Cores ou tamanhos inválidos.')
        return list(dict.fromkeys(v.strip() for v in value))
    colors=choices('colors');sizes=choices('sizes')
    registered={r['name'] for r in c.execute('SELECT name FROM colors')}
    if any(v not in registered for v in colors):raise ValueError('Selecione somente cores cadastradas.')
    modality=d.get('modality')
    if modality not in ('Pronta entrega','Sob encomenda'):raise ValueError('Modalidade inválida.')
    pid=d.get('id');previous=None
    if pid:
        previous=c.execute('SELECT * FROM products WHERE id=%s AND deleted_at IS NULL FOR UPDATE',(int(pid),)).fetchone()
        if not previous:abort(404)
    photos=d.get('photos',json.loads(previous['photos']) if previous else [])
    if not isinstance(photos,list) or len(photos)>12:raise ValueError('Lista de fotos inválida.')
    for url in photos:
        if not safe_media(url,c):raise ValueError('Imagem não pertence ao armazenamento da loja.')
    if status=='published' and not photos:raise ValueError('Produto publicado precisa de pelo menos uma foto.')
    variations=d.get('variation_photos',json.loads(previous['variation_photos']) if previous else {})
    if not isinstance(variations,dict) or any(k not in colors or v not in photos for k,v in variations.items()):raise ValueError('Associe cada foto de variação a uma cor e imagem do produto.')
    vals=(d['name'].strip(),d['description'].strip(),cat,sub,str(d.get('material','')).strip()[:200],json.dumps(sizes,ensure_ascii=False),json.dumps(colors,ensure_ascii=False),d['care'].strip(),modality,money(price),float(promo),int(bool(d.get('highlighted',previous['highlighted'] if previous else False))),status,json.dumps(photos),json.dumps(variations),ts)
    if previous:
        c.execute('UPDATE products SET name=%s,description=%s,category_id=%s,subcategory_id=%s,material=%s,sizes=%s,colors=%s,care=%s,modality=%s,price=%s,promo_percent=%s,highlighted=%s,status=%s,photos=%s,variation_photos=%s,updated_at=%s WHERE id=%s',vals+(int(pid),))
    else:
        pid=c.execute('INSERT INTO products(code,name,description,category_id,subcategory_id,material,sizes,colors,care,modality,price,promo_percent,highlighted,status,photos,variation_photos,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',('PRD-'+secrets.token_hex(6).upper(),)+vals+(ts,)).fetchone()['id']
    c.commit();r=c.execute('SELECT * FROM products WHERE id=%s',(pid,)).fetchone();return jsonify(product_dict(r))
@app.post('/api/admin/product/<int:pid>/photo')
def admin_photo(pid):
    if not require_admin():return jsonify({'error':'Faça login como administradora.'}),403
    f=request.files.get('photo')
    if not f:return jsonify({'error':'Selecione uma imagem.'}),400
    c=db();r=c.execute('SELECT photos FROM products WHERE id=%s AND deleted_at IS NULL FOR UPDATE',(pid,)).fetchone()
    if not r:abort(404)
    photos=json.loads(r['photos'] or '[]')
    if len(photos)>=12:return jsonify({'error':'Limite de 12 fotos por produto.'}),400
    try:image_bytes=normalize_image(f.stream)
    except ValueError as exc:return jsonify({'error':str(exc)}),400
    path=store_image(c,image_bytes);photos.append(path)
    c.execute('UPDATE products SET photos=%s,updated_at=%s WHERE id=%s',(json.dumps(photos),now(),pid));c.commit()
    return jsonify({'ok':True,'photos':photos})
@app.post('/api/admin/product/<int:pid>/main-photo')
def admin_main_photo(pid):
    if not require_admin():return jsonify({'error':'forbidden'}),403
    idx=int((request.json or {}).get('index',0)); c=db(); r=c.execute('SELECT photos FROM products WHERE id=%s',(pid,)).fetchone();
    if not r:return jsonify({'error':'Produto não encontrado.'}),404
    photos=json.loads(r['photos'] or '[]');
    if idx<0 or idx>=len(photos):c.close();return jsonify({'error':'Foto inválida.'}),400
    photos=[photos[idx]]+[p for i,p in enumerate(photos) if i!=idx]; c.execute('UPDATE products SET photos=%s,updated_at=%s WHERE id=%s',(json.dumps(photos),now(),pid)); c.commit(); c.close(); return jsonify({'ok':True,'photos':photos})
@app.delete('/api/admin/product/<int:pid>/photo')
def admin_delete_photo(pid):
    idx=int(request.args.get('index',-1));c=db();r=c.execute('SELECT photos,variation_photos,status FROM products WHERE id=%s AND deleted_at IS NULL FOR UPDATE',(pid,)).fetchone()
    if not r:abort(404)
    photos=json.loads(r['photos']);variations=json.loads(r['variation_photos'])
    if idx<0 or idx>=len(photos):raise ValueError('Foto inválida.')
    if r['status']=='published' and len(photos)==1:raise ValueError('Mantenha uma foto no produto publicado ou salve como rascunho.')
    removed=photos.pop(idx);variations={k:v for k,v in variations.items() if v!=removed}
    c.execute('UPDATE products SET photos=%s,variation_photos=%s,updated_at=%s WHERE id=%s',(json.dumps(photos),json.dumps(variations),now(),pid));c.commit()
    # Keep media bytes: references and backup/rollback must remain valid.
    return jsonify({'ok':True,'photos':photos})
@app.delete('/api/admin/product/<int:pid>')
def admin_product_delete(pid):
    c=db();r=c.execute('UPDATE products SET deleted_at=%s,status=%s,updated_at=%s WHERE id=%s AND deleted_at IS NULL RETURNING id',(now(),'draft',now(),pid)).fetchone()
    if not r:abort(404)
    c.commit();return jsonify({'ok':True})

@app.post('/api/admin/category')
def admin_category():
    if not require_admin():return jsonify({'error':'forbidden'}),403
    d=request.json or {}; name=d.get('name','').strip()
    if not name:return jsonify({'error':'Nome obrigatório.'}),400
    c=db()
    try:
        c.execute('INSERT INTO categories(name,position) VALUES(%s,%s)',(name,999))
        c.commit()
    except psycopg.IntegrityError:
        c.rollback(); c.close();return jsonify({'error':'Já existe.'}),400
    c.close();return jsonify({'ok':True})
@app.delete('/api/admin/category/<int:cid>')
def admin_category_delete(cid):
    c=db();row=c.execute('SELECT name FROM categories WHERE id=%s FOR UPDATE',(cid,)).fetchone()
    if not row:abort(404)
    if row['name']=='Sem categoria':raise ValueError('A categoria de segurança não pode ser excluída.')
    unc=c.execute("SELECT id FROM categories WHERE name='Sem categoria'").fetchone()['id']
    linked=c.execute('UPDATE products SET category_id=%s,subcategory_id=NULL WHERE category_id=%s',(unc,cid)).rowcount
    c.execute('DELETE FROM subcategories WHERE category_id=%s',(cid,));c.execute('DELETE FROM categories WHERE id=%s',(cid,));c.commit()
    return jsonify({'ok':True,'moved_to_uncategorized':linked})

@app.delete('/api/admin/subcategory/<int:sid>')
def admin_subcategory_delete(sid):
    if not require_admin(): return jsonify({'error':'forbidden'}),403
    c=db(); c.execute('UPDATE products SET subcategory_id=NULL WHERE subcategory_id=%s',(sid,)); c.execute('DELETE FROM subcategories WHERE id=%s',(sid,)); c.commit(); c.close(); return jsonify({'ok':True})

@app.post('/api/admin/color')
def admin_color():
    if not require_admin(): return jsonify({'error':'forbidden'}),403
    name=(request.json or {}).get('name','').strip()
    if not name: return jsonify({'error':'Nome da cor é obrigatório.'}),400
    c=db()
    try:
        c.execute('INSERT INTO colors(name,position) VALUES(%s,%s)',(name,9999)); c.commit()
    except psycopg.IntegrityError:
        c.rollback(); c.close(); return jsonify({'error':'Essa cor já existe.'}),400
    c.close(); return jsonify({'ok':True})

@app.delete('/api/admin/color/<int:cid>')
def admin_color_delete(cid):
    if not require_admin(): return jsonify({'error':'forbidden'}),403
    c=db(); r=c.execute('SELECT name FROM colors WHERE id=%s',(cid,)).fetchone()
    if not r: c.close(); return jsonify({'error':'Cor não encontrada.'}),404
    # Removing a color from the list also removes it from products so it cannot remain selectable in the store.
    rows=c.execute('SELECT id,colors FROM products').fetchall()
    for row in rows:
        try: vals=json.loads(row['colors'] or '[]')
        except: vals=[]
        new=[v for v in vals if v!=r['name']]
        if new!=vals: c.execute('UPDATE products SET colors=%s,updated_at=%s WHERE id=%s',(json.dumps(new,ensure_ascii=False),now(),row['id']))
    c.execute('DELETE FROM colors WHERE id=%s',(cid,)); c.commit(); c.close(); return jsonify({'ok':True})

@app.post('/api/admin/settings')
def admin_settings():
    d=request.get_json() or {};allowed={'whatsapp','instagram','store_name','footer_phrase','above_footer','contact_email','contact_extra','logo','banner'};c=db()
    for k in allowed.intersection(d):
        value=str(d[k] or '').strip()
        if len(value)>2000:raise ValueError('Configuração muito longa.')
        if k=='whatsapp':
            value=clean_digits(value)
            if len(value) in (10,11):value='55'+value
            if value and not 12<=len(value)<=15:raise ValueError('Informe WhatsApp com DDI e DDD.')
        if k in ('logo','banner') and value and not safe_media(value,c):raise ValueError('Envie a imagem pelo botão de upload.')
        if k=='instagram' and value:
            value=value.removeprefix('https://www.instagram.com/').removeprefix('https://instagram.com/').strip('/').lstrip('@')
            if not re.fullmatch(r'[A-Za-z0-9_.]{1,30}',value):raise ValueError('Instagram inválido.')
        c.execute('INSERT INTO settings(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,value))
    c.commit();return jsonify({'ok':True})
@app.post('/api/admin/password')
def admin_password():
    if not require_admin():return jsonify({'error':'forbidden'}),403
    d=request.json or {}; c=db(); r=c.execute('SELECT password_hash FROM admins WHERE id=%s',(require_admin(),)).fetchone()
    if not r or not check_password_hash(r['password_hash'],d.get('current','')):c.close();return jsonify({'error':'Senha atual incorreta.'}),400
    if not 10<=len(d.get('new',''))<=128 or d.get('new')!=d.get('confirm'):c.close();return jsonify({'error':'As novas senhas não coincidem.'}),400
    c.execute('UPDATE admins SET password_hash=%s,session_version=session_version+1 WHERE id=%s',(generate_password_hash(d['new']),require_admin()));c.commit();c.close();return jsonify({'ok':True})

@app.errorhandler(404)
def notfound(e): return jsonify({'error':'Não encontrado.'}),404

from hardening import install
install(app,db,require_admin,require_customer)
from extensions import install as install_extensions
install_extensions(app,db,now,safe_media)
from commerce import install as install_commerce
install_commerce(app,db,product_dict,require_customer,now)

if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5000')), debug=False)
