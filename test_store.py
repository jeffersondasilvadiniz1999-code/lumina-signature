import io,json,os,secrets,subprocess,hashlib
from pathlib import Path
import pytest,psycopg
from PIL import Image
from app import app,db,init
from media import normalize_image
from conftest import mutate


def test_regression_invalid_featured_sql_proven():
    with app.app_context():
        c=db()
        with pytest.raises(psycopg.errors.UndefinedColumn):
            c.execute('SELECT p.* FROM products p WHERE p.status="published"')
        c.rollback()


def test_existing_backup_counts_and_blobs():
    snapshot=Path('../private-audit/lumina-backup-20261015.json')
    if not snapshot.exists():pytest.skip('Snapshot privado necessário para comparação do backup real.')
    source=json.loads(snapshot.read_text())['tables']
    with app.app_context():
        c=db()
        for row in source['products']:
            saved=c.execute('SELECT * FROM products WHERE id=%s',(row['id'],)).fetchone()
            assert saved['photos']==row['photos']
        for row in source['uploaded_images']:
            saved=c.execute('SELECT data FROM uploaded_images WHERE name=%s',(row['name'],)).fetchone()
            assert bytes(saved['data'])==bytes.fromhex(row['data'][2:])


def test_catalog_and_featured_work_after_confirmed_sale(client):
    assert client.get('/api/products').status_code==200
    r=client.get('/api/featured');assert r.status_code==200,r.json
    assert isinstance(r.json,list)
    assert len(client.get('/api/products').json)>=1


def test_create_publish_edit_filter_and_image_persistence(owner,client,product):
    pid=product['id'];assert any(p['id']==pid for p in client.get('/api/products').json)
    image=product['photos'][0];r=client.get(image);assert r.status_code==200 and r.mimetype=='image/jpeg'
    original=r.data
    product.update(price=145.80,description='Descrição atualizada',colors=['Prata'],sizes=['20 cm'])
    r=mutate(owner,'/api/admin/product',json=product);assert r.status_code==200,r.json
    p=client.get('/api/product/'+str(pid)).json;assert p['price']==pytest.approx(145.80);assert p['description']=='Descrição atualizada'
    assert pid in [p['id'] for p in client.get('/api/products?q=AUDITORIA&color=Prata&size=20%20cm&sort=az').json]
    assert pid not in [p['id'] for p in client.get('/api/products?color=Dourado').json]
    # Re-run migrations and reload application in a separate process; bytes and records must survive.
    script="from app import app,init; import hashlib;\nwith app.app_context():init()\nc=app.test_client();r=c.get('/api/product/%d');assert r.status_code==200;assert hashlib.sha256(c.get('%s').data).hexdigest()=='%s'"%(pid,image,hashlib.sha256(original).hexdigest())
    r=subprocess.run([__import__('sys').executable,'-c',script],capture_output=True,text=True,timeout=30)
    assert r.returncode==0,r.stderr[-1000:]

@pytest.mark.parametrize('format',['PNG','JPEG','WEBP','GIF','BMP','TIFF','HEIF'])
def test_real_image_formats_and_misleading_extensions(owner,product,format):
    b=io.BytesIO();Image.new('RGB',(80,50),(200,100,90)).save(b,format=format);b.seek(0)
    r=mutate(owner,f"/api/admin/product/{product['id']}/photo",data={'photo':(b,'screenshot.not-an-extension')})
    assert r.status_code==200,r.json
    data=owner.get(r.json['photos'][-1]);assert data.status_code==200
    assert Image.open(io.BytesIO(data.data)).format=='JPEG'

@pytest.mark.parametrize('payload',[b'#!/bin/sh\necho hacked',b'MZ'+b'\0'*200,b'<svg onload="alert(1)"></svg>',b'not an image'])
def test_reject_disguised_files(owner,product,payload):
    r=mutate(owner,f"/api/admin/product/{product['id']}/photo",data={'photo':(io.BytesIO(payload),'photo.png')})
    assert r.status_code==400


def test_image_limits(owner,product):
    r=mutate(owner,f"/api/admin/product/{product['id']}/photo",data={'photo':(io.BytesIO(b'x'*(21*1024*1024)),'photo.png')})
    assert r.status_code==413


def test_csrf_and_anonymous_authorization(client,product):
    assert client.post('/api/admin/product',json=product).status_code==403
    assert mutate(client,'/api/admin/product',json=product).status_code==401
    assert client.get('/api/admin/orders').status_code==401
    assert mutate(client,'/api/logout',json={},headers={'Origin':'https://attacker.invalid'}).status_code==403


