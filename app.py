import os
import json
import uuid
import base64
from datetime import datetime
from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, send_file, jsonify
)
from PIL import Image, ImageDraw, ImageFont

from crypto import (
    generate_keys, sign_certificate, verify_certificate,
    keys_exist, get_public_key_pem
)
from qr_generator import make_qr

app = Flask(__name__)
app.secret_key = 'qrcert-secret-2026'

BASE_DIR    = os.path.dirname(__file__)
QR_DIR      = os.path.join(BASE_DIR, 'static', 'qrcodes')
CERT_DIR    = os.path.join(BASE_DIR, 'static', 'certs')
UPLOAD_DIR  = os.path.join(BASE_DIR, 'static', 'uploads')
DB_FILE     = os.path.join(BASE_DIR, 'certificates.json')
SETTINGS_FILE = os.path.join(BASE_DIR, 'settings.json')

for d in [QR_DIR, CERT_DIR, UPLOAD_DIR]:
    os.makedirs(d, exist_ok=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def load_db():
    if not os.path.exists(DB_FILE):
        return []
    with open(DB_FILE, 'r') as f:
        return json.load(f)

def save_db(records):
    with open(DB_FILE, 'w') as f:
        json.dump(records, f, indent=2)

def find_cert(cert_id):
    for r in load_db():
        if r['id'] == cert_id:
            return r
    return None

def load_settings():
    if not os.path.exists(SETTINGS_FILE):
        return {}
    with open(SETTINGS_FILE, 'r') as f:
        return json.load(f)

def save_settings(data):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(data, f, indent=2)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'png', 'jpg', 'jpeg'}


# ── Certificate image builder ─────────────────────────────────────────────────

