/* Simulate DOM event dispatch and successful API responses. Does not connect to Atlas. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const elements = new Map();
function el(id) {
  if (!elements.has(id)) {
    const obj = {
      id, hidden: false, value: '', textContent: '', innerHTML: '',
      className: '', resetCount: 0, elements: { namedItem: () => ({ value: '' }) },
      scrollIntoView() {}, reset() { this.resetCount += 1; },
      querySelector() { return { required: false }; },
      addEventListener() {}
    };
    elements.set(id, obj);
  }
  return elements.get(id);
}
const register = el('register-form');
register.fields = { firstName: 'Test', lastName: 'Customer', email: 'new@example.test', password: 'password-12345', role: 'customer' };
const login = el('login-form');
login.fields = { email: 'new@example.test', password: 'password-12345' };

const user = { id: 'test', role: 'customer', email: 'new@example.test', personalInfo: { firstName: 'Test', lastName: 'Customer' } };
const requests = [];
async function fetch(url, opts={}) {
  requests.push({url,method:opts.method});
  const result = url.startsWith('/api/products?') ? {products: []} :
    url === '/api/auth/register' ? {message: 'Customer account created successfully.', user} :
    url === '/api/auth/login' ? {accessToken: 'mock-jwt', user} :
    url === '/api/auth/me' ? {user} :
    url === '/api/cart' ? {cart: {items: []}} :
    url === '/api/orders/mine' ? {orders: []} :
    {message:'unexpected mock request'};
  return {ok:true, json:async()=>result};
}
class FakeFormData {
  constructor(form) { this.form=form; }
  *entries() { yield* Object.entries(this.form.fields||{}); }
}
const sandbox = {
  document: {getElementById:el, querySelectorAll:()=>[]},
  window: {scrollTo(){}}, fetch, FormData:FakeFormData,
  URLSearchParams, Intl, Number, String, Promise, console
};
const file=path.resolve(__dirname, '../app/static/marketplace.js');
vm.runInNewContext(fs.readFileSync(file,'utf8'), sandbox, {filename:file});
function dispatch(form) {
  const event={currentTarget:form, preventDefault(){}};
  form.onsubmit(event);
  // Event.currentTarget becomes null once the synchronous dispatch finishes.
  event.currentTarget=null;
}
const settle=()=>new Promise(done=>setTimeout(done,20));
(async()=>{
  dispatch(register);
  await settle();
  assert.equal(register.resetCount,1,'registration must reset the captured form after await');
  assert.match(el('notice').textContent,/Customer account created successfully/);
  assert.equal(el('notice').className,'notice ok');
  assert.equal(requests.filter(r=>r.url==='/api/auth/register').length,1);
  dispatch(login);
  await settle();
  assert.equal(login.resetCount,1,'login must reset the captured form after await');
  assert.match(el('notice').textContent,/Signed in as Test \(customer\)/);
  assert.equal(el('auth-nav').textContent,'Account');
  assert.equal(el('workspace').hidden,false,'dashboard workspace must become visible');
  assert.equal(el('notice').className,'notice ok');
  assert.equal(requests.filter(r=>r.url==='/api/auth/login').length,1);
  console.log('PASS: registration and login succeed when event.currentTarget is nulled after dispatch.');
})().catch(err=>{console.error(err);process.exitCode=1;});
