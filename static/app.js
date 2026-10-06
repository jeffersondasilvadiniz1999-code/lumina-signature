const $=s=>document.querySelector(s);const $$=s=>document.querySelectorAll(s);const key='lumina_guest_cart';
async function api(url,opt={}){let r=await fetch(url,{headers:{'Content-Type':'application/json',...(opt.headers||{})},...opt});let d=await r.json().catch(()=>({}));if(!r.ok)throw new Error(d.error||'Ocorreu um erro.');return d}
const money=v=>Number(v||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
let guest=JSON.parse(localStorage.getItem(key)||'[]');
let editingProduct=null;
function saveGuest(){localStorage.setItem(key,JSON.stringify(guest));badge()}
function badge(){let n=guest.reduce((a,x)=>a+Number(x.qty||0),0);$$('.cart-badge').forEach(e=>e.textContent=n>9?'9+':n)}
async function syncCart(){let me=await api('/api/me');if(!me.customer)return;let server=(await api('/api/cart')).items||[];let merged=[...server];for(const x of guest){let i=merged.findIndex(y=>y.product_id===x.product_id&&y.color===x.color&&y.size===x.size&&y.material===x.material);if(i>=0)merged[i].qty+=x.qty;else merged.push(x)}await api('/api/cart',{method:'POST',body:JSON.stringify({items:merged})});guest=[];saveGuest()}
async function cartItems(){let me=await api('/api/me');return me.customer?(await api('/api/cart')).items:guest}
async function setCart(items){let me=await api('/api/me');if(me.customer)await api('/api/cart',{method:'POST',body:JSON.stringify({items})});else{guest=items;saveGuest()}}
function photo(p){return p.photos&&p.photos.length?p.photos[0]:'/static/placeholder.svg'}
function card(p){return `<article class="card"><a href="/product/${p.id}"><div class="pic"><img src="${photo(p)}" alt="${esc(p.name)}"></div></a><div class="body"><small>${esc(p.category_name||'')}</small><h3>${esc(p.name)}</h3><p>${p.promo_percent>0?`<span class="old">${money(p.price)}</span> `:''}<span class="price">${money(p.final_price)}</span>${p.promo_percent>0?` <span class="off">${p.promo_percent}% OFF</span>`:''}</p><a class="btn" href="/product/${p.id}">Ver produto</a></div></article>`}
function esc(s){return String(s??'').replace(/[&<>'"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[m]))}
async function home(){
  badge();
  let query=location.search.replace(/^\?/,'');
  let [cs,products,allProducts,featured]=await Promise.all([api('/api/categories'),api('/api/products?'+query),api('/api/products'),api('/api/featured')]);
  let q=new URLSearchParams(location.search);
  $('#featured').innerHTML=featured.length?featured.map(card).join(''):'<p>Nenhum produto em destaque nos últimos 30 dias.</p>';
  let promo=products.filter(p=>p.promo_percent>0);
  $('#promosGrid').innerHTML=promo.length?promo.map(card).join(''):'<p>Nenhuma promoção ativa.</p>';
  $('#catalog').innerHTML=products.length?products.map(card).join(''):'<div class="empty"><h3>Nenhum produto encontrado.</h3><button class="btn" onclick="location.href='/'">Ver todos os produtos</button></div>';
  $('#cats').innerHTML=cs.filter(c=>c.name!=='Sem categoria').map(c=>`<button class="cat" onclick="location.href='/?category=${c.id}#catalogo'">${esc(c.name)}</button>`).join('');
  $('#search').value=q.get('q')||'';
  $('#catFilter').innerHTML='<option value="">Todas as categorias</option>'+cs.filter(c=>c.name!=='Sem categoria').map(c=>`<option value="${c.id}" ${q.get('category')===String(c.id)?'selected':''}>${esc(c.name)}</option>`).join('');
  let registeredColors=await api('/api/colors'); let allowedColorNames=new Set(registeredColors.map(c=>c.name)); let colors=[...new Set(allProducts.flatMap(p=>p.colors||[]).filter(v=>v&&allowedColorNames.has(v)))].sort((a,b)=>a.localeCompare(b,'pt-BR'));
  let sizes=[...new Set(allProducts.flatMap(p=>p.sizes||[]).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'pt-BR',{numeric:true}));
  let materials=[...new Set(allProducts.map(p=>p.material).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'pt-BR'));
  $('#colorFilter').innerHTML='<option value="">Todas as cores</option>'+colors.map(v=>`<option value="${esc(v)}" ${q.get('color')===v?'selected':''}>${esc(v)}</option>`).join('');
  $('#sizeFilter').innerHTML='<option value="">Todos os tamanhos</option>'+sizes.map(v=>`<option value="${esc(v)}" ${q.get('size')===v?'selected':''}>${esc(v)}</option>`).join('');
  $('#materialFilter').value=q.get('material')||''; $('#modalityFilter').value=q.get('modality')||''; $('#promoFilter').value=q.get('promo')||''; $('#sort').value=q.get('sort')||'recent';
}
function applyFilters(){let p=new URLSearchParams();let ids=['q','catFilter','colorFilter','sizeFilter','materialFilter','modalityFilter','promoFilter','sort'];ids.forEach(id=>{let e=$('#'+id);if(e&&e.value)p.set(id==='catFilter'?'category':id==='modalityFilter'?'modality':id==='promoFilter'?'promo':id,e.value)});location.href='/?'+p.toString()+'#catalogo'}
let state={p:null,color:null,size:null,material:null,qty:1,photo:0};
async function productPage(pid){let p=await api('/api/product/'+pid);state={p,color:p.colors?.[0]||null,size:p.sizes?.[0]||null,material:p.material&&false? p.material:null,qty:1,photo:0};drawProduct()}
function drawProduct(){let p=state.p;if(!p)return;let imgs=p.photos||[];let main=imgs[state.photo]||'/static/placeholder.svg';$('#prod').innerHTML=`<div class="detail"><div><div class="gallery"><img src="${main}" alt="${esc(p.name)}"></div>${imgs.length>1?`<div class="thumbs">${imgs.map((x,i)=>`<img class="${i===state.photo?'active':''}" src="${x}" onclick="state.photo=${i};drawProduct()">`).join('')}</div>`:''}</div><div><small>${esc(p.category_name||'')}</small><h1>${esc(p.name)}</h1><p>${p.promo_percent>0?`<span class="old">${money(p.price)}</span> `:''}<b>${money(p.final_price)}</b></p><p><b>${esc(p.modality)}</b></p>${p.colors.length?`<h3>Cor</h3><div class="chips">${p.colors.map(v=>`<button class="chip ${state.color===v?'active':''}" onclick="state.color='${jsq(v)}';drawProduct()">${esc(v)}</button>`).join('')}</div>`:''}${p.sizes.length?`<h3>Tamanho</h3><div class="chips">${p.sizes.map(v=>`<button class="chip ${state.size===v?'active':''}" onclick="state.size='${jsq(v)}';drawProduct()">${esc(v)}</button>`).join('')}</div>`:''}<div class="qty"><button onclick="state.qty=Math.max(1,state.qty-1);drawProduct()">−</button><span>${state.qty}</span><button onclick="state.qty++;drawProduct()">+</button></div><p><button class="btn" onclick="addToCart()">Adicionar ao carrinho</button></p><h3>Descrição</h3><p>${esc(p.description)}</p>${p.material?`<h3>Material</h3><p>${esc(p.material)}</p>`:''}<h3>Cuidados com a peça</h3><p>${esc(p.care)}</p></div></div>`}
function jsq(v){return String(v).replace(/\\/g,'\\\\').replace(/'/g,"\\'")}
async function addToCart(){let p=state.p;let items=await cartItems();let item={product_id:p.id,name:p.name,qty:state.qty,unit_price:p.final_price,color:state.color,size:state.size,material:null};let i=items.findIndex(x=>x.product_id===item.product_id&&x.color===item.color&&x.size===item.size&&x.material===item.material);if(i>=0)items[i].qty+=item.qty;else items.push(item);await setCart(items);alert('Produto adicionado ao carrinho!');location.href='/cart'}
async function cartPage(){badge();let items=await cartItems();if(!items.length){$('#cart').innerHTML='<div class="box empty"><h2>Seu carrinho está vazio.</h2><a class="btn" href="/">Ver todos os produtos</a></div>';$('#total').textContent=money(0);return}let total=items.reduce((s,x)=>s+Number(x.unit_price)*Number(x.qty),0);$('#cart').innerHTML=items.map((x,i)=>`<div class="cartrow"><div class="thumb"><img src="${x.photo||'/static/placeholder.svg'}"></div><div><b>${esc(x.name)}</b><small><br>${esc(x.variation_text||[x.color,x.size,x.material].filter(Boolean).join(' · '))}</small><br>${money(x.unit_price)} un.</div><div class="qty"><button onclick="changeQty(${i},-1)">−</button><span>${x.qty}</span><button onclick="changeQty(${i},1)">+</button></div><div class="line-total"><b>${money(x.unit_price*x.qty)}</b> <button class="btn danger" onclick="removeCart(${i})">×</button></div></div>`).join('');$('#total').textContent=money(total)}
async function changeQty(i,n){let items=await cartItems();items[i].qty=Math.max(1,items[i].qty+n);await setCart(items);cartPage()}
async function removeCart(i){let items=await cartItems();items.splice(i,1);await setCart(items);cartPage()}
async function checkout(){let me=await api('/api/me');if(!me.customer){location.href='/account?next=checkout';return}let items=await cartItems();try{let r=await api('/api/order',{method:'POST',body:JSON.stringify({items})});if(!r.whatsapp){alert('Pedido criado, mas o WhatsApp da loja ainda não foi cadastrado no painel administrativo.');location.href='/account';return}let url='https://wa.me/'+r.whatsapp+'?text='+encodeURIComponent(r.message);location.href=url}catch(e){alert(e.message)}}
async function accountPage(){let me=await api('/api/me');if(!me.customer){$('#account').innerHTML=`<div class="two"><div class="box"><h2>Entrar</h2><form class="form" onsubmit="login(event)"><input id="lemail" type="email" placeholder="E-mail" required><input id="lpass" type="password" placeholder="Senha" required><button class="btn">Entrar</button></form></div><div class="box"><h2>Criar conta</h2><form class="form" onsubmit="register(event)"><input id="remail" type="email" placeholder="E-mail" required><input id="rwa" placeholder="WhatsApp" required><input id="rpass" type="password" placeholder="Senha" required><input id="rconf" type="password" placeholder="Confirmar senha" required><button class="btn">Criar conta</button></form></div></div>`;return}let os=await api('/api/orders');$('#account').innerHTML=`<div class="box"><h2>Minha conta</h2><p>E-mail: <b>${esc(me.customer.email)}</b></p><p>WhatsApp: <b>${esc(me.customer.whatsapp)}</b></p><form class="form" onsubmit="changeWa(event)"><input id="cwa" value="${esc(me.customer.whatsapp)}" placeholder="WhatsApp"><button class="btn secondary">Atualizar WhatsApp</button></form><h3>Alterar senha</h3><form class="form" onsubmit="changePw(event)"><input id="ccur" type="password" placeholder="Senha atual"><input id="cnew" type="password" placeholder="Nova senha"><input id="cconf" type="password" placeholder="Repetir nova senha"><button class="btn secondary">Alterar senha</button></form><button class="btn danger" onclick="logout()">Sair</button></div><div class="box"><h2>Meus pedidos</h2>${os.length?os.map(o=>`<div class="order"><b>${o.code}</b> · <span class="status">${o.status}</span><br>${new Date(o.created_at+'Z').toLocaleString('pt-BR')}<br>${o.items.map(x=>`${x.qty}× ${esc(x.name)}${x.variation_text?' — '+esc(x.variation_text):''}`).join('<br>')}<br><b>${money(o.total)}</b></div>`).join(''):'Nenhum pedido ainda.'}</div>`}
async function login(e){e.preventDefault();try{await api('/api/login',{method:'POST',body:JSON.stringify({email:$('#lemail').value,password:$('#lpass').value})});await syncCart();let q=new URLSearchParams(location.search);location.href=q.get('next')==='checkout'?'/cart':'/account'}catch(x){alert(x.message)}}
async function register(e){e.preventDefault();try{await api('/api/register',{method:'POST',body:JSON.stringify({email:$('#remail').value,password:$('#rpass').value,confirm:$('#rconf').value,whatsapp:$('#rwa').value})});await syncCart();let q=new URLSearchParams(location.search);location.href=q.get('next')==='checkout'?'/cart':'/account'}catch(x){alert(x.message)}}
async function changeWa(e){e.preventDefault();try{await api('/api/customer/whatsapp',{method:'POST',body:JSON.stringify({whatsapp:$('#cwa').value})});alert('WhatsApp atualizado.');accountPage()}catch(x){alert(x.message)}}
async function changePw(e){e.preventDefault();try{await api('/api/customer/password',{method:'POST',body:JSON.stringify({current:$('#ccur').value,new:$('#cnew').value,confirm:$('#cconf').value})});alert('Senha alterada.')}catch(x){alert(x.message)}}
async function logout(){await api('/api/logout',{method:'POST'});guest=[];saveGuest();location.href='/'}
async function adminPage(){let me=await api('/api/me');if(!me.admin){$('#adminapp').innerHTML=`<div class="box" style="max-width:500px;margin:auto"><h1>Área administrativa</h1><form class="form" onsubmit="adminLogin(event)"><input id="aemail" type="email" value="admin@lumina.local" required><input id="apass" type="password" placeholder="Senha" required><button class="btn">Entrar</button></form><p class="notice">Use a senha administrativa definida na configuração da loja.</p></div>`;return}adminDashboard()}
async function adminLogin(e){e.preventDefault();try{await api('/api/admin/login',{method:'POST',body:JSON.stringify({email:$('#aemail').value,password:$('#apass').value})});adminDashboard()}catch(x){alert(x.message)}}
function adminNav(active='dashboard'){return `<div class="adminbar"><button class="btn" onclick="adminDashboard()">Dashboard</button><button class="btn secondary" onclick="adminOrders()">Pedidos</button><button class="btn secondary" onclick="adminProducts()">Produtos</button><button class="btn secondary" onclick="adminCatalogSettings()">Categorias e cores</button><button class="btn secondary" onclick="adminSettings()">Configurações</button><button class="btn secondary" onclick="location.href='/'">Visualizar loja</button><button class="btn secondary" onclick="logout()">Sair</button></div>`}
async function adminDashboard(){
  let [s,os,top]=await Promise.all([api('/api/admin/stats'),api('/api/admin/orders'),api('/api/admin/top-products?days=30')]);
  let topHtml=top.length?top.map((x,i)=>`<div class="order"><b>${i+1}. ${esc(x.name)}</b><br>${x.units} unidade(s) vendida(s) · ${x.orders} pedido(s) · ${money(x.revenue)}</div>`).join(''):'<p>Nenhuma venda confirmada nos últimos 30 dias.</p>';
  $('#adminapp').innerHTML=adminNav()+`<div class="metrics"><div class="metric">Faturamento<strong>${money(s.sales)}</strong></div><div class="metric">Pedidos confirmados<strong>${s.confirmed_orders}</strong></div><div class="metric">Pendentes<strong>${s.pending}</strong></div><div class="metric">Cancelados<strong>${s.canceled}</strong></div><div class="metric">Ticket médio<strong>${money(s.ticket)}</strong></div></div><div class="panel"><h2>Produtos mais vendidos — últimos 30 dias</h2>${topHtml}</div><div class="panel"><h2>Pedidos recentes</h2>${os.slice(0,8).map(adminOrder).join('')||'<p>Nenhum pedido.</p>'}</div>`;
}
function adminOrder(o){let buttons='';if(o.status==='Aguardando confirmação')buttons=`<button class="btn" onclick="setStatus(${o.id},'Confirmado')">Confirmar</button><button class="btn danger" onclick="setStatus(${o.id},'Cancelado')">Cancelar</button>`;else if(o.status==='Cancelado')buttons=`<button class="btn secondary" onclick="setStatus(${o.id},'Aguardando confirmação')">Reabrir</button><button class="btn" onclick="setStatus(${o.id},'Confirmado')">Confirmar</button>`;return `<div class="order"><b>${o.code}</b> · <span class="status">${o.status}</span><br>${esc(o.email)} · WhatsApp: ${esc(o.whatsapp)}<br>${money(o.total)}<br>${o.items.map(x=>`${x.qty}× ${esc(x.name)}${x.variation_text?' — '+esc(x.variation_text):''}`).join('<br>')}<div class="toolbar">${buttons}<button class="btn secondary" onclick="showHistory(${o.id})">Histórico</button></div></div>`}
async function setStatus(id,status){if(!confirm(`Tem certeza que deseja alterar para ${status}?`))return;try{await api('/api/admin/order/'+id+'/status',{method:'POST',body:JSON.stringify({status})});adminDashboard()}catch(e){alert(e.message)}}
async function showHistory(id){let h=await api('/api/admin/order/'+id+'/history');alert(h.map(x=>`${x.created_at} — ${x.action}: ${x.details}`).join('\n')||'Sem alterações registradas.')}
async function adminOrders(){let os=await api('/api/admin/orders');$('#adminapp').innerHTML=adminNav('orders')+`<div class="panel"><h2>Pedidos</h2>${os.map(adminOrder).join('')||'<p>Nenhum pedido.</p>'}</div>`}
async function adminProducts(){let ps=await api('/api/admin/products');$('#adminapp').innerHTML=adminNav('products')+`<div class="toolbar"><button class="btn" onclick="newProduct()">+ Adicionar produto</button></div><div class="grid">${ps.map(p=>`<article class="card"><div class="pic">${p.photos.length?`<img src="${p.photos[0]}">`:''}</div><div class="body"><h3>${esc(p.name)}</h3><p>${money(p.final_price)}</p><small>${p.status==='published'?'Publicado':'Rascunho'} · ${p.code}</small><div class="toolbar"><button class="btn" onclick='editProduct(${JSON.stringify(p)})'>Editar</button><button class="btn secondary" onclick="deleteProduct(${p.id})">Excluir</button></div></div></article>`).join('')}</div>`}
function newProduct(){productForm({})}function editProduct(p){productForm(p)}
async function adminCatalogSettings(){
  let [cs,colors]=await Promise.all([api('/api/categories'),api('/api/colors')]);
  $('#adminapp').innerHTML=adminNav('catalog')+`<div class="panel"><h2>Categorias</h2><form class="form" onsubmit="addCategory(event)"><input id="newCat" placeholder="Nova categoria" required><button class="btn">Adicionar categoria</button></form><div class="grid">${cs.filter(c=>c.name!=='Sem categoria').map(c=>`<div class="box"><h3>${esc(c.name)}</h3><button class="btn danger" onclick="deleteCategory(${c.id})">Excluir categoria</button></div>`).join('')}</div></div><div class="panel"><h2>Cores disponíveis</h2><form class="form" onsubmit="addColor(event)"><input id="newColor" placeholder="Ex.: Preto, Azul, Dourado" required><button class="btn">Adicionar cor</button></form><div class="toolbar">${colors.map(c=>`<span class="notice">${esc(c.name)} <button type="button" class="btn danger" onclick="deleteColor(${c.id})">×</button></span>`).join('')}</div></div>`;
}
async function addCategory(e){e.preventDefault();try{await api('/api/admin/category',{method:'POST',body:JSON.stringify({name:$('#newCat').value})});adminCatalogSettings()}catch(x){alert(x.message)}}
async function deleteCategory(id){if(!confirm('Existem produtos vinculados a essa categoria. Você quer mesmo excluir essa categoria?'))return;try{await api('/api/admin/category/'+id,{method:'DELETE'});adminCatalogSettings()}catch(x){alert(x.message)}}
async function addColor(e){e.preventDefault();try{await api('/api/admin/color',{method:'POST',body:JSON.stringify({name:$('#newColor').value})});adminCatalogSettings()}catch(x){alert(x.message)}}
async function deleteColor(id){if(!confirm('Excluir esta cor da lista? Ela será removida dos produtos que a utilizam.'))return;try{await api('/api/admin/color/'+id,{method:'DELETE'});adminCatalogSettings()}catch(x){alert(x.message)}}
async function productForm(p){
  editingProduct=p||{};
  let [cs,colors]=await Promise.all([api('/api/categories'),api('/api/colors')]);
  let promoYes=Number(p.promo_percent||0)>0;
  $('#adminapp').innerHTML=adminNav('products')+`<div class="panel"><h2>${p.id?'Editar':'Novo'} produto</h2>
  <form class="form" onsubmit="saveProduct(event,${p.id||0})">
    <input id="pn" value="${esc(p.name||'')}" placeholder="Nome" required>
    <textarea id="pd" placeholder="Descrição" required>${esc(p.description||'')}</textarea>
    <select id="pcat" required>${cs.map(c=>`<option value="${c.id}" ${p.category_id==c.id?'selected':''}>${esc(c.name)}</option>`).join('')}</select>
    <input id="pmat" value="${esc(p.material||'')}" placeholder="Material">
    <input id="psizes" value="${esc((p.sizes||[]).join(', '))}" placeholder="Tamanhos em cm, separados por vírgula">
    <div><label><b>Cores disponíveis neste produto</b></label><div class="color-picker">${colors.map(c=>`<label class="color-option"><input type="checkbox" name="productColor" value="${esc(c.name)}" ${(p.colors||[]).includes(c.name)?'checked':''}><span>${esc(c.name)}</span></label>`).join('')||'<small class="muted">Nenhuma cor cadastrada ainda. Cadastre as cores em “Categorias e cores”.</small>'}</div><small class="muted">Selecione somente as cores que esta peça possui. A lista vem de “Categorias e cores”.</small></div>
    <textarea id="pcare" placeholder="Cuidados com a peça" required>${esc(p.care||'')}</textarea>
    <select id="pmod"><option ${p.modality==='Pronta entrega'?'selected':''}>Pronta entrega</option><option ${p.modality==='Sob encomenda'?'selected':''}>Sob encomenda</option></select>
    <div class="panel"><h3>Preço</h3><input id="pprice" type="number" step="0.01" min="0" value="${p.price??''}" placeholder="Preço" required>
      <label>Promoção</label>
      <select id="ppromoyes" onchange="togglePromoFields()"><option value="nao" ${!promoYes?'selected':''}>Não</option><option value="sim" ${promoYes?'selected':''}>Sim</option></select>
      <div id="promoFields" style="display:${promoYes?'grid':'none'};gap:8px;margin-top:8px">
        <input id="ppromo" type="number" min="1" max="100" step="1" value="${promoYes?p.promo_percent:''}" placeholder="Porcentagem de desconto (1 a 100)">
        <div class="notice" id="promoResult"></div>
      </div>
    </div>
    <div class="panel"><h3>Destaques automáticos</h3><p class="muted">A loja destaca automaticamente as 10 joias mais vendidas nos últimos 30 dias. Não é necessário selecionar produtos manualmente.</p></div>
    <div class="panel"><h3>Fotos do produto</h3><p class="muted">Adicione uma ou mais fotos. Formatos permitidos: JPG, JPEG ou PNG. A primeira foto é a principal.</p>
      <input id="photoInput" type="file" accept="image/jpeg,image/png,.jpg,.jpeg,.png" multiple>
      <div id="photoPreview" class="toolbar"></div>
      ${p.id && (p.photos||[]).length?`<div class="toolbar">${(p.photos||[]).map((x,i)=>`<div><img class="admin-photo" src="${x}"><br><button type="button" class="btn secondary" onclick="mainPhoto(${p.id},${i})">${i===0?'Principal':'Tornar principal'}</button><button type="button" class="btn danger" onclick="deletePhoto(${p.id},${i})">Excluir</button></div>`).join('')}</div>`:''}
    </div>
    <div><button class="btn" type="submit" value="published">Publicar produto</button> <button type="button" class="btn secondary" onclick="saveDraft(${p.id||0})">Salvar como rascunho</button></div>
  </form></div>`;
  $('#photoInput').onchange=previewSelectedPhotos; $('#pprice').oninput=updatePromoResult; $('#ppromo')?.addEventListener('input',updatePromoResult); updatePromoResult();
}
function togglePromoFields(){let yes=$('#ppromoyes')?.value==='sim'; if($('#promoFields'))$('#promoFields').style.display=yes?'grid':'none'; if(!yes&&$('#ppromo'))$('#ppromo').value=''; updatePromoResult()}
function updatePromoResult(){let box=$('#promoResult'); if(!box)return; if($('#ppromoyes')?.value!=='sim'){box.textContent='Sem promoção: o produto será vendido pelo preço cadastrado.';return} let price=Number($('#pprice')?.value||0),pct=Number($('#ppromo')?.value||0); if(!price||!pct){box.textContent='Informe o preço e a porcentagem para calcular o valor promocional.';return} if(pct<1||pct>100){box.textContent='A porcentagem deve estar entre 1 e 100.';return} box.textContent=`Valor promocional: ${money(price*(1-pct/100))}`;}
function previewSelectedPhotos(){let box=$('#photoPreview'); if(!box)return; let files=[...($('#photoInput')?.files||[])]; box.innerHTML=files.map(f=>`<span class="notice">${esc(f.name)}</span>`).join('')||''}
async function collectProductData(id,status){let promoYes=$('#ppromoyes').value==='sim'; let pct=promoYes?Number($('#ppromo').value||0):0; if(promoYes&&(pct<1||pct>100))throw new Error('A porcentagem da promoção deve estar entre 1 e 100.'); let current=editingProduct; return {id:id||null,name:$('#pn').value.trim(),description:$('#pd').value.trim(),category_id:Number($('#pcat').value),material:$('#pmat').value.trim(),sizes:$('#psizes').value.split(',').map(x=>x.trim()).filter(Boolean),colors:[...document.querySelectorAll('input[name="productColor"]:checked')].map(x=>x.value),care:$('#pcare').value.trim(),modality:$('#pmod').value,price:Number($('#pprice').value),promo_percent:pct,status,photos:current?.photos||[]};}
async function uploadSelectedPhotos(id){let files=[...($('#photoInput')?.files||[])]; for(const f of files){let fd=new FormData();fd.append('photo',f);let r=await fetch('/api/admin/product/'+id+'/photo',{method:'POST',body:fd});let d=await r.json();if(!r.ok)throw new Error(d.error||'Erro ao enviar foto.');}}
async function saveProduct(e,id){
  e.preventDefault();
  let status=e.submitter?.value||'published';
  try{
    let d=await collectProductData(id,status);
    let files=[...($('#photoInput')?.files||[])];
    if(status==='published' && !(d.photos.length||files.length)) throw new Error('Para publicar, adicione pelo menos uma foto do produto.');
    if(files.length && (!id || !d.photos.length)){
      d.status='draft';
      let r=await api('/api/admin/product',{method:'POST',body:JSON.stringify(d)});
      await uploadSelectedPhotos(r.id);
      let p=(await api('/api/admin/products')).find(x=>x.id===r.id);
      if(status==='published'){
        d=await collectProductData(r.id,'published');
        d.photos=p.photos;
        await api('/api/admin/product',{method:'POST',body:JSON.stringify(d)});
      }
    }else{
      let r=await api('/api/admin/product',{method:'POST',body:JSON.stringify(d)});
      if(files.length)await uploadSelectedPhotos(r.id||id);
    }
    adminProducts();
  }catch(x){alert(x.message)}
}
async function saveDraft(id){try{let d=await collectProductData(id,'draft');let r=await api('/api/admin/product',{method:'POST',body:JSON.stringify(d)});if($('#photoInput')?.files?.length)await uploadSelectedPhotos(r.id||id);adminProducts()}catch(x){alert(x.message)}}
async function uploadPhoto(id){let f=$('#photoInput').files[0];if(!f)return alert('Escolha uma foto.');let fd=new FormData();fd.append('photo',f);let r=await fetch('/api/admin/product/'+id+'/photo',{method:'POST',body:fd});let d=await r.json();if(!r.ok)return alert(d.error||'Erro');let p=(await api('/api/admin/products')).find(x=>x.id===id);productForm(p)}
async function mainPhoto(id,i){await api('/api/admin/product/'+id+'/main-photo',{method:'POST',body:JSON.stringify({index:i})});productForm((await api('/api/admin/products')).find(x=>x.id===id))}
async function deletePhoto(id,i){if(!confirm('Excluir esta foto?'))return;await fetch('/api/admin/product/'+id+'/photo?index='+i,{method:'DELETE'});productForm((await api('/api/admin/products')).find(x=>x.id===id))}
async function deleteProduct(id){if(!confirm('Excluir este produto do catálogo? O histórico de pedidos será preservado.'))return;await fetch('/api/admin/product/'+id,{method:'DELETE'});adminProducts()}
async function adminSettings(){let s=await api('/api/settings');$('#adminapp').innerHTML=adminNav('settings')+`<div class="panel"><h2>Configurações da loja</h2><p class="muted">A aparência da loja é fixa. Aqui você configura somente os contatos.</p><form class="form" onsubmit="saveSettings(event)"><input id="swa" value="${esc(s.whatsapp||'')}" placeholder="WhatsApp que receberá os pedidos"><input id="sig" value="${esc(s.instagram||'')}" placeholder="@Instagram da loja"><button class="btn">Salvar</button></form></div><div class="panel"><h2>Alterar senha administrativa</h2><form class="form" onsubmit="changeAdminPw(event)"><input id="acur" type="password" placeholder="Senha atual"><input id="anew" type="password" placeholder="Nova senha"><input id="aconf" type="password" placeholder="Repetir nova senha"><button class="btn">Alterar senha</button></form></div>`}
async function saveSettings(e){e.preventDefault();try{await api('/api/admin/settings',{method:'POST',body:JSON.stringify({whatsapp:$('#swa').value,instagram:$('#sig').value})});alert('Configurações salvas.')}catch(x){alert(x.message)}}
async function changeAdminPw(e){e.preventDefault();try{await api('/api/admin/password',{method:'POST',body:JSON.stringify({current:$('#acur').value,new:$('#anew').value,confirm:$('#aconf').value})});alert('Senha alterada.')}catch(x){alert(x.message)}}
