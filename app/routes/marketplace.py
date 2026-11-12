"""EcoCraft marketplace CRUD, ownership, transactions and MongoDB aggregation.

Shared Atlas write policy: original team seed documents are NEVER mutated.
Only WEB26-registered customers/artists and products belonging to WEB26 artists
are eligible for writes. Admin actions target only WEB26 accounts/products.
"""
from datetime import datetime, timezone
from decimal import Decimal
import re

from bson import ObjectId, Decimal128
from flask import Blueprint, current_app, g, jsonify, request
from pymongo.errors import PyMongoError, DuplicateKeyError, OperationFailure

from ..db import get_database, get_client
from ..image_uploads import (MAX_IMAGE_BYTES, MAX_REQUEST_BYTES, InvalidImage,
                             UploadNotConfigured, UploadFailed, upload_product_photo)
from ..security import api_error, auth_required, require_write_enabled, can_edit_user, public_user
from ..marketplace_core import BadInput, obj, string, whole, money, rate, parse_product, parse_address, amounts, order_totals, order_status

shop_bp=Blueprint('shop',__name__)


def safe(fn):
    """Convert expected input/database exceptions to predictable JSON without leaking details."""
    from functools import wraps
    @wraps(fn)
    def wrapped(*a,**k):
        try:return fn(*a,**k)
        except BadInput as exc:return api_error('VALIDATION_ERROR',str(exc),400)
        except DuplicateKeyError:return api_error('DUPLICATE','A matching record already exists',409)
        except (PyMongoError,ValueError) as exc:
            current_app.logger.exception('Marketplace operation failed')
            return api_error('DATABASE_UNAVAILABLE','MongoDB operation could not be completed',503)
    return wrapped


def oid(raw):
    """Convert a client-supplied identifier to ObjectId, reporting malformed IDs as input errors."""
    if not isinstance(raw,str) or not ObjectId.is_valid(raw):raise BadInput('Invalid MongoDB ObjectId')
    return ObjectId(raw)


def jsonify_doc(value):
    """Serialize BSON IDs, money and dates recursively while withholding passwordHash."""
    if isinstance(value,ObjectId):return str(value)
    if isinstance(value,Decimal128):return format(value.to_decimal(),'.2f')
    if isinstance(value,Decimal):return format(value,'.2f')
    if isinstance(value,datetime):return value.isoformat()
    if isinstance(value,list):return [jsonify_doc(v) for v in value]
    if isinstance(value,dict):return {k:jsonify_doc(v) for k,v in value.items() if k!='passwordHash'}
    return value


def written():
    """Combine write opt-in with caller eligibility; this gate never replaces record ownership checks."""
    denied=require_write_enabled()
    if denied is not None:return denied
    if not can_edit_user(g.current_user):
        return api_error('SEEDED_RECORD_PROTECTED','Original seed accounts cannot perform demo writes',403)
    return None


def demo_artist(db,artist_id):
    """Check whether the product owner is an eligible artist under the configured seed policy."""
    user=db.users.find_one({'_id':artist_id,'role':'artist'})
    return user is not None and can_edit_user(user)


def own_product(db,product_id):
    """Find an artist-owned editable product; deny another artist's or original seed product."""
    doc=db.products.find_one({'_id':product_id,'artistId':g.current_user['_id']})
    if not doc:return None
    if not demo_artist(db,doc['artistId']):return None
    return doc


def demo_product(db,doc):
    """Require an existing product whose owning artist passes the seed-eligibility policy."""
    return bool(doc and demo_artist(db,doc['artistId']))


def query_page():
    """Parse bounded ASCII pagination; callers raise the returned BadInput on invalid input."""
    page=request.args.get('page','1')
    if not (page.isascii() and page.isdigit()) or not 1<=int(page)<=100:return BadInput('page must be between 1 and 100')
    return int(page)


