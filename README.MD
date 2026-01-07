# Pishow – A Minimal Slideshow for Legacy Devices

Pishow is a lightweight slideshow solution designed specifically for older devices—including outdated smart TVs and
tablets. It delivers a simple HTML page that continuously cycles through images and videos stored on your network. With
no reliance on JavaScript (using meta refresh instead), Pishow is ideal for browsers with limited or no scripting
support.


## Features

- **Multi-Device Operation:**  
  Each device maintains its own media queue and state, ensuring personalized playback and seamless resumption across
  sessions.

- **Persistent State & Queue Management:**  
  Device-specific settings and media queues are saved to disk using lightweight binary files. The media list updates
  automatically as files are added, removed, or modified.

- **Device Identification:**  
  Unique identifiers are generated based on the device’s user-agent and IP address, allowing each device to have its own
  configuration.

- **Flexible Media Support:**  
  Supports images and videos in various formats, depending on your device's capabilities.

- **Customizable Settings Panel:**  
  Each device can be individually configured via a settings page (`/go`):
    - **Photo Display Time:** Set the duration (minimum 5 seconds) for which photos are shown.
    - **Only Photo Mode:** Display only images and skip videos.
    - **Sequential Mode:** Play media in sequential order (new media are appended without random shuffling).
    - **Counters & File Names:** Optionally display playback counters and file names.
    - **Video Background Mode:** Choose between continuous video playback or a static background. In static mode, a
      frame is extracted from the video; if that fails, an image from the library is used, or a gradient is generated as
      a fallback.

- **Admin Panel:**  
  Accessible at `/admin`, the admin panel provides:
    - An overview of all connected devices along with their settings and current media queue status.
    - Controls to update the media list, clear individual device queues, delete devices, and remotely edit device
      settings.

- **Automatic Media Conversion:**  
  New media files can be uploaded (via the admin panel or directly to the designated folder) and are automatically
  converted—images are compressed and resized (up to 3840×2160 at ~60% quality) and videos re-encoded to MP4—using
  FFmpeg and supporting libraries.  
  *Dependencies: ffmpeg, pillow-heif, httpx (installed via requirements.txt).*
- **Collections with deduplication:**  
  Media is grouped by folders (each folder = collection, subfolders are separate collections). Devices and defaults pick
  collections independently; hidden folders/files (starting with `.`) and video cover files are ignored. Duplicate files
  across collections are served once thanks to hardlink-based deduplication (see below).


## Collections

- Each folder in `MEDIA_DIR` is a collection; subfolders are separate collections.
- In the UI (admin or `/go`) you can choose collections per device, reset to default, or quick-start a single collection
  (saves the device selection and rebuilds the queue).
- Default collections are configured in the admin panel (by default root `/` + `uploaded` if present).
- Hidden folders/files (start with `.`) and temporary video cover files are ignored for collections and counts.


## Deduplication (hard links)

- Goal: if the same file lives in multiple collections, show/store a single instance via hardlinks.
- Flow:
  - Runs in background after idle: 15 minutes without changes (or 60 seconds if `DEBUG=true`); override with `DEDUP_IDLE_SECONDS`.
  - Any file change (watchdog, manual refresh in admin) sets a “changed” marker.
  - Pass hashes files (SHA-256); keeps the first, replaces the rest with a **hardlink** to it.
  - Skips: hidden files/folders, video cover suffix files, `uploaded_raw`, existing links/symlinks.
  - If conversion is active (`storage/converter.lock`), dedup won’t start.
  - On service start, dedup will run after the first interval even if no changes were seen (to catch pre-existing dupes).
- Storage: hardlinks have no “primary” file — all names point to the same content. File explorers may show full size per
  name, but disk space is used once. Check via `fsutil hardlink list <file>` (Windows) or `stat`/`ls -li` (Linux).
  - Hardlinks require the same filesystem/volume; if files are on different devices/mounts, dedup logs a skip.


## Why Pishow?

Many modern slideshow solutions rely on JavaScript and heavy frameworks that can cause compatibility issues on older
devices. Pishow offers a minimalist, resource-efficient alternative by using:

- **No Scripts:** Pure HTML with meta refresh.
- **Customizable, Device-Specific Settings:** Each device can be tailored to its own capabilities.
- **Low Resource Consumption:** Designed to run smoothly on legacy hardware.


## Supported Formats & Media Recommendations

*Compatibility depends on your device’s codecs and supported formats.*

**Recommended:**

- **Images:** `.jpg`, `.jpeg`, `.png`
- **Videos:** `.mp4`, `.mov`

> **Note:** Video duration detection may not work perfectly for all formats. Converting media with tools like `ffmpeg`
> is recommended for non-standard formats.


## Tested Devices

| Device                      | OS/Browser                                                  | Notes                                                                                                                  |
|-----------------------------|-------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| **LG Smart TV (webOS 3.0)** | Mozilla/5.0 (Linux; NetCast) AppleWebKit/537.31 Chrome/38.0 | Runs continuously for over 2 hours. Some devices may not support video looping—static background mode is used instead. |
| **iPad 2 (16GB)**           | Safari (iOS 9.3.5)                                          | Stable playback with full support for customizable settings.                                                           |

*Note:* On devices with limited RAM or when playing very large files, playback may be interrupted. For example, one
tested TV restarted when attempting to display a panorama image with a resolution of 12,000+ pixels and a size over
24MB.


## Preparing Your Media

For optimal performance, consider the following tips:

- **Compress Videos:**  
  Use [Rotato Video Compressor](https://tools.rotato.app/compress) or `ffmpeg` to re-encode videos. A recommended ffmpeg
  command (often better than Rotato) is:
    ```bash
    ffmpeg -i input.mp4 -c:v libx264 -preset slow -crf 30 -pix_fmt yuv420p -movflags faststart -c:a aac -b:a 128k output.mp4
    ```

- **Resize Images:**  
  Resize images to match your display resolution, set JPEG quality to 60–70%, and remove unnecessary metadata.

> **Tip:** If your device struggles with rotated videos (a common issue with mobile recordings), re-encoding will ensure
> correct rotation and aspect ratio since many decoders do not honor the rotate attribute.


## Installation & Deployment

### 1. Clone the Repository

```sh
git clone https://github.com/nikmedoed/pishow.git
cd pishow
```

### 2. Set Up Dependencies

```sh
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure the Media Directory

Edit the `.env` file to specify the path to your media folder:

```ini
MEDIA_DIR = /path/to/gallery
```

### 4. Run the Application

```sh
python run.py
```

By default, the server runs on `http://0.0.0.0:8000`. Open this URL in your browser on your device.

### 5. Deploy as a Systemd Service

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


## Update Script

Pishow includes an update script to simplify the update process. Simply run:

```sh
./update.sh
```

This script will pull the latest changes from the repository and restart the service if necessary.


## Feedback & Contributions

If you find Pishow useful or have suggestions for improvement, please open an issue or submit a pull request.


## Development Ideas

The first version was based on JavaScript with modern styles and transition effects. This version is minimalistic. If
you’d like to implement a modern mode with advanced features, feel free to fork the project and contribute.


## Acknowledgements

Pishow leverages [iphone-inline-video](https://github.com/fregante/iphone-inline-video) for improved video support on
older iOS devices. Many thanks to fregante and all contributors!


*This README is current as of the latest update. Contributions and feedback are welcome.*
