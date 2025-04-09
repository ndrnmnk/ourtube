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
            'length': entry.get('duration'),
            'video_url': entry.get('url')
        })
    return results


def prepare_video(url, identifier, sm, width, height, nc):
    """Downloads the worst quality video that meets the specified width and height using yt-dlp and converts it further.

    Parameters:
        url (str): The URL of the video to download.
        identifier (str): A unique identifier for the video file.
        sm (int): Scaling method; Look at reformat_video for details.
        width (int): The minimum desired width of the video.
        height (int): The minimum desired height of the video.
        nc(bool): No convertion; disables convertion for devices that support h264 codec.
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
        reformat_video(video_path, sm, width, height, nc)
        logging.info(f"Successfully downloaded video to {video_path}")
        return orientation_landscape
    except yt_dlp.DownloadError as e:
        logging.error(f"An error occurred while downloading the video: {e}")
        return "landscape"


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


def reformat_video(path, scale_method, screen_w, screen_h, nc):
    """Convert video using ffmpeg with specific arguments"""
    if nc:
        command = ["mv", os.path.join(path, "unprocessed.mp4"), os.path.join(path, "result.mp4")]
    else:
        command = [
            "ffmpeg",
            "-i", os.path.join(path, "unprocessed.mp4"),
            "-c:v", "mpeg4",
            "-preset", "fast",
            "-b:v", config_instance.get("video_bitrate"),
            "-c:a", "aac",
            "-b:a", config_instance.get("audio_bitrate")
        ]
        if scale_method == 0:  # Scale to screen resolution while keeping aspect ratio
            args = ["-vf", f"scale='min({screen_w},iw)':'min({screen_h},ih)':force_original_aspect_ratio=decrease"]
        elif scale_method == 1:  # Scale and crop to exactly match screen resolution
            args = ["-vf", (
                    f"scale='if(gt(a,{screen_w}/{screen_h}),{screen_h}*a,{screen_w})':"
                    f"'if(gt(a,{screen_w}/{screen_h}),{screen_h},{screen_w}/a)',"
                    f"crop={screen_w}:{screen_h}"
                )]
        elif scale_method == 2:  # Stretch to screen resolution (ignore aspect ratio)
            args = ["-vf", f"scale={screen_w}:{screen_h}"]
        else:  # Convert without scaling
            args = []
        command.extend(args)
        command.extend(["-y", os.path.join(path, "result.mp4")])
    print(command)
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
