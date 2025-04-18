import os
import glob
import shutil
import logging
import subprocess
import yt_dlp
from config import config_instance


def search(query, identifier, max_results=10):
    """
    Use yt-dlp to fetch top search results.

    :param query: str, the search phrase
    :param identifier: str, used to save thumbnails
    :param max_results: int, number of results to fetch (default is 10)
    :return: list of dict, each containing video title and URL
    """
    if os.path.exists(os.path.join("youtube", "thumbnails", identifier)):
        shutil.rmtree(os.path.join("youtube", "thumbnails", identifier))
        logging.info(f"deleted old thumbnails for {identifier}")
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
        results.append({
            'title': entry.get('title'),
            'creator': entry.get('uploader'),
            'length': int(entry.get('duration')),
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
        fps (int): Target fps of a video.
    """
    try:
        video_path = os.path.join("youtube", "videos", identifier)

        # Remove temporary file if it exists
        if os.path.exists(video_path):
            shutil.rmtree(video_path)

        ydl_options = {'quiet': True}

        # yt-dlp video format filter for the worst quality meeting the requirements
        with yt_dlp.YoutubeDL(ydl_options) as ydl:
            info = ydl.extract_info(url, download=False)
            video_width = info.get('width', 480)
            video_height = info.get('height', 320)
            length = int(info.get('duration'))

            if video_height < video_width:
                orientation_landscape = True
                format_filter = f"worstvideo[ext=mp4][width>={width}]+bestaudio[ext=m4a]/mp4"
            else:
                orientation_landscape = False
                format_filter = f"worstvideo[ext=mp4][height>={height}]+bestaudio[ext=m4a]/mp4"

        ydl_options = {'quiet': True, 'outtmpl': os.path.join(video_path, "unprocessed.mp4"), 'format': format_filter}
        # run downloading with
        with yt_dlp.YoutubeDL(ydl_options) as ydl:
            ydl.download([url])

        if not orientation_landscape:
            width, height = height, width
        reformat_video(video_path, sm, dtype, width, height, fps, orientation_landscape)
        logging.info(f"Successfully downloaded video to {video_path}")
        return orientation_landscape, length
    except yt_dlp.DownloadError as e:
        logging.error(f"An error occurred while downloading the video: {e}")
        return "landscape", length


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
        ydl_options = {
            'quiet': True,
            'skip_download': True,
            'writethumbnail': True,
            'outtmpl': str(output_path) + ".unprocessed",
        }
        with yt_dlp.YoutubeDL(ydl_options) as ydl:
            ydl.download([url])

        convert_thumbnail(output_path)

        logging.info(f"Thumbnail downloaded to {output_path}")
    except yt_dlp.DownloadError as e:
        logging.error(f"An error occurred during downloading thumbnail: {e}")


def reformat_video(path, scale_method, device_type, screen_w, screen_h, fps, orientation_landscape):
    """Convert video using ffmpeg with specific arguments
    Device types:
        0: Old android phone; 3gp+aac, no rotation
        1: New android phone; just scale video, no rotation
        2: Java phone; 3gp+amr, rotate if needed
        3: Java phone; 3gp+aac, rotate if needed
        4: Windows Mobile PDA; mp4+aac
    Scale methods:
        0: Scale to screen resolution while KEEPING aspect ratio
        1: Scale and crop for perfect match
        2: Stretch to screen resolution while IGNORING aspect ratio
    """
    if device_type == 2:
        print("DEVICE TYPE 2")
        if screen_h >= 228 and screen_w >= 352:
            screen_w, screen_h = 352, 228
        elif screen_h >= 144 and screen_w >= 176:
            screen_w, screen_h = 176, 144
        else:
            screen_w, screen_h = 128, 96

    filters = []
    # Rotation check
    if device_type in (2, 3, 4):
        if (screen_w < screen_h) == orientation_landscape:
            filters.append("transpose=1")
    # Scaling logic
    if scale_method == 0:
        # filters.append(f"scale='min({screen_w},iw)':'min({screen_h},ih)':force_original_aspect_ratio=decrease")
        filters.append(
            f"scale='min({screen_w},iw)':"
            f"'min({screen_h},ih)':force_original_aspect_ratio=decrease,"
            f"pad=iw-mod(iw\\,4):ih-mod(ih\\,4):x=0:y=0"
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

    audio_bitrate = config_instance.get("audio_bitrate")
    if device_type == 0:  # Old Android (3gp + AAC)
        conv_args = ["-c:v", "mpeg4", "-c:a", "aac", "-f", "mp4"]
        file_ext = "mp4"
    elif device_type == 2:  # Java (3gp + AMR), mono 8kHz audio
        conv_args = ["-c:v", "h263", "-c:a", "libopencore_amrnb", "-ac", "1", "-ar", "8000", "-f", "3gp"]
        audio_bitrate = "12.2k"
        file_ext = "3gp"
    elif device_type == 3:  # Java (3gp + AAC)
        conv_args = ["-c:v", "mpeg4", "-c:a", "aac", "-f", "3gp"]
        file_ext = "3gp"
    elif device_type == 4:  # Windows Mobile
        conv_args = ["-c:v", "wmv2", "-c:a", "wmav2", "-f", "asf"]
        file_ext = "wmv"
    else:  # New Android (mp4)
        conv_args = []
        file_ext = "mp4"

    command = [
        "ffmpeg",
        "-i", os.path.join(path, "unprocessed.mp4"),
        "-preset", "fast",
        "-b:v", config_instance.get("video_bitrate"),
        "-b:a", audio_bitrate,
        "-r", fps,
        *conv_args, *scale_args,
        "-y", os.path.join(path, f"result.{file_ext}")
    ]

    subprocess.run(command, check=True)

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
        subprocess.run([
            "ffmpeg",
            "-i", input_file,
            "-vf", "scale=96:54",
            path + ".jpg",
            "-y"
        ], check=True)

    except subprocess.CalledProcessError as e:
        logging.error(f"Error occurred while processing the image: {e}")
