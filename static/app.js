const $=s=>document.querySelector(s);const $$=s=>document.querySelectorAll(s);const key='lumina_guest_cart';
async function api(url,opt={}){
  const headers=new Headers(opt.headers||{});
  if(opt.body && !(opt.body instanceof FormData))headers.set('Content-Type','application/json');
  const method=(opt.method||'GET').toUpperCase();
  if(!['GET','HEAD','OPTIONS'].includes(method)){
    const tokenResponse=await fetch('/api/csrf',{credentials:'same-origin',cache:'no-store'});
    if(!tokenResponse.ok)throw new Error('Não foi possível validar a sessão. Atualize a página.');
    headers.set('X-CSRF-Token',(await tokenResponse.json()).token);
  }
  const response=await fetch(url,{...opt,headers,credentials:'same-origin',cache:'no-store'});
  const data=await response.json().catch(()=>({error:'Resposta inválida do servidor.'}));
  if(!response.ok)throw new Error(data.error||'Não foi possível concluir a operação.');
  return data;
}
function showError(error){
  let box=document.getElementById('appError');
  if(!box){box=document.createElement('div');box.id='appError';box.className='notice';box.setAttribute('role','alert');document.querySelector('main')?.prepend(box)}
  box.textContent=error?.message||'Não foi possível carregar esta seção. Atualize a página.';
}
window.addEventListener('unhandledrejection',e=>{e.preventDefault();showError(e.reason)});
function safeImage(value){
 if(typeof value!=='string')return '/static/placeholder.svg';
 if(/^\/uploads\/[a-f0-9]{24,32}\.jpg$/.test(value)||/^\/static\/uploads\/[a-f0-9]{24,32}\.jpg$/.test(value)||value==='/static/placeholder.svg')return value;
 return '/static/placeholder.svg';
}

