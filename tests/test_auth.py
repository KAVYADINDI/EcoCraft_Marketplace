"""Offline HTTP tests: no live database writes, no Atlas credentials needed."""
import jwt
import pytest
from bson import ObjectId
from werkzeug.security import generate_password_hash

from app import create_app
from tests.fakes import FakeMongoClient

TEST_SECRET = "local-test-secret-very-long-and-unpredictable-1234"


@pytest.fixture()
def dev_app():
    app = create_app({
        "TESTING": True,
        "MONGO_URI": "mongodb://unused",
        "MONGO_DB_NAME": "ecocraft_dev",
        "ENABLE_DEV_WRITES": True,
        "JWT_SECRET_KEY": TEST_SECRET,
    })
    app.extensions["mongo_client"] = FakeMongoClient()
    return app


@pytest.fixture()
def dev_client(dev_app):
    return dev_app.test_client()


def register_customer(dev_client, email="customer@example.test"):
    return dev_client.post('/api/auth/register', json={"role":"customer","email":email,"password":"test-password-12345","firstName":"Demo","lastName":"Buyer"})


def test_live_database_is_write_protected_even_if_flag_is_true():
    app = create_app({"TESTING":True,"MONGO_DB_NAME":"ecocraft","ENABLE_DEV_WRITES":True,"ENABLE_TEAM_DEMO_WRITES":False})
    r=app.test_client().post('/api/auth/register',json={"role":"customer"})
    assert r.status_code==403
    assert r.get_json()['error']['code']=='TEAM_DEMO_WRITES_DISABLED'


def test_artist_registration_is_pending_without_selling_access(dev_client, dev_app):
    response=dev_client.post('/api/auth/register',json={"role":"artist","email":"artist@example.test","password":"test-password-12345","firstName":"Ada","lastName":"Maker","originStory":"I weave responsibly."})
    assert response.status_code==201
    assert 'under review' in response.get_json()['message']
    stored=dev_app.extensions['mongo_client'].database.users.find_one({'email':'artist@example.test'})
    assert stored['artistProfile']=={'originStory':'I weave responsibly.','onboardingStatus':'request_received'}
    assert stored['role']=='artist'
    assert '$' in stored['passwordHash'] and stored['passwordHash'] != 'test-password-12345'
    denied=dev_client.post('/api/auth/login',json={'email':'artist@example.test','password':'test-password-12345'})
    assert denied.status_code==403


def test_customer_registration_and_login_and_me(dev_client):
    resp=register_customer(dev_client)
    assert resp.status_code==201
    login=dev_client.post('/api/auth/login',json={'email':'customer@example.test','password':'test-password-12345'})
    assert login.status_code==200
    assert login.get_json()['tokenType']=='Bearer'
    token=login.get_json()['accessToken']
    me=dev_client.get('/api/auth/me',headers={'Authorization':'Bearer '+token})
    assert me.status_code==200
    assert me.get_json()['user']['role']=='customer'
    assert 'passwordHash' not in me.get_data(as_text=True)


def test_public_registration_rejects_admin_and_unknown_fields(dev_client):
    bad=dev_client.post('/api/auth/register',json={'email':'admin@example.test','role':'admin','password':'test-password-12345','firstName':'A','lastName':'B'})
    assert bad.status_code==400
    bad2=dev_client.post('/api/auth/register',json={'email':'customer2@example.test','role':'customer','password':'test-password-12345','firstName':'A','lastName':'B','isAdmin':True})
    assert bad2.status_code==400


def test_duplicate_email_is_rejected(dev_client):
    assert register_customer(dev_client).status_code==201
    assert register_customer(dev_client).status_code==409


def test_invalid_login_is_generic(dev_client):
    assert register_customer(dev_client).status_code==201
    r=dev_client.post('/api/auth/login',json={'email':'customer@example.test','password':'wrong-password'})
    assert r.status_code==401 and r.get_json()['error']['code']=='INVALID_CREDENTIALS'


def test_existing_werkzeug_pbkdf2_passwords_supported(dev_app):
    client=dev_app.test_client()
    users=dev_app.extensions['mongo_client'].database.users
    users.insert_one({'userID':'ADM001','email':'admin@example.test',
      'passwordHash':generate_password_hash('legacy-admin-password',method='pbkdf2:sha256:600000'),
      'role':'admin','personalInfo':{'firstName':'Demo','lastName':'Admin'}})
    r=client.post('/api/auth/login',json={'email':'admin@example.test','password':'legacy-admin-password'})
    assert r.status_code==200


def test_customer_cannot_access_admin_artist_list(dev_client):
    register_customer(dev_client)
    token=dev_client.post('/api/auth/login',json={'email':'customer@example.test','password':'test-password-12345'}).get_json()['accessToken']
    r=dev_client.get('/api/admin/artists',headers={'Authorization':'Bearer '+token})
    assert r.status_code==403


def test_admin_can_list_artists_filtered(dev_app):
    client=dev_app.test_client()
    users=dev_app.extensions['mongo_client'].database.users
    users.insert_one({'userID':'ADM001','email':'admin@example.test','passwordHash':generate_password_hash('test-admin-password'), 'role':'admin','personalInfo':{'firstName':'Demo','lastName':'Admin'}})
    users.insert_one({'userID':'ART001','email':'maker@example.test','passwordHash':generate_password_hash('test-maker-password'),'role':'artist','personalInfo':{'firstName':'M','lastName':'A'},'artistProfile':{'originStory':'I make things','onboardingStatus':'request_received'}})
    token=client.post('/api/auth/login',json={'email':'admin@example.test','password':'test-admin-password'}).get_json()['accessToken']
    r=client.get('/api/admin/artists?status=request_received',headers={'Authorization':'Bearer '+token})
    assert r.status_code==200 and len(r.get_json()['artists'])==1


def test_edit_own_profile_only(dev_client):
    register_customer(dev_client)
    token=dev_client.post('/api/auth/login',json={'email':'customer@example.test','password':'test-password-12345'}).get_json()['accessToken']
    headers={'Authorization':'Bearer '+token}
    resp=dev_client.patch('/api/auth/me',json={'firstName':'Updated','mobile':'555-0100'},headers=headers)
    assert resp.status_code==200 and resp.get_json()['user']['personalInfo']['firstName']=='Updated'
    resp2=dev_client.patch('/api/auth/me',json={'role':'admin'},headers=headers)
    assert resp2.status_code==400


def test_expired_token_rejected(dev_client):
    token=jwt.encode({'sub':str(ObjectId()), 'iss':'ecocraft-local','iat':1,'exp':2}, TEST_SECRET,algorithm='HS256')
    response=dev_client.get('/api/auth/me',headers={'Authorization':'Bearer '+token})
    assert response.status_code==401
    assert response.get_json()['error']['code']=='TOKEN_EXPIRED'


def test_empty_token_rejected(dev_client):
    assert dev_client.get('/api/auth/me').status_code==401
