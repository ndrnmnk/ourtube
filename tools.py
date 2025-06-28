import os
import re
import glob
import shutil
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
                f"+bestaudio[ext=m4a]/mp4"
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
    """
    Use yt-dlp to fetch top search results.

    :param query: str, the search phrase
    :param max_results: int, number of results to fetch (default is 10)
    :return: list of dict, each containing video title and URL
    """
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
            'video_url': entry.get('url')
        })
    return results

def generate_ffmpeg_cmd(path, scale_method, device_type, screen_w, screen_h, fps, streaming_requested):
    """Convert video using ffmpeg with specific arguments
    Device types:
        0: Old android phone
        1: New android phone; just scale video
        2: Java phone; a lot of adjustments
        3: Symbian phone; like old android but lower bitrates
        4: Windows Mobile PDA;
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
    else:  # New Android (mp4, h264 + aac)
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
    proc = subprocess.Popen(["ffmpeg", "-loglevel", "quiet", "-i", os.path.join(path, "result.mkv"), "-f", container_names[device_type], os.path.join(path, f"result.{file_ext}")])
    proc.communicate()
    os.remove(os.path.join(path, "result.mkv"))
    return file_ext

def prepare_thumbnail(url, idx, thumbnail_id):
    """Download the thumbnail using yt-dlp and convert it using ffmpeg"""
    # figure out a path first
    output_path = os.path.join("thumbnails", idx)
    if not os.path.exists(output_path):
        os.mkdir(output_path)
    output_path = os.path.join(output_path, thumbnail_id)
    if os.path.exists(output_path):
        shutil.rmtree(output_path)
    output_path = os.path.join(output_path, "img")

    try:
        subprocess.run(["yt-dlp", "--quiet", "--skip-download", "--write-thumbnail", "-o", output_path, url], check=True)

        convert_thumbnail(output_path)

        logging.info(f"Thumbnail downloaded to {output_path}")
    except yt_dlp.DownloadError as e:
        logging.error(f"An error occurred during downloading thumbnail: {e}")

def convert_thumbnail(path):
    """Converts video thumbnails to jpg"""
    try:
        # Find the file with the given base path and any extension
        files = glob.glob(path + ".*")
        if not files:
            logging.error(f"No file found with base path: {path}")
            return
        input_file = files[0]  # Since there are no conflicts, take the first match
        # Run ffmpeg command to resize and convert the image to jpg
        subprocess.run([ "ffmpeg", "-loglevel", "error", "-i", input_file, "-vf", "scale=96:54", path + ".jpg", "-y" ], check=True)

    except subprocess.CalledProcessError as e:
        logging.error(f"Error occurred while processing the image: {e}")

def get_video_length(url):
    with yt_dlp.YoutubeDL({}) as ydl:
        info_dict = ydl.extract_info(url, download=False)
        return info_dict.get("duration")

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

def seconds_to_readable(seconds):
    if seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes:02}:{secs:02}"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02}:{minutes:02}:{secs:02}"

def progress_bar_gen(progress_str):
    # Convert to integer
    try:
        p_int = int(progress_str.replace("Progress: ", "").replace("%", ""))
    except ValueError:
        p_int = 1

    # Progress bar is 10 characters long without []
    p_dec = p_int // 10
    return '[' + '#'*p_dec + '_'*(10-p_dec) + '] ' + str(p_int) + "%"

def render_template(filename, replacements):
    with open(os.path.join("web", filename)) as wap_file:
        template = wap_file.read()
    for key, value in replacements.items():
        template = template.replace(key, value)
    return template

def is_url(query):
    pattern = re.compile("^https?://\\S*\\.\\S+$")
    match = re.search(pattern, query)
    if match:
        return True
    else:
        return False

def render_error_settings_wml(template, request, swap_dict=None):
    if swap_dict is None:
        swap_dict = {}
    swap_dict["~0"] = request.args.get('url')
    swap_dict["~2"] =  request.args.get('i') or swap_dict["~2"]
    swap_dict["~3"] = request.args.get('l') or swap_dict["~3"]
    swap_dict["~4"] = request.args.get('dtype') or "2"
    swap_dict["~5"] = request.args.get('w') or "128"
    swap_dict["~6"] = request.args.get('h') or "96"
    swap_dict["~7"] = request.args.get('fps') or "12"
    swap_dict["~8"] = request.args.get('sm') or "1"
    swap_dict["~9"] = request.args.get('fp') or "1"
    print(swap_dict)
    res = render_template(template, swap_dict)
    return res


def approximate_bitrate(width, height, fps):
    compression_ratio = 25

    # Bitrate estimation
    raw_bitrate = width * height * fps  # pixels per second
    compressed_bitrate = raw_bitrate / compression_ratio  # bits per second

    bitrate_mbps = compressed_bitrate / 1_000
    print(bitrate_mbps)
    return str(round(bitrate_mbps, 2)) + "k"
