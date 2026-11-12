"""Static integration checks for image upload forms and the protected endpoint."""
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
H=(ROOT/'app/templates/marketplace.html').read_text(encoding='utf-8')
J=(ROOT/'app/static/marketplace.js').read_text(encoding='utf-8')
R=(ROOT/'app/routes/marketplace.py').read_text(encoding='utf-8')
S=(ROOT/'app/__init__.py').read_text(encoding='utf-8')

class TestImageFeature(unittest.TestCase):
    def test_file_input(self):self.assertIn('id="product-image-file"',H)
    def test_https_url_input(self):self.assertIn('id="product-image-url"',H)
    def test_remove_input(self):self.assertIn('id="product-image-remove"',H)
    def test_upload_is_authenticated(self):
        self.assertIn("@shop_bp.post('/products/image-upload')\n@auth_required('artist')",R)
    def test_upload_guarded(self):
        self.assertIn('denied=written()',R)
        self.assertIn("g.current_user.get('artistProfile',{}).get('onboardingStatus')!='approved'",R)
    def test_upload_content_limit_per_request(self):self.assertIn('request.max_content_length=MAX_REQUEST_BYTES',R)
    def test_frontend_multipart(self):self.assertIn("body.append('file',file)",J)
    def test_image_url_saves_to_mongo_product(self):
        self.assertIn('d.images=[url]',J)
        self.assertIn('d.images=[imageUrl]',J)
    def test_image_removal(self):self.assertIn('if(removeImage)d.images=[]',J)
    def test_existing_image_on_edit(self):self.assertIn("p.images?.[0]||''",J)
    def test_cloud_secrets_server_only(self):
        self.assertIn('CLOUDINARY_API_SECRET',S)
        self.assertNotIn('CLOUDINARY_API_SECRET',H+J)

if __name__=='__main__':unittest.main()
