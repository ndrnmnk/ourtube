import os
import glob
import shutil
import logging
import subprocess
import yt_dlp
from config import config_instance


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
            leng = int(entry.get('duration'))
        except TypeError:
            leng = 0
        results.append({
            'title': entry.get('title'),
            'creator': entry.get('uploader'),
            'length': leng,
            'video_url': entry.get('url')
        })
    return results

def prepare_video(url, identifier, dtype, sm, width, height, fps):
    """Downloads the worst quality video that meets the specified width and height using yt-dlp and converts it further.

    Parameters:
        url (str): The URL of the video to download.
        identifier (str): A unique identifier for the video file.
        dtype(int): Device type; defines to which format convert the video.
        sm (int): Scaling method; Look at reformat_video for details.
        width (int): The minimum desired width of the video.
        height (int): The minimum desired height of the video.
        fps (str): Target fps of a video.
    """
    try:
        video_path = os.path.join("youtube", "videos", identifier)
        os.makedirs(video_path, exist_ok=True)

        format_filter = (
            f"bestvideo[ext=mp4][vcodec^=avc1]"
            f"[height>={min(height, width)}][width>={min(width, height)}]"
            f"[height<={max(height, width)}][width<={max(width, height)}]"
            f"+bestaudio[ext=m4a]/mp4"
        )

        ydl_cmd = ["yt-dlp", "--quiet", "-f", format_filter, "-o", "-", url]

        ffmpeg_cmd, file_ext = reformat_video(video_path, sm, dtype, width, height, fps)
        ydl_proc = subprocess.Popen(ydl_cmd, stdout=subprocess.PIPE)
        ffmpeg_proc = subprocess.Popen(ffmpeg_cmd, stdin=ydl_proc.stdout)
        ydl_proc.stdout.close()  # Allow yt-dlp to receive SIGPIPE if ffmpeg exits
        ffmpeg_proc.communicate()
        ydl_proc.wait()

        if ydl_proc.returncode != 0:
            logging.error(f"yt-dlp exited with code {ydl_proc.returncode}")
            return "err"
        if ffmpeg_proc.returncode != 0:
            logging.error(f"ffmpeg exited with code {ffmpeg_proc.returncode}")
            return "err"

        logging.info(f"Successfully downloaded video to {video_path}")
        return file_ext
    except Exception as e:
        logging.error(f"An error occurred while downloading the video: {e}")
        return "err"

def reformat_video(path, scale_method, device_type, screen_w, screen_h, fps):
    """Convert video using ffmpeg with specific arguments
    Device types:
        0: Old android phone
        1: New android phone; just scale video
        2: Java phone; 3gp+amr
        3: Symbian phone; 3gp+aac
        4: Windows Mobile PDA; mp4+aac
    Scale methods:
        0: Scale to screen resolution while KEEPING aspect ratio
        1: Scale and crop for perfect match
        2: Stretch to screen resolution while IGNORING aspect ratio
    """
    if device_type == 5 and scale_method > 2:
        command = [
            "ffmpeg", "-loglevel", "error",
            "-i", "pipe:0",
            "-c", "copy",
            "-y", os.path.join(path, "result.mp4")
        ]
        return command, "mp4"

    if device_type == 2:
        if screen_h >= 228 and screen_w >= 352:
            screen_w, screen_h = 352, 228
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

    if device_type == 0:  # Old Android (3gp + AAC)
        conv_args = ["-c:v", "mpeg4", "-c:a", "aac", "-f", "mp4"]
        video_bitrate = config_instance.get("android_vb")
        audio_bitrate = config_instance.get("android_ab")
        file_ext = "mp4"
    elif device_type == 2:  # Java (3gp + AMR), mono 8kHz audio
        conv_args = ["-c:v", "h263", "-profile:v", "0", "-c:a", "libopencore_amrnb", "-ac", "1",
                     "-ar", "8000", "-f", "3gp", "-metadata", "major_brand=3gp5", "-movflags", "+faststart"]
        video_bitrate = config_instance.get("j2me_vb")
        audio_bitrate = config_instance.get("j2me_ab")
        file_ext = "3gp"
    elif device_type == 3:  # Symbian (3gp + AAC)
        conv_args = ["-c:v", "mpeg4", "-ac", "1", "-c:a", "aac", "-f", "3gp"]
        video_bitrate = config_instance.get("symb_vb")
        audio_bitrate = config_instance.get("symb_ab")
        file_ext = "3gp"
    elif device_type == 4:  # Windows Mobile
        conv_args = ["-c:v", "wmv2", "-c:a", "wmav2", "-f", "asf"]
        video_bitrate = config_instance.get("wm_vb")
        audio_bitrate = config_instance.get("wm_ab")
        file_ext = "wmv"
    else:  # New Android (mp4)
        conv_args = []
        video_bitrate = config_instance.get("android_vb")
        audio_bitrate = config_instance.get("android_ab")
        file_ext = "mp4"

    command = [
        "ffmpeg", "-loglevel", "error",
        "-i", "pipe:0",
        "-preset", "fast",
        "-b:v", video_bitrate,
        "-b:a", audio_bitrate,
        "-r", fps,
        *conv_args, *scale_args,
        "-y", os.path.join(path, f"result.{file_ext}")
    ]
    return command, file_ext

def prepare_thumbnail(url, idx, thumbnail_id):
    """Download the thumbnail using yt-dlp and convert it using ffmpeg"""
    # figure out a path first
    output_path = os.path.join("youtube", "thumbnails", idx)
    if not os.path.exists(output_path):
        os.mkdir(output_path)
    output_path = os.path.join(output_path, thumbnail_id)
    if os.path.exists(output_path):
        shutil.rmtree(output_path)
    output_path = os.path.join(output_path, "img")

    try:
        subprocess.run(["yt-dlp", "--quiet", "--skip-download", "--write-thumbnail", "-o", output_path+".unprocessed", url], check=True)

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
