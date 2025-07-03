import os
import re
import threading

import yt_dlp
import logging
import subprocess
from collections import deque
from config import config_instance

class VideoProcessor:
    def __init__(self, url, identifier, dtype, sm, width, height, fps, allow_streaming, duration):
        """
        Downloads the worst quality video that meets the specified width and height using yt-dlp and converts it further.

        Parameters:
            url (str): The URL of the video to download.
            identifier (str): A unique identifier for the video file.
            dtype (int): Device type; defines to which format convert the video.
            sm (int): Scaling method; Look at reformat_video for details.
            width (int): The minimum desired width of the video.
            height (int): The minimum desired height of the video.
            fps (int): Target fps of a video.
            allow_streaming (bool): Allow streaming with this video file while it's not fully converted.
            duration (int): Target video duration. Used for calculating progress.
        """

        self.video_url = url
        self.identifier = identifier
        self.sm = sm
        self.dtype = dtype
        self.width = width
        self.height = height
        self.fps = fps
        self.allow_streaming = allow_streaming
        self.duration = duration

        self.progress = ""
        self.res = None
        self.new_msg = False
        self.msg = []
        self.processes = []

    def start_conversion(self):
        threading.Thread(target = self._convert).start()

    def _convert(self):
        try:
            video_path = os.path.join("videos", self.identifier)
            os.makedirs(video_path, exist_ok=True)

            format_filter = (
                f"bestvideo[ext=mp4][vcodec^=avc1]"
                f"[height>={min(self.height, self.width)}][width>={min(self.width, self.height)}]"
                f"[height<={max(self.height, self.width)}][width<={max(self.width, self.height)}]"
                f"+bestaudio/mp4/bestaudio"
            )

            ydl_cmd = ["yt-dlp", "--quiet", "-f", format_filter, "-o", "-", self.video_url]
            ffmpeg_cmd, file_ext = generate_ffmpeg_cmd(video_path, self.sm, self.dtype, self.width, self.height, self.fps, self.allow_streaming)

            self.processes.append(subprocess.Popen(ydl_cmd, stdout=subprocess.PIPE))
            self.processes.append(subprocess.Popen(ffmpeg_cmd, stdin=self.processes[0].stdout, stderr=subprocess.PIPE,
                                           universal_newlines=True, bufsize=1))

            self.processes[0].stdout.close()  # Let yt-dlp handle SIGPIPE if ffmpeg exits

            speed_deque = deque(maxlen=3)
            speed_re = re.compile(r"speed=\s*([\d.]+)x")
            progress_re = re.compile(r"time=\s*(\S+)")
            streaming_checked = False
            have_to_recontainer = False
            i = 0

            for line in self.processes[1].stderr:
                print(line)

                if len(speed_deque) < 3:
                    # Extract speed
                    speed_match = speed_re.search(line)
                    if speed_match:
                        speed = float(speed_match.group(1))
                        if i > 0:
                            speed_deque.append(speed)
                        i += 1

                # After collecting enough speed samples, decide on RTSP
                if not streaming_checked and len(speed_deque) == 3 and self.allow_streaming:
                    streaming_checked = True
                    avg_speed = sum(speed_deque) / 3
                    if avg_speed > 1.5:
                        self.res = "mkv"
                        return
                    else:
                        have_to_recontainer = True
                        self.msg.append("Msg: Conversion too slow; Switching to regular mode\n")
                        self.new_msg = True

                # Yield progress info
                prog_match = progress_re.search(line)
                if prog_match:
                    progress = ffmpeg_time_to_seconds(prog_match.group(1))
                    self.progress = f"Progress: {int(progress * 100 / self.duration)}%\n"

            # Wait for processes to finish
            self.processes[1].communicate()
            self.processes[0].wait()

            if self.processes[0].returncode != 0 or self.processes[1].returncode != 0:
                logging.error(f"One of the processes exited with non-zero code")
                self.res = "err"
                return

            if have_to_recontainer:
                recontainer_video(video_path, self.dtype)

            logging.info(f"Successfully downloaded video to {video_path}")
            self.res = file_ext
            return

        except Exception as e:
            logging.error(f"An error occurred while downloading the video: {e}")
            self.res = "err"
            return

    def cancel(self):
        for proc in self.processes:
            proc.terminate()


