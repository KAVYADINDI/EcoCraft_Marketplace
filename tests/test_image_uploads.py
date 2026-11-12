"""Image-upload tests that run without Flask, MongoDB, or a Cloudinary account."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('image_uploads_standalone',ROOT/'app'/'image_uploads.py')
image_uploads=importlib.util.module_from_spec(spec)
spec.loader.exec_module(image_uploads)

PNG=b'\x89PNG\r\n\x1a\n' + b'00fake-test-file'
JPEG=b'\xff\xd8\xff' + b'00fake-test-file'
WEBP=b'RIFF'+b'1234'+b'WEBP' + b'00fake-test-file'

class FakeResponse:
    def __init__(self,data): self.data=data
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,*args):return self.data

class Tests(unittest.TestCase):
    def test_png(self): self.assertEqual(image_uploads.validate_photo(PNG),('image/png','png'))
    def test_jpeg(self): self.assertEqual(image_uploads.validate_photo(JPEG),('image/jpeg','jpg'))
    def test_webp(self): self.assertEqual(image_uploads.validate_photo(WEBP),('image/webp','webp'))
    def test_empty(self):
        with self.assertRaises(image_uploads.InvalidImage):image_uploads.validate_photo(b'')
    def test_svg_rejected(self):
        with self.assertRaises(image_uploads.InvalidImage):image_uploads.validate_photo(b'<svg><script/></svg>')
    def test_random_text_rejected(self):
        with self.assertRaises(image_uploads.InvalidImage):image_uploads.validate_photo(b'hello')
    def test_large_rejected(self):
        with self.assertRaises(image_uploads.InvalidImage):image_uploads.validate_photo(PNG+b'Z'*(image_uploads.MAX_IMAGE_BYTES))
    def test_unconfigured(self):
        with self.assertRaises(image_uploads.UploadNotConfigured):image_uploads.upload_product_photo(PNG,'','','')
    def test_cloud_name_validation(self):
        with self.assertRaises(image_uploads.UploadNotConfigured):image_uploads.upload_product_photo(PNG,'bad/cloud','k','s')
    def test_multipart_contains_image(self):
        body=image_uploads.multipart({'folder':'ecocraft/demo-products'},PNG,'image/png','png','bound')
        self.assertIn(PNG,body)
        self.assertIn(b'name="file"',body)
        self.assertIn(b'filename="product.png"',body)
    def test_signed_server_only_upload(self):
        seen={}
        def opener(req,timeout):
            seen['url']=req.full_url;seen['auth']=req.get_header('Authorization');seen['data']=req.data
            return FakeResponse(json.dumps({'secure_url':'https://res.cloudinary.com/ecocraft-cloud/image/upload/v1/p.png'}).encode())
        url=image_uploads.upload_product_photo(PNG,'ecocraft-cloud','mykey','mysecret',open_url=opener)
        self.assertEqual(url,'https://res.cloudinary.com/ecocraft-cloud/image/upload/v1/p.png')
        self.assertTrue(seen['url'].startswith('https://api.cloudinary.com/v1_1/ecocraft-cloud/image/upload'))
        self.assertTrue(seen['auth'].startswith('Basic '))
        self.assertNotIn(b'mysecret',seen['data'])
    def test_non_https_host_rejected(self):
        def opener(req,timeout):return FakeResponse(b'{"secure_url":"http://example.com/a.png"}')
        with self.assertRaises(image_uploads.UploadFailed):image_uploads.upload_product_photo(PNG,'ecocraft-cloud','key','secret',open_url=opener)
    def test_wrong_cloud_rejected(self):
        def opener(req,timeout):return FakeResponse(b'{"secure_url":"https://res.cloudinary.com/some-other-cloud/image/upload/a.png"}')
        with self.assertRaises(image_uploads.UploadFailed):image_uploads.upload_product_photo(PNG,'ecocraft-cloud','key','secret',open_url=opener)
    def test_bad_api_response(self):
        def opener(req,timeout):return FakeResponse(b'not json')
        with self.assertRaises(image_uploads.UploadFailed):image_uploads.upload_product_photo(PNG,'ecocraft-cloud','key','secret',open_url=opener)

if __name__=='__main__':unittest.main()
