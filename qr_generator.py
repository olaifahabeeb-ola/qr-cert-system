import qrcode
from qrcode.image.pure import PyPNGImage
from PIL import Image
import io


def make_qr(data: str, box_size=15, border=5) -> Image.Image:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=box_size,
        border=border,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color='black', back_color='white')
    return img.get_image()