def test_viewer_cannot_modify(client,product):
    with app.app_context():row=db().execute("SELECT id,session_version FROM admins WHERE email='audit-viewer@example.invalid'").fetchone()
    with client.session_transaction() as s:s['admin_id']=row['id'];s['admin_version']=row['session_version']
    assert client.get('/api/admin/products').status_code==200
    assert mutate(client,'/api/admin/product',json=product).status_code==403


def test_draft_is_private(owner,client,product):
    product['status']='draft';assert mutate(owner,'/api/admin/product',json=product).status_code==200
    assert client.get('/api/product/'+str(product['id'])).status_code==404


def test_invalid_category_status_price_and_colors(owner,product):
    for override in [{'category_id':99999999},{'status':'Publicado'},{'price':-1},{'price':'NaN'},{'colors':['unregistered']}]:
        assert mutate(owner,'/api/admin/product',json={**product,**override}).status_code==400


def test_quote_checkout_deduplication_and_history(owner,customer,product):
    assert mutate(owner,'/api/admin/settings',json={'whatsapp':'5584999999999'}).status_code==200
    item={'product_id':product['id'],'qty':2,'color':'Dourado','size':'17 cm','unit_price':0.01}
    quote=mutate(customer,'/api/quote',json={'items':[item]});assert quote.status_code==200,quote.json
    assert quote.json['total']==216
    assert mutate(customer,'/api/cart',json={'items':[item]}).status_code==200
    key=secrets.token_hex(16)
    one=mutate(customer,'/api/order',json={'items':[item]},headers={'Idempotency-Key':key});assert one.status_code==200,one.json
    two=mutate(customer,'/api/order',json={'items':[item]},headers={'Idempotency-Key':key});assert two.json['code']==one.json['code']
    assert one.json['total']==216 and 'Dourado' in one.json['message'] and '17 cm' in one.json['message']
    rows=customer.get('/api/orders').json;order=next(o for o in rows if o['code']==one.json['code']);assert order['status']=='Aguardando confirmação'
    for status in ['Confirmado','Cancelado']:
        assert mutate(owner,f"/api/admin/order/{order['id']}/status",json={'status':status}).status_code==200
    assert len(owner.get(f"/api/admin/order/{order['id']}/history").json)==3
    assert owner.get('/api/admin/stats').status_code==200
    assert customer.get('/api/cart').json['items']==[]
    invalid={**item,'color':'unregistered'}
    assert mutate(customer,'/api/order',json={'items':[invalid]},headers={'Idempotency-Key':secrets.token_hex(16)}).status_code==400
    assert mutate(customer,'/api/order',json={'items':[{**item,'qty':3}]},headers={'Idempotency-Key':key}).status_code==409


def test_order_requires_configured_whatsapp(owner,customer,product):
    mutate(owner,'/api/admin/settings',json={'whatsapp':''})
    r=mutate(customer,'/api/order',json={'items':[{'product_id':product['id'],'qty':1,'color':'Dourado','size':'17 cm'}]},headers={'Idempotency-Key':secrets.token_hex(16)})
    assert r.status_code==400
    mutate(owner,'/api/admin/settings',json={'whatsapp':'5584999999999'})


def test_categories_and_safe_archival(owner,client,product):
    with app.app_context():unc=db().execute("SELECT id FROM categories WHERE name='Sem categoria'").fetchone()['id']
    assert mutate(owner,f'/api/admin/category/{unc}',method='DELETE').status_code==400
    assert mutate(owner,f"/api/admin/product/{product['id']}",method='DELETE').status_code==200
    assert client.get('/api/product/'+str(product['id'])).status_code==404
    with app.app_context():assert db().execute('SELECT id FROM products WHERE id=%s',(product['id'],)).fetchone()


def test_login_logout_rate_limit_and_security_headers(client):
    r=mutate(client,'/api/admin/login',json={'email':'audit-owner@example.invalid','password':'test-password-only-12345'});assert r.status_code==200
    assert client.get('/api/admin/products').status_code==200
    assert mutate(client,'/api/logout',json={}).status_code==200
    assert client.get('/api/admin/products').status_code==401
    for _ in range(9):r=mutate(client,'/api/admin/login',json={'email':'nobody@example.invalid','password':'wrong'})
    assert r.status_code==429
    response=client.get('/api/products');assert response.headers['Cache-Control']=='no-store';assert response.headers['X-Content-Type-Options']=='nosniff'


def test_recovery_not_falsely_reported_available(client,monkeypatch):
    monkeypatch.delenv('SMTP_HOST',raising=False)
    assert mutate(client,'/api/password/forgot',json={'email':'someone@example.invalid'}).status_code==503


