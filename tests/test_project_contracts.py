"""Dependency-free integration contracts: route inventory, frontend bindings, Atlas schema.
These are structural checks, NOT substitutes for the Flask HTTP test suite.
"""
from pathlib import Path
import unittest, json, re, ast
ROOT=Path(__file__).resolve().parents[1]
BACKEND = (ROOT / "app/routes/marketplace.py").read_text(encoding="utf-8")
FRONTEND = (ROOT / "app/static/marketplace.js").read_text(encoding="utf-8")
HTML = (ROOT / "app/templates/marketplace.html").read_text(encoding="utf-8")
AUDIT = json.loads(
    (ROOT / "reports/atlas_schema_audit.json").read_text(encoding="utf-8")
)
SCRIPT = (ROOT / "scripts/recreate_demo.js").read_text(encoding="utf-8")


class Contracts(unittest.TestCase):
    def test_all_five_collections(self):self.assertEqual(set(AUDIT['collections']),{'users','products','cart','orders','reviews'})
    def test_all_collections_strict_validation(self):
        for v in AUDIT['collections'].values():self.assertEqual((v['validationLevel'],v['validationAction']),('strict','error'))
    def test_decimal128_money(self):self.assertEqual(AUDIT['collections']['products']['validator']['$jsonSchema']['properties']['price']['bsonType'],'decimal')
    def test_unique_user_email(self):self.assertTrue(any(v.get('unique') and v['keys'][0][0]=='email' for v in AUDIT['collections']['users']['indexes']))
    def test_unique_cart(self):self.assertTrue(any(v.get('unique') and v['keys'][0][0]=='customerId' for v in AUDIT['collections']['cart']['indexes']))
    def test_protected_recreation_target(self):self.assertIn("const DEMO_DB = 'ecocraft_submission_dev'",SCRIPT);self.assertNotIn('db.getSiblingDB(\'ecocraft\')',SCRIPT)
    def test_all_collections_recreated(self):
        for name in AUDIT['collections']:self.assertIn(f'target.createCollection("{name}"',SCRIPT)
    def test_all_five_collections_seeded(self):
        for name in ('users','products','cart','orders','reviews'):self.assertIn(f'target.{name}.insert',SCRIPT)
    def test_recreate_indexes(self):self.assertIn('createIndex(',SCRIPT)
    def test_only_safe_shared_record_writes(self):self.assertIn('can_edit_user',BACKEND);self.assertIn('demo_product',BACKEND);self.assertIn('require_write_enabled',BACKEND)
    def test_genuine_mongo_aggregation(self):self.assertIn('products.aggregate(pipeline)',BACKEND);self.assertIn("'$group'",BACKEND)
    def test_mongo_transaction(self):self.assertIn('start_transaction()',BACKEND);self.assertIn('start_session()',BACKEND)
    def test_required_frontend_controls_exist(self):
        html_ids=set(re.findall(r'\bid="([^"]+)"',HTML));used=set(re.findall(r"\$\('([^']+)'\)",FRONTEND));self.assertFalse(used-html_ids,used-html_ids)
    def test_frontend_no_mongo_connection_string(self):self.assertNotIn('mongodb+srv://',FRONTEND);self.assertIn("fetch('/api'+path",FRONTEND)
    def test_frontend_sanitizes_user_text(self):self.assertIn("const esc=",FRONTEND)
    def test_frontend_all_five_actions(self):
        for method in ("'POST'","'PATCH'","'DELETE'"):self.assertIn(method,FRONTEND)
        for path in ('/products','/cart/items','/orders/checkout','/reviews','/analytics/categories','/auth/login','/auth/register'):self.assertIn(path,FRONTEND)
    def test_routes_have_auth_on_writes(self):
        tree=ast.parse(BACKEND)
        for node in tree.body:
            if not isinstance(node,ast.FunctionDef):continue
            decorators=[ast.unparse(x) for x in node.decorator_list]
            write=any(re.search(r'@?shop_bp\.(post|patch|delete)\(',d) for d in decorators)
            if write:self.assertTrue(any(x.startswith('auth_required(') for x in decorators),node.name)
    def test_old_tests_preserved(self):
        for file in ('test_auth.py','test_health.py','test_team_demo_mode.py','test_audit_rules.py'):self.assertTrue((ROOT/'tests'/file).is_file())

if __name__=='__main__':unittest.main()