def search(query, max_results=10):
    ydl_options = {
        'quiet': True,  # Suppress yt-dlp output
        'skip_download': True,  # Don't download videos
        'extract_flat': True,  # Only extract metadata
    }

    with yt_dlp.YoutubeDL(ydl_options) as ydl:
        search_url = f"ytsearch{max_results}:{query}"
        info = ydl.extract_info(search_url, download=False)

    results = []
    for idx, entry in enumerate(info.get('entries', [])):
        try:
            duration = int(entry.get('duration'))
        except TypeError:
            duration = 0
        results.append({
            'title': entry.get('title'),
            'creator': entry.get('uploader'),
            'length': duration,
            'video_url': entry.get('url'),
            'thumbnail_url': generate_yt_thumbnail_url(entry.get('url'))
        })
    return results

def search_sc(query, max_results=10):
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,  # Don't download, just list
        'force_generic_extractor': False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        results = ydl.extract_info(f"scsearch{max_results}:{query}", download=False)
        entries = results.get('entries', [])

    res = []
    for entry in entries:
        try:
            duration = int(entry.get('duration'))
        except TypeError:
            duration = 0
        try:
            th_url = entry["thumbnails"][4]["url"]
        except:
            th_url = entry.get('url')
        res.append({
            'title': entry.get('title'),
            'creator': entry.get('uploader'),
            'length': duration,
            'video_url': entry.get('url'),
            'thumbnail_url': th_url
        })

    return res

def generate_ffmpeg_cmd(path, scale_method, device_type, screen_w, screen_h, fps, streaming_requested):
    """Convert video using ffmpeg with specific arguments
    Device types:
        0: Old android phone
        1: Generic new device; just scale video
        2: Java phone; a lot of adjustments
        3: Symbian phone; like old android but lower bitrates
        4: Windows Mobile PDA;
        5: Windows 95-era PC;
    Scale methods:
        0: Scale to screen resolution while KEEPING aspect ratio
        1: Scale and crop for perfect match
        2: Stretch to screen resolution while IGNORING aspect ratio
    Streaming:
        If user made a request with RTSP or MKV support, container will be replaced with MKV.
        If this isn't fast enough in RTSP mode, video will be moved to a different container on first play request
    """

    if (device_type == 1 or device_type > 4) and scale_method > 2:
        file_ext = "mp4"
        command = [
            "ffmpeg", "-i", "pipe:0",
            "-max_muxing_queue_size", "9999",
            "-c:v", "copy", "-c:a", "aac",
            "-b:a", config_instance.get("android_ab"),
            "-f", "mp4"
        ]
        if streaming_requested:
            command[-1] = "matroska"
            file_ext = "mkv"
        command.extend(["-y", os.path.join(path, f"result.{file_ext}")])
        return command, file_ext

    if device_type == 2:
        if screen_h >= 576 and screen_w >= 704:
            screen_w, screen_h = 704, 576
        elif screen_h >= 288 and screen_w >= 352:
            screen_w, screen_h = 352, 288
        elif screen_h >= 144 and screen_w >= 176:
            screen_w, screen_h = 176, 144
        else:
            screen_w, screen_h = 128, 96

    filters = []
    # Scaling logic
    if scale_method == 0:
        if scale_method == 0:
            filters.append(
                f"scale='min({screen_w},iw)':"
                f"'min({screen_h},ih)':force_original_aspect_ratio=decrease,"
                f"pad=ceil(iw/4)*4:ceil(ih/4)*4"
            )
    elif scale_method == 1:
        filters.append((
            f"scale='if(gt(a,{screen_w}/{screen_h}),{screen_h}*a,{screen_w})':"
            f"'if(gt(a,{screen_w}/{screen_h}),{screen_h},{screen_w}/a)',"
            f"crop={screen_w}:{screen_h}"
        ))
    elif scale_method == 2:
        filters.append(f"scale={screen_w}:{screen_h}")
    # compose scale_args
    scale_args = ["-vf", ",".join(filters)] if filters else []

    if device_type == 0:  # Old Android (3gp, mpeg4 + aac)
        conv_args = ["-c:v", "mpeg4", "-c:a", "aac", "-movflags", "+faststart", "-f", "3gp"]
        video_bitrate = config_instance.get("android_vb")
        audio_bitrate = config_instance.get("android_ab")
        file_ext = "3gp"
    elif device_type == 2:  # Java (3gp, h263 + AMR)
        conv_args = ["-c:v", "h263", "-profile:v", "0", "-c:a", "libopencore_amrnb", "-ac", "1",
                     "-ar", "8000", "-metadata", "major_brand=3gp5", "-movflags", "+faststart", "-f", "3gp"]
        video_bitrate = config_instance.get("j2me_vb")
        audio_bitrate = config_instance.get("j2me_ab")
        file_ext = "3gp"
    elif device_type == 3:  # Symbian (3gp, mpeg4 + AAC)
        conv_args = ["-c:v", "mpeg4", "-ac", "1", "-c:a", "aac", "-movflags", "+faststart", "-f", "3gp"]
        video_bitrate = config_instance.get("symb_vb")
        audio_bitrate = config_instance.get("symb_ab")
        file_ext = "3gp"
    elif device_type == 4:  # Windows Mobile (asf, wmv2 + wmav2)
        conv_args = ["-c:v", "wmv2", "-c:a", "wmav2", "-movflags", "+faststart", "-f", "asf"]
        video_bitrate = config_instance.get("wm_vb")
        audio_bitrate = config_instance.get("wm_ab")
        file_ext = "wmv"
    elif device_type == 5:  # Windows 95-era PCs
        conv_args = ["-c:v", "mpeg1video", "-maxrate", "300k", "-bufsize", "300k", "-bf", "0", "-g", "12",
                     "-pix_fmt", "yuv420p", "-c:a", "mp2", "-ar", "22050", "-f", "mpeg"]
        video_bitrate = "300k"
        audio_bitrate = "96k"
        file_ext = "mpg"
    else:  # Assuming generic new
        conv_args = ["-movflags", "+faststart", "-f", "mp4"]
        video_bitrate = approximate_bitrate(screen_w, screen_h, fps)
        audio_bitrate = config_instance.get("android_ab")
        file_ext = "mp4"

    if streaming_requested:
        conv_args[-1] = "matroska"
        file_ext = "mkv"

    command = [
        "ffmpeg",
        "-i", "pipe:0",
        "-preset", "fast",
        "-max_muxing_queue_size", "9999",
        "-b:v", video_bitrate,
        "-b:a", audio_bitrate,
        "-r", str(fps),
        *conv_args, *scale_args,
        "-y", os.path.join(path, f"result.{file_ext}")
    ]
    return command, file_ext

