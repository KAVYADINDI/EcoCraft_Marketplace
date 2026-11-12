"""Offline tests for the one-time shared-admin creation add-on; no Atlas access."""
import io
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from werkzeug.security import check_password_hash
from scripts.create_shared_admin import (
    TEAM_ADMIN_ID, ExistingAccountError, configuration_error,
    CONFIRMATION, insert_once, prepare_document, run,
)


class FakeUsers:
    def __init__(self, docs=None):
        self.docs = list(docs or [])
        self.inserts = 0

    def find_one(self, selector):
        return next((d for d in self.docs if any(
            d.get(key) == value for part in selector['$or'] for key, value in part.items()
        )), None)

    def insert_one(self, doc):
        self.docs.append(dict(doc))
        self.inserts += 1
        return SimpleNamespace(inserted_id='new-admin-test-id')


class SharedAdminCreationTests(unittest.TestCase):
    def base_env(self):
        return {
            'MONGO_DB_NAME': 'ecocraft',
            'ENABLE_TEAM_DEMO_WRITES': 'true',
            'MONGO_URI': 'mongodb://example.invalid:27017',
            'MONGO_USERNAME': 'testuser',
            'MONGO_PASSWORD': 'testpassword',
        }

    def test_correct_shared_db_is_allowed(self):
        self.assertIsNone(configuration_error(self.base_env()))

    def test_wrong_database_refused(self):
        env = self.base_env()
        env['MONGO_DB_NAME'] = 'ecocraft_dev'
        self.assertIsNotNone(configuration_error(env))

    def test_writes_disabled_refused(self):
        env = self.base_env()
        env['ENABLE_TEAM_DEMO_WRITES'] = 'false'
        self.assertIsNotNone(configuration_error(env))

    def test_missing_uri_refused(self):
        env = self.base_env()
        env['MONGO_URI'] = ''
        self.assertIsNotNone(configuration_error(env))

    def test_only_one_of_username_and_password_refused(self):
        env = self.base_env()
        env['MONGO_PASSWORD'] = ''
        self.assertIsNotNone(configuration_error(env))

    def test_valid_doc_satisfies_shape_and_hash(self):
        doc = prepare_document(' TEAM-ADMIN@EXAMPLE.ORG ', 'EcoCraft', 'Team', 'SomethingStrong2026!')
        self.assertEqual(doc['email'], 'team-admin@example.org')
        self.assertEqual(doc['userID'], TEAM_ADMIN_ID)
        self.assertEqual(doc['role'], 'admin')
        self.assertEqual(doc['personalInfo'], {'firstName': 'EcoCraft', 'lastName': 'Team'})
        self.assertNotIn('artistProfile', doc)
        self.assertNotIn('password', doc)
        self.assertNotEqual(doc['passwordHash'], 'SomethingStrong2026!')
        self.assertTrue(check_password_hash(doc['passwordHash'], 'SomethingStrong2026!'))

    def test_invalid_credentials_rejected_without_writes(self):
        for email, password in [('bad-email', 'SomethingStrong2026!'),
                                ('team@example.org', 'short')]:
            with self.subTest(email=email, password_len=len(password)):
                with self.assertRaises(ValueError):
                    prepare_document(email, 'EcoCraft', 'Team', password)

    def test_only_inserts_one_does_not_modify_seeded_admins(self):
        seeded = [
            {'userID': 'ADM001', 'email': 'admin001@gmail.com', 'role': 'admin'},
            {'userID': 'ADM002', 'email': 'admin002@gmail.com', 'role': 'admin'},
        ]
        users = FakeUsers(seeded)
        original_snapshot = [dict(d) for d in users.docs]
        doc = prepare_document('team@example.org', 'EcoCraft', 'Team', 'SomethingStrong2026!')
        insert_once(users, doc)
        self.assertEqual(users.inserts, 1)
        self.assertEqual(users.docs[:2], original_snapshot)
        self.assertEqual(len(users.docs), 3)

    def test_repeat_creation_refuses_and_does_not_insert(self):
        users = FakeUsers()
        doc = prepare_document('team@example.org', 'EcoCraft', 'Team', 'SomethingStrong2026!')
        insert_once(users, doc)
        with self.assertRaises(ExistingAccountError):
            insert_once(users, doc)
        self.assertEqual(users.inserts, 1)

    def test_existing_email_is_not_overwritten(self):
        users = FakeUsers([{'userID': 'ADM001', 'email': 'team@example.org', 'role': 'admin'}])
        doc = prepare_document('team@example.org', 'EcoCraft', 'Team', 'SomethingStrong2026!')
        with self.assertRaises(ExistingAccountError):
            insert_once(users, doc)
        self.assertEqual(users.inserts, 0)

    def test_interactive_confirmation_inserts_once(self):
        seeded = [
            {'userID': 'ADM001', 'email': 'admin001@gmail.com', 'role': 'admin'},
            {'userID': 'ADM002', 'email': 'admin002@gmail.com', 'role': 'admin'},
        ]
        users = FakeUsers(seeded)
        class FakeDatabase:
            def __init__(self):
                self.users = users
            def command(self, command):
                assert command == 'ping'
                return {'ok': 1}
            def list_collection_names(self):
                return ['users', 'products', 'cart', 'orders', 'reviews']
        class FakeClient:
            closed = False
            def __getitem__(self, name):
                assert name == 'ecocraft'
                return FakeDatabase()
            def close(self):
                self.closed = True
        client = FakeClient()
        from scripts import create_shared_admin as script
        with patch.dict(os.environ, self.base_env(), clear=True), \
             patch.object(script, 'load_dotenv'), \
             patch.object(script.sys.stdin, 'isatty', return_value=True), \
             patch.object(script, 'MongoClient', return_value=client), \
             patch('builtins.input', side_effect=['team-admin@example.org', 'EcoCraft', 'Team', CONFIRMATION]), \
             patch.object(script.getpass, 'getpass', side_effect=['SomethingStrong2026!', 'SomethingStrong2026!']), \
             patch('sys.stdout', new_callable=io.StringIO) as output:
            result = run()
        self.assertEqual(result, 0)
        self.assertEqual(users.inserts, 1)
        self.assertEqual(users.docs[:2], seeded)
        self.assertEqual(users.docs[2]['userID'], TEAM_ADMIN_ID)
        self.assertTrue(client.closed)
        self.assertNotIn('SomethingStrong2026!', output.getvalue())

    def test_no_confirmation_means_no_connection_or_write(self):
        from scripts import create_shared_admin as script
        with patch.dict(os.environ, self.base_env(), clear=True), \
             patch.object(script, 'load_dotenv'), \
             patch.object(script.sys.stdin, 'isatty', return_value=True), \
             patch.object(script, 'MongoClient') as make_client, \
             patch('builtins.input', side_effect=['team-admin@example.org', 'EcoCraft', 'Team', 'CANCEL']), \
             patch.object(script.getpass, 'getpass', side_effect=['SomethingStrong2026!', 'SomethingStrong2026!']), \
             patch('sys.stdout', new_callable=io.StringIO):
            result = run()
        self.assertEqual(result, 2)
        make_client.assert_not_called()

    def test_writes_off_means_no_connection_or_prompt(self):
        from scripts import create_shared_admin as script
        env = self.base_env()
        env['ENABLE_TEAM_DEMO_WRITES'] = 'false'
        with patch.dict(os.environ, env, clear=True), \
             patch.object(script, 'load_dotenv'), \
             patch.object(script, 'MongoClient') as make_client, \
             patch('builtins.input') as prompt, \
             patch('sys.stdout', new_callable=io.StringIO):
            result = run()
        self.assertEqual(result, 2)
        make_client.assert_not_called()
        prompt.assert_not_called()


if __name__ == '__main__':
    unittest.main()
