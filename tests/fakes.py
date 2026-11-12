"""Tiny in-memory test double for account, seed-protection and product-route tests. Does not contact Atlas."""
from copy import deepcopy
from types import SimpleNamespace

from bson import ObjectId
from pymongo.errors import DuplicateKeyError


class FakeCursor:
    def __init__(self, values):
        self.values = [deepcopy(v) for v in values]
    def sort(self, key, direction):
        self.values.sort(key=lambda row: row.get(key, ""), reverse=(direction == -1))
        return self
    def skip(self, n):
        self.values = self.values[n:]
        return self
    def limit(self, n):
        self.values = self.values[:n]
        return self
    def __iter__(self):
        return iter(self.values)


class FakeUsers:
    def __init__(self):
        self.docs = []
    def _matches(self, doc, filter_doc):
        for key, value in filter_doc.items():
            nested = doc
            for part in key.split("."):
                nested = nested.get(part) if isinstance(nested, dict) else None
            if nested != value:
                return False
        return True
    def insert_one(self, doc):
        if any(other['email'] == doc['email'] or other['userID'] == doc['userID'] for other in self.docs):
            raise DuplicateKeyError('fake duplicate')
        doc = deepcopy(doc)
        doc['_id'] = ObjectId()
        self.docs.append(doc)
        return SimpleNamespace(inserted_id=doc['_id'])
    def find_one(self, filter_doc):
        return next((deepcopy(d) for d in self.docs if self._matches(d,filter_doc)),None)
    def update_one(self, filter_doc, update_doc):
        for doc in self.docs:
            if self._matches(doc, filter_doc):
                for path, value in update_doc.get('$set',{}).items():
                    nested=doc
                    parts=path.split('.')
                    for part in parts[:-1]: nested=nested.setdefault(part,{})
                    nested[parts[-1]]=value
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)
    def find(self, filter_doc):
        return FakeCursor([doc for doc in self.docs if self._matches(doc,filter_doc)])


class FakeDB:
    def __init__(self):
        self.users=FakeUsers()


class FakeMongoClient:
    def __init__(self):
        self.database = FakeDB()
    def __getitem__(self, db_name):
        assert db_name in {'ecocraft_dev', 'ecocraft'}
        return self.database
