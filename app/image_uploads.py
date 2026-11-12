"""Validated product-photo uploads to Cloudinary, independent of Flask/MongoDB.

The browser never receives Cloudinary API credentials. MongoDB stores HTTPS URLs,
not image binary, preserving the team's existing products.images array schema.
"""
import base64
import json
import re
import secrets
from urllib import request as http
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse

MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_REQUEST_BYTES = MAX_IMAGE_BYTES + (512 * 1024)


class InvalidImage(ValueError):
    pass


class UploadNotConfigured(RuntimeError):
    pass


class UploadFailed(RuntimeError):
    pass


def detect_image_type(raw):
    """Allow only JPEG, PNG and WEBP, based on the actual bytes, not filename."""
    if raw[:8] == b'\x89PNG\r\n\x1a\n':
        return 'image/png', 'png'
    if raw[:3] == b'\xff\xd8\xff':
        return 'image/jpeg', 'jpg'
    if len(raw) >= 12 and raw[:4] == b'RIFF' and raw[8:12] == b'WEBP':
        return 'image/webp', 'webp'
    raise InvalidImage('Choose a valid PNG, JPEG, or WebP image')


def validate_photo(raw):
    """Check nonempty bytes, the 4 MB cap and supported file signatures; not a full decoder."""
    if not isinstance(raw, bytes) or not raw:
        raise InvalidImage('Choose an image first')
    if len(raw) > MAX_IMAGE_BYTES:
        raise InvalidImage('Image must be 4 MB or smaller')
    return detect_image_type(raw)


def multipart(fields, image_bytes, file_mime, extension, boundary):
    """Build a multipart request with a server-generated filename, independent of the user filename."""
    chunks=[]
    for name,value in fields.items():
        chunks.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode('utf-8')])
    chunks.extend([f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="product.{extension}"\r\nContent-Type: {file_mime}\r\n\r\n'.encode('ascii'),image_bytes,b'\r\n',f'--{boundary}--\r\n'.encode('ascii')])
    return b''.join(chunks)


def upload_product_photo(raw, cloud_name, api_key, api_secret, *, open_url=None):
    """Publish validated image via HTTPS; credentials remain server-side.

    Network I/O is injectable for dependency-free unit testing.
    """
    mime,extension=validate_photo(raw)
    if not (re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',cloud_name or '')
            and isinstance(api_key,str) and api_key.strip()
            and isinstance(api_secret,str) and api_secret.strip()):
        raise UploadNotConfigured('Cloudinary image uploading is not configured')
    boundary='----EcoCraft'+secrets.token_hex(16)
    body=multipart({'folder':'ecocraft/demo-products'},raw,mime,extension,boundary)
    credentials=base64.b64encode((api_key+':'+api_secret).encode('utf-8')).decode('ascii')
    url=f'https://api.cloudinary.com/v1_1/{cloud_name}/image/upload'
    req=http.Request(url,data=body,headers={
        'Content-Type':'multipart/form-data; boundary='+boundary,
        'Authorization':'Basic '+credentials,
        'Accept':'application/json',
        'User-Agent':'EcoCraft-Course-App/1.0',
    },method='POST')
    try:
        opener=open_url or http.urlopen
        with opener(req,timeout=25) as response:
            data=json.loads(response.read(64*1024).decode('utf-8'))
    except (HTTPError,URLError,OSError,ValueError,UnicodeDecodeError) as exc:
        raise UploadFailed('Image hosting service rejected the upload or could not be reached') from exc
    uploaded=data.get('secure_url') if isinstance(data,dict) else None
    parsed=urlparse(uploaded) if isinstance(uploaded,str) else None
    # Only accept Cloudinary HTTPS URLs, never arbitrary remote redirects.
    if not parsed or parsed.scheme!='https' or parsed.netloc!='res.cloudinary.com' or not parsed.path.startswith('/'+cloud_name+'/'):
        raise UploadFailed('Image host returned an invalid image URL')
    return uploaded
