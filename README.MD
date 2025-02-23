# Pishow - A simple slideshow with extensive device coverage

Pishow is a minimal slideshow solution designed to run on old devices, including outdated smart TVs and tablets. It generates a simple HTML page that cycles through images and videos stored on your network. Unlike modern solutions, Pishow does not rely on JavaScript, making it ideal for browsers with limited or no scripting support.

## ✨ Features

- **Works on outdated devices** — Designed for old TVs, smart displays, and legacy browsers that don't support JavaScript.
- **No heavy scripts** — The slideshow refreshes using HTML meta refresh, ensuring compatibility with restricted browsers.
- **Random looping playback** — Displays images and videos in a shuffled sequence.
- **Lightweight & stable** — Runs for hours without memory leaks or performance degradation.
- **Supports network storage** — Load media directly from your NAS or a shared drive.

## 🎥 Supported Formats

Supported formats depend on the browser and device. By default, the following are recognized:
- **Images:** `.jpg`, `.jpeg`, `.png`
- **Videos:** `.mp4`, `.mov`
- Depends on the codec and format support on the target device

💡 **Codec note:** While `.mp4` is supported, some older devices may fail to play videos encoded with H.264 Level 5 or above.

## 🛠 Tested Devices

| Device | OS/Browser | Notes |
|--------|-----------|-------|
| **LG Smart TV (webOS 3.0)** | Mozilla/5.0 (Linux; NetCast) AppleWebKit/537.31 Chrome/38.0 | Worked for 2+ hours without issues. Failed with H.264 Level 5 and ultra-high-resolution panoramas. |
| **iPad 2 (16GB)** | Safari | Stable playback. |

## 📦 Preparing Your Media

For optimal performance:
- **Compress videos**: [Rotato Video Compressor](https://tools.rotato.app/compress)
- **Resize images**: Match your display resolution, set JPEG quality to 60-70%, and remove metadata.

## 🚀 Installation & Deployment

### 1️⃣ **Clone the Repository**
```sh
git clone https://github.com/nikmedoed/pishow.git
cd pishow
```

### 2️⃣ **Set Up Dependencies**
```sh
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3️⃣ **Configure Media Directory**
Edit `.env` and set the path to your media folder:
```ini
MEDIA_DIR=/path/to/gallery
```

### 4️⃣ **Run the Application**
```sh
python run.py
```

By default, the server runs on `http://0.0.0.0:8000`. Open this in your browser on your device.

### 5️⃣ **Deploy as a Systemd Service**
To run Pishow automatically on startup:

1. Create a systemd service file:
   ```sh
   sudo nano /etc/systemd/system/pishow.service
   ```

2. Add the following content:
   ```ini
   [Unit]
   Description=Pishow Slideshow
   After=network.target

   [Service]
   User=youruser
   WorkingDirectory=/home/youruser/pishow
   ExecStart=/home/youruser/pishow/venv/bin/uvicorn run:app --host 0.0.0.0 --port 8000 --reload=false
   Restart=always
   EnvironmentFile=/home/youruser/pishow/.env

   [Install]
   WantedBy=multi-user.target
   ```

3. Enable and start the service:
   ```sh
   sudo systemctl daemon-reload
   sudo systemctl enable pishow.service
   sudo systemctl start pishow.service
   ```

## 🎯 Why This Project?

Many existing slideshow solutions rely on JavaScript, making them incompatible with older devices. Pishow takes a different approach:
- **No scripts** — Just pure HTML and meta refresh.
- **Minimalist approach** — A straightforward media viewer without unnecessary overhead.
- **Optimized for low-power devices** — Runs on low-end hardware without lag.

---

📢 **Feedback & Contributions**
If you find this project useful or have suggestions, feel free to open an issue or contribute! 🚀
```