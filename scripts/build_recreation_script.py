"""Generate a stand-alone mongosh submission script from the read-only Atlas audit.
Run offline with: python scripts/build_recreation_script.py
Never connects to or writes to MongoDB.
"""
from pathlib import Path
import json, hashlib
ROOT=Path(__file__).resolve().parents[1]
audit=json.loads((ROOT/'reports/atlas_schema_audit.json').read_text())
assert audit['database']=='ecocraft'
for name in ('users','products','cart','orders','reviews'):
    assert name in audit['collections']

def passhash(password,salt):
    """Generate reproducible hashes for fictional submission-only users, not live shared accounts."""
    iterations=600000
    digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),iterations).hex()
    return f'pbkdf2:sha256:{iterations}${salt}${digest}'

lines=["/* EcoCraft MongoDB submission recreation script. Execute in mongosh.",
       " * Never points at the live/shared ecocraft database!",
       " * This script DROPS AND REBUILDS ONLY ecocraft_submission_dev.",
       " * Usage: mongosh 'YOUR_ATLAS_CONNECTION_URI' --file scripts/recreate_demo.js",
       " * Use demo DB users only; do not use production credentials in source files.",
       " */", "const DEMO_DB = 'ecocraft_submission_dev';",
       "if (DEMO_DB !== 'ecocraft_submission_dev') throw new Error('Unsafe target database');",
       "const target = db.getSiblingDB(DEMO_DB);",
       "if (target.getName() === 'ecocraft') throw new Error('REFUSING to touch shared database');",
       "target.dropDatabase(); // restricted to the dedicated submission-demo database above", ""]
for name,details in audit['collections'].items():
    opts={'validator':details['validator'],'validationLevel':details.get('validationLevel','strict'),'validationAction':details.get('validationAction','error')}
    lines.append('target.createCollection('+json.dumps(name)+', '+json.dumps(opts,ensure_ascii=False)+');')
    for idx in details['indexes']:
        if idx['name']=='_id_':continue
        keys={f:v for f,v in idx['keys']}
        kw={'name':idx['name']}
        if idx.get('unique'):kw['unique']=True
        lines.append('target.getCollection('+json.dumps(name)+').createIndex('+json.dumps(keys)+', '+json.dumps(kw)+');')
    lines.append('')
lines += ["// Deterministic sample records exercise references and embedded relationships.",
"const adminId = ObjectId('67aa00000000000000000001');",
"const artistId = ObjectId('67aa00000000000000000002');",
"const buyerId = ObjectId('67aa00000000000000000003');",
"const secondBuyerId = ObjectId('67aa00000000000000000004');",
"const productId = ObjectId('67aa00000000000000000011');",
"const secondProductId = ObjectId('67aa00000000000000000012');",
"const orderId = ObjectId('67aa00000000000000000021');",
"const demoPassword = 'EcoCraftDemo2026!'; // For local submission-only demo accounts.",
"target.users.insertMany([",
"  {_id: adminId,userID:'DEMO-ADM-1',email:'demo.admin@example.test',passwordHash:"+json.dumps(passhash('EcoCraftDemo2026!','demoAdmin2026'))+",role:'admin',personalInfo:{firstName:'Alex',lastName:'Admin'}},",
"  {_id: artistId,userID:'DEMO-ART-1',email:'demo.artist@example.test',passwordHash:"+json.dumps(passhash('EcoCraftDemo2026!','demoArtist2026'))+",role:'artist',personalInfo:{firstName:'Avery',lastName:'Maker'},artistProfile:{originStory:'Turning discarded glass into reusable home decor.',onboardingStatus:'approved'}},",
"  {_id: buyerId,userID:'DEMO-CUS-1',email:'demo.buyer@example.test',passwordHash:"+json.dumps(passhash('EcoCraftDemo2026!','demoBuyer2026'))+",role:'customer',personalInfo:{firstName:'Jordan',lastName:'Buyer'}},",
"  {_id: secondBuyerId,userID:'DEMO-CUS-2',email:'demo.second@example.test',passwordHash:"+json.dumps(passhash('EcoCraftDemo2026!','demoSecond2026'))+",role:'customer',personalInfo:{firstName:'Riley',lastName:'Shopper'}}",
"]);",
"target.products.insertMany([",
"  {_id:productId,artistId:artistId,title:'Reclaimed Glass Candle Holder',description:'Hand-shaped candle holder made from rescued glass.',price:NumberDecimal('28.00'),category:'Home Decor',materials:['Recycled glass'],sustainability:{certified:false,details:'Uses reclaimed glass'},inventory:{quantityAvailable:9},commissionRate:10,approvalStatus:'approved',listProduct:true,tags:['recycled','handmade']},",
"  {_id:secondProductId,artistId:artistId,title:'Upcycled Fabric Tote',description:'Reusable shopping tote made from fabric offcuts.',price:NumberDecimal('35.00'),category:'Accessories',materials:['Fabric offcuts','Cotton thread'],inventory:{quantityAvailable:15},commissionRate:10,approvalStatus:'approved',listProduct:true,tags:['tote','reusable']} ",
"]);",
"target.cart.insertOne({_id:ObjectId('67aa00000000000000000031'),customerId:secondBuyerId,items:[{productId:secondProductId,quantity:2}]});",
"target.orders.insertOne({_id:orderId,customerId:buyerId,items:[{productId:productId,productSnapshot:{title:'Reclaimed Glass Candle Holder',artistId:artistId,artistName:'Avery Maker'},quantity:1,unitPrice:NumberDecimal('28.00'),commissionRate:10,commissionAmount:NumberDecimal('2.80'),artistPayout:NumberDecimal('25.20'),status:'active',shipping:{status:'delivered',shippedAt:ISODate('2026-10-20T10:00:00Z')}}],shippingAddress:{street:'101 Sample Avenue',city:'Demo City',state:'MO',zipCode:'64093',country:'United States'},totals:{subtotal:NumberDecimal('28.00'),commissionTotal:NumberDecimal('2.80'),totalAmount:NumberDecimal('28.00'),artistPayoutTotal:NumberDecimal('25.20')},orderStatus:'completed'});",
"target.reviews.insertOne({_id:ObjectId('67aa00000000000000000041'),productId:productId,customerId:buyerId,orderId:orderId,rating:NumberInt(5),comment:'Creative use of recycled materials.'});",
"print('EcoCraft recreated in: ' + target.getName());",
"for (const name of ['users','products','cart','orders','reviews']) print(name + ': ' + target.getCollection(name).countDocuments({}) + ' documents');",
"print('Demo login: demo.admin@example.test / demo.artist@example.test / demo.buyer@example.test, password: ' + demoPassword);",
]
p=ROOT/'scripts/recreate_demo.js'
p.write_text('\n'.join(lines)+'\n')
print('Wrote',p,'(',p.stat().st_size,'bytes)')