@shop_bp.get('/products')
@safe
def browse():
    """Read only approved/listed products; escape search text before constructing regex filters."""
    page=query_page()
    if isinstance(page,BadInput):raise page
    term=request.args.get('search','').strip()
    category=request.args.get('category','').strip()
    if len(term)>80 or len(category)>100:raise BadInput('Search or category is too long')
    query={'listProduct':True,'approvalStatus':'approved'}
    if term:query['$or']=[{'title':{'$regex':re.escape(term),'$options':'i'}},{'description':{'$regex':re.escape(term),'$options':'i'}},{'tags':{'$regex':re.escape(term),'$options':'i'}}]
    if category:query['category']=category
    docs=get_database().products.find(query).sort('_id',-1).skip((page-1)*20).limit(20)
    return jsonify(products=jsonify_doc(list(docs)),page=page,pageSize=20),200


@shop_bp.get('/products/mine')
@auth_required('artist')
@safe
def my_products():
    """Read the authenticated artist's listings, including products awaiting moderation."""
    docs=get_database().products.find({'artistId':g.current_user['_id']}).sort('_id',-1).limit(200)
    return jsonify(products=jsonify_doc(list(docs))),200


@shop_bp.post('/products/image-upload')
@auth_required('artist')
@safe
def upload_image():
    """Upload an eligible artist photo to hosting; product creation remains a separate request."""
    denied=written()
    if denied:return denied
    if g.current_user.get('artistProfile',{}).get('onboardingStatus')!='approved':
        return api_error('ARTIST_NOT_APPROVED','Artist access is not approved',403)
    # Set before accessing multipart data; other API requests retain the 16 KB limit.
    request.max_content_length=MAX_REQUEST_BYTES
    photo=request.files.get('file')
    if photo is None:
        return api_error('VALIDATION_ERROR','Choose an image first',400)
    raw=photo.stream.read(MAX_IMAGE_BYTES+1)
    if len(raw)>MAX_IMAGE_BYTES:
        return api_error('PAYLOAD_TOO_LARGE','Image must be 4 MB or smaller',413)
    try:
        url=upload_product_photo(raw,current_app.config['CLOUDINARY_CLOUD_NAME'],
                                 current_app.config['CLOUDINARY_API_KEY'],
                                 current_app.config['CLOUDINARY_API_SECRET'])
    except InvalidImage as exc:
        return api_error('VALIDATION_ERROR',str(exc),400)
    except UploadNotConfigured:
        return api_error('UPLOAD_NOT_CONFIGURED','Image uploading is not configured; use an HTTPS image URL',503)
    except UploadFailed:
        return api_error('UPLOAD_FAILED','Image hosting service could not complete the upload',502)
    return jsonify(url=url),201


@shop_bp.post('/products')
@auth_required('artist')
@safe
def create_product():
    """Insert a new owned product with server-controlled pending status and Decimal128 price."""
    denied=written()
    if denied:return denied
    fields=parse_product(request.get_json(silent=True))
    fields['price']=Decimal128(fields['price'])
    doc={'_id':ObjectId(),'artistId':g.current_user['_id'],**fields,'commissionRate':10,'approvalStatus':'pending_review','listProduct':False}
    get_database().products.insert_one(doc)
    return jsonify(product=jsonify_doc(doc),message='Product submitted for admin approval'),201


@shop_bp.patch('/products/<item_id>')
@auth_required('artist')
@safe
def update_product(item_id):
    """Validate an owned product edit, protect ordered inventory and require renewed approval."""
    denied=written()
    if denied:return denied
    db=get_database()
    existing=own_product(db,oid(item_id))
    if not existing:return api_error('NOT_FOUND','Editable product not found',404)
    # Inventory is derived from orders; disallow direct inventory replacement on products already ordered.
    changes=parse_product(request.get_json(silent=True),partial=True)
    if 'price' in changes:changes['price']=Decimal128(changes['price'])
    if 'inventory.quantityAvailable' in changes and db.orders.find_one({'items.productId':existing['_id']}):
        if changes['inventory.quantityAvailable'] != existing['inventory']['quantityAvailable']:
            return api_error('CONFLICT','Inventory of ordered products cannot be directly overwritten',409)
        del changes['inventory.quantityAvailable']
    changes.update({'approvalStatus':'pending_review','listProduct':False})
    db.products.update_one({'_id':existing['_id'],'artistId':g.current_user['_id']},{'$set':changes})
    return jsonify(product=jsonify_doc(db.products.find_one({'_id':existing['_id']}))),200


