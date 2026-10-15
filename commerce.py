import hashlib,json,re,secrets
from decimal import Decimal,ROUND_HALF_UP
from datetime import datetime,timedelta,timezone
from flask import request,jsonify,session,abort


def install(app,db,product_dict,require_customer,now):
    def quote(items,c):
        if not isinstance(items,list) or not 1<=len(items)<=100:raise ValueError('Carrinho vazio ou maior que o limite de 100 itens.')
        clean=[];total=Decimal('0')
        for x in items:
            if not isinstance(x,dict):raise ValueError('Item inválido.')
            pid=int(x.get('product_id',0));qty=int(x.get('qty',0))
            if not 1<=qty<=99:raise ValueError('A quantidade deve estar entre 1 e 99.')
            r=c.execute("SELECT * FROM products WHERE id=%s AND status='published' AND deleted_at IS NULL",(pid,)).fetchone()
            if not r:raise ValueError('Um produto não está mais disponível. Remova-o do carrinho.')
            p=product_dict(r)
            for key,choices in [('color',p['colors']),('size',p['sizes'])]:
                if choices and x.get(key) not in choices:raise ValueError('Selecione uma '+('cor' if key=='color' else 'medida')+' válida para '+p['name']+'.')
                if not choices and x.get(key) not in (None,''):raise ValueError('Variação não disponível.')
            unit=(Decimal(str(p['price']))*(1-Decimal(str(p['promo_percent']))/100)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
            variations=[v for v in [x.get('color'),x.get('size')] if v]
            clean.append({'product_id':pid,'code':p['code'],'name':p['name'],'qty':qty,'unit_price':float(unit),'color':x.get('color') or None,'size':x.get('size') or None,'material':None,'variation_text':' · '.join(variations),'photo':p['photos'][0] if p['photos'] else '/static/placeholder.svg'})
            total+=unit*qty
        return clean,total

    @app.post('/api/quote')
    def cart_quote():
        items=(request.get_json() or {}).get('items',[])
        if not items:return jsonify({'items':[],'total':0})
        clean,total=quote(items,db());return jsonify({'items':clean,'total':float(total)})

    def set_cart():
        cid=require_customer()
        if not cid:abort(401)
        items=(request.get_json() or {}).get('items',[]);c=db()
        clean,_=quote(items,c) if items else ([],0)
        c.execute('INSERT INTO carts(customer_id,items,updated_at) VALUES(%s,%s,%s) ON CONFLICT(customer_id) DO UPDATE SET items=excluded.items,updated_at=excluded.updated_at',(cid,json.dumps(clean,ensure_ascii=False),now()));c.commit()
        return jsonify({'ok':True})
    app.add_url_rule('/api/cart','set_cart',set_cart,methods=['POST'])

    def create_order():
        cid=require_customer()
        if not cid:abort(401)
        data=request.get_json() or {};key=request.headers.get('Idempotency-Key','')
        if not re.fullmatch(r'[a-zA-Z0-9_-]{16,100}',key):raise ValueError('Atualize a página para gerar uma chave de pedido válida.')
        items=data.get('items',[])
        canonical=[{k:x.get(k) for k in ('product_id','qty','color','size')} for x in items] if isinstance(items,list) and all(isinstance(x,dict) for x in items) else None
        if canonical is None:raise ValueError('Carrinho inválido.')
        fingerprint=hashlib.sha256(json.dumps(canonical,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        c=db();c.execute('SELECT id FROM customers WHERE id=%s FOR UPDATE',(cid,))
        existing=c.execute('SELECT * FROM orders WHERE customer_id=%s AND idempotency_key=%s',(cid,key)).fetchone()
        s={r['key']:r['value'] for r in c.execute('SELECT * FROM settings')}
        wa=''.join(x for x in s.get('whatsapp','') if x.isdigit())
        if len(wa) in (10,11):wa='55'+wa
        if not wa:raise ValueError('A loja ainda não configurou o WhatsApp. Entre em contato antes de finalizar.')
        if existing:
            if existing['request_fingerprint']!=fingerprint:return jsonify({'error':'Chave já usada para outro carrinho. Atualize a página.'}),409
            clean=json.loads(existing['items']);total=Decimal(str(existing['total']));code=existing['code']
        else:
            clean,total=quote(items,c);code='#'+secrets.token_hex(6).upper();created=now();exp=(datetime.now(timezone.utc).replace(tzinfo=None)+timedelta(days=30)).isoformat(timespec='seconds')
            oid=c.execute('INSERT INTO orders(code,customer_id,status,items,subtotal,total,created_at,updated_at,expires_at,idempotency_key,request_fingerprint) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',(code,cid,'Aguardando confirmação',json.dumps(clean,ensure_ascii=False),float(total),float(total),created,created,exp,key,fingerprint)).fetchone()['id']
            c.execute("UPDATE carts SET items='[]',updated_at=%s WHERE customer_id=%s",(created,cid))
            c.execute('INSERT INTO order_changes(order_id,action,details,created_at) VALUES(%s,%s,%s,%s)',(oid,'Criado','Pedido criado pelo cliente',created));c.commit()
        lines='\n'.join(f"• {x['name']} — {x['variation_text'] or 'Sem variação'} — {x['qty']}x R$ {x['unit_price']:.2f} = R$ {x['unit_price']*x['qty']:.2f}" for x in clean)
        message=f'Olá! Gostaria de finalizar o pedido {code}.\n\n{lines}\n\nTotal: R$ {total:.2f}\nAguardo confirmação da loja.'
        return jsonify({'ok':True,'code':code,'total':float(total),'whatsapp':wa,'message':message})
    app.add_url_rule('/api/order','create_order',create_order,methods=['POST'])
