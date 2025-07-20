import os
import re
import json
import yt_dlp
import logging
import threading
import subprocess
from collections import deque

from utils import tools_web
from utils.cleaner import Cleaner
from utils.config import config_instance, Config


def handle_conversion(request_args, client_arp):
    identifier = request_args.get("i")
    video_url = request_args.get("url")

    if not identifier or not video_url:
        return {"error": "Missing parameters"}

    try:
        dtype = tools_web.validate_int_arg(request_args, 'dtype')
        width = tools_web.validate_int_arg(request_args, 'w')
        height = tools_web.validate_int_arg(request_args, 'h')
        fps = tools_web.validate_int_arg(request_args, 'fps')
        sm = tools_web.validate_int_arg(request_args, 'sm')
        ap = tools_web.validate_int_arg(request_args, 'ap')
        fp = tools_web.validate_int_arg(request_args, 'fp')
        duration = int(request_args.get("l", 0))
        mono = request_args.get("mono") == "1"
    except ValueError as e:
        # logging.error(e)
        return {"error": str(e)}

    if not duration:
        duration = get_video_length(video_url)

    if width < height:
        width, height = height, width

    if client_arp or Config().check_arp():
        video_url = "https://www.youtube.com/watch?v=XA8I5AG_7to"

    Cleaner().remove_content_at(os.path.join("cache", "content", identifier))
    Config().add_conv_task(
        identifier,
        VideoProcessor(video_url, identifier, dtype, ap, mono, sm, width, height, fps, fp, duration)
    )
    Config().conv_tasks[identifier].start_conversion()

    return {"identifier": identifier, "duration": duration}

def search_yt(query, page=0, max_results=10):
    start_index = max_results*page
    end_index = start_index + max_results

    ydl_options = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': True,
    }

    with yt_dlp.YoutubeDL(ydl_options) as ydl:
        result = ydl.extract_info(f"ytsearch{end_index}:{query}", download=False)
        entries = result['entries'][start_index:end_index]

    results = []
    for idx, entry in enumerate(entries):
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

def search_sc(query, page=0, max_results=10):
    start_index = max_results*page
    end_index = start_index + max_results

    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'force_generic_extractor': False,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        results = ydl.extract_info(f"scsearch{end_index}:{query}", download=False)
        entries = results['entries'][start_index:end_index]

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

