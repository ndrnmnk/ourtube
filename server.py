from flask import Flask, Response, request, send_file, jsonify, stream_with_context
from urllib.parse import unquote
import flask.json as json
import logging
import time
import uuid
import os
from config import Config
from cleaner import Cleaner
from arp import arp
import tools

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

def create_server(self_arp):
    app = Flask(__name__)

    @app.route('/api/convert', methods=['GET'])
    def convert_video():
        client_arp = arp(request.remote_addr)
        video_url = request.args.get('url')
        identifier = request.args.get('i')
        try:
            dtype = int(request.args.get('dtype'))
            width = int(request.args.get('w'))
            height = int(request.args.get('h'))
            fps = request.args.get("fps")
            sm = int(request.args.get('sm'))
            fp = request.args.get("fp") == "1"
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid numeric parameter(s).", "video_url": None, "fp": False}), 400

        if width < height:
            width, height = height, width
            
        duration = int(request.args.get('len'))
        if not duration:
            duration = tools.get_video_length(video_url)

        if self_arp or client_arp:
            video_url = "https://www.youtube.com/watch?v=XA8I5AG_7to"

        required = {"url": video_url, "identifier": identifier}
        for field, value in required.items():
            if not value:
                return jsonify({"error": f"{field} is required", "video_url": None, "fp": False}), 400 if field == "url" else 403
        if not is_valid_uuid(identifier):
            return jsonify({"error": "Not a valid uuid.", "video_url": None, "fp": False}), 403

        Cleaner().remove_content_at(os.path.join("videos", identifier))

        def generate_response():
            try:
                for progress in tools.prepare_video(video_url, identifier, dtype, sm, width, height, fps, fp, duration):
                    if len(progress) != 3:
                        yield progress

                # When generator exits, last progress would be file extension
                video_url_processed = f"api/video/{identifier}.{progress}"
                Cleaner().add_content(
                    os.path.join("videos", identifier),
                    time.time() + duration * Config().get("video_lifetime_multiplier")
                )
                yield json.dumps({"video_url": video_url_processed, "fp": (progress == "mkv")}) + "\n"
            except Exception as e:
                logging.error(e)
                yield json.dumps({"error": "Failed to convert video", "fp": False}) + "\n"

        return Response(stream_with_context(generate_response()), mimetype="text/plain")

    @app.route('/api/search', methods=['GET'])
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
            Cleaner().remove_content_at(os.path.join("thumbnails", identifier))
            Cleaner().add_content(os.path.join("thumbnails", identifier), time.time() + Config().get("thumbnail_lifetime"))
        return res

    @app.route('/api/convert_thumbnail')
    def serve_image():
        pic_url = request.args.get('url')
        identifier = request.args.get('i')
        thid = request.args.get('thid')  # thid stands for thumbnail id

        required = {"url": pic_url, "identifier": identifier}
        for field, value in required.items():
            if not value:
                return jsonify({"error": f"{field} is required"}), 400 if field == "url" else 403
        if not is_valid_uuid(identifier):
            return jsonify({"error": "Not a valid uuid."}), 403

        image_path = os.path.join("thumbnails", identifier, thid, "img.jpg")
        try:
            tools.prepare_thumbnail(pic_url, identifier, thid)
            return send_file(image_path, mimetype='image/jpg')
        except FileNotFoundError:
            # since this only happens when thumbnail couldn't be converted
            logging.warning(f"Thumbnail not found: {image_path}")
            return jsonify({"error": "Thumbnail wasn't converted"}), 404

    @app.route('/api/video/<identifier>.<ext>')
    def stream_video(identifier, ext):
        raw = (request.args.get('raw') == "1")
        file_path = os.path.join("videos", identifier, f"result.{ext}")

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