@shop_bp.delete('/products/<item_id>')
@auth_required('artist')
@safe
def delete_product(item_id):
    """Delete only an owned product with no cart, order or review references."""
    denied=written()
    if denied:return denied
    db=get_database(); existing=own_product(db,oid(item_id))
    if not existing:return api_error('NOT_FOUND','Editable product not found',404)
    pid=existing['_id']
    if db.cart.find_one({'items.productId':pid}) or db.orders.find_one({'items.productId':pid}) or db.reviews.find_one({'productId':pid}):
        return api_error('CONFLICT','This product is referenced by carts, orders, or reviews; it cannot be deleted',409)
    db.products.delete_one({'_id':pid,'artistId':g.current_user['_id']})
    return jsonify(message='Product deleted'),200


@shop_bp.get('/admin/products')
@auth_required('admin')
@safe
def admin_products():
    """Read a bounded moderation list, optionally filtered by product approval status."""
    status=request.args.get('status','pending_review')
    if status not in {'pending_review','approved','rejected','all'}:raise BadInput('Invalid status')
    q={} if status=='all' else {'approvalStatus':status}
    return jsonify(products=jsonify_doc(list(get_database().products.find(q).sort('_id',-1).limit(100)))),200


@shop_bp.patch('/admin/artists/<artist_id>/approval')
@auth_required('admin')
@safe
def review_artist(artist_id):
    """Let an admin moderate only an eligible new artist, preserving original artist records."""
    denied=require_write_enabled()
    if denied:return denied
    data=obj(request.get_json(silent=True),{'status'},('status',))
    status=data['status']
    if not isinstance(status,str) or status not in {'approved','rejected','waiting_for_documents','received_documents'}:raise BadInput('Invalid approval status')
    db=get_database(); user=db.users.find_one({'_id':oid(artist_id),'role':'artist'})
    if not user:return api_error('NOT_FOUND','Artist not found',404)
    if not can_edit_user(user):return api_error('SEEDED_RECORD_PROTECTED','Original artist cannot be modified',403)
    db.users.update_one({'_id':user['_id'],'userID':user['userID']},{'$set':{'artistProfile.onboardingStatus':status}})
    return jsonify(user=public_user(db.users.find_one({'_id':user['_id']}))),200


@shop_bp.patch('/admin/products/<item_id>/review')
@auth_required('admin')
@safe
def review_product(item_id):
    """Let an admin set approval/listing and optional commission on eligible new products."""
    denied=require_write_enabled()
    if denied:return denied
    data=obj(request.get_json(silent=True),{'status','commissionRate'},('status',))
    if not isinstance(data['status'],str) or data['status'] not in {'approved','rejected'}:raise BadInput('Invalid product review status')
    db=get_database(); doc=db.products.find_one({'_id':oid(item_id)})
    if not doc:return api_error('NOT_FOUND','Product not found',404)
    if not demo_product(db,doc):return api_error('SEEDED_RECORD_PROTECTED','Original products cannot be modified',403)
    changes={'approvalStatus':data['status'],'listProduct':data['status']=='approved'}
    if 'commissionRate' in data:changes['commissionRate']=rate(data['commissionRate'])
    db.products.update_one({'_id':doc['_id']},{'$set':changes})
    return jsonify(product=jsonify_doc(db.products.find_one({'_id':doc['_id']}))),200


