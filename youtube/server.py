from flask import Flask, Response, request, send_file, jsonify
from urllib.parse import unquote
from config import config_instance
from youtube import tools
import logging
import time
import uuid
import os

def is_valid_uuid(s):
    try:
        u = uuid.UUID(s)
        return u.version == 4
    except ValueError:
        return False

def generate(file_path, start, end):
    with open(file_path, 'rb') as f:
        f.seek(start)
        remaining = end - start + 1
        chunk_size = 8192
        while remaining > 0:
            chunk = f.read(min(chunk_size, remaining))
            if not chunk:
                break
            yield chunk
            remaining -= len(chunk)

def create_server(cleaner):
    app = Flask(__name__)

    @app.route('/convert', methods=['GET'])
    def convert_video():
        youtube_url = request.args.get('url')
        identifier = request.args.get('i')
        try:
            dtype = int(request.args.get('dtype'))
            width = int(request.args.get('w'))
            height = int(request.args.get('h'))
            fps = request.args.get("fps")
            sm = int(request.args.get('sm'))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid numeric parameter(s)."}), 400

        required = {"url": youtube_url, "identifier": identifier}
        for field, value in required.items():
            if not value:
                return jsonify({"error": f"{field} is required", "video_url": None}), 400 if field == "url" else 403
        if not is_valid_uuid(identifier):
            return jsonify({"error": "Not a valid uuid.", "video_url": None}), 403

        try:
            cleaner.remove_content_at(os.path.join("youtube", "videos", identifier))
            orientation, length = tools.prepare_video(youtube_url, identifier, dtype, sm, width, height, fps)
            cleaner.add_content(os.path.join("youtube", "videos", identifier), time.time() + length * config_instance.get("video_lifetime_multiplier"))
            return jsonify({"video_url": os.path.join("video", identifier), "orientation": orientation}), 200
        except Exception as e:
            logging.error(f"Failed to convert video: {e}")
            return jsonify({"error": "Failed to convert video", "video_url": None}), 500

    @app.route('/search', methods=['GET'])
    def search():
        query = unquote(request.args.get('q'))
        identifier = request.args.get('i')
        th = request.args.get('th')

        required = {"query": query, "identifier": identifier}
        for field, value in required.items():
            if not value:
                return jsonify({"error": f"{field} is required"}), 400 if field == "query" else 403
        if not is_valid_uuid(identifier):
            return jsonify({"error": "Not a valid uuid."}), 403

        res = tools.search(query, identifier)
        if th:
            cleaner.remove_content_at(os.path.join("youtube", "thumbnails", identifier))
            cleaner.add_content(os.path.join("youtube", "thumbnails", identifier), time.time() + config_instance.get("thumbnail_lifetime"))
        return res

    @app.route('/convert_thumbnail')
    def serve_image():
        youtube_url = request.args.get('url')
        identifier = request.args.get('i')
        thid = request.args.get('thid')  # thid stands for thumbnail id

        required = {"url": youtube_url, "identifier": identifier}
        for field, value in required.items():
            if not value:
                return jsonify({"error": f"{field} is required"}), 400 if field == "url" else 403
        if not is_valid_uuid(identifier):
            return jsonify({"error": "Not a valid uuid."}), 403

        image_path = os.path.join("thumbnails", identifier, thid, "img.jpg")
        try:
            tools.prepare_thumbnail(youtube_url, identifier, thid)
            return send_file(image_path, mimetype='image/jpg')
        except FileNotFoundError:
            # since this only happens when thumbnail couldn't be converted
            logging.warning(f"Thumbnail not found: {image_path}")
            return jsonify({"error": "Thumbnail wasn't converted"}), 404

    @app.route('/video/<identifier>.<ext>')
    def stream_video(identifier, ext):
        file_path = os.path.join("youtube", "videos", identifier, f"result.{ext}")
        mt = "video/" + ext
        try:
            video_file = open(file_path, 'rb')
        except FileNotFoundError:
            logging.warning(f"Video not found: {file_path}")
            return jsonify({"error": "Video not found"}), 404

        # Handle byte-range requests for streaming
        range_header = request.headers.get('Range', None)
        if not range_header:
            # Serve the entire file if no Range header is provided
            return Response(video_file.read(), mimetype=mt)

        # Parse the Range header
        size = os.path.getsize(file_path)
        byte_range = range_header.strip().split('=')[-1]
        start, end = byte_range.split('-')

        start = int(start)
        end = int(end) if end else size - 1

        video_file.seek(start)

        # Build the response
        response = Response(generate(file_path, start, end), 206, mimetype=mt)
        response.headers.add("Content-Range", f"bytes {start}-{end}/{size}")
        response.headers.add("Accept-Ranges", "bytes")
        response.headers.add("Content-Length", str(end - start + 1))
        return response

    return app
