from flask import Blueprint, Response, request, send_file, jsonify, stream_with_context, json
from utils import tools_web, tools_conv
from utils.cleaner import Cleaner
from utils.config import Config
from utils.arp import arp
import logging
import time
import os

api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route('/convert', methods=['GET'])
def convert():
    client_arp = arp(request.remote_addr)
    temp = tools_conv.handle_conversion(request.args.to_dict(), client_arp)

    identifier = temp["identifier"]
    duration = temp["duration"]

    task = Config().conv_tasks[identifier]

    def generate_response():
        try:
            while task.res is None:
                yield task.progress
                if task.new_msg:
                    task.new_msg = False
                    yield task.msg[-1]
                time.sleep(1)

            # When generator exits, last progress would be file extension
            file_ext = task.res
            if file_ext == "err":
                raise Exception("Failed to convert")
            rtsp_url, http_url = tools_web.generate_links(request.host.split(':')[0], f"api/playback/{identifier}.{file_ext}")
            Cleaner().add_content(
                os.path.join("cache", "content", identifier),
                time.time() + duration * Config().get("video_lifetime_multiplier")
            )

            fp = file_ext == "mkv"
            if not fp:
                rtsp_url = http_url
            yield json.dumps({"http_url": http_url, "rtsp_url": rtsp_url, "fp": fp}) + "\n"
            Config().del_conv_task(identifier)
            return
        except Exception as e:
            logging.error(e)
            yield json.dumps({"error": "Failed to convert", "fp": False}) + "\n"
            return

    return Response(stream_with_context(generate_response()), mimetype="text/plain")


@api_bp.route('/cancel-conversion', methods=['GET'])
def cancel_conversion():
    identifier = request.args.get('i')
    if not identifier:
        return jsonify({"error": "identifier is required"}), 403
    Config().conv_tasks[identifier].cancel()
    Cleaner().remove_content_at(os.path.join("cache", "content", identifier))
    return jsonify({"status": "ok"}), 200


@api_bp.route('/search', methods=['GET'])
def search():
    query = request.args.get('q')
    identifier = request.args.get('i')
    th = request.args.get('th')
    try:
        max_res = int(request.args.get('maxres'))
    except (TypeError, ValueError):
        max_res = 10
    page = tools_web.validate_int_arg(request.args.to_dict(), "page")
    isc = request.args.get('isc') == "1"  # isc stands for "is SoundCloud"
    if th:
        Cleaner().remove_content_at(os.path.join("cache", "thumbnails", identifier))
        Cleaner().add_content(os.path.join("cache", "thumbnails", identifier), time.time() + Config().get("thumbnail_lifetime"))

    if not query:
        return jsonify({"error": "Query is required"}), 400
    if not identifier or not tools_web.is_valid_uuid(identifier):
        return jsonify({"error": "Not a valid uuid."}), 403

    if not isc:
        res = tools_conv.search_yt(query, page, max_res)
    else:
        res = tools_conv.search_sc(query, page, max_res)

    return res


@api_bp.route('/convert_thumbnail', methods=['GET'])
def serve_image():
    pic_url = request.args.get('url')
    identifier = request.args.get('i')
    thid = request.args.get('thid')  # thid stands for thumbnail id

    if not pic_url:
        return jsonify({"error": "Thumbnail URL is required"}), 400
    if not tools_web.is_valid_uuid(identifier):
        return jsonify({"error": "Not a valid uuid."}), 403

    image_path = os.path.join("..", "cache", "thumbnails", identifier, thid, "img.jpg")
    try:
        tools_conv.prepare_thumbnail(pic_url, identifier, thid)
        return send_file(image_path, mimetype='image/jpg')
    except FileNotFoundError:
        logging.warning(f"Thumbnail not found: {image_path}")
        return jsonify({"error": "Thumbnail wasn't converted"}), 404


@api_bp.route('/playback/<identifier>.<ext>', methods=['GET'])
def stream(identifier, ext):
    raw = (request.args.get('raw') == "1")
    file_path = os.path.join("cache", "content", identifier, f"result.{ext}")

    mime_types = {
        "mp4": "video/mp4",
        "3gp": "video/3gpp",
        "wmv": "video/x-ms-wmv",
        "avi": "video/x-msvideo",
        "mov": "video/quicktime",
        "mkv": "video/x-matroska",
        "mpg": "video/mpeg",
        "wav": "audio/x-wav",
        "mp3": "audio/mpeg",
        "m4a": "audio/mp4",
        "aiff": "audio/x-aiff"
    }
    mt = mime_types.get(ext.lower(), "application/octet-stream")

    # Handle byte-range requests for streaming
    range_header = request.headers.get('Range', None)
    if not range_header or raw:
        file_path = os.path.join("..", file_path)
        response = send_file(file_path, mimetype=mt, as_attachment=True)
        response.headers.pop('Transfer-Encoding', None)
        response.headers["Connection"] = "close"
        return response

    # Parse the Range header if present
    try:
        size = os.path.getsize(file_path)
        range_parts = range_header.strip().split('=')[-1]
        start, end = range_parts.split('-')

        start = int(start)
        end = int(end) if end else size - 1

        if start >= size:
            raise ValueError("Start range is beyond file size.")
        if end >= size:
            end = size - 1
    except (ValueError, IndexError):
        logging.error("Invalid Range header.")
        return jsonify({"error": "Invalid range"}), 416

    # Open the file and generate a streaming response
    try:
        response = Response(generate(file_path, start, end), status=206, mimetype=mt)
        response.headers.add("Content-Range", f"bytes {start}-{end}/{size}")
        response.headers.add("Accept-Ranges", "bytes")
        response.headers.add("Content-Length", str(end - start + 1))
        response.headers.add("Connection", "keep-alive")
        return response
    except FileNotFoundError:
        logging.warning(f"Content not found not found: {file_path}")
        return jsonify({"error": "Content not found"}), 404


def generate(file_path, start, end):
    """ Generator to yield chunks of the video file for streaming. """
    with open(file_path, 'rb') as f:
        f.seek(start)
        remaining = end - start + 1
        chunk_size = 8192  # 16KB chunks for streaming
        while remaining > 0:
            chunk = f.read(min(chunk_size, remaining))
            if not chunk:
                break
            yield chunk
            remaining -= len(chunk)