def test_main_photo_and_variation(owner,client,product):
    b=io.BytesIO();Image.new('RGB',(32,32),'blue').save(b,'WEBP');b.seek(0)
    r=mutate(owner,f"/api/admin/product/{product['id']}/photo",data={'photo':(b,'camera.webp')});assert r.status_code==200
    product.update(photos=r.json['photos'],variation_photos={'Dourado':r.json['photos'][-1]},highlighted=True)
    assert mutate(owner,'/api/admin/product',json=product).status_code==200
    assert mutate(owner,f"/api/admin/product/{product['id']}/main-photo",json={'index':1}).status_code==200
    assert client.get('/api/product/'+str(product['id'])).json['photos'][0]==r.json['photos'][-1]
    assert product['id'] in [p['id'] for p in client.get('/api/featured').json]


def test_persistent_settings_and_subcategories(owner,client,product):
    settings={'store_name':'Lumina Signature','footer_phrase':'Rodapé de validação','instagram':'@lumina.signature','whatsapp':'84999999999'}
    assert mutate(owner,'/api/admin/settings',json=settings).status_code==200
    result=client.get('/api/settings').json;assert result['footer_phrase']==settings['footer_phrase'];assert result['whatsapp']=='5584999999999'
    name='AUDITORIA '+secrets.token_hex(4)
    assert mutate(owner,'/api/admin/subcategory',json={'category_id':product['category_id'],'name':name}).status_code==200
    sub=next(x for x in client.get('/api/subcategories').json if x['name']==name)
    product['subcategory_id']=sub['id'];assert mutate(owner,'/api/admin/product',json=product).status_code==200
    assert product['id'] in [p['id'] for p in client.get('/api/products?subcategory='+str(sub['id'])).json]
    assert owner.get('/api/admin/revenue?year=2026&month=10').status_code==200


def test_invitation_one_use_and_viewer_permissions(owner,client):
    email='audit-'+secrets.token_hex(5)+'@example.invalid'
    response=mutate(owner,'/api/admin/invites',json={'email':email,'role':'viewer'});assert response.status_code==200
    token=response.json['url'].split('#')[1]
    data={'token':token,'password':'test-only-invitation-password','confirm':'test-only-invitation-password'}
    assert mutate(client,'/api/admin/accept-invite',json=data).status_code==200
    assert mutate(client,'/api/admin/accept-invite',json=data).status_code==400
    with app.app_context():assert db().execute('SELECT role FROM admins WHERE email=%s',(email,)).fetchone()['role']=='viewer'


def test_real_password_recovery_flow_with_mock_email(client,customer,monkeypatch):
    import mailer
    sent=[]
    class SMTP:
        def __init__(self,*a,**k):pass
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def starttls(self,**k):pass
        def send_message(self,m):sent.append(m)
    monkeypatch.setenv('SMTP_HOST','smtp.example.invalid');monkeypatch.setenv('MAIL_FROM','store@example.invalid');monkeypatch.setenv('PUBLIC_BASE_URL','https://shop.example.invalid')
    monkeypatch.setattr(mailer.smtplib,'SMTP',SMTP)
    response=mutate(client,'/api/password/forgot',json={'email':'audit-customer@example.invalid'});assert response.status_code==200 and sent
    token=sent[-1].get_content().split('#')[1].split()[0]
    data={'token':token,'password':'test-new-password-12345','confirm':'test-new-password-12345'}
    assert mutate(client,'/api/password/reset',json=data).status_code==200
    assert mutate(client,'/api/password/reset',json=data).status_code==400
    assert customer.get('/api/me').json['customer'] is None


def test_malformed_json_is_not_success(client):
    assert mutate(client,'/api/login',json=[]).status_code==400


def test_migration_repeat_keeps_data():
    with app.app_context():
        c=db();before=c.execute('SELECT count(*) AS n FROM products').fetchone()['n'];c.close();init();init()
        assert db().execute('SELECT count(*) AS n FROM products').fetchone()['n']==before


def test_restore_refuses_existing_database(tmp_path):
    from manage import restore
    path=tmp_path/'backup.json';path.write_text(json.dumps({'format':'lumina-backup-v1','tables':{}}))
    with pytest.raises(RuntimeError,match='vazio'):restore(path)


def test_https_email_provider_contract(monkeypatch):
    import mailer
    monkeypatch.setenv('BREVO_API_KEY','test-only-key');monkeypatch.setenv('MAIL_FROM','store@example.invalid');monkeypatch.setenv('RENDER','true')
    requests=[]
    class Response:
        status=201
        def __enter__(self):return self
        def __exit__(self,*a):pass
    def fake(req,timeout):requests.append(req);return Response()
    monkeypatch.setattr(mailer,'urlopen',fake)
    assert mailer.configured()
    mailer.send_reset('customer@example.invalid','Test message')
    assert requests[0].full_url=='https://api.brevo.com/v3/smtp/email'
    assert json.loads(requests[0].data)['to'][0]['email']=='customer@example.invalid'
