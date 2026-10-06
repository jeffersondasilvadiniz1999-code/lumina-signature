from flask import Flask, render_template, request, jsonify, session, send_from_directory, send_file
from werkzeug.security import generate_password_hash, check_password_hash
import os, json, secrets, re, io
from dotenv import load_dotenv
load_dotenv()
import psycopg
from psycopg.rows import dict_row
from PIL import Image, ImageOps
from datetime import datetime, timedelta

BASE=os.path.dirname(os.path.abspath(__file__))
DATABASE_URL=os.environ.get('DATABASE_URL','').strip()
UPLOAD=os.path.join(BASE,'static','uploads')
os.makedirs(UPLOAD,exist_ok=True)
app=Flask(__name__)
app.secret_key=os.environ.get('LUMINA_SECRET')
if not app.secret_key:
    raise RuntimeError('LUMINA_SECRET não configurada.')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.environ.get('RENDER') == 'true')
app.config['MAX_CONTENT_LENGTH']=8*1024*1024

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
    if not DATABASE_URL:
        raise RuntimeError('DATABASE_URL não configurada.')
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)

def now(): return datetime.utcnow().isoformat(timespec='seconds')
def money(v): return round(float(v),2)
def clean_digits(v): return ''.join(ch for ch in str(v or '') if ch.isdigit())

