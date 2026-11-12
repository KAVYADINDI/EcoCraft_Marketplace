"""Pure logic tests; run via unittest even if Flask/PyMongo aren't installed."""
import unittest
from decimal import Decimal
import importlib.util
from pathlib import Path
spec=importlib.util.spec_from_file_location('marketplace_core',Path(__file__).resolve().parents[1]/'app'/'marketplace_core.py')
core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
BadInput,money,rate,whole,string,obj,parse_product,parse_address,amounts,order_totals,order_status=[getattr(core,k) for k in ('BadInput','money','rate','whole','string','obj','parse_product','parse_address','amounts','order_totals','order_status')]

class MarketCoreTests(unittest.TestCase):
    def product(self):
        return dict(title='Recycled Bowl',description='Created from reclaimed glass',price='15.20',category='Home Decor',materials=['Glass'],quantityAvailable=2,tags=['reuse'])

    def test_product_valid(self):
        p=parse_product(self.product());self.assertEqual(p['price'],Decimal('15.20'));self.assertEqual(p['inventory'],{'quantityAvailable':2})
    def test_product_minimum_fields(self):
        p=self.product();del p['category'];self.assertRaises(BadInput,parse_product,p)
    def test_product_negative_price(self):
        p=self.product();p['price']='-2';self.assertRaises(BadInput,parse_product,p)
    def test_product_too_many_decimals(self):
        p=self.product();p['price']='2.001';self.assertRaises(BadInput,parse_product,p)
    def test_product_nan(self):
        p=self.product();p['price']='NaN';self.assertRaises(BadInput,parse_product,p)
    def test_product_infinity(self):
        p=self.product();p['price']='Infinity';self.assertRaises(BadInput,parse_product,p)
    def test_product_quantity_float(self):
        p=self.product();p['quantityAvailable']=1.5;self.assertRaises(BadInput,parse_product,p)
    def test_product_quantity_bool(self):
        p=self.product();p['quantityAvailable']=True;self.assertRaises(BadInput,parse_product,p)
    def test_product_materials_required(self):
        p=self.product();p['materials']=[];self.assertRaises(BadInput,parse_product,p)
    def test_product_unknown_field_rejected(self):
        p=self.product();p['artistId']='danger';self.assertRaises(BadInput,parse_product,p)
    def test_product_status_injection_rejected(self):
        p=self.product();p['approvalStatus']='approved';self.assertRaises(BadInput,parse_product,p)
    def test_product_commission_injection_rejected(self):
        p=self.product();p['commissionRate']=0;self.assertRaises(BadInput,parse_product,p)
    def test_valid_partial_product(self):
        self.assertEqual(parse_product({'title':'Better'},True),{'title':'Better'})
    def test_partial_empty_rejected(self):
        self.assertRaises(BadInput,parse_product,{},True)
    def test_product_bad_image_scheme(self):
        p=self.product();p['images']=['javascript:alert(1)'];self.assertRaises(BadInput,parse_product,p)
    def test_money_roundtrip(self):
        self.assertEqual(money('9.99'),Decimal('9.99'))
    def test_money_rejects_boolean(self):
        self.assertRaises(BadInput,money,True)
    def test_rate_valid(self):
        self.assertEqual(rate(10),10);self.assertEqual(rate('12.5'),12.5)
    def test_rate_bad(self):
        for a in (-1,101,True,'NaN','10.123'):
            with self.subTest(a=a):self.assertRaises(BadInput,rate,a)
    def test_address_required(self):
        self.assertRaises(BadInput,parse_address,{'street':'Street'})
    def test_address_valid(self):
        addr=dict(street='1 A',city='Warrensburg',state='MO',zipCode='64093',country='USA')
        self.assertEqual(parse_address(addr),addr)
    def test_commission_money_exact(self):
        self.assertEqual(amounts(Decimal('10.00'),3,10),(Decimal('30.00'),Decimal('3.00'),Decimal('27.00')))
    def test_commission_rounding(self):
        self.assertEqual(amounts(Decimal('0.05'),1,10)[1],Decimal('0.01'))
    def test_order_totals_cancelled_excluded(self):
        items=[{'unitPrice':Decimal('10'),'quantity':2,'commissionRate':10,'status':'active'},{'unitPrice':Decimal('20'),'quantity':1,'commissionRate':10,'status':'cancelled'}]
        self.assertEqual(order_totals(items)['totalAmount'],Decimal('20.00'))
    def test_order_status_pending(self):
        self.assertEqual(order_status([{'status':'active','shipping':{'status':'pending'}}]),'pending')
    def test_order_status_partial(self):
        self.assertEqual(order_status([{'status':'active','shipping':{'status':'shipped'}},{'status':'active','shipping':{'status':'pending'}}]),'partially_shipped')
    def test_order_status_cancelled(self):
        self.assertEqual(order_status([{'status':'cancelled','shipping':{'status':'pending'}}]),'cancelled')
    def test_order_status_completed(self):
        self.assertEqual(order_status([{'status':'active','shipping':{'status':'delivered'}}]),'completed')
    def test_order_status_shipped(self):
        self.assertEqual(order_status([{'status':'active','shipping':{'status':'shipped'}}]),'shipped')
    def test_empty_json(self):
        self.assertRaises(BadInput,obj,[],{'x'})

if __name__=='__main__':unittest.main()