def customer_only():
    """Apply the write/seed policy after the customer role decorator has authenticated the caller."""
    denied=written()
    if denied:return denied
    return None


@shop_bp.get('/cart')
@auth_required('customer')
@safe
def get_cart():
    """Read the caller's unique cart or return an empty cart shape without inserting a document."""
    doc=get_database().cart.find_one({'customerId':g.current_user['_id']})
    return jsonify(cart=jsonify_doc(doc) if doc else {'customerId':str(g.current_user['_id']),'items':[]}),200


@shop_bp.post('/cart/items')
@auth_required('customer')
@safe
def cart_add():
    """Add or merge a cart item after eligibility/stock checks; array replacement is not transactional."""
    denied=customer_only()
    if denied:return denied
    data=obj(request.get_json(silent=True),{'productId','quantity'},('productId','quantity'))
    qty=whole(data['quantity'],'quantity',1,100)
    db=get_database(); pid=oid(data['productId']); product=db.products.find_one({'_id':pid,'approvalStatus':'approved','listProduct':True})
    if not product:return api_error('NOT_FOUND','Active product not found',404)
    if not demo_product(db,product):return api_error('SEEDED_RECORD_PROTECTED','Demo purchases use newly registered artists and their products only',403)
    existing=db.cart.find_one({'customerId':g.current_user['_id']})
    items=existing['items'][:] if existing else []
    match=next((x for x in items if x['productId']==pid),None)
    total=(match['quantity'] if match else 0)+qty
    if total>product['inventory']['quantityAvailable'] or total>100:
        return api_error('OUT_OF_STOCK','Requested quantity exceeds available stock',409)
    if match:match['quantity']=total
    else:items.append({'productId':pid,'quantity':qty})
    db.cart.update_one({'customerId':g.current_user['_id']},{'$set':{'items':items},'$setOnInsert':{'_id':ObjectId(),'customerId':g.current_user['_id']}},upsert=True)
    return jsonify(cart=jsonify_doc(db.cart.find_one({'customerId':g.current_user['_id']}))),200


@shop_bp.patch('/cart/items/<item_id>')
@auth_required('customer')
@safe
def cart_quantity(item_id):
    """Replace an existing cart quantity after validating the integer and available stock."""
    denied=customer_only()
    if denied:return denied
    data=obj(request.get_json(silent=True),{'quantity'},('quantity',))
    qty=whole(data['quantity'],'quantity',1,100); pid=oid(item_id)
    db=get_database(); cart=db.cart.find_one({'customerId':g.current_user['_id']})
    if not cart or not any(x['productId']==pid for x in cart['items']):return api_error('NOT_FOUND','Cart item not found',404)
    product=db.products.find_one({'_id':pid,'approvalStatus':'approved','listProduct':True})
    if not product or qty>product['inventory']['quantityAvailable']:return api_error('OUT_OF_STOCK','Product unavailable or insufficient stock',409)
    items=[{**x,'quantity':qty} if x['productId']==pid else x for x in cart['items']]
    db.cart.update_one({'_id':cart['_id'],'customerId':g.current_user['_id']},{'$set':{'items':items}})
    return jsonify(cart=jsonify_doc(db.cart.find_one({'_id':cart['_id']}))),200


@shop_bp.delete('/cart/items/<item_id>')
@auth_required('customer')
@safe
def cart_remove(item_id):
    """Remove an item from the eligible customer's own cart without deleting the product."""
    denied=customer_only()
    if denied:return denied
    pid=oid(item_id); db=get_database(); cart=db.cart.find_one({'customerId':g.current_user['_id']})
    if not cart or not any(x['productId']==pid for x in cart['items']):return api_error('NOT_FOUND','Cart item not found',404)
    db.cart.update_one({'_id':cart['_id'],'customerId':g.current_user['_id']},{'$pull':{'items':{'productId':pid}}})
    return jsonify(cart=jsonify_doc(db.cart.find_one({'_id':cart['_id']}))),200