def generate_ffmpeg_cmd_video(path, scale_method, device_type, screen_w, screen_h, fps, streaming_requested, mono_audio):
    """Convert video using ffmpeg with specific arguments
    Device types: check in config.yaml
    Scale methods:
        0: Scale to screen resolution while KEEPING aspect ratio
        1: Scale and crop for perfect match
        2: Stretch to screen resolution while IGNORING aspect ratio
        Others: Do nothing
    Streaming:
        If user made a request with RTSP or MKV support, container will be replaced with MKV.
        If this isn't fast enough in RTSP mode, video will be moved to a different container after conversion
    """

    if (device_type == 1 or device_type > 4) and scale_method > 2:
        file_ext = "mp4"
        command = [
            "ffmpeg", "-i", "pipe:0",
            "-max_muxing_queue_size", "9999",
            "-c:v", "copy", "-c:a", "aac",
            "-b:a", config_instance.get("video_conv_commands")[device_type][2],
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

    if device_type > 11 or device_type < 0:
        device_type = 1

    t = config_instance.get("video_conv_commands")[device_type]
    conv_args = t[0]
    video_bitrate = t[1]
    audio_bitrate = t[2]
    file_ext = t[3]

    if device_type in (2, 5, 11):
        mono_audio = True

    if video_bitrate == "0k":
        video_bitrate = approximate_bitrate(screen_w, screen_h, fps)

    if streaming_requested:
        conv_args[-1] = "matroska"
        file_ext = "mkv"

    if mono_audio:
        conv_args.extend(["-ac", "1"])

    command = [
        "ffmpeg", "-y",
        "-i", "pipe:0",
        "-preset", "fast",
        "-max_muxing_queue_size", "9999",
        "-b:v", video_bitrate,
        "-b:a", audio_bitrate,
        "-r", str(fps),
        *conv_args, *scale_args,
        os.path.join(path, f"result.{file_ext}")
    ]
    return command, file_ext

def generate_ffmpeg_cmd_audio(path, device_type, audio_profile, mono, streaming):
    t = 0

    if device_type in (2, 3):
        if audio_profile == 2:
            t = 1
            mono = True
        elif audio_profile == 1:
            t = 2
    elif device_type == 5:
        if audio_profile == 2:
            t = 3
            mono = True
        elif audio_profile == 1:
            t = 4
    elif device_type == 8:
        t = 5
    elif device_type == 9:
        t = 6
    elif device_type == 10:
        t = 3
        mono = True

    conv_args, file_ext = config_instance.get("audio_conv_commands")[t]
    if streaming:
        conv_args[-1] = "matroska"
        file_ext = "mkv"
    if mono:
        conv_args.extend(["-ac", "1"])

    return ["ffmpeg", "-y", "-i", "pipe:0", *conv_args, os.path.join(path, f"result.{file_ext}")], file_ext

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
    output_path = os.path.join("cache", "thumbnails", idx, thumbnail_id)
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


class VideoProcessor:
    def __init__(self, url, identifier, dtype, audio_profile, mono_audio, sm, width, height, fps, allow_streaming, duration):
        """
        Downloads the worst quality video that meets the specified width and height using yt-dlp and converts it further.

        Parameters:
            url (str): The URL of the video to download.
            identifier (str): A unique identifier for the video file.
            dtype (int): Device type; defines to which format convert the video.
            audio_profile (int): defines what audio format to use for certain device types.
            mono_audio (bool): If to use mono audio.
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
        self.audio_profile = audio_profile
        self.mono_audio = mono_audio

        self.progress = ""
        self.res = None
        self.new_msg = False
        self.msg = []
        self.processes = []

    def start_conversion(self):
        threading.Thread(target = self._convert).start()

    def _convert(self):
        try:
            video_path = os.path.join("cache", "content", self.identifier)
            os.makedirs(video_path, exist_ok=True)

            format_filter = (
                f"bestvideo[ext=mp4][vcodec^=avc1]"
                f"[height>={min(self.height, self.width)}][width>={min(self.width, self.height)}]"
                f"[height<={max(self.height, self.width)}][width<={max(self.width, self.height)}]"
                f"+bestaudio/mp4/bestaudio"
            )

            result = subprocess.run(["yt-dlp", "-f", format_filter, "--print-json", "--simulate", self.video_url], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            info = json.loads(result.stdout)

            requested_formats = info.get("requested_formats")
            if requested_formats:
                # video + audio selected
                has_video = any(f.get("vcodec") != "none" for f in requested_formats)
                has_audio = any(f.get("acodec") != "none" for f in requested_formats)
            else:
                # single format selected (could be audio only)
                has_video = info.get("vcodec") != "none"
                has_audio = info.get("acodec") != "none"

            if has_audio and not has_video:
                self.allow_streaming = self.allow_streaming == 1
                ffmpeg_cmd, file_ext = generate_ffmpeg_cmd_audio(video_path, self.dtype, self.audio_profile, self.mono_audio, self.allow_streaming)
            else:
                ffmpeg_cmd, file_ext = generate_ffmpeg_cmd_video(video_path, self.sm, self.dtype, self.width, self.height, self.fps, self.allow_streaming, self.mono_audio)

            ydl_cmd = ["yt-dlp", "--quiet", "-f", format_filter, "-o", "-", self.video_url]

            self.processes.append(subprocess.Popen(ydl_cmd, stdout=subprocess.PIPE))
            self.processes.append(subprocess.Popen(ffmpeg_cmd, stdin=self.processes[0].stdout, stderr=subprocess.PIPE, universal_newlines=True, bufsize=1))

            self.processes[0].stdout.close()  # Let yt-dlp handle SIGPIPE if ffmpeg exits

            speed_deque = deque(maxlen=3)
            speed_re = re.compile(r"speed=\s*([\d.]+)x")
            progress_re = re.compile(r"time=\s*(\S+)")
            streaming_checked = False
            have_to_recontainer = False
            i = 0

            for line in self.processes[1].stderr:
                # print(line)

                # measure speed for streaming
                if len(speed_deque) < 3:
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

                # Get progress info for progress bars
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
