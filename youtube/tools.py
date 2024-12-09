import os
import shutil
import glob
import subprocess
import yt_dlp
import asyncio
from pathlib import Path


async def search_youtube(phrase, identifier, th, max_results=10):
    """
    Use yt-dlp to fetch top YouTube search results asynchronously.

    :param phrase: str, the search phrase
    :param identifier: str, used to save thumbnails
    :param max_results: int, number of results to fetch (default is 10)
    :return: list of dict, each containing video title and URL
    """
    try:
        shutil.rmtree(f"youtube/thumbnails/{identifier}")
    except FileNotFoundError:
        pass
    ydl_opts = {
        'quiet': True,  # Suppress yt-dlp output
        'skip_download': True,  # Don't download videos
        'extract_flat': True,  # Only extract metadata, no actual videos
    }

    async def fetch_thumbnail(url, path):
        await get_thumbnail(url, path)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        search_url = f"ytsearch{max_results}:{phrase}"
        info = ydl.extract_info(search_url, download=False)

    results = []
    tasks = []
    for idx, entry in enumerate(info.get('entries', [])):
        thumbnail_path = f"{identifier}/{idx}"
        if th:
            tasks.append(fetch_thumbnail(entry.get('url'), thumbnail_path))
        results.append({
            'title': entry.get('title'),
            'creator': entry.get('uploader', 'Unknown'),  # Placeholder for now
            'length': entry.get('duration'),
            'thumbnail': f'/thumbnail/{thumbnail_path}',
            'video_url': entry.get('url')
        })

    # Run all thumbnail fetch tasks concurrently
    await asyncio.gather(*tasks)
    return results


def download_video(url, identifier, width, height):
    """
    Downloads the worst quality video that meets the specified width and height
    using yt-dlp and saves it temporarily for further processing.

    Parameters:
        url (str): The URL of the video to download.
        identifier (str): A unique identifier for the video file.
        width (int): The minimum desired width of the video.
        height (int): The minimum desired height of the video.
    """
    try:
        video_path = f"youtube/videos/{identifier}"
        temp_video_path = f"{video_path}t.mp4"

        # Remove temporary file if it exists
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)

        # yt-dlp video format filter for the worst quality meeting the requirements
        with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
            info = ydl.extract_info(url, download=False)
            video_width = info.get('width', 0)
            video_height = info.get('height', 0)

        if video_width < video_height:
            to_return = "portrait"
            format_filter = f"worstvideo[ext=mp4][height>={height}]+bestaudio[ext=m4a]/mp4"
        else:
            to_return = "landscape"
            format_filter = f"worstvideo[ext=mp4][width>={width}]+bestaudio[ext=m4a]/mp4"
        # format_filter = f"mp4"
        video_cmd = [
            "yt-dlp",
            "-o", temp_video_path,  # Specify output file path
            "-f", format_filter,
            url
        ]

        # Run the yt-dlp command
        subprocess.run(video_cmd, check=True)
        reformat_video(video_path)
        print(f"Video downloaded to {temp_video_path}")
        return to_return
    except subprocess.CalledProcessError as e:
        print(f"An error occurred while downloading the video: {e}")
        return 0


async def get_thumbnail(url, path):
    """
    Download the thumbnail asynchronously using yt-dlp and convert it using ffmpeg
    """
    try:
        output_path = Path("youtube/thumbnails") / path
        output_path.parent.mkdir(parents=True, exist_ok=True)

        thumbnail_cmd = [
            "yt-dlp",
            "--quiet",
            "--write-thumbnail",  # Download thumbnail
            "-o", str(output_path)+".unprocessed",  # Specify output file path
            "--skip-download",  # Skip downloading the video
            url
        ]
        process = await asyncio.create_subprocess_exec(*thumbnail_cmd)
        await process.communicate()  # Wait for the process to finish
        convert_thumbnail(output_path)

        if process.returncode == 0:
            print(f"Thumbnail downloaded to {output_path}")
        else:
            print(f"Failed to download thumbnail for {url}")
    except Exception as e:
        print(f"An error occurred: {e}")


def reformat_video(path):
    command = [
        "ffmpeg",
        "-i", path+"t.mp4",
        "-c:v", "mpeg4",
        "-preset", "fast",
        "-b:v", "1200k",
        "-c:a", "aac",
        "-b:a", "128k",
        "-y",
        path+".mp4"
    ]
    subprocess.run(command)


def convert_thumbnail(path):
    try:
        # Find the file with the given base path and any extension
        files = glob.glob(f"{path}.*")
        if not files:
            print(f"No file found with base path: {path}")
            return None

        input_file = files[0]  # Since there are no conflicts, take the first match
        output_file = f"{path}.jpg"

        # Run ffmpeg command to resize and convert the image to jpg
        subprocess.run([
            "ffmpeg",
            "-i", input_file,
            "-vf", "scale=96:54",
            output_file,
            "-y"
        ], check=True)

        return output_file
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while processing the image: {e}")
        return None