def d128(value):return Decimal128(value)


@shop_bp.post('/orders/checkout')
@auth_required('customer')
@safe
def checkout():
    """Atomically recheck stock, deduct inventory, create snapshots/totals and clear the caller's cart."""
    denied=customer_only()
    if denied:return denied
    payload=obj(request.get_json(silent=True),{'shippingAddress'},('shippingAddress',))
    address=parse_address(payload['shippingAddress']); db=get_database()
    # The transaction guarantees inventory and order creation succeed or fail together.
    # MongoDB Atlas replica sets support transactions. No silent non-transaction fallback.
    with get_client().start_session() as session:
        with session.start_transaction():
            cart=db.cart.find_one({'customerId':g.current_user['_id']},session=session)
            if not cart or not cart.get('items'):raise BadInput('Cart is empty')
            items=[]
            for chosen in cart['items']:
                pid=chosen['productId']; qty=whole(chosen['quantity'],'quantity',1,100)
                product=db.products.find_one({'_id':pid,'approvalStatus':'approved','listProduct':True},session=session)
                if not product:raise BadInput('A cart product is no longer available')
                artist=db.users.find_one({'_id':product['artistId'],'role':'artist'},session=session)
                if not artist or not can_edit_user(artist) or artist['artistProfile']['onboardingStatus']!='approved':
                    raise BadInput('Cart contains an unavailable artist product')
                result=db.products.update_one({'_id':pid,'inventory.quantityAvailable':{'$gte':qty}}, {'$inc':{'inventory.quantityAvailable':-qty}},session=session)
                if result.modified_count!=1:raise BadInput('Not enough stock for '+product['title'])
                price=product['price'].to_decimal()
                _,commission,payout=amounts(price,qty,product['commissionRate'])
                items.append({'productId':pid,'productSnapshot':{'title':product['title'],'artistId':artist['_id'],'artistName':artist['personalInfo']['firstName']+' '+artist['personalInfo']['lastName']},'quantity':qty,'unitPrice':product['price'],'commissionRate':product['commissionRate'],'commissionAmount':d128(commission),'artistPayout':d128(payout),'status':'active','shipping':{'status':'pending'}})
            totals={k:d128(v) for k,v in order_totals(items).items()}
            order={'_id':ObjectId(),'customerId':g.current_user['_id'],'items':items,'shippingAddress':address,'totals':totals,'orderStatus':'pending'}
            db.orders.insert_one(order,session=session)
            db.cart.delete_one({'_id':cart['_id'],'customerId':g.current_user['_id']},session=session)
    return jsonify(order=jsonify_doc(order),message='Order placed (coursework demo; no payment processed)'),201


@shop_bp.get('/orders/mine')
@auth_required('customer')
@safe
def my_orders():
    """Read only the authenticated customer's order history."""
    docs=get_database().orders.find({'customerId':g.current_user['_id']}).sort('_id',-1).limit(100)
    return jsonify(orders=jsonify_doc(list(docs))),200


@shop_bp.get('/orders/sales')
@auth_required('artist')
@safe
def artist_sales():
    """Expose only the caller's sales items while retaining original order-item indices."""
    docs=get_database().orders.find({'items.productSnapshot.artistId':g.current_user['_id']}).sort('_id',-1).limit(100)
    # Keep only current artist's item details (avoid disclosure of other artists' sales).
    results=[]
    for doc in docs:
        results.append({'orderId':str(doc['_id']),'items':jsonify_doc([{**x,'itemIndex':i} for i,x in enumerate(doc['items']) if x['productSnapshot']['artistId']==g.current_user['_id']])})
    return jsonify(sales=results),200