def build_certificate_image(cert_data, qr_img, cert_id,
                             student_photo_path=None):
    settings = load_settings()

    # Canvas — A4 landscape at 150dpi
    W, H = 1684, 1191
    img  = Image.new('RGB', (W, H), '#FFFEF9')
    draw = ImageDraw.Draw(img)

    # ── Outer gold border ──
    for i in range(8):
        draw.rectangle([i, i, W-1-i, H-1-i],
                       outline='#C8A415' if i % 2 == 0 else '#1a3a6b')
    draw.rectangle([18, 18, W-19, H-19], outline='#C8A415', width=3)
    draw.rectangle([24, 24, W-25, H-25], outline='#1a3a6b', width=1)

    # ── Navy header bar ──
    draw.rectangle([0, 0, W, 180], fill='#1a3a6b')
    draw.rectangle([0, 177, W, 183], fill='#C8A415')

    # ── School logo (top left) ──
    logo_path = settings.get('logo')
    if logo_path and os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert('RGBA')
            logo.thumbnail((140, 140), Image.LANCZOS)
            img.paste(logo, (30, 20), logo)
        except Exception:
            pass

    # ── Institution name (header) ──
    try:
        font_big   = ImageFont.load_default(size=38)
        font_med   = ImageFont.load_default(size=24)
        font_small = ImageFont.load_default(size=18)
        font_body  = ImageFont.load_default(size=20)
        font_name  = ImageFont.load_default(size=44)
        font_cert  = ImageFont.load_default(size=28)
        font_tiny  = ImageFont.load_default(size=15)
    except TypeError:
        font_big = font_med = font_small = font_body = \
        font_name = font_cert = font_tiny = ImageFont.load_default()

    draw.text((W//2, 55),  'FEDERAL POLYTECHNIC OFFA',
              fill='white', anchor='mm', font=font_big)
    draw.text((W//2, 100), 'KWARA STATE, NIGERIA',
              fill='#C8A415', anchor='mm', font=font_med)
    draw.text((W//2, 138), 'Department of Software and Web Development',
              fill='rgba(255,255,255,200)', anchor='mm', font=font_small)
    draw.text((W//2, 165), 'OFFICE OF THE REGISTRAR',
              fill='#C8A415', anchor='mm', font=font_small)

    # ── Certificate title ──
    draw.text((W//2, 230), 'CERTIFICATE OF COMPLETION',
              fill='#1a3a6b', anchor='mm', font=font_big)

    # Gold underline
    tw = 520
    draw.rectangle([W//2 - tw//2, 250, W//2 + tw//2, 254],
                   fill='#C8A415')

    # ── Body text ──
    draw.text((W//2, 300),
              'This is to certify that',
              fill='#555555', anchor='mm', font=font_body)

    # Student name
    draw.text((W//2, 370),
              cert_data.get('name', '').upper(),
              fill='#1a3a6b', anchor='mm', font=font_name)
    draw.rectangle([200, 400, W-200, 403], fill='#C8A415')

    draw.text((W//2, 440),
              'having successfully fulfilled all academic requirements'
              ' is hereby awarded the',
              fill='#444444', anchor='mm', font=font_body)

    draw.text((W//2, 490),
              cert_data.get('qualification', ''),
              fill='#1a3a6b', anchor='mm', font=font_cert)

    draw.text((W//2, 535),
              f"in  {cert_data.get('course', '')}",
              fill='#333333', anchor='mm', font=font_body)

    draw.text((W//2, 575),
              f"with  {cert_data.get('grade', '')}",
              fill='#1a3a6b', anchor='mm', font=font_cert)

    # Details row
    draw.text((W//2, 630),
              f"Matric No:  {cert_data.get('matric', '')}"
              f"          |          "
              f"Date Issued:  {cert_data.get('issue_date', '')}",
              fill='#666666', anchor='mm', font=font_body)

    # Gold divider
    draw.rectangle([60, 660, W-60, 662], fill='#C8A415')

    # ── Student photo (top right) ──
    photo_x, photo_y = W - 220, 200
    draw.rectangle([photo_x - 5, photo_y - 5,
                    photo_x + 165, photo_y + 205],
                   outline='#C8A415', width=3)
    if student_photo_path and os.path.exists(student_photo_path):
        try:
            photo = Image.open(student_photo_path).convert('RGB')
            photo = photo.resize((160, 200), Image.LANCZOS)
            img.paste(photo, (photo_x, photo_y))
        except Exception:
            draw.rectangle([photo_x, photo_y, photo_x+160, photo_y+200],
                           fill='#e0e0e0')
            draw.text((photo_x+80, photo_y+100), 'PHOTO',
                      fill='#aaa', anchor='mm', font=font_body)
    else:
        draw.rectangle([photo_x, photo_y, photo_x+160, photo_y+200],
                       fill='#f0f0f0')
        draw.text((photo_x+80, photo_y+100), 'NO PHOTO',
                  fill='#bbb', anchor='mm', font=font_small)

    # ── Signatures ──
    sig_y     = 720
    sig_line  = sig_y + 80

    # Rector signature
    rector_sig = settings.get('rector_sig')
    if rector_sig and os.path.exists(rector_sig):
        try:
            sig_img = Image.open(rector_sig).convert('RGBA')
            sig_img.thumbnail((200, 80), Image.LANCZOS)
            img.paste(sig_img, (120, sig_y), sig_img)
        except Exception:
            pass
    draw.line([(80, sig_line), (380, sig_line)], fill='#333', width=2)
    draw.text((230, sig_line + 20), 'RECTOR',
              fill='#1a3a6b', anchor='mm', font=font_body)
    draw.text((230, sig_line + 42), 'Federal Polytechnic Offa',
              fill='#888', anchor='mm', font=font_tiny)

    # Registrar signature
    reg_sig = settings.get('registrar_sig')
    if reg_sig and os.path.exists(reg_sig):
        try:
            sig_img = Image.open(reg_sig).convert('RGBA')
            sig_img.thumbnail((200, 80), Image.LANCZOS)
            img.paste(sig_img, (580, sig_y), sig_img)
        except Exception:
            pass
    draw.line([(540, sig_line), (840, sig_line)], fill='#333', width=2)
    draw.text((690, sig_line + 20), 'REGISTRAR',
              fill='#1a3a6b', anchor='mm', font=font_body)
    draw.text((690, sig_line + 42), 'Federal Polytechnic Offa',
              fill='#888', anchor='mm', font=font_tiny)

    # ── QR code (bottom right) ──
    qr_size    = 180
    qr_resized = qr_img.resize((qr_size, qr_size), Image.NEAREST)
    qr_x = W - qr_size - 80
    qr_y = sig_y - 10
    draw.rectangle([qr_x - 8, qr_y - 8,
                    qr_x + qr_size + 8, qr_y + qr_size + 8],
                   outline='#C8A415', width=2)
    img.paste(qr_resized, (qr_x, qr_y))
    draw.text((qr_x + qr_size//2, qr_y + qr_size + 18),
              'Scan to Verify', fill='#888',
              anchor='mm', font=font_tiny)

    # ── Certificate ID + watermark ──
    draw.text((W//2, H - 55),
              f'Certificate ID: {cert_id}   |   '
              f'Verify at: qr-cert-system-qftr.onrender.com/verify',
              fill='#aaaaaa', anchor='mm', font=font_tiny)

    # Diagonal watermark
    watermark = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    wdraw     = ImageDraw.Draw(watermark)
    try:
        wfont = ImageFont.load_default(size=80)
    except TypeError:
        wfont = ImageFont.load_default()
    wdraw.text((W//2, H//2), 'FEDERAL POLYTECHNIC OFFA',
               fill=(26, 58, 107, 18), anchor='mm', font=wfont)
    img = Image.alpha_composite(img.convert('RGBA'),
                                watermark).convert('RGB')

    return img


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    total = len(load_db())
    return render_template('index.html',
                           keys_ready=keys_exist(), total=total)

@app.route('/admin')
def admin():
    certs    = load_db()
    settings = load_settings()
    return render_template('admin.html', certs=certs,
                           keys_ready=keys_exist(), settings=settings)

@app.route('/admin/generate-keys', methods=['POST'])
def generate_keys_route():
    generate_keys()
    flash('RSA-2048 key pair generated successfully.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/settings', methods=['POST'])
def save_settings_route():
    settings = load_settings()

    for field, key in [
        ('logo',         'logo'),
        ('rector_sig',   'rector_sig'),
        ('registrar_sig','registrar_sig'),
    ]:
        file = request.files.get(field)
        if file and allowed_file(file.filename):
            filename = f"{key}.{file.filename.rsplit('.',1)[1].lower()}"
            path     = os.path.join(UPLOAD_DIR, filename)
            file.save(path)
            settings[key] = path

    save_settings(settings)
    flash('Settings saved successfully.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/issue', methods=['GET', 'POST'])
def issue():
    if not keys_exist():
        flash('Please generate keys before issuing certificates.', 'warning')
        return redirect(url_for('admin'))

    if request.method == 'POST':
        cert_data = {
            'name':          request.form['name'].strip(),
            'matric':        request.form['matric'].strip(),
            'course':        request.form['course'].strip(),
            'qualification': request.form['qualification'].strip(),
            'grade':         request.form['grade'].strip(),
            'issue_date':    request.form['issue_date'].strip(),
            'institution':   'Federal Polytechnic Offa',
            'department':    'Department of Software and Web Development',
        }

        cert_id              = str(uuid.uuid4())[:8].upper()
        cert_data['cert_id'] = cert_id

        # Save student photo
        student_photo_path = None
        photo = request.files.get('student_photo')
        if photo and allowed_file(photo.filename):
            ext                = photo.filename.rsplit('.', 1)[1].lower()
            photo_filename     = f"{cert_id}_photo.{ext}"
            student_photo_path = os.path.join(UPLOAD_DIR, photo_filename)
            photo.save(student_photo_path)

        payload    = sign_certificate(cert_data)
        qr_payload = (
            f"https://qr-cert-system-qftr.onrender.com"
            f"/verify?cert_id={cert_id}"
        )

        record = {
            'id':          cert_id,
            'cert_data':   cert_data,
            'payload':     payload,
            'issued_at':   datetime.now().isoformat(),
            'qr_file':     f'{cert_id}_qr.png',
            'cert_file':   f'{cert_id}_cert.png',
            'photo_file':  f'{cert_id}_photo.{photo.filename.rsplit(".",1)[1].lower()}' if photo and allowed_file(photo.filename) else None,
        }
        db = load_db()
        db.append(record)
        save_db(db)

        qr_img = make_qr(qr_payload, box_size=8, border=3)
        qr_img.save(os.path.join(QR_DIR, record['qr_file']))

        cert_img = build_certificate_image(
            cert_data, qr_img, cert_id, student_photo_path
        )
        cert_img.save(os.path.join(CERT_DIR, record['cert_file']))

        flash(f'Certificate issued! ID: {cert_id}', 'success')
        return redirect(url_for('view_cert', cert_id=cert_id))

    return render_template('issue.html')

@app.route('/certificate/<cert_id>')
def view_cert(cert_id):
    record = find_cert(cert_id)
    if not record:
        flash('Certificate not found.', 'danger')
        return redirect(url_for('admin'))
    return render_template('view_cert.html', record=record)

@app.route('/verify', methods=['GET', 'POST'])
def verify():
    result    = None
    cert_data = None

    # Handle QR scan redirect
    cert_id_param = request.args.get('cert_id', '').strip().upper()
    if cert_id_param:
        record = find_cert(cert_id_param)
        if record:
            valid, message = verify_certificate(record['payload'])
            result    = {'valid': valid, 'message': message}
            cert_data = record['cert_data']
        else:
            result = {'valid': False,
                      'message': f'No certificate found with ID: {cert_id_param}'}

    if request.method == 'POST':
        raw           = request.form.get('payload', '').strip()
        cert_id_input = request.form.get('cert_id', '').strip().upper()

        if cert_id_input:
            record = find_cert(cert_id_input)
            if record:
                valid, message = verify_certificate(record['payload'])
                result    = {'valid': valid, 'message': message}
                cert_data = record['cert_data']
            else:
                result = {'valid': False,
                          'message': f'No certificate found with ID: {cert_id_input}'}
        elif raw:
            try:
                payload = json.loads(raw)
                valid, message = verify_certificate(payload)
                result    = {'valid': valid, 'message': message}
                cert_data = payload.get('data')
            except json.JSONDecodeError:
                result = {'valid': False,
                          'message': 'Invalid JSON. Please check the input.'}

    return render_template('verify.html', result=result, cert_data=cert_data)

@app.route('/verify/api/<cert_id>')
def verify_api(cert_id):
    record = find_cert(cert_id.upper())
    if not record:
        return jsonify({'valid': False, 'message': 'Certificate not found'}), 404
    valid, message = verify_certificate(record['payload'])
    return jsonify({
        'valid':     valid,
        'message':   message,
        'cert_data': record['cert_data'] if valid else None
    })

@app.route('/public-key')
def public_key():
    pem = get_public_key_pem()
    return render_template('public_key.html', pem=pem)

@app.route('/download/qr/<cert_id>')
def download_qr(cert_id):
    record = find_cert(cert_id)
    if not record:
        flash('Not found.', 'danger')
        return redirect(url_for('admin'))
    return send_file(
        os.path.join(QR_DIR, record['qr_file']),
        as_attachment=True,
        download_name=f'cert_{cert_id}_qr.png'
    )

@app.route('/download/cert/<cert_id>')
def download_cert(cert_id):
    record = find_cert(cert_id)
    if not record:
        flash('Not found.', 'danger')
        return redirect(url_for('admin'))
    return send_file(
        os.path.join(CERT_DIR, record['cert_file']),
        as_attachment=True,
        download_name=f'certificate_{cert_id}.png'
    )

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)