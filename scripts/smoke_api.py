"""Real HTTP smoke suite for a running local EcoCraft Flask app.

Safe default: only GET requests. Use --write explicitly to create NEW demo
users and NEW linked records in shared ecocraft; it never edits seed records.
Use --write --admin-email <existing-team-admin> for full end-to-end tests.
The password is read securely with getpass and never stored in a file.
"""
import argparse
import getpass
import json
import sys
import uuid
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from urllib.error import HTTPError, URLError

class API:
    def __init__(self,base):self.base=base.rstrip('/');self.passed=0
    def check(self,path,method='GET',body=None,token=None,expect=200,label=None):
        headers={'Accept':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        if body is not None:headers['Content-Type']='application/json'
        request=Request(self.base+'/api'+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
        try:
            with urlopen(request,timeout=15) as r:status=r.status;result=json.loads(r.read())
        except HTTPError as e:
            status=e.code;result=json.loads(e.read().decode())
        if status!=expect:raise AssertionError(f'{label or method+" "+path}: expected {expect}, got {status}: {result}')
        print(f'  PASS {label or method+" "+path} (HTTP {status})');self.passed+=1
        return result

def main():
    """Default to read-only HTTP checks; real new-record writes require explicit opt-in and confirmation."""
    parser=argparse.ArgumentParser(description='Run safe local EcoCraft HTTP checks')
    parser.add_argument('--url',default='http://127.0.0.1:5000')
    parser.add_argument('--write',action='store_true',help='Explicitly create fresh demo documents through the API')
    parser.add_argument('--admin-email',help='Email of existing authorized team admin; required in write mode')
    args=parser.parse_args()
    if args.write and urlparse(args.url).hostname not in {'localhost','127.0.0.1','::1'}:
        parser.error('Write-mode smoke tests are restricted to localhost only')
    api=API(args.url)
    try:
        print('\nREAD-ONLY CHECKS')
        assert api.check('/health')['status']=='ok'
        assert api.check('/health/db')['status']=='ok'
        assert 'products' in api.check('/products')
        assert 'categories' in api.check('/analytics/categories')
        if not args.write:
            print(f'\n{api.passed} READ-ONLY HTTP checks passed. To test writes, use --write --admin-email YOUR_ADMIN_EMAIL.');return 0
        if not args.admin_email:parser.error('--admin-email is required with --write')
        print('\nEXPLICIT WRITE-TEST MODE: generates ONLY new demo users/products/carts/orders/reviews')
        if input('Enter YES to create demo records in your configured database: ').strip()!='YES':
            print('Cancelled before any write');return 1
        adminpw=getpass.getpass('Existing team admin password (not recorded): ')
        admin=api.check('/auth/login','POST',{'email':args.admin_email,'password':adminpw},expect=200,label='admin login')
        assert admin['user']['role']=='admin','The account must have admin role'
        at=admin['accessToken']
        marker=uuid.uuid4().hex[:10]
        userpw='EcoCraftTest_'+uuid.uuid4().hex[:18]+'!'
        artistpw='EcoCraftArtist_'+uuid.uuid4().hex[:18]+'!'
        customer=f'ecocraft-customer-{marker}@example.test'
        artist=f'ecocraft-artist-{marker}@example.test'
        print('Generated user accounts (keep these if you wish to test manually):')
        print('  Customer:',customer,'password:',userpw)
        print('  Artist:',artist,'password:',artistpw)
        try:
            customer_doc=api.check('/auth/register','POST',dict(role='customer',email=customer,password=userpw,firstName='WEB26',lastName='TestCustomer'),expect=201,label='create customer')
            artist_doc=api.check('/auth/register','POST',dict(role='artist',email=artist,password=artistpw,firstName='WEB26',lastName='TestArtist',originStory='I reuse fabric scraps to make beautiful accessories.'),expect=201,label='create artist pending')
            assert customer_doc['user']['userID'].startswith('WEB26-')
            assert artist_doc['user']['userID'].startswith('WEB26-')
            api.check('/auth/login','POST',{'email':artist,'password':artistpw},expect=403,label='pending artist cannot login')
            api.check('/admin/artists/'+artist_doc['user']['id']+'/approval','PATCH',{'status':'approved'},at,200,'admin approves new artist')
            at_artist=api.check('/auth/login','POST',{'email':artist,'password':artistpw},expect=200,label='artist login')['accessToken']
            ct=api.check('/auth/login','POST',{'email':customer,'password':userpw},expect=200,label='customer login')['accessToken']
            api.check('/auth/me','PATCH',{'firstName':'Updated','mobile':'555-0105'},ct,200,'customer profile update')
            api.check('/auth/me','PATCH',{'role':'admin'},ct,400,'reject role privilege escalation')
            api.check('/admin/products',token=ct,expect=403,label='customer cannot see admin moderation')
            payload=dict(title=f'WEB26 Recycled Tote {marker}',description='A hand-stitched tote made from reclaimed textiles.',price='27.50',category='Accessories',materials=['Reclaimed fabric','Cotton thread'],quantityAvailable=10,tags=['eco','upcycled'])
            api.check('/products','POST',{**payload,'price':'-2'},at_artist,400,'reject negative product price')
            api.check('/products','POST',{**payload,'approvalStatus':'approved'},at_artist,400,'reject forged product approval')
            p1=api.check('/products','POST',payload,at_artist,201,'create product')['product']['_id']
            p2=api.check('/products','POST',{**payload,'title':f'WEB26 Recycled Pouch {marker}','price':'12.00'},at_artist,201,'create second product')['product']['_id']
            unused=api.check('/products','POST',{**payload,'title':f'WEB26 Unused Product {marker}'},at_artist,201,'create unused product')['product']['_id']
            api.check('/products/'+p1,'PATCH',{'title':f'WEB26 Improved Tote {marker}'},at_artist,200,'update product and resubmit')
            for id in (p1,p2):api.check('/admin/products/'+id+'/review','PATCH',{'status':'approved','commissionRate':10},at,200,'approve new product')
            result=api.check('/products?search='+marker,label='product search via API')
            assert any(p['_id']==p1 for p in result['products'])
            categories=api.check('/analytics/categories',label='MongoDB aggregation')
            assert categories.get('pipelineStages')==['$match','$group','$sort','$limit']
            api.check('/cart/items','POST',{'productId':p1,'quantity':2},ct,200,'add first cart item')
            api.check('/cart/items','POST',{'productId':p2,'quantity':1},ct,200,'add second cart item')
            api.check('/cart/items/'+p1,'PATCH',{'quantity':1},ct,200,'update cart quantity')
            api.check('/cart/items/'+p2,'DELETE',token=ct,label='remove cart item')
            api.check('/cart/items','POST',{'productId':p2,'quantity':1},ct,200,'re-add second cart item')
            address=dict(street='101 Demo Avenue',city='Warrensburg',state='MO',zipCode='64093',country='United States')
            order=api.check('/orders/checkout','POST',{'shippingAddress':address},ct,201,'checkout with MongoDB transaction')['order']
            order_id=order['_id'];assert len(order['items'])==2
            api.check('/orders/mine',token=ct,label='customer order history')
            api.check('/orders/sales',token=at_artist,label='artist order items')
            review=api.check('/reviews','POST',{'orderId':order_id,'productId':p1,'rating':5,'comment':'Excellent craft'},ct,201,'verified-purchase review')['review']
            api.check('/reviews','POST',{'orderId':order_id,'productId':p1,'rating':4},ct,409,'duplicate review blocked')
            api.check('/reviews/'+review['_id'],'PATCH',{'rating':4},ct,200,'update review')
            api.check('/products/'+p1+'/reviews',label='read product reviews')
            api.check('/reviews/'+review['_id'],'DELETE',token=ct,label='delete own review')
            api.check('/orders/'+order_id+'/items/0/ship','PATCH',{'status':'shipped','trackingNumber':'DEMO-'+marker},at_artist,200,'ship first item')
            api.check('/orders/'+order_id+'/items/1/cancel','PATCH',{},ct,200,'cancel second unshipped item')
            api.check('/orders/'+order_id+'/items/1/cancel','PATCH',{},ct,409,'double cancellation blocked')
            api.check('/orders/'+order_id+'/items/0/ship','PATCH',{'status':'delivered'},at_artist,200,'deliver first item')
            api.check('/products/'+p1,'DELETE',token=at_artist,expect=409,label='referenced product deletion blocked')
            api.check('/products/'+unused,'DELETE',token=at_artist,label='delete unused new product')
        finally:
            print('\nAccounts created for this test use these addresses:',customer,'and',artist)
            print('The test does not delete placed orders: history must remain consistent.')
        print(f'\nPASS: {api.passed} HTTP checks, including live CRUD, validation, transactions and aggregation.');return 0
    except (AssertionError,URLError,ValueError) as e:
        print('\nFAIL:',e,file=sys.stderr)
        print('Only newly generated demo records were eligible for writes.',file=sys.stderr)
        return 1

if __name__=='__main__':sys.exit(main())