def recontainer_video(path, device_type):
    if device_type > 4:
        device_type = 1
    file_exts = ["3gp", "mp4", "3gp", "3gp", "wmv"]
    container_names = ["3gp", "mp4", "3gp", "3gp", "asf"]
    file_ext = file_exts[device_type]
    proc = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", os.path.join(path, "result.mkv"), "-f", container_names[device_type], os.path.join(path, f"result.{file_ext}")])
    proc.communicate()
    os.remove(os.path.join(path, "result.mkv"))
    return file_ext

def prepare_thumbnail(thumbnail_url, idx, thumbnail_id):
    output_path = os.path.join("thumbnails", idx, thumbnail_id)
    os.makedirs(output_path)
    output_path = os.path.join(output_path, "img.jpg")

    try:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-i", thumbnail_url, "-vf", "scale=-1:54", output_path, "-y" ], check=True)

        logging.info(f"Thumbnail downloaded to {output_path}")
    except Exception as e:
        logging.error(f"An error occurred during downloading thumbnail: {e}")

def generate_yt_thumbnail_url(url):
    if 'v=' in url:
        video_id = url.split('v=')[1].split('&')[0]
    elif "/shorts/" in url:
        video_id = url.split('shorts/')[1].split('&')[0]
    else:
        return ""

    # Construct the fastest thumbnail URL (smallest size)
    return f"https://img.youtube.com/vi/{video_id}/default.jpg"

def get_video_length(url):
    try:
        result = subprocess.run(['yt-dlp', '--skip-download', '--print', '"%duration"', url],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        duration_seconds = int(result.stdout.strip())
    except:
        duration_seconds = 600
    return duration_seconds

def ffmpeg_time_to_seconds(time_str):
    if time_str == "N/A":
        return 0.0

    # Split off the milliseconds
    if '.' in time_str:
        time_part, ms = time_str.rsplit('.', 1)
        ms = float('0.' + ms)
    else:
        time_part = time_str
        ms = 0.0

    # Split the main time into components
    parts = list(map(int, time_part.split(':')))

    hours, minutes, seconds = parts
    total_seconds = (
        hours * 3600 +
        minutes * 60 +
        seconds +
        ms
    )
    return total_seconds

def approximate_bitrate(width, height, fps):
    bpp = 0.15  # bits per pixel

    # Bitrate estimation
    raw_bitrate = width * height * fps  # pixels per second
    compressed_bitrate = raw_bitrate * bpp  # bits per second

    bitrate_kbps = compressed_bitrate / 1_000
    return str(round(bitrate_kbps, 2)) + "k"
