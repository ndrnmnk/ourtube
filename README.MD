# OurTube

**OurTube** is a lightweight media app designed for **Android devices**, **J2ME feature phones** and everything else that can access the web.
It enables users to search, stream, and watch videos from YouTube, SoundCloud and other platforms on legacy hardware that normally can't access them.

> ⚠️ **Disclaimer**  
> Using this software to download or stream content may violate their respective Terms of Service.  
> This project is intended for educational and personal use only. The maintainers are not responsible for any misuse and do not condone illegal or unauthorized use of the software.
---

## Features

- Works on Android version **1.0 to 15** (tested from Android 2.3.6 to 15)
- Compatible with J2ME phones (tested on **Nokia 6300** and **Nokia N85**)
- WAP & HTML websites for other devices
- Server handles:
  - YouTube and SoundCloud search
  - Playback from yt-dlp supported websites via HTTP progressive download and RTSP
  - Thumbnail loading (Android only)
- **No login or API key required**

It uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) for fetching content and [FFmpeg](https://ffmpeg.org/) for transcoding.

---

## Getting Started

### Server Setup

If your OS is macOS or Linux-based, try running this in terminal:
```bash
git clone https://github.com/ndrnmnk/ourtube;
cd ourtube;
setup.sh
```
If you are on Windows or the command has failed, check out `MANUAL-INSTALLATION.md`.  
Make sure FFmpeg is installed, functional and available in you system `PATH`.

---

Edit `config.yaml` and `DeadRTSP/config.yaml` if you want to change server settings (default ones usually work fine).  
You’ll see both your local and public IP printed on launch — those will be used in the client app.

### Client setup

Download the client from the [Releases](https://github.com/ndrnmnk/ourtube/releases) tab and transfer it to your device.  
After installing it, enter the server IP. On Android, click `Settings` to see field for it.

Now, you should be able to watch videos and listen to music, but it's recommended to play with other settings.

---

### Notes for J2ME Users

Most Java phones only support `h263` codec, which restricts available resolutions. Videos may not scale to full screen.  
If your device supports `mpeg4` (e.g., Symbian-based phones), enable it to get better quality and proper scaling.

### Notes for Android Users

Some devices do support `h264` codec, which completely avoids conversion, significantly reducing wait times. 
You should try enabling it in the settings.

RTSP can significantly reduce wait times, but it works only with external players and sacrifices seeking.

### Notes for website users

Website can be accessed at `http://{your_ip}:5001/html` and WAP version at `http://{your_ip}:5001/wap`.  
It's heavily recommended to use HTML version if possible for better experience.

Cookies in HTML version aren't necessary - they just save settings, so you don't have to re-enter these every time.

### Known bugs

- "Load more" button introduces duplicate results (unfixable)
- Random errors with some specific URLs

---

## Footage

Outdated, now it's a bit faster

![Demo](https://raw.githubusercontent.com/ndrnmnk/ndrnmnk/main/ourtube.gif)