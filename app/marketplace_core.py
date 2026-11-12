"""Framework-free marketplace validation and exact currency calculations.

Do not trust client-supplied prices, ownership, status, commissions, or totals.
"""
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

MONEY = Decimal('0.01')
CATEGORIES = None  # EcoCraft allows new handmade craft categories.

class BadInput(ValueError):
    pass


def obj(value, fields=None, required=()):
    """Require an object, reject fields outside the allowlist, and enforce required keys."""
    if not isinstance(value, dict):
        raise BadInput('A JSON object is required')
    if fields is not None and set(value) - set(fields):
        raise BadInput('Unknown fields: ' + ', '.join(sorted(set(value)-set(fields))))
    if any(field not in value for field in required):
        raise BadInput('Missing required fields: ' + ', '.join(k for k in required if k not in value))
    return value


def string(value, name, max_length=200, min_length=1):
    """Trim a string and enforce its field-specific length bounds."""
    if not isinstance(value, str) or not min_length <= len(value.strip()) <= max_length:
        raise BadInput(f'{name} must contain {min_length}-{max_length} characters')
    return value.strip()


def whole(value, name, minimum=0, maximum=100000):
    """Validate an integer in range; reject booleans even though Python treats them as integers."""
    if type(value) is not int or not minimum <= value <= maximum:
        raise BadInput(f'{name} must be a whole number from {minimum} to {maximum}')
    return value


def money(value, name='price', allow_zero=False):
    """Return an exact two-decimal price; BSON conversion belongs to the persistence layer."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise BadInput(f'{name} must be a valid price')
    try:
        n = Decimal(str(value))
    except InvalidOperation:
        raise BadInput(f'{name} must be a valid price') from None
    if not n.is_finite() or n < (Decimal('0') if allow_zero else MONEY) or n > Decimal('9999999.99') or n != n.quantize(MONEY):
        raise BadInput(f'{name} must be a nonnegative amount with at most 2 decimal places')
    return n.quantize(MONEY)


def rate(value):
    """Validate a commission percentage from 0 to 100, rather than a fractional multiplier."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise BadInput('commissionRate must be between 0 and 100')
    try:
        n = Decimal(str(value))
    except InvalidOperation:
        raise BadInput('commissionRate must be between 0 and 100') from None
    if not n.is_finite() or not Decimal(0) <= n <= Decimal(100) or n.as_tuple().exponent < -2:
        raise BadInput('commissionRate must be between 0 and 100 with at most 2 decimal places')
    return int(n) if n == int(n) else float(n)


def parse_product(data, partial=False):
    """Validate allowed product fields; partial updates use dotted inventory paths for MongoDB."""
    fields = {'title','description','price','category','materials','quantityAvailable','dimensions','careInstructions','tags','images','sustainability','copyrightText','returnPolicy'}
    obj(data, fields, () if partial else ('title','description','price','category','materials','quantityAvailable'))
    if partial and not data:
        raise BadInput('At least one product field is required')
    result = {}
    for field, limit in [('title',120),('description',3000),('category',100),('dimensions',200),('careInstructions',1000),('copyrightText',500),('returnPolicy',1000)]:
        if field in data:
            result[field] = string(data[field], field, limit, 0 if field in {'dimensions','careInstructions','copyrightText','returnPolicy'} else 1)
    if 'price' in data:
        result['price'] = money(data['price'])
    if 'quantityAvailable' in data:
        result['inventory.quantityAvailable' if partial else 'inventory'] = (whole(data['quantityAvailable'],'quantityAvailable',0,100000) if partial else {'quantityAvailable':whole(data['quantityAvailable'],'quantityAvailable',0,100000)})
    for name, maximum in [('materials',15),('tags',20),('images',8)]:
        if name in data:
            items=data[name]
            if not isinstance(items,list) or len(items)>maximum or (name=='materials' and not items):
                raise BadInput(f'{name} must be an array of 1-{maximum} items' if name=='materials' else f'{name} must be an array with at most {maximum} items')
            if name=='images':
                for item in items:
                    string(item,'image URL',1024)
                    if not re.fullmatch(r'https://[^\s]+',item):
                        raise BadInput('Image URLs must start with https://')
                result[name]=items
            else:
                result[name]=[string(v,name,100) for v in items]
    if 'sustainability' in data:
        v=obj(data['sustainability'],{'certified','details'})
        if 'certified' in v and type(v['certified']) is not bool:
            raise BadInput('sustainability.certified must be true or false')
        result['sustainability']={**({'certified':v['certified']} if 'certified' in v else {}),**({'details':string(v['details'],'sustainability.details',500,0)} if 'details' in v else {})}
    return result


def parse_address(data):
    """Require and normalize the five shipping-address fields used by order documents."""
    fields=('street','city','state','zipCode','country')
    obj(data, fields, fields)
    return {k:string(data[k],k,120) for k in fields}


def amounts(unit_price, quantity, commission_rate):
    """Compute subtotal, percentage commission and payout with explicit currency rounding."""
    subtotal=(unit_price * quantity).quantize(MONEY, rounding=ROUND_HALF_UP)
    commission=(subtotal * Decimal(str(commission_rate))/100).quantize(MONEY, rounding=ROUND_HALF_UP)
    return subtotal,commission,(subtotal-commission).quantize(MONEY)


def order_totals(items):
    """Sum active order items only; cancelled items no longer contribute to totals."""
    subtotal=commission=payout=Decimal('0.00')
    for item in items:
        if item['status']!='active':
            continue
        price=item['unitPrice'].to_decimal() if hasattr(item['unitPrice'],'to_decimal') else Decimal(str(item['unitPrice']))
        a,b,c=amounts(price,item['quantity'],item['commissionRate'])
        subtotal+=a; commission+=b; payout+=c
    return dict(subtotal=subtotal.quantize(MONEY),commissionTotal=commission.quantize(MONEY),totalAmount=subtotal.quantize(MONEY),artistPayoutTotal=payout.quantize(MONEY))


def order_status(items):
    """Derive overall fulfillment from active items; all cancelled means cancelled."""
    live=[v for v in items if v['status']=='active']
    if not live:return 'cancelled'
    s=[v['shipping']['status'] for v in live]
    if all(x=='delivered' for x in s):return 'completed'
    if all(x in ('shipped','delivered') for x in s):return 'shipped'
    if any(x in ('shipped','delivered') for x in s):return 'partially_shipped'
    return 'pending'
