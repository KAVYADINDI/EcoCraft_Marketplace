/* Offline DOM/API simulation of the real marketplace script. No network access. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const elements = new Map();
function el(id) {
  if (!elements.has(id)) elements.set(id, {
    id, value:'', files:[], checked:false, disabled:false, hidden:false,
    fields:{}, textContent:'', className:'', innerHTML:'',
    elements:{namedItem(name){return el('field-'+name)}},
    addEventListener(){}, scrollIntoView(){}, removeAttribute(name){delete this[name]},
    reset(){el('product-image-file').files=[];el('product-image-url').value='';el('product-image-remove').checked=false},
  });
  return elements.get(id);
}
class FormData {
  constructor(form){this.fields=form?.fields||{};this.parts=[]}
  *entries(){yield* Object.entries(this.fields)}
  append(...args){this.parts.push(args)}
}
const user={id:'artist',role:'artist',email:'artist@example.test',personalInfo:{firstName:'Test'}};
const requests=[];
const photos=['https://example.test/one.png','https://example.test/two.png'];
const product={_id:'product',title:'Tote',description:'Cotton tote',price:'25.00',category:'Bags',materials:['Cotton'],inventory:{quantityAvailable:2},images:photos};
let failSave=false;
async function fetch(url,options={}) {
  requests.push({url,...options});
  if(url==='/api/products'&&failSave)return {ok:false,json:async()=>({error:{message:'Save failed'}})};
  const data=url.startsWith('/api/products?')?{products:[]}:
    url==='/api/auth/login'?{accessToken:'fake-jwt',user}:
    url==='/api/auth/me'?{user}:
    url==='/api/products/mine'?{products:[product]}:
    url==='/api/orders/sales'?{sales:[]}:
    url==='/api/products/image-upload'?{url:'https://res.cloudinary.com/demo/image/upload/a.png'}:
    {product,message:'Saved'};
  return {ok:true,json:async()=>data};
}
vm.runInNewContext(fs.readFileSync(path.resolve(__dirname,'../app/static/marketplace.js'),'utf8'),{
  document:{getElementById:el,querySelectorAll:()=>[]},window:{scrollTo(){}},
  fetch,FormData,URLSearchParams,URL,Intl,console,
});
const settle=()=>new Promise(resolve=>setTimeout(resolve,20));
function submit(id){const event={currentTarget:el(id),preventDefault(){}};el(id).onsubmit(event);event.currentTarget=null}
function draft(){
  el('product-form').fields={editingId:'',title:'Tote',description:'Cotton tote',price:'25.00',category:'Bags',materials:'Cotton',tags:'eco',quantityAvailable:'2',imageFile:{},imageUrl:'',removeImage:'on'};
  el('product-image-file').files=[];el('product-image-url').value='';el('product-image-remove').checked=false;
}
function save(){return requests.filter(r=>r.url==='/api/products'||r.url==='/api/products/product').at(-1)}
(async()=>{
  el('login-form').fields={email:user.email,password:'fake-password'};submit('login-form');await settle();
  draft();submit('product-form');await settle();
  let body=JSON.parse(save().body);
  for(const field of ['editingId','imageFile','imageUrl','removeImage'])assert.equal(field in body,false);
  assert.equal('images' in body,false,'optional image must not block normal submission');
  draft();el('product-image-url').value=photos[0];submit('product-form');await settle();
  assert.deepEqual(JSON.parse(save().body).images,[photos[0]]);
  el('artist-products').onclick({target:{closest(selector){return selector==='[data-edit-product]'?{dataset:{editProduct:'product'}}:null}}});
  assert.equal(el('product-image-url').value,photos[0]);
  assert.equal(el('product-image-preview').src,photos[0]);
  draft();el('product-form').fields.editingId='product';el('product-image-url').value=photos[0];submit('product-form');await settle();
  assert.equal('images' in JSON.parse(save().body),false,'editing other fields must preserve every existing image');
  draft();el('product-form').fields.editingId='product';el('product-image-remove').checked=true;submit('product-form');await settle();
  assert.deepEqual(JSON.parse(save().body).images,[]);
  draft();el('product-image-file').files=[{size:20000,type:'image/png'}];failSave=true;submit('product-form');await settle();
  const upload=requests.find(r=>r.url==='/api/products/image-upload');
  assert.equal(upload.headers.Authorization,'Bearer fake-jwt');
  assert.equal('Content-Type' in upload.headers,false,'browser must provide multipart boundary');
  assert.equal(upload.body.parts[0][0],'file');
  assert.deepEqual(JSON.parse(save().body).images,['https://res.cloudinary.com/demo/image/upload/a.png']);
  assert.equal(el('save-product').disabled,false,'failure must permit retry');
  failSave=false;submit('product-form');await settle();
  assert.equal(requests.filter(r=>r.url==='/api/products/image-upload').length,1,'retry reuses uploaded URL');
  draft();el('product-image-url').value='http://example.test/image.png';const count=requests.length;submit('product-form');await settle();
  assert.equal(requests.length,count,'invalid URLs must not save');
  console.log('PASS: optional image, URL, multipart upload, edit preservation, removal, retry, and validation.');
})().catch(error=>{console.error(error);process.exitCode=1});