const money=v=>Number(v||0).toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
let guest=[];try{const stored=JSON.parse(localStorage.getItem(key)||'[]');if(Array.isArray(stored))guest=stored}catch(e){localStorage.removeItem(key)}
let editingProduct=null;
function saveGuest(){localStorage.setItem(key,JSON.stringify(guest));badge()}
async function badge(){try{const me=await api('/api/me');const items=me.customer?(await api('/api/cart')).items:guest;const n=items.reduce((sum,x)=>sum+Number(x.qty||0),0);$$('.cart-badge').forEach(e=>e.textContent=n>9?'9+':n)}catch(e){/* Cart page reports actionable errors. */}}
async function syncCart(){let me=await api('/api/me');if(!me.customer)return;let server=(await api('/api/cart')).items||[];let merged=[...server];for(const x of guest){let i=merged.findIndex(y=>y.product_id===x.product_id&&y.color===x.color&&y.size===x.size&&y.material===x.material);if(i>=0)merged[i].qty+=x.qty;else merged.push(x)}await api('/api/cart',{method:'POST',body:JSON.stringify({items:merged})});guest=[];saveGuest()}
async function cartItems(){let me=await api('/api/me');return me.customer?(await api('/api/cart')).items:guest}
async function setCart(items){let me=await api('/api/me');if(me.customer)await api('/api/cart',{method:'POST',body:JSON.stringify({items})});else{guest=items;saveGuest()}}
function photo(p){return safeImage(p.photos?.[0])}
function card(p){return `<article class="card"><a href="/product/${p.id}"><div class="pic"><img src="${photo(p)}" alt="${esc(p.name)}"></div></a><div class="body"><small>${esc(p.category_name||'')}</small><h3>${esc(p.name)}</h3><p>${p.promo_percent>0?`<span class="old">${money(p.price)}</span> `:''}<span class="price">${money(p.final_price)}</span>${p.promo_percent>0?` <span class="off">${p.promo_percent}% OFF</span>`:''}</p><a class="btn" href="/product/${p.id}">Ver produto</a></div></article>`}
function esc(s){return String(s??'').replace(/[&<>'"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[m]))}
async function home(){
  badge();
  let query=location.search.replace(/^\?/,'');
  let [cs,products,allProducts,featured]=await Promise.all([api('/api/categories'),api('/api/products?'+query),api('/api/products'),api('/api/featured').catch(()=>null)]);
  let q=new URLSearchParams(location.search);
  $('#featured').innerHTML=featured===null?'<p>Não foi possível carregar os destaques. O catálogo continua disponível.</p>':featured.length?featured.map(card).join(''):'<p>Nenhum produto em destaque nos últimos 30 dias.</p>';
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
function applyFilters(){let p=new URLSearchParams();let mappings={search:'q',catFilter:'category',colorFilter:'color',sizeFilter:'size',materialFilter:'material',modalityFilter:'modality',promoFilter:'promo',sort:'sort'};Object.entries(mappings).forEach(([id,param])=>{let e=$('#'+id);if(e&&e.value)p.set(param,e.value)});location.href='/?'+p.toString()+'#catalogo'}
let state={p:null,color:null,size:null,material:null,qty:1,photo:0};
async function productPage(pid){let p=await api('/api/product/'+pid);state={p,color:p.colors?.[0]||null,size:p.sizes?.[0]||null,material:p.material&&false? p.material:null,qty:1,photo:0};drawProduct()}
function drawProduct(){let p=state.p;if(!p)return;let imgs=p.photos||[];let main=imgs[state.photo]||'/static/placeholder.svg';$('#prod').innerHTML=`<div class="detail"><div><div class="gallery"><img src="${esc(safeImage(main))}" alt="${esc(p.name)}"></div>${imgs.length>1?`<div class="thumbs">${imgs.map((x,i)=>`<img class="${i===state.photo?'active':''}" src="${esc(safeImage(x))}" onclick="state.photo=${i};drawProduct()">`).join('')}</div>`:''}</div><div><small>${esc(p.category_name||'')}</small><h1>${esc(p.name)}</h1><p>${p.promo_percent>0?`<span class="old">${money(p.price)}</span> `:''}<b>${money(p.final_price)}</b></p><p><b>${esc(p.modality)}</b></p>${p.colors.length?`<h3>Cor</h3><div class="chips">${p.colors.map(v=>`<button class="chip ${state.color===v?'active':''}" onclick="chooseColor(${p.colors.indexOf(v)})">${esc(v)}</button>`).join('')}</div>`:''}${p.sizes.length?`<h3>Tamanho</h3><div class="chips">${p.sizes.map(v=>`<button class="chip ${state.size===v?'active':''}" onclick="chooseSize(${p.sizes.indexOf(v)})">${esc(v)}</button>`).join('')}</div>`:''}<div class="qty"><button onclick="state.qty=Math.max(1,state.qty-1);drawProduct()">−</button><span>${state.qty}</span><button onclick="state.qty++;drawProduct()">+</button></div><p><button class="btn" onclick="addToCart()">Adicionar ao carrinho</button></p><h3>Descrição</h3><p>${esc(p.description)}</p>${p.material?`<h3>Material</h3><p>${esc(p.material)}</p>`:''}<h3>Cuidados com a peça</h3><p>${esc(p.care)}</p></div></div>`}

async function addToCart(){let p=state.p;let items=await cartItems();let item={product_id:p.id,name:p.name,qty:state.qty,unit_price:p.final_price,color:state.color,size:state.size,material:null};let i=items.findIndex(x=>x.product_id===item.product_id&&x.color===item.color&&x.size===item.size&&x.material===item.material);if(i>=0)items[i].qty+=item.qty;else items.push(item);await setCart(items);alert('Produto adicionado ao carrinho!');location.href='/cart'}

async function changeQty(i,n){let items=await cartItems();items[i].qty=Math.max(1,items[i].qty+n);await setCart(items);cartPage()}
async function removeCart(i){let items=await cartItems();items.splice(i,1);await setCart(items);cartPage()}

async function accountPage(){let me=await api('/api/me');if(!me.customer){$('#account').innerHTML=`<div class="two"><div class="box"><h2>Entrar</h2><form class="form" onsubmit="login(event)"><input id="lemail" type="email" placeholder="E-mail" required><input id="lpass" type="password" placeholder="Senha" required><button class="btn">Entrar</button></form></div><div class="box"><h2>Criar conta</h2><form class="form" onsubmit="register(event)"><input id="remail" type="email" placeholder="E-mail" required><input id="rwa" placeholder="WhatsApp" required><input id="rpass" type="password" placeholder="Senha" required><input id="rconf" type="password" placeholder="Confirmar senha" required><button class="btn">Criar conta</button></form></div></div>`;return}let os=await api('/api/orders');$('#account').innerHTML=`<div class="box"><h2>Minha conta</h2><p>E-mail: <b>${esc(me.customer.email)}</b></p><p>WhatsApp: <b>${esc(me.customer.whatsapp)}</b></p><form class="form" onsubmit="changeWa(event)"><input id="cwa" value="${esc(me.customer.whatsapp)}" placeholder="WhatsApp"><button class="btn secondary">Atualizar WhatsApp</button></form><h3>Alterar senha</h3><form class="form" onsubmit="changePw(event)"><input id="ccur" type="password" placeholder="Senha atual"><input id="cnew" type="password" placeholder="Nova senha"><input id="cconf" type="password" placeholder="Repetir nova senha"><button class="btn secondary">Alterar senha</button></form><button class="btn danger" onclick="logout()">Sair</button></div><div class="box"><h2>Meus pedidos</h2>${os.length?os.map(o=>`<div class="order"><b>${esc(o.code)}</b> · <span class="status">${esc(o.status)}</span><br>${new Date(o.created_at+'Z').toLocaleString('pt-BR')}<br>${o.items.map(x=>`${x.qty}× ${esc(x.name)}${x.variation_text?' — '+esc(x.variation_text):''}`).join('<br>')}<br><b>${money(o.total)}</b></div>`).join(''):'Nenhum pedido ainda.'}</div>`}
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
function adminOrder(o){let buttons='';if(o.status==='Aguardando confirmação')buttons=`<button class="btn" onclick="setStatus(${o.id},'Confirmado')">Confirmar</button><button class="btn danger" onclick="setStatus(${o.id},'Cancelado')">Cancelar</button>`;else if(o.status==='Cancelado')buttons=`<button class="btn secondary" onclick="setStatus(${o.id},'Aguardando confirmação')">Reabrir</button><button class="btn" onclick="setStatus(${o.id},'Confirmado')">Confirmar</button>`;return `<div class="order"><b>${esc(o.code)}</b> · <span class="status">${esc(o.status)}</span><br>${esc(o.email)} · WhatsApp: ${esc(o.whatsapp)}<br>${money(o.total)}<br>${o.items.map(x=>`${x.qty}× ${esc(x.name)}${x.variation_text?' — '+esc(x.variation_text):''}`).join('<br>')}<div class="toolbar">${buttons}<button class="btn secondary" onclick="showHistory(${o.id})">Histórico</button></div></div>`}
async function setStatus(id,status){if(!confirm(`Tem certeza que deseja alterar para ${status}?`))return;try{await api('/api/admin/order/'+id+'/status',{method:'POST',body:JSON.stringify({status})});adminDashboard()}catch(e){alert(e.message)}}
async function showHistory(id){let h=await api('/api/admin/order/'+id+'/history');alert(h.map(x=>`${x.created_at} — ${x.action}: ${x.details}`).join('\n')||'Sem alterações registradas.')}
async function adminOrders(){let os=await api('/api/admin/orders');$('#adminapp').innerHTML=adminNav('orders')+`<div class="panel"><h2>Pedidos</h2>${os.map(adminOrder).join('')||'<p>Nenhum pedido.</p>'}</div>`}
async function adminProducts(){let ps=await api('/api/admin/products');$('#adminapp').innerHTML=adminNav('products')+`<div class="toolbar"><button class="btn" onclick="newProduct()">+ Adicionar produto</button></div><div class="grid">${ps.map(p=>`<article class="card"><div class="pic">${p.photos.length?`<img src="${esc(safeImage(p.photos[0]))}">`:''}</div><div class="body"><h3>${esc(p.name)}</h3><p>${money(p.final_price)}</p><small>${p.status==='published'?'Publicado':'Rascunho'} · ${p.code}</small><div class="toolbar"><button class="btn" onclick="editProductById(${p.id})">Editar</button><button class="btn secondary" onclick="deleteProduct(${p.id})">Excluir</button></div></div></article>`).join('')}</div>`}
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
    <label><input id="phigh" type="checkbox" ${p.highlighted?'checked':''}> Destacar este produto</label><div class="panel"><h3>Destaques automáticos</h3><p class="muted">A loja destaca automaticamente as 10 joias mais vendidas nos últimos 30 dias. Não é necessário selecionar produtos manualmente.</p></div>
    <div class="panel"><h3>Fotos do produto</h3><p class="muted">Adicione uma ou mais fotos. Formatos permitidos: JPG, PNG, WebP, HEIC/HEIF, GIF, BMP e TIFF (até 20 MB). A primeira foto é a principal.</p>
      <input id="photoInput" type="file" accept="image/*,.heic,.heif,.webp,.tif,.tiff,.bmp,.gif" multiple>
      <div id="photoPreview" class="toolbar"></div>
      ${p.id && (p.photos||[]).length?`<div class="toolbar">${(p.photos||[]).map((x,i)=>`<div><img class="admin-photo" src="${esc(safeImage(x))}"><br><button type="button" class="btn secondary" onclick="mainPhoto(${p.id},${i})">${i===0?'Principal':'Tornar principal'}</button><button type="button" class="btn danger" onclick="deletePhoto(${p.id},${i})">Excluir</button></div>`).join('')}</div>`:''}
    </div>
    <div><button class="btn" type="submit" value="published">Publicar produto</button> <button type="button" class="btn secondary" onclick="saveDraft(${p.id||0})">Salvar como rascunho</button></div>
  </form></div>`;
  await addProductExtras(p,cs); $('#photoInput').onchange=previewSelectedPhotos; $('#pprice').oninput=updatePromoResult; $('#ppromo')?.addEventListener('input',updatePromoResult); updatePromoResult();
}
function togglePromoFields(){let yes=$('#ppromoyes')?.value==='sim'; if($('#promoFields'))$('#promoFields').style.display=yes?'grid':'none'; if(!yes&&$('#ppromo'))$('#ppromo').value=''; updatePromoResult()}
function updatePromoResult(){let box=$('#promoResult'); if(!box)return; if($('#ppromoyes')?.value!=='sim'){box.textContent='Sem promoção: o produto será vendido pelo preço cadastrado.';return} let price=Number($('#pprice')?.value||0),pct=Number($('#ppromo')?.value||0); if(!price||!pct){box.textContent='Informe o preço e a porcentagem para calcular o valor promocional.';return} if(pct<1||pct>100){box.textContent='A porcentagem deve estar entre 1 e 100.';return} box.textContent=`Valor promocional: ${money(price*(1-pct/100))}`;}

async function collectProductData(id,status){let promoYes=$('#ppromoyes').value==='sim'; let pct=promoYes?Number($('#ppromo').value||0):0; if(promoYes&&(pct<1||pct>100))throw new Error('A porcentagem da promoção deve estar entre 1 e 100.'); let current=editingProduct; return {id:id||null,name:$('#pn').value.trim(),description:$('#pd').value.trim(),category_id:Number($('#pcat').value),material:$('#pmat').value.trim(),sizes:$('#psizes').value.split(',').map(x=>x.trim()).filter(Boolean),colors:[...document.querySelectorAll('input[name="productColor"]:checked')].map(x=>x.value),care:$('#pcare').value.trim(),modality:$('#pmod').value,price:Number($('#pprice').value),promo_percent:pct,status,photos:current?.photos||[],highlighted:$('#phigh')?.checked||false,subcategory_id:$('#psub')?.value||null,variation_photos:collectVariationPhotos()};}









async function changeAdminPw(e){e.preventDefault();try{await api('/api/admin/password',{method:'POST',body:JSON.stringify({current:$('#acur').value,new:$('#anew').value,confirm:$('#aconf').value})});alert('Senha alterada.')}catch(x){alert(x.message)}}

async function editProductById(id){const product=(await api('/api/admin/products')).find(p=>p.id===id);if(!product)throw new Error('Produto não encontrado.');await productForm(product)}
function chooseColor(index){state.color=state.p.colors[index];const image=state.p.variation_photos?.[state.color];if(image){const i=state.p.photos.indexOf(image);if(i>=0)state.photo=i}drawProduct()}
function chooseSize(index){state.size=state.p.sizes[index];drawProduct()}
async function previewSelectedPhotos(){
 const box=$('#photoPreview');if(!box)return;box.replaceChildren();
 for(const file of [...($('#photoInput')?.files||[])]){
  const wrapper=document.createElement('div');const name=document.createElement('small');name.textContent=file.name;wrapper.append(name);
  if(file.size>20*1024*1024){name.textContent+=' — maior que 20 MB';box.append(wrapper);continue}
  const img=document.createElement('img');img.className='admin-photo';img.alt='Prévia de '+file.name;
  const objectURL=URL.createObjectURL(file);img.onload=()=>URL.revokeObjectURL(objectURL);img.onerror=()=>{URL.revokeObjectURL(objectURL);img.remove();name.textContent+=' — a prévia será gerada após a conversão no servidor'};img.src=objectURL;wrapper.prepend(img);box.append(wrapper);
 }
}
async function uploadSelectedPhotos(id){
 let files=[...($('#photoInput')?.files||[])];for(const f of files){const fd=new FormData();fd.append('photo',f);const result=await api('/api/admin/product/'+id+'/photo',{method:'POST',body:fd});editingProduct.photos=result.photos}
}
let savingProduct=false;
async function persistProduct(id,status){
 if(savingProduct)return;savingProduct=true;
 const buttons=[...document.querySelectorAll('#adminapp form button')];buttons.forEach(b=>b.disabled=true);
 try{
  let data=await collectProductData(id,status);const files=[...($('#photoInput')?.files||[])];
  if(status==='published'&&!data.photos.length&&!files.length)throw new Error('Adicione pelo menos uma foto para publicar.');
  const targetId=id||editingProduct?.id;
  data.id=targetId||null;
  // Save new/no-photo products as drafts until the actual image transaction succeeds.
  if(files.length&&!data.photos.length)data.status='draft';
  let saved=await api('/api/admin/product',{method:'POST',body:JSON.stringify(data)});editingProduct=saved;
  await uploadSelectedPhotos(saved.id);
  saved=(await api('/api/admin/products')).find(p=>p.id===saved.id);editingProduct=saved;
  if(saved.status!==status){await api('/api/admin/product',{method:'POST',body:JSON.stringify({...saved,status})})}
  alert(status==='published'?'Produto publicado e confirmado no banco.':'Rascunho salvo e confirmado no banco.');await adminProducts();
 }catch(error){
  showError(error);alert(error.message);
  // Preserve the saved draft identity to prevent duplicate products on a retry.
  if(editingProduct?.id)await productForm(editingProduct);
 }finally{savingProduct=false;buttons.forEach(b=>b.disabled=false)}
}
async function saveProduct(e,id){e.preventDefault();await persistProduct(id||editingProduct?.id,'published')}
async function saveDraft(id){await persistProduct(id||editingProduct?.id,'draft')}
async function mainPhoto(id,index){try{await api('/api/admin/product/'+id+'/main-photo',{method:'POST',body:JSON.stringify({index})});await editProductById(id)}catch(e){showError(e)}}
async function deletePhoto(id,index){if(!confirm('Remover esta foto do produto?'))return;try{await api('/api/admin/product/'+id+'/photo?index='+index,{method:'DELETE'});await editProductById(id)}catch(e){showError(e)}}
async function deleteProduct(id){if(!confirm('Arquivar este produto? Os dados e pedidos serão preservados.'))return;try{await api('/api/admin/product/'+id,{method:'DELETE'});await adminProducts()}catch(e){showError(e)}}
let checkoutBusy=false;
async function checkout(){
 if(checkoutBusy)return;
 const me=await api('/api/me');if(!me.customer){location.href='/account?next=checkout';return}
 checkoutBusy=true;
 try{
  const items=await cartItems();const identity=JSON.stringify(items.map(x=>({product_id:x.product_id,qty:x.qty,color:x.color,size:x.size})));
  let saved;try{saved=JSON.parse(sessionStorage.getItem('lumina_checkout')||'null')}catch(e){}
  if(!saved||saved.identity!==identity){saved={identity,key:crypto.randomUUID()};sessionStorage.setItem('lumina_checkout',JSON.stringify(saved))}
  const result=await api('/api/order',{method:'POST',headers:{'Idempotency-Key':saved.key},body:JSON.stringify({items})});
  guest=[];saveGuest();location.href='https://wa.me/'+result.whatsapp+'?text='+encodeURIComponent(result.message);
 }catch(e){showError(e);alert(e.message)}finally{checkoutBusy=false}
}
async function cartPage(){
 badge();let items=await cartItems();
 if(items.length){const quote=await api('/api/quote',{method:'POST',body:JSON.stringify({items})});items=quote.items;await setCart(items)}
 if(!items.length){$('#cart').innerHTML='<div class="box empty"><h2>Seu carrinho está vazio.</h2><a class="btn" href="/">Ver produtos</a></div>';$('#total').textContent=money(0);return}
 $('#cart').innerHTML=items.map((x,i)=>`<div class="cartrow"><div class="thumb"><img src="${esc(safeImage(x.photo))}" alt="${esc(x.name)}"></div><div><b>${esc(x.name)}</b><small><br>${esc(x.variation_text)}</small><br>${money(x.unit_price)} un.</div><div class="qty"><button onclick="changeQty(${i},-1)">−</button><span>${x.qty}</span><button onclick="changeQty(${i},1)">+</button></div><div class="line-total"><b>${money(x.unit_price*x.qty)}</b><button class="btn danger" onclick="removeCart(${i})">×</button></div></div>`).join('');
 $('#total').textContent=money(items.reduce((sum,x)=>sum+x.unit_price*x.qty,0));badge();
}
async function addProductExtras(p,cs){
 const subs=await api('/api/subcategories');
 const sub=document.createElement('select');sub.id='psub';sub.innerHTML='<option value="">Sem subcategoria</option>'+subs.filter(s=>s.category_id===Number($('#pcat').value)).map(s=>`<option value="${s.id}" ${p.subcategory_id===s.id?'selected':''}>${esc(s.name)}</option>`).join('');$('#pcat').after(sub);
 $('#pcat').onchange=()=>{sub.innerHTML='<option value="">Sem subcategoria</option>'+subs.filter(s=>s.category_id===Number($('#pcat').value)).map(s=>`<option value="${s.id}">${esc(s.name)}</option>`).join('')};
 if(p.photos?.length){const box=document.createElement('div');box.id='variationPhotos';box.className='panel';box.innerHTML='<h3>Fotos por cor</h3>'+(p.colors||[]).map((color,i)=>`<label>${esc(color)}<select data-variation="${esc(color)}"><option value="">Foto principal</option>${p.photos.map((url,j)=>`<option value="${esc(url)}" ${p.variation_photos?.[color]===url?'selected':''}>Foto ${j+1}</option>`).join('')}</select></label>`).join('');$('#photoPreview').after(box)}
}
function collectVariationPhotos(){const out={};document.querySelectorAll('[data-variation]').forEach(e=>{if(e.value)out[e.dataset.variation]=e.value});return out}
async function forgotPassword(){const email=$('#lemail')?.value||prompt('Informe seu email cadastrado:');if(!email)return;try{const result=await api('/api/password/forgot',{method:'POST',body:JSON.stringify({email})});alert(result.message)}catch(e){showError(e)}}
const originalAccountPage=accountPage;
accountPage=async function(){await originalAccountPage();if($('#lemail')){const button=document.createElement('button');button.type='button';button.className='btn secondary';button.textContent='Esqueci minha senha';button.onclick=forgotPassword;$('#lemail').closest('form').append(button)}};
async function adminSettings(){
 const s=await api('/api/settings');$('#adminapp').innerHTML=adminNav('settings')+`<div class="panel"><h2>Configurações da loja</h2><form class="form" onsubmit="saveSettings(event)">
 <label>Nome da loja<input id="sname" value="${esc(s.store_name||'Lumina Signature')}" required></label>
 <label>WhatsApp com DDI e DDD<input id="swa" value="${esc(s.whatsapp||'')}"></label><label>Instagram<input id="sig" value="${esc(s.instagram||'')}"></label>
 <label>Frase do rodapé<textarea id="sfooter">${esc(s.footer_phrase||'')}</textarea></label><label>Texto acima do rodapé<textarea id="sabove">${esc(s.above_footer||'')}</textarea></label>
 <label>Email de contato<input id="semail" type="email" value="${esc(s.contact_email||'')}"></label><label>Contato adicional<input id="sextra" value="${esc(s.contact_extra||'')}"></label>
 <label>Logotipo<input type="file" accept="image/*,.heic,.heif" id="slogo"></label><label>Banner<input type="file" accept="image/*,.heic,.heif" id="sbanner"></label><button class="btn">Salvar</button></form></div>
 <div class="panel"><h2>Alterar senha administrativa</h2><form class="form" onsubmit="changeAdminPw(event)"><input id="acur" type="password" placeholder="Senha atual" required><input id="anew" type="password" placeholder="Nova senha" minlength="12" required><input id="aconf" type="password" placeholder="Repetir senha" required><button class="btn">Alterar senha</button></form></div>
 <div class="panel"><h2>Convidar administradora</h2><form class="form" onsubmit="inviteAdmin(event)"><input id="inviteEmail" type="email" placeholder="Email da convidada" required><select id="inviteRole"><option value="viewer">Somente visualização</option><option value="owner">Acesso total</option></select><button class="btn">Gerar convite</button></form><div id="inviteLink"></div></div>`;
}
async function saveSettings(e){e.preventDefault();const button=e.submitter;button.disabled=true;try{
 const values={store_name:$('#sname').value,whatsapp:$('#swa').value,instagram:$('#sig').value,footer_phrase:$('#sfooter').value,above_footer:$('#sabove').value,contact_email:$('#semail').value,contact_extra:$('#sextra').value};
 for(const field of ['logo','banner']){const file=$('#s'+field).files[0];if(file){const data=new FormData();data.append('photo',file);values[field]=(await api('/api/admin/media',{method:'POST',body:data})).url}}
 await api('/api/admin/settings',{method:'POST',body:JSON.stringify(values)});alert('Configurações confirmadas no banco.');
 }catch(error){showError(error)}finally{button.disabled=false}}
async function inviteAdmin(e){e.preventDefault();try{const result=await api('/api/admin/invites',{method:'POST',body:JSON.stringify({email:$('#inviteEmail').value,role:$('#inviteRole').value})});const link=document.createElement('a');link.href=result.url;link.textContent='Abrir convite (expira em 48 horas)';$('#inviteLink').replaceChildren(link)}catch(error){showError(error)}}
async function applyBranding(){try{const settings=await api('/api/settings');
 document.querySelectorAll('.brand').forEach(node=>{if(settings.logo){const img=document.createElement('img');img.src=safeImage(settings.logo);img.alt=settings.store_name||'Lumina Signature';img.style.maxWidth='150px';img.style.maxHeight='64px';node.replaceChildren(img)}});
 if(settings.store_name){document.querySelector('.hero h1')?.replaceChildren(document.createTextNode(settings.store_name));document.querySelectorAll('.footer strong').forEach(n=>n.textContent=settings.store_name)}
 if(settings.banner){const hero=document.querySelector('.hero');if(hero){const img=document.createElement('img');img.src=safeImage(settings.banner);img.alt=settings.store_name||'Lumina Signature';img.className='store-banner';hero.prepend(img)}}
 if(settings.above_footer){const text=document.createElement('p');text.textContent=settings.above_footer;document.querySelector('.footer')?.prepend(text)}
 }catch(error){showError(error)}}
applyBranding();
const originalCatalogSettings=adminCatalogSettings;
adminCatalogSettings=async function(){await originalCatalogSettings();const [categories,subcategories]=await Promise.all([api('/api/categories'),api('/api/subcategories')]);const section=document.createElement('div');section.className='panel';section.innerHTML=`<h2>Subcategorias</h2><form class="form" onsubmit="addSubcategory(event)"><select id="subCategoryParent">${categories.map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select><input id="subCategoryName" placeholder="Nome da subcategoria" required><button class="btn">Adicionar subcategoria</button></form><div>${subcategories.map(s=>`<p>${esc(categories.find(c=>c.id===s.category_id)?.name||'')} — ${esc(s.name)} <button class="btn danger" onclick="deleteSubcategory(${s.id})">Excluir</button></p>`).join('')}</div>`;$('#adminapp').append(section)};
async function addSubcategory(e){e.preventDefault();try{await api('/api/admin/subcategory',{method:'POST',body:JSON.stringify({category_id:Number($('#subCategoryParent').value),name:$('#subCategoryName').value})});await adminCatalogSettings()}catch(error){showError(error)}}
async function deleteSubcategory(id){if(!confirm('Excluir esta subcategoria? Os produtos serão preservados.'))return;try{await api('/api/admin/subcategory/'+id,{method:'DELETE'});await adminCatalogSettings()}catch(error){showError(error)}}
const originalDashboard=adminDashboard;
adminDashboard=async function(){await originalDashboard();const section=document.createElement('section');section.className='panel';section.innerHTML=`<h2>Faturamento por período</h2><form class="toolbar" onsubmit="loadRevenue(event)"><input id="revenueYear" type="number" min="2020" max="2100" value="${new Date().getFullYear()}" aria-label="Ano"><select id="revenueMonth" aria-label="Mês"><option value="">Ano inteiro</option>${Array.from({length:12},(_,i)=>`<option value="${i+1}">${i+1}</option>`).join('')}</select><button class="btn">Consultar</button></form><div id="revenueResult"></div>`;$('#adminapp').append(section)};
async function loadRevenue(e){e.preventDefault();try{const result=await api('/api/admin/revenue?year='+encodeURIComponent($('#revenueYear').value)+'&month='+encodeURIComponent($('#revenueMonth').value));$('#revenueResult').textContent=`${result.orders} pedido(s) confirmado(s) — ${money(result.total)}`}catch(error){showError(error)}}