def init():
    c=db()
    for statement in SCHEMA.split(';'):
        if statement.strip(): c.execute(statement)
    defaults={'store_name':'Lumina Signature','whatsapp':'','instagram':'','footer_phrase':'Brilhe do seu jeito. ✨','above_footer':'','contact_email':'','contact_extra':'','admin_email':'admin@lumina.local'}
    for k,v in defaults.items(): c.execute('INSERT INTO settings(key,value) VALUES(%s,%s) ON CONFLICT(key) DO NOTHING',(k,v))
    if not c.execute('SELECT 1 FROM admins').fetchone():
        if len(os.environ.get('ADMIN_INITIAL_PASSWORD','')) < 12:
            raise RuntimeError('Configure ADMIN_INITIAL_PASSWORD com pelo menos 12 caracteres para criar a administradora.')
        c.execute('INSERT INTO admins(email,password_hash,created_at) VALUES(%s,%s,%s)',(defaults['admin_email'],generate_password_hash(os.environ['ADMIN_INITIAL_PASSWORD']),now()))
    if not c.execute('SELECT 1 FROM categories').fetchone():
        for i,n in enumerate(['Anéis','Colares','Brincos','Pulseiras','Conjuntos','Braceletes']): c.execute('INSERT INTO categories(name,position) VALUES(%s,%s)',(n,i))
    c.execute('INSERT INTO categories(name,position) VALUES(%s,%s) ON CONFLICT(name) DO NOTHING',('Sem categoria',9999))
    if not c.execute('SELECT 1 FROM colors').fetchone():
        for i,n in enumerate(['Prata','Dourado','Rosé']): c.execute('INSERT INTO colors(name,position) VALUES(%s,%s)',(n,i))
    if not c.execute('SELECT 1 FROM products').fetchone():
        cats={r['name']:r['id'] for r in c.execute('SELECT * FROM categories')}
        samples=[
            ('PRD-TEST001','Colar Aurora','Peça delicada para compor o visual com elegância.',cats['Colares'],'Aço inoxidável',['45 cm','50 cm'],['Dourado','Rosé'],'Evite água e perfume.','Pronta entrega',144,0,1),
            ('PRD-TEST002','Brinco Bella','Brinco leve e versátil para o dia a dia.',cats['Brincos'],'Aço inoxidável',[],['Dourado','Prata'],'Evite produtos químicos.','Pronta entrega',79.90,0,1),
            ('PRD-TEST003','Pulseira Serena','Pulseira delicada com opções de tamanho.',cats['Pulseiras'],'Aço inoxidável',['17 cm','19 cm'],['Prata','Rosé'],'Guardar seca e longe de produtos químicos.','Sob encomenda',99.90,10,0)]
        for code,name,desc,cat,mat,sizes,colors,care,mod,price,promo,high in samples:
            c.execute('INSERT INTO products(code,name,description,category_id,subcategory_id,material,sizes,colors,care,modality,price,promo_percent,highlighted,status,photos,variation_photos,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(code,name,desc,cat,None,mat,json.dumps(sizes),json.dumps(colors),care,mod,price,promo,high,'published',json.dumps(['/static/placeholder.svg']),json.dumps({}),now(),now()))
    c.commit(); c.close()
init()

def settings():
    c=db(); s={r['key']:r['value'] for r in c.execute('SELECT * FROM settings')}; c.close(); return s

def product_dict(r):
    d=dict(r)
    for k in ('photos','sizes','colors'):
        try:d[k]=json.loads(d[k] or '[]')
        except:d[k]=[]
    try:d['variation_photos']=json.loads(d['variation_photos'] or '{}')
    except:d['variation_photos']={}
    d['final_price']=money(d['price']*(1-d['promo_percent']/100))
    d['highlighted']=bool(d['highlighted'])
    return d

def require_admin(): return session.get('admin_id')
def require_customer(): return session.get('customer_id')

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
    c=db(); image=c.execute('SELECT data FROM uploaded_images WHERE name=%s',(name,)).fetchone(); c.close()
    if image: return send_file(io.BytesIO(bytes(image['data'])),mimetype='image/jpeg')
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
    sql="SELECT p.*,c.name category_name FROM products p JOIN categories c ON c.id=p.category_id WHERE p.status='published'"; args=[]
    if q: sql+=' AND lower(p.name) LIKE lower(%s)'; args.append('%'+q+'%')
    if cat: sql+=' AND p.category_id=%s'; args.append(cat)
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
    cutoff=(datetime.utcnow()-timedelta(days=30)).isoformat(timespec='seconds')
    c=db(); rows=c.execute("SELECT items FROM orders WHERE status='Confirmado' AND created_at>=%s",(cutoff,)).fetchall(); totals={}
    for row in rows:
        try: items=json.loads(row['items'] or '[]')
        except: items=[]
        for item in items:
            pid=item.get('product_id'); qty=max(0,int(item.get('qty',0)))
            if pid: totals[int(pid)]=totals.get(int(pid),0)+qty
    ids=sorted(totals,key=lambda pid:(-totals[pid],pid))[:10]
    if not ids: c.close(); return jsonify([])
    ph=','.join(['%s']*len(ids)); found={r['id']:product_dict(r) for r in c.execute(f'SELECT p.*,c.name category_name FROM products p JOIN categories c ON c.id=p.category_id WHERE p.status="published" AND p.id IN ({ph})',ids)}; c.close()
    return jsonify([{**found[pid],'units_sold_30d':totals[pid]} for pid in ids if pid in found])

@app.get('/api/product/<int:pid>')
def api_product(pid):
    c=db(); r=c.execute('SELECT p.*,c.name category_name FROM products p JOIN categories c ON c.id=p.category_id WHERE p.id=%s',(pid,)).fetchone(); c.close()
    return jsonify(product_dict(r)) if r else (jsonify({'error':'Produto não encontrado.'}),404)

@app.post('/api/register')
def register():
    d=request.json or {}; email=d.get('email','').strip().lower(); pw=d.get('password',''); conf=d.get('confirm',''); wa=d.get('whatsapp','').strip()
    if not email or not pw or pw!=conf or not wa:return jsonify({'error':'Preencha e confirme todos os campos.'}),400
    c=db()
    try:
        cur=c.execute('INSERT INTO customers(email,password_hash,whatsapp,created_at) VALUES(%s,%s,%s,%s) RETURNING id',(email,generate_password_hash(pw),wa,now())); cid=cur.fetchone()['id']; c.execute('INSERT INTO carts(customer_id,items,updated_at) VALUES(%s,%s,%s)',(cid,'[]',now())); c.commit()
    except psycopg.IntegrityError:
        c.rollback(); c.close(); return jsonify({'error':'Este e-mail já possui uma conta.'}),400
    c.close(); session['customer_id']=cid; return jsonify({'ok':True})

@app.post('/api/login')
def login():
    d=request.json or {}; email=d.get('email','').strip().lower(); c=db(); r=c.execute('SELECT * FROM customers WHERE email=%s',(email,)).fetchone(); c.close()
    if not r or not check_password_hash(r['password_hash'],d.get('password','')):return jsonify({'error':'E-mail ou senha inválidos.'}),401
    session['customer_id']=r['id']; return jsonify({'ok':True})
@app.post('/api/logout')
def logout(): session.clear(); return jsonify({'ok':True})
@app.get('/api/me')
def me():
    c=db(); out={'customer':None,'admin':None}
    if require_customer():
        r=c.execute('SELECT id,email,whatsapp FROM customers WHERE id=%s',(require_customer(),)).fetchone(); out['customer']=dict(r) if r else None
    if require_admin():
        r=c.execute('SELECT id,email FROM admins WHERE id=%s',(require_admin(),)).fetchone(); out['admin']=dict(r) if r else None
    c.close(); return jsonify(out)

@app.post('/api/customer/password')
def customer_password():
    cid=require_customer(); d=request.json or {}; c=db(); r=c.execute('SELECT password_hash FROM customers WHERE id=%s',(cid,)).fetchone()
    if not r or not check_password_hash(r['password_hash'],d.get('current','')): c.close(); return jsonify({'error':'Senha atual incorreta.'}),400
    if not d.get('new') or d.get('new')!=d.get('confirm'): c.close(); return jsonify({'error':'As novas senhas não coincidem.'}),400
    c.execute('UPDATE customers SET password_hash=%s WHERE id=%s',(generate_password_hash(d['new']),cid)); c.commit(); c.close(); return jsonify({'ok':True})
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
@app.post('/api/cart')
def set_cart():
    cid=require_customer()
    if not cid:return jsonify({'error':'login'}),401
    items=(request.json or {}).get('items',[]); c=db(); c.execute('INSERT INTO carts(customer_id,items,updated_at) VALUES(%s,%s,%s) ON CONFLICT(customer_id) DO UPDATE SET items=excluded.items,updated_at=excluded.updated_at',(cid,json.dumps(items),now())); c.commit(); c.close(); return jsonify({'ok':True})

@app.post('/api/order')
def create_order():
    cid=require_customer()
    if not cid:return jsonify({'error':'Faça login para finalizar o pedido.'}),401
    d=request.json or {}; items=d.get('items',[])
    if not items:return jsonify({'error':'Seu carrinho está vazio.'}),400
    # Snapshot product data from database; client cannot set prices.
    c=db(); clean=[]; subtotal=0
    for x in items:
        pid=int(x.get('product_id',0)); r=c.execute("SELECT * FROM products WHERE id=%s AND status='published'",(pid,)).fetchone()
        if not r: continue
        p=product_dict(r); qty=max(1,int(x.get('qty',1))); unit=p['final_price']; item={'product_id':pid,'code':p['code'],'name':p['name'],'qty':qty,'unit_price':unit,'color':x.get('color'),'size':x.get('size'),'material':x.get('material'),'variation_text':' · '.join([v for v in [x.get('color'),x.get('size'),x.get('material')] if v])}
        clean.append(item); subtotal+=unit*qty
    if not clean:c.close(); return jsonify({'error':'Nenhum produto válido no carrinho.'}),400
    subtotal=money(subtotal); code='#'+secrets.token_hex(5).upper(); created=now(); exp=(datetime.utcnow()+timedelta(days=30)).isoformat(timespec='seconds')
    oid=c.execute('INSERT INTO orders(code,customer_id,status,items,subtotal,total,created_at,updated_at,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',(code,cid,'Aguardando confirmação',json.dumps(clean,ensure_ascii=False),subtotal,subtotal,created,created,exp)).fetchone()['id']
    c.execute("UPDATE carts SET items='[]',updated_at=%s WHERE customer_id=%s",(created,cid)); c.execute('INSERT INTO order_changes(order_id,action,details,created_at) VALUES(%s,%s,%s,%s)',(oid,'Criado','Pedido criado pelo cliente',created)); c.commit(); c.close()
    s=settings(); wa=clean_digits(s.get('whatsapp')); lines='\n'.join([f"• {x['name']}{(' — '+x['variation_text']) if x['variation_text'] else ''} — {x['qty']}x — R$ {x['unit_price']*x['qty']:.2f}" for x in clean]); msg=f"Olá! 😊\nGostaria de finalizar o meu pedido {code}.\n\nProdutos:\n{lines}\n\nTotal do pedido: R$ {subtotal:.2f}\n\nAguardo a confirmação do pedido. 💕\n\nFinalização do pedido {code}"
    return jsonify({'ok':True,'code':code,'total':subtotal,'whatsapp':wa,'message':msg})

@app.get('/api/orders')
def orders():
    cid=require_customer();
    if not cid:return jsonify({'error':'login'}),401
    c=db(); rows=c.execute('SELECT * FROM orders WHERE customer_id=%s ORDER BY created_at DESC',(cid,)).fetchall(); out=[]; changed=False
    for r in rows:
        d=dict(r)
        if d['status']=='Aguardando confirmação' and datetime.fromisoformat(d['expires_at'])<datetime.utcnow():
            c.execute("UPDATE orders SET status='Cancelado',updated_at=%s WHERE id=%s",(now(),d['id'])); c.execute('INSERT INTO order_changes(order_id,action,details,created_at) VALUES(%s,%s,%s,%s)',(d['id'],'Cancelamento automático','Pedido passou 30 dias sem confirmação',now())); d['status']='Cancelado'; changed=True
        d['items']=json.loads(d['items']); out.append(d)
    if changed:c.commit()
    c.close(); return jsonify(out)

# ADMIN
@app.post('/api/admin/login')
def admin_login():
    d=request.json or {}; c=db(); r=c.execute('SELECT * FROM admins WHERE email=%s',(d.get('email','').strip().lower(),)).fetchone(); c.close()
    if not r or not check_password_hash(r['password_hash'],d.get('password','')):return jsonify({'error':'Acesso administrativo inválido.'}),401
    session['admin_id']=r['id']; return jsonify({'ok':True})
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
    cutoff=(datetime.utcnow()-timedelta(days=days)).isoformat(timespec='seconds')
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
        d=dict(r); d['items']=json.loads(d['items']); out.append(d)
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
    c=db(); r=c.execute('SELECT status FROM orders WHERE id=%s',(oid,)).fetchone()
    if not r:c.close();return jsonify({'error':'Pedido não encontrado.'}),404
    old=r['status']
    # Reopening is allowed only when currently cancelled.
    if old!='Cancelado' and old!='Aguardando confirmação' and status=='Aguardando confirmação': c.close(); return jsonify({'error':'Só pedidos cancelados podem ser reabertos.'}),400
    if old=='Confirmado' and status=='Cancelado': pass
    c.execute('UPDATE orders SET status=%s,updated_at=%s WHERE id=%s',(status,now(),oid)); c.execute('INSERT INTO order_changes(order_id,action,details,created_at) VALUES(%s,%s,%s,%s)',(oid,'Status alterado',f'{old} → {status}',now())); c.commit(); c.close(); return jsonify({'ok':True})

@app.get('/api/admin/products')
def admin_products():
    if not require_admin():return jsonify({'error':'forbidden'}),403
    c=db(); rows=[product_dict(r) for r in c.execute('SELECT * FROM products ORDER BY created_at DESC')]; c.close(); return jsonify(rows)

def valid_image(filename): return bool(re.search(r'\.(jpe%sg|png)$',filename,re.I))
@app.post('/api/admin/product')
def admin_product_save():
    if not require_admin():return jsonify({'error':'forbidden'}),403
    d=request.json or {}; required=['name','description','category_id','care','modality','price']
    if any(d.get(x) in [None,''] for x in required):return jsonify({'error':'Preencha os campos obrigatórios.'}),400
    status=d.get('status','draft'); photos=d.get('photos',[])
    if status=='published' and not photos:return jsonify({'error':'Produto publicado precisa ter pelo menos uma foto.'}),400
    # Only colors created by the administrator may be assigned to products.
    c=db(); registered={r['name'] for r in c.execute('SELECT name FROM colors').fetchall()}
    selected_colors=[]
    for value in d.get('colors',[]) or []:
        name=str(value).strip()
        if name and name in registered and name not in selected_colors:selected_colors.append(name)
    if any(str(v).strip() not in registered for v in (d.get('colors',[]) or []) if str(v).strip()):
        c.close(); return jsonify({'error':'Uma ou mais cores selecionadas não estão cadastradas em “Categorias e cores”.'}),400
    ts=now(); pid=d.get('id'); vals=(d['name'].strip(),d['description'].strip(),int(d['category_id']),None,d.get('material','').strip(),json.dumps(d.get('sizes',[]),ensure_ascii=False),json.dumps(selected_colors,ensure_ascii=False),d['care'].strip(),d['modality'],float(d['price']),max(0,min(100,float(d.get('promo_percent',0)))),0,status,json.dumps(photos,ensure_ascii=False),json.dumps(d.get('variation_photos',{}),ensure_ascii=False),ts)
    if pid:
        c.execute('UPDATE products SET name=%s,description=%s,category_id=%s,subcategory_id=%s,material=%s,sizes=%s,colors=%s,care=%s,modality=%s,price=%s,promo_percent=%s,highlighted=%s,status=%s,photos=%s,variation_photos=%s,updated_at=%s WHERE id=%s',vals+(int(pid),))
    else:
        code='PRD-'+secrets.token_hex(4).upper(); pid=c.execute('INSERT INTO products(code,name,description,category_id,subcategory_id,material,sizes,colors,care,modality,price,promo_percent,highlighted,status,photos,variation_photos,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',(code,)+vals+(ts,)).fetchone()['id']
    c.commit(); r=c.execute('SELECT * FROM products WHERE id=%s',(pid,)).fetchone(); c.close(); return jsonify(product_dict(r))
@app.post('/api/admin/product/<int:pid>/photo')
def admin_photo(pid):
    if not require_admin():return jsonify({'error':'forbidden'}),403
    f=request.files.get('photo')
    if not f or not f.filename or not valid_image(f.filename):return jsonify({'error':'Envie uma imagem JPG/JPEG ou PNG.'}),400
    ext=os.path.splitext(f.filename)[1].lower()
    if ext not in ('.jpg','.jpeg','.png'):
        return jsonify({'error':'Formato inválido. Use JPG, JPEG ou PNG.'}),400
    try:
        img=ImageOps.exif_transpose(Image.open(f.stream)).convert('RGB')
        fitted=ImageOps.contain(img,(1000,1000),method=Image.Resampling.LANCZOS)
        canvas=Image.new('RGB',(1000,1000),'white'); canvas.paste(fitted,((1000-fitted.width)//2,(1000-fitted.height)//2))
        name=f'{secrets.token_hex(12)}.jpg'; buffer=io.BytesIO(); canvas.save(buffer,'JPEG',quality=92,optimize=True); image_bytes=buffer.getvalue()
    except Exception:
        return jsonify({'error':'Não foi possível processar essa imagem. Tente outro JPG, JPEG ou PNG.'}),400
    c=db(); r=c.execute('SELECT photos FROM products WHERE id=%s',(pid,)).fetchone()
    if not r:return jsonify({'error':'Produto não encontrado.'}),404
    c.execute('INSERT INTO uploaded_images(name,data) VALUES(%s,%s)',(name,image_bytes))
    photos=json.loads(r['photos'] or '[]'); photos.append('/uploads/'+name); c.execute('UPDATE products SET photos=%s,updated_at=%s WHERE id=%s',(json.dumps(photos),now(),pid)); c.commit(); c.close(); return jsonify({'ok':True,'photos':photos})
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
    if not require_admin():return jsonify({'error':'forbidden'}),403
    idx=int(request.args.get('index',-1)); c=db(); r=c.execute('SELECT photos FROM products WHERE id=%s',(pid,)).fetchone();
    if not r:c.close();return jsonify({'error':'Produto não encontrado.'}),404
    photos=json.loads(r['photos'] or '[]');
    if idx<0 or idx>=len(photos):c.close();return jsonify({'error':'Foto inválida.'}),400
    path=photos.pop(idx); c.execute('UPDATE products SET photos=%s,updated_at=%s WHERE id=%s',(json.dumps(photos),now(),pid)); c.commit(); c.close()
    if path.startswith('/uploads/'):
        try:os.remove(os.path.join(UPLOAD,os.path.basename(path)))
        except OSError:pass
    return jsonify({'ok':True,'photos':photos})
@app.delete('/api/admin/product/<int:pid>')
def admin_product_delete(pid):
    if not require_admin():return jsonify({'error':'forbidden'}),403
    c=db(); c.execute('DELETE FROM products WHERE id=%s',(pid,)); c.commit(); c.close(); return jsonify({'ok':True})

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
    if not require_admin():return jsonify({'error':'forbidden'}),403
    c=db(); linked=c.execute('SELECT COUNT(*) n FROM products WHERE category_id=%s',(cid,)).fetchone()['n'];
    if linked:
        unc=c.execute("SELECT id FROM categories WHERE name='Sem categoria'").fetchone()['id']
        c.execute('UPDATE products SET category_id=%s,subcategory_id=NULL WHERE category_id=%s',(unc,cid)); c.execute('DELETE FROM categories WHERE id=%s',(cid,)); c.commit(); c.close(); return jsonify({'ok':True,'moved_to_uncategorized':linked})
    c.execute('DELETE FROM categories WHERE id=%s',(cid,)); c.commit(); c.close(); return jsonify({'ok':True})

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
    if not require_admin():return jsonify({'error':'forbidden'}),403
    d=request.json or {}; allowed=['whatsapp','instagram']
    c=db()
    for k in allowed:
        if k in d:c.execute('INSERT INTO settings(key,value) VALUES(%s,%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,str(d[k] or '').strip()))
    c.commit(); c.close(); return jsonify({'ok':True})
@app.post('/api/admin/password')
def admin_password():
    if not require_admin():return jsonify({'error':'forbidden'}),403
    d=request.json or {}; c=db(); r=c.execute('SELECT password_hash FROM admins WHERE id=%s',(require_admin(),)).fetchone()
    if not r or not check_password_hash(r['password_hash'],d.get('current','')):c.close();return jsonify({'error':'Senha atual incorreta.'}),400
    if not d.get('new') or d.get('new')!=d.get('confirm'):c.close();return jsonify({'error':'As novas senhas não coincidem.'}),400
    c.execute('UPDATE admins SET password_hash=%s WHERE id=%s',(generate_password_hash(d['new']),require_admin()));c.commit();c.close();return jsonify({'ok':True})

@app.errorhandler(404)
def notfound(e): return jsonify({'error':'Não encontrado.'}),404

if __name__=='__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '5000')), debug=False)
