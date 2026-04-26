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

BASE_DIR = os.path.dirname(__file__)
QR_DIR   = os.path.join(BASE_DIR, 'static', 'qrcodes')
CERT_DIR = os.path.join(BASE_DIR, 'static', 'certs')
DB_FILE  = os.path.join(BASE_DIR, 'certificates.json')

os.makedirs(QR_DIR,   exist_ok=True)
os.makedirs(CERT_DIR, exist_ok=True)


# ── Database helpers ─────────────────────────────────────────────────────────

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


# ── Certificate image builder ────────────────────────────────────────────────

def build_certificate_image(cert_data, qr_img, cert_id):
    W, H = 1200, 850
    img  = Image.new('RGB', (W, H), '#FAFAF7')
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    # Borders
    for i in range(5):
        draw.rectangle([i, i, W-1-i, H-1-i], outline='#1a3a6b')
    draw.rectangle([12, 12, W-13, H-13], outline='#c8a415', width=2)

    # Header bar
    draw.rectangle([0, 0, W, 130], fill='#1a3a6b')

    font = ImageFont.load_default()

    draw.text((W//2, 35),  'FEDERAL POLYTECHNIC OFFA',
              fill='white',   anchor='mm', font=font)
    draw.text((W//2, 58),  'KWARA STATE, NIGERIA',
              fill='#c8a415', anchor='mm', font=font)
    draw.text((W//2, 82),  'Department of Software and Web Development',
              fill='white',   anchor='mm', font=font)
    draw.text((W//2, 108), 'CERTIFICATE OF COMPLETION',
              fill='#c8a415', anchor='mm', font=font)

    # Gold divider
    draw.rectangle([50, 140, W-50, 143], fill='#c8a415')

    draw.text((W//2, 185), 'This is to certify that',
              fill='#555', anchor='mm', font=font)
    draw.text((W//2, 230), cert_data.get('name', '').upper(),
              fill='#1a3a6b', anchor='mm', font=font)
    draw.line([(250, 250), (950, 250)], fill='#c8a415', width=1)

    draw.text((W//2, 280),
              'having successfully completed all requirements has been awarded',
              fill='#555', anchor='mm', font=font)
    draw.text((W//2, 325), cert_data.get('qualification', ''),
              fill='#1a3a6b', anchor='mm', font=font)
    draw.text((W//2, 368), f"in  {cert_data.get('course', '')}",
              fill='#333', anchor='mm', font=font)
    draw.text((W//2, 410), f"Classification:  {cert_data.get('grade', '')}",
              fill='#333', anchor='mm', font=font)
    draw.text((W//2, 450),
              f"Matric No: {cert_data.get('matric', '')}   |   "
              f"Date Issued: {cert_data.get('issue_date', '')}",
              fill='#555', anchor='mm', font=font)

    draw.rectangle([50, 488, W-50, 490], fill='#c8a415')

    # QR code (right side)
    qr_size    = 220
    qr_resized = qr_img.resize((qr_size, qr_size), Image.NEAREST)
    qr_x, qr_y = W - qr_size - 60, 510
    img.paste(qr_resized, (qr_x, qr_y))
    draw.text((qr_x + qr_size//2, qr_y + qr_size + 15),
              'Scan to Verify', fill='#888', anchor='mm', font=font)

    # Signature lines
    sig_y = 600
    draw.line([(80,  sig_y), (320, sig_y)], fill='#333', width=1)
    draw.text((200, sig_y + 18), 'Rector',
              fill='#555', anchor='mm', font=font)
    draw.line([(430, sig_y), (670, sig_y)], fill='#333', width=1)
    draw.text((550, sig_y + 18), 'Registrar',
              fill='#555', anchor='mm', font=font)

    draw.text((400, 760),
              f'Certificate ID: {cert_id}', fill='#aaa', anchor='mm', font=font)
    draw.text((400, 785),
              'Cryptographically Signed — Verify at system URL',
              fill='#bbb', anchor='mm', font=font)

    return img


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    total = len(load_db())
    return render_template('index.html', keys_ready=keys_exist(), total=total)


@app.route('/admin')
def admin():
    certs = load_db()
    return render_template('admin.html', certs=certs, keys_ready=keys_exist())


@app.route('/admin/generate-keys', methods=['POST'])
def generate_keys_route():
    generate_keys()
    flash('RSA-2048 key pair generated successfully.', 'success')
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

        cert_id          = str(uuid.uuid4())[:8].upper()
        cert_data['cert_id'] = cert_id

        payload  = sign_certificate(cert_data)
        qr_json  = json.dumps(payload, separators=(',', ':'))

        if len(qr_json.encode('utf-8')) > 216:
            qr_payload = json.dumps(
                {'cert_id': cert_id, 'verify': 'scan'}, separators=(',', ':')
            )
        else:
            qr_payload = qr_json

        record = {
            'id':        cert_id,
            'cert_data': cert_data,
            'payload':   payload,
            'issued_at': datetime.now().isoformat(),
            'qr_file':   f'{cert_id}_qr.png',
            'cert_file': f'{cert_id}_cert.png',
        }
        db = load_db()
        db.append(record)
        save_db(db)

        qr_img  = make_qr(qr_payload, box_size=8, border=3)
        qr_img.save(os.path.join(QR_DIR, record['qr_file']))

        cert_img = build_certificate_image(cert_data, qr_img, cert_id)
        cert_img.save(os.path.join(CERT_DIR, record['cert_file']))

        flash(f'Certificate issued successfully! ID: {cert_id}', 'success')
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

    if request.method == 'POST':
        raw            = request.form.get('payload', '').strip()
        cert_id_input  = request.form.get('cert_id', '').strip().upper()

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
                if 'cert_id' in payload and 'data' not in payload:
                    record = find_cert(payload['cert_id'])
                    if record:
                        valid, message = verify_certificate(record['payload'])
                        result    = {'valid': valid, 'message': message}
                        cert_data = record['cert_data']
                    else:
                        result = {'valid': False,
                                  'message': 'Certificate ID not found in system.'}
                else:
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