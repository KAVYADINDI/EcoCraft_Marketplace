"""Product integration regressions; database and image hosting are entirely fake."""
import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from bson import BSON, Decimal128

from app import create_app
from app.image_uploads import MAX_IMAGE_BYTES, UploadFailed, UploadNotConfigured
from app.security import create_access_token
from tests.fakes import FakeMongoClient


@pytest.fixture
def studio(monkeypatch):
    app = create_app({'TESTING': True, 'MONGO_DB_NAME': 'ecocraft',
                      'ENABLE_TEAM_DEMO_WRITES': True,
                      'JWT_SECRET_KEY': 'offline-product-test-secret-at-least-32-characters',
                      'CLOUDINARY_CLOUD_NAME': '', 'CLOUDINARY_API_KEY': '',
                      'CLOUDINARY_API_SECRET': ''})
    mongo = FakeMongoClient()
    app.extensions['mongo_client'] = mongo
    user = {'userID': 'WEB26-ART-offline', 'email': 'artist@example.test',
            'role': 'artist', 'personalInfo': {'firstName': 'Test', 'lastName': 'Artist'},
            'artistProfile': {'onboardingStatus': 'approved'}}
    user['_id'] = mongo.database.users.insert_one(user).inserted_id
    with app.app_context():
        token, _ = create_access_token(user)
    host = Mock(return_value='https://res.cloudinary.com/demo/image/upload/test.png')
    monkeypatch.setattr('app.routes.marketplace.upload_product_photo', host)
    return app, app.test_client(), mongo.database, {'Authorization': 'Bearer ' + token}, host


def upload(client, headers, raw=b'\x89PNG\r\n\x1a\nexample'):
    return client.post('/api/products/image-upload', headers=headers,
                       data={'file': (io.BytesIO(raw), 'photo.png')})


def test_upload_authentication_and_role(studio):
    app, client, db, headers, host = studio
    assert upload(client, {}).status_code == 401
    db.users.docs[0]['role'] = 'customer'
    assert upload(client, headers).status_code == 403
    host.assert_not_called()


@pytest.mark.parametrize('condition', ['disabled', 'seeded', 'pending'])
def test_upload_preserves_existing_write_guards(studio, condition):
    app, client, db, headers, host = studio
    if condition == 'disabled':
        app.config['ENABLE_TEAM_DEMO_WRITES'] = False
    elif condition == 'seeded':
        db.users.docs[0]['userID'] = 'ART001'
    else:
        db.users.docs[0]['artistProfile']['onboardingStatus'] = 'request_received'
    assert upload(client, headers).status_code == 403
    host.assert_not_called()


def test_upload_multipart_over_json_limit(studio):
    app, client, db, headers, host = studio
    response = upload(client, headers, b'\x89PNG\r\n\x1a\n' + b'x' * 20000)
    assert response.status_code == 201
    assert response.json == {'url': host.return_value}
    host.assert_called_once()
    assert app.config['MAX_CONTENT_LENGTH'] == 16 * 1024
    assert client.post('/api/products', headers=headers,
                       json={'title': 'x' * 20000}).status_code == 413


def test_upload_missing_file(studio):
    _, client, _, headers, host = studio
    assert client.post('/api/products/image-upload', headers=headers, data={}).status_code == 400
    host.assert_not_called()


def test_upload_too_large(studio):
    _, client, _, headers, host = studio
    assert upload(client, headers, b'x' * (MAX_IMAGE_BYTES + 1)).status_code == 413
    host.assert_not_called()


@pytest.mark.parametrize('error,status', [(UploadNotConfigured(), 503), (UploadFailed(), 502)])
def test_upload_service_errors(studio, error, status):
    _, client, _, headers, host = studio
    host.side_effect = error
    response = upload(client, headers)
    assert response.status_code == status
    assert 'error' in response.json


def test_upload_rejects_invalid_bytes_without_network(studio, monkeypatch):
    from app.image_uploads import upload_product_photo
    monkeypatch.setattr('app.routes.marketplace.upload_product_photo', upload_product_photo)
    _, client, _, headers, _ = studio
    assert upload(client, headers, b'<svg/>').status_code == 400


def test_product_price_is_encodable_and_images_survive_update(studio):
    _, client, db, headers, _ = studio
    class Products:
        doc = None
        def insert_one(self, doc):
            BSON.encode(doc)  # Real PyMongo encoding rejects bare Python Decimal.
            self.doc = doc
        def find_one(self, query):
            return self.doc
        def update_one(self, query, update):
            BSON.encode(update)
            self.doc.update(update['$set'])
    db.products = Products()
    db.orders = SimpleNamespace(find_one=lambda query: None)
    image = 'https://example.test/photo.png'
    created = client.post('/api/products', headers=headers, json={
        'title': 'Tote', 'description': 'Reclaimed fabric', 'price': '25.50',
        'category': 'Accessories', 'materials': ['Cotton'], 'quantityAvailable': 2,
        'images': [image]})
    assert created.status_code == 201
    assert isinstance(db.products.doc['price'], Decimal128)
    assert created.json['product']['images'] == [image]
    product_id = created.json['product']['_id']
    edited = client.patch('/api/products/' + product_id, headers=headers, json={'price': '28.00'})
    assert edited.status_code == 200
    assert edited.json['product']['price'] == '28.00'
    assert edited.json['product']['images'] == [image]
    assert edited.json['product']['approvalStatus'] == 'pending_review'
    assert edited.json['product']['listProduct'] is False


def test_marketplace_assets_resolve(studio):
    _, client, _, _, _ = studio
    assert client.get('/').status_code == 200
    assert client.get('/static/marketplace.css').status_code == 200
    assert client.get('/static/marketplace.js').status_code == 200