@shop_bp.patch('/orders/<order_id>/items/<int:idx>/cancel')
@auth_required('customer')
@safe
def cancel_order_item(order_id,idx):
    """Atomically cancel an active unshipped item, restore stock once and recalculate totals."""
    denied=customer_only()
    if denied:return denied
    db=get_database(); user_id=g.current_user['_id']; order_oid=oid(order_id)
    with get_client().start_session() as session:
        with session.start_transaction():
            order=db.orders.find_one({'_id':order_oid,'customerId':user_id},session=session)
            if not order:return api_error('NOT_FOUND','Order not found',404)
            if idx<0 or idx>=len(order['items']):raise BadInput('Invalid order item index')
            item=order['items'][idx]
            if item['status']!='active' or item['shipping']['status']!='pending':
                return api_error('CONFLICT','Only active unshipped items can be cancelled',409)
            product=db.products.find_one({'_id':item['productId']},session=session)
            artist=db.users.find_one({'_id':item['productSnapshot']['artistId']},session=session)
            if not product or not artist or not can_edit_user(artist):
                return api_error('SEEDED_RECORD_PROTECTED','Original product inventory is protected',403)
            item['status']='cancelled';item['cancelledAt']=datetime.now(timezone.utc)
            db.products.update_one({'_id':item['productId']},{'$inc':{'inventory.quantityAvailable':item['quantity']}},session=session)
            totals={k:d128(v) for k,v in order_totals(order['items']).items()}
            db.orders.update_one({'_id':order['_id'],'customerId':user_id},{'$set':{'items':order['items'],'totals':totals,'orderStatus':order_status(order['items'])}},session=session)
    return jsonify(message='Item cancelled and stock restored',order=jsonify_doc(db.orders.find_one({'_id':order_oid}))),200


@shop_bp.patch('/orders/<order_id>/items/<int:idx>/ship')
@auth_required('artist')
@safe
def ship_item(order_id,idx):
    """Advance only the artist's active item through shipping states; do not decrement stock again."""
    denied=written()
    if denied:return denied
    data=obj(request.get_json(silent=True),{'status','trackingNumber'},('status',))
    if not isinstance(data['status'],str) or data['status'] not in {'shipped','delivered'}:raise BadInput('status must be shipped or delivered')
    db=get_database();o=oid(order_id)
    with get_client().start_session() as session:
        with session.start_transaction():
            order=db.orders.find_one({'_id':o,'items.productSnapshot.artistId':g.current_user['_id']},session=session)
            if not order:return api_error('NOT_FOUND','Artist order not found',404)
            if idx<0 or idx>=len(order['items']):raise BadInput('Invalid order item index')
            item=order['items'][idx]
            if item['productSnapshot']['artistId']!=g.current_user['_id']:return api_error('FORBIDDEN','Not your order item',403)
            if item['status']!='active':return api_error('CONFLICT','Cancelled items cannot be shipped',409)
            previous=item['shipping']['status'];status=data['status']
            if (previous,status) not in {('pending','shipped'),('shipped','delivered')}:
                return api_error('CONFLICT','Shipping status must move pending → shipped → delivered',409)
            item['shipping']['status']=status
            if status=='shipped':
                item['shipping']['shippedAt']=datetime.now(timezone.utc)
                if 'trackingNumber' in data:item['shipping']['trackingNumber']=string(data['trackingNumber'],'trackingNumber',100)
            elif 'trackingNumber' in data:raise BadInput('trackingNumber may only be set when shipping')
            db.orders.update_one({'_id':o},{'$set':{'items':order['items'],'orderStatus':order_status(order['items'])}},session=session)
    return jsonify(order=jsonify_doc(db.orders.find_one({'_id':o}))),200


@shop_bp.get('/products/<item_id>/reviews')
@safe
def product_reviews(item_id):
    """Read a bounded public review list for a valid product identifier."""
    docs=get_database().reviews.find({'productId':oid(item_id)}).sort('_id',-1).limit(100)
    return jsonify(reviews=jsonify_doc(list(docs))),200


