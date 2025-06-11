from flask import Flask, Response, request, send_file, jsonify, stream_with_context
from urllib.parse import unquote
from config import config_instance
from youtube import tools
from concurrent.futures import ThreadPoolExecutor
import flask.json as json
from arp import arp
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

def create_server(cleaner, arp_true):
    app = Flask(__name__)

    @app.route('/convert', methods=['GET'])
    def convert_video():
        arp2 = arp(request.remote_addr)
        youtube_url = request.args.get('url')
        identifier = request.args.get('i')
        try:
            dtype = int(request.args.get('dtype'))
            width = int(request.args.get('w'))
            height = int(request.args.get('h'))
            fps = request.args.get("fps")
            sm = int(request.args.get('sm'))
            length = int(request.args.get('len'))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid numeric parameter(s)."}), 400

        if arp_true or arp2:
            youtube_url = "https://www.youtube.com/watch?v=XA8I5AG_7to"

        required = {"url": youtube_url, "identifier": identifier}
        for field, value in required.items():
            if not value:
                return jsonify({"error": f"{field} is required", "video_url": None}), 400 if field == "url" else 403
        if not is_valid_uuid(identifier):
            return jsonify({"error": "Not a valid uuid.", "video_url": None}), 403

        cleaner.remove_content_at(os.path.join("youtube", "videos", identifier))

        def generate_response():
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(tools.prepare_video, youtube_url, identifier, dtype, sm, width, height, fps)

                # While the task is running
                while not future.done():
                    yield " \n\n"

                # Get the result when done
                try:
                    file_ext = future.result()
                    if file_ext == "err":
                        yield json.dumps({"error": "Failed to convert video"}) + "\n"
                        return
                    res = json.dumps({"video_url": os.path.join("video", identifier + '.' + file_ext)}) + "\n"
                    cleaner.add_content(os.path.join("youtube", "videos", identifier), time.time() + length * config_instance.get("video_lifetime_multiplier"))
                    yield res
                    return
                except Exception as e:
                    logging.error(e)
                    yield json.dumps({"error": "Failed to convert video"}) + "\n"

        return Response(stream_with_context(generate_response()), mimetype="application/json")

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

        res = tools.search(query)
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
        raw = (request.args.get('raw') == "1")
        file_path = os.path.join("youtube", "videos", identifier, f"result.{ext}")

        mime_types = {
            "mp4": "video/mp4",
            "3gp": "video/3gpp",
            "wmv": "video/x-ms-wmv"
        }
        mt = mime_types.get(ext.lower(), "application/octet-stream")

        # Handle byte-range requests for streaming
        range_header = request.headers.get('Range', None)
        if not range_header or raw:
            response = send_file(os.path.join("videos", identifier, f"result.{ext}"), mimetype=mt, as_attachment=False, conditional=True)
            response.headers.pop('Transfer-Encoding', None)  # Ensuring no Transfer-Encoding is applied
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
            return jsonify({"error": "Invalid range"}), 416  # HTTP 416 Range Not Satisfiable

        # Open the video file and generate a streaming response
        try:
            response = Response(generate(file_path, start, end), status=206, mimetype=mt)
            response.headers.add("Content-Range", f"bytes {start}-{end}/{size}")
            response.headers.add("Accept-Ranges", "bytes")
            # response.headers.add("Content-Length", str(end - start + 1))
            response.headers.add("Connection", "keep-alive")
            return response
        except FileNotFoundError:
            logging.warning(f"Video not found: {file_path}")
            return jsonify({"error": "Video not found"}), 404

    return app
