"""Decode real image contents and re-encode pixels. Never serve original uploads."""
import io, os, warnings, secrets
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener
register_heif_opener()
Image.MAX_IMAGE_PIXELS = 36_000_000
ALLOWED = {'JPEG','PNG','WEBP','HEIF','HEIC','GIF','BMP','TIFF'}
MAX_BYTES = 20 * 1024 * 1024


def normalize_image(stream):
    raw = stream.read(MAX_BYTES + 1)
    if not raw or len(raw) > MAX_BYTES: raise ValueError('Envie uma imagem de até 20 MB.')
    # Reject executable/script signatures even when followed by valid image data.
    if raw[:2] in (b'MZ',b'#!') or raw[:4] in (b'\x7fELF',b'PK\x03\x04'): raise ValueError('O arquivo não é uma imagem segura.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as check:
                if check.format not in ALLOWED: raise ValueError('Formato não suportado. Use JPG, PNG, WebP, HEIC/HEIF, GIF, BMP ou TIFF.')
                check.verify()
            with Image.open(io.BytesIO(raw)) as source:
                source.seek(0) # animated GIF/TIFF: deliberately use first frame
                source.load()
                pixels = ImageOps.exif_transpose(source).convert('RGBA')
                pixels.thumbnail((1600,1600),Image.Resampling.LANCZOS)
                background=Image.new('RGB',pixels.size,'white')
                background.paste(pixels,mask=pixels.getchannel('A'))
                output=io.BytesIO()
                background.save(output,'JPEG',quality=86,optimize=True)
                return output.getvalue()
    except (UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning,SyntaxError) as exc:
        raise ValueError('Não foi possível ler a imagem. Ela pode estar corrompida ou exceder 36 megapixels.') from exc


def store_image(connection, image_bytes):
    name=secrets.token_hex(16)+'.jpg'
    url=None; public_id=None
    if os.environ.get('CLOUDINARY_URL'):
        import cloudinary, cloudinary.uploader
        cloudinary.config(secure=True)
        result=cloudinary.uploader.upload(io.BytesIO(image_bytes),resource_type='image',folder='lumina/products',public_id=name[:-4],overwrite=False,timeout=40)
        url=result['secure_url']; public_id=result['public_id']
        if not url.startswith('https://res.cloudinary.com/'): raise RuntimeError('Destino de imagem inválido.')
    # Permanent Postgres copy also enables backups and rollback if CDN becomes unavailable.
    connection.execute('INSERT INTO uploaded_images(name,data,mime_type,cloudinary_public_id,delivery_url) VALUES(%s,%s,%s,%s,%s)',(name,image_bytes,'image/jpeg',public_id,url))
    return '/uploads/'+name
