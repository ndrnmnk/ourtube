# OurTube

**OurTube** is a lightweight YouTube frontend designed for **Android devices** and **J2ME feature phones**. It enables users to search, stream, and watch YouTube videos on legacy hardware that normally can't access modern video platforms. Also, watching videos from other platforms is supported (but no searching).

> ⚠️ **Disclaimer**  
> Using this software to download or stream content from YouTube or other websites may violate their respective Terms of Service.  
> This project is intended for educational and personal use only. The maintainers are not responsible for any misuse and do not condone illegal or unauthorized use of the software.
---

## Features

- Works on Android version **1.0 to 15** (tested from Android 2.3.6 to 15)
- Compatible with J2ME phones (tested on **Nokia 6300** and **Nokia N85**)
- Server handles:
  - YouTube search
  - Playback from YouTube and other yt-dlp supported websites via HTTP progressive download
  - Thumbnail loading (Android only)
- Uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) for fetching content and [ffmpeg](https://ffmpeg.org/) for transcoding
- **No login or API key required**

---

## Getting Started

### Server Setup

```bash
git clone https://github.com/ndrnmnk/ourtube
cd ourtube
python3 -m venv venv
source venv/bin/activate
pip install -r youtube/requirements.txt
```
Make sure ffmpeg is installed and functional.

Edit `config.json` if you want to change server settings (default settings usually work fine).

To launch the server:

```bash
python3 launcher.py
```
You’ll see both your local and public IP printed on launch — those will be used in the client app.

### Client setup

Download the client from the [Releases](https://github.com/ndrnmnk/ourtube/releases) tab and transfer it to your device.

After installing it, enter the server IP. On Android, click `Settings` to see field for it.

Now, you should be able to watch videos, but it's recommended to play with other settings.

### Notes for J2ME Users

Most Java phones only support `h263` codec, which restricts available resolutions. Videos may not scale to full screen.

If your device supports `mpeg4` (e.g., Symbian-based phones), enable it to get better quality and proper scaling.

### Notes for Android Users

Some devices do support `h264` codec, which completely avoids conversion, significantly reducing wait times. 
You should try enabling it in the settings.

---

## How It Works

1. The server receives a search query or video URL.
2. It uses `yt-dlp` to fetch video content and metadata.
3. The video is piped directly into `ffmpeg`, which transcodes it to a format supported by low-end devices.
4. The transcoded file is temporarily saved to disk and served to the client via HTTP (progressive download).
5. The file is deleted after a short period.

---

## Footage

This is outdated, now it's faster:

![Demo](https://raw.githubusercontent.com/ndrnmnk/ndrnmnk/main/ourtube.gif)