@shop_bp.post('/reviews')
@auth_required('customer')
@safe
def add_review():
    """Create a verified review for the customer's active purchased item; unique index prevents duplicates."""
    denied=customer_only()
    if denied:return denied
    data=obj(request.get_json(silent=True),{'productId','orderId','rating','comment'},('productId','orderId','rating'))
    pid=oid(data['productId']);order_id=oid(data['orderId']);rating=whole(data['rating'],'rating',1,5)
    db=get_database();order=db.orders.find_one({'_id':order_id,'customerId':g.current_user['_id']})
    if not order or not any(i['productId']==pid and i['status']=='active' for i in order['items']):
        return api_error('NOT_VERIFIED','An active purchased order item is required for reviews',403)
    prod=db.products.find_one({'_id':pid})
    if not demo_product(db,prod):return api_error('SEEDED_RECORD_PROTECTED','Reviews are limited to fresh demo products',403)
    doc={'_id':ObjectId(),'productId':pid,'customerId':g.current_user['_id'],'orderId':order_id,'rating':rating}
    if 'comment' in data:doc['comment']=string(data['comment'],'comment',1000,0)
    db.reviews.insert_one(doc)
    return jsonify(review=jsonify_doc(doc)),201


@shop_bp.patch('/reviews/<review_id>')
@auth_required('customer')
@safe
def edit_review(review_id):
    """Update only the caller's eligible review, allowing rating/comment fields."""
    denied=customer_only()
    if denied:return denied
    data=obj(request.get_json(silent=True),{'rating','comment'})
    if not data:raise BadInput('Supply rating or comment')
    db=get_database();doc=db.reviews.find_one({'_id':oid(review_id),'customerId':g.current_user['_id']})
    if not doc:return api_error('NOT_FOUND','Review not found',404)
    if not demo_product(db,db.products.find_one({'_id':doc['productId']})):
        return api_error('SEEDED_RECORD_PROTECTED','Original reviews cannot be modified',403)
    changes={}
    if 'rating' in data:changes['rating']=whole(data['rating'],'rating',1,5)
    if 'comment' in data:changes['comment']=string(data['comment'],'comment',1000,0)
    db.reviews.update_one({'_id':doc['_id'],'customerId':g.current_user['_id']},{'$set':changes})
    return jsonify(review=jsonify_doc(db.reviews.find_one({'_id':doc['_id']}))),200


@shop_bp.delete('/reviews/<review_id>')
@auth_required('customer')
@safe
def delete_review(review_id):
    """Remove only the caller's eligible review while preserving original seeded reviews."""
    denied=customer_only()
    if denied:return denied
    db=get_database();doc=db.reviews.find_one({'_id':oid(review_id),'customerId':g.current_user['_id']})
    if not doc:return api_error('NOT_FOUND','Review not found',404)
    if not demo_product(db,db.products.find_one({'_id':doc['productId']})):
        return api_error('SEEDED_RECORD_PROTECTED','Original review records are protected',403)
    db.reviews.delete_one({'_id':doc['_id'],'customerId':g.current_user['_id']})
    return jsonify(message='Review removed'),200


@shop_bp.get('/analytics/categories')
@safe
def category_aggregation():
    """Genuine MongoDB aggregation pipeline, not Python-side grouping."""
    pipeline=[{'$match':{'listProduct':True,'approvalStatus':'approved'}}, {'$group':{'_id':'$category','productCount':{'$sum':1},'averagePrice':{'$avg':'$price'}}},{'$sort':{'productCount':-1,'_id':1}},{'$limit':30}]
    docs=get_database().products.aggregate(pipeline)
    return jsonify(categories=jsonify_doc([{'category':v['_id'],'productCount':v['productCount'],'averagePrice':v.get('averagePrice')} for v in docs]),pipelineStages=['$match','$group','$sort','$limit']),200
