import requests
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

conv_tasks = {}

def generate_links(host, path):
    rtsp_link = f"rtsp://{host}:8554/{path}"
    http_link = f"http://{host}:5001/{path}"
    return rtsp_link, http_link

def validate_int_arg(arg_name):
    val = request.args.get(arg_name)
    try:
        return int(val)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid value for '{arg_name}': {val}")

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
            fps = int(request.args.get("fps"))
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

        conv_tasks[identifier] = tools.VideoProcessor(video_url, identifier, dtype, sm, width, height, fps, fp, duration)

        def generate_response():
            try:
                while conv_tasks[identifier].res is None:
                    yield conv_tasks[identifier].progress
                    if conv_tasks[identifier].new_msg:
                        conv_tasks[identifier].new_msg = False
                        yield conv_tasks[identifier].msg[-1]
                    time.sleep(1)

                file_ext = conv_tasks[identifier].res
                if file_ext == "err":
                    raise Exception("Failed to convert video")
                # When generator exits, last progress would be file extension
                rtsp_url, http_url = generate_links(request.host.split(':')[0], f"api/video/{identifier}.{file_ext}")
                Cleaner().add_content(
                    os.path.join("videos", identifier),
                    time.time() + duration * Config().get("video_lifetime_multiplier")
                )
                yield json.dumps({"http_url": http_url, "rtsp_url": rtsp_url, "fp": (file_ext == "mkv")}) + "\n"
                del conv_tasks[identifier]
                return
            except Exception as e:
                logging.error(e)
                yield json.dumps({"error": "Failed to convert video", "fp": False}) + "\n"
                return

        conv_tasks[identifier].start_conversion()
        return Response(stream_with_context(generate_response()), mimetype="text/plain")

    @app.route('/api/cancel-conversion', methods=['GET'])
    def cancel_conversion():
        identifier = request.args.get('i')
        if not identifier:
            return jsonify({"error": "identifier is required"}), 403
        conv_tasks[identifier].cancel()
        Cleaner().remove_content_at(os.path.join("videos", identifier))
        return jsonify({"status": "ok"}), 200

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

    @app.route('/api/convert_thumbnail', methods=['GET'])
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

    @app.route('/api/video/<identifier>.<ext>', methods=['GET'])
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

    @app.route('/wap', methods=['GET'])
    def serve_wap_homepage():
        return send_file(os.path.join("web", "Home.wml"), mimetype="text/vnd.wap.wml")

    @app.route('/wap/search-res', methods=['GET'])
    def serve_wap_search_res():
        query = request.args.get("q")
        if not query:
            return Response("Missing query", status=400, mimetype="text/plain")

        sure = request.args.get("sure") == 1
        if tools.is_url(query) and not sure:
            return Response(tools.render_template("UrlAction.wml", {"~1": query}), mimetype="text/vnd.wap.wml")

        # since searching requires UUID, generate one
        identifier = uuid.uuid4()
        results_json = requests.get(f"http://127.0.0.1:5001/api/search?i={identifier}&q={query}&th=0").json()

        results_markup = []
        for video in results_json:
            results_markup.append(
                '------<br/>\n'
                f'{video["title"]}<br/>\n'
                f'By {video["creator"]}<br/>\n'
                f'{tools.seconds_to_readable(video["length"])}<br/>\n'
                '<anchor>'
                'Play'
                '<go href="settings" method="get">'
                f'<postfield name="l" value="{video["length"]}"/>'
                f'<postfield name="url" value="{video["video_url"]}"/>'
                '</go>'
                '</anchor>'
            )

        res = tools.render_template("SearchResults.wml", {"~1": "\n".join(results_markup)})

        return Response(res, mimetype="text/vnd.wap.wml")

    @app.route('/wap/settings', methods=['GET'])
    def serve_wap_video_settings():
        url = request.args.get("url")
        if not url:
            return Response("Missing url", status=400, mimetype="text/plain")

        swap_dict = {}
        if not request.args.__contains__("l"):
            swap_dict["~3"] = tools.get_video_length(url)
        if not request.args.__contains__("i"):
            swap_dict["~2"] = str(uuid.uuid4())
        res = tools.render_error_settings_wml("VideoSettings.wml", request, swap_dict)

        return Response(res, mimetype="text/vnd.wap.wml")

    @app.route('/wap/convert', methods=['GET'])
    def wap_convert():
        identifier = request.args.get("i")
        duration = request.args.get("l")

        if not identifier:
            return Response("Missing identifier", status=403, mimetype="text/plain")
        elif not duration:
            return Response("Missing duration", status=400, mimetype="text/plain")

        if request.args.keys().__contains__('url'):
            client_arp = arp(request.remote_addr)
            video_url = request.args.get('url')
            try:
                dtype = validate_int_arg('dtype')
                width = validate_int_arg('w')
                height = validate_int_arg('h')
                fps = validate_int_arg("fps")
                sm = validate_int_arg('sm')
                fp = request.args.get("fp") == "1"
            except ValueError as e:
                return Response(tools.render_error_settings_wml("InvalidInput.wml", request, {"~1": str(e)}), mimetype="text/vnd.wap.wml")

            if width < height:
                width, height = height, width

            if self_arp or client_arp:
                video_url = "https://www.youtube.com/watch?v=XA8I5AG_7to"

            Cleaner().remove_content_at(os.path.join("videos", identifier))
            conv_tasks[identifier] = tools.VideoProcessor(video_url, identifier, dtype, sm, width, height, fps, fp, int(duration))
            conv_tasks[identifier].start_conversion()

        proc = conv_tasks[identifier]
        page_markup = [tools.progress_bar_gen(proc.progress) + "<br/>"]

        if proc.new_msg:
            proc.new_msg = False
            page_markup.append(proc.msg + "<br/>")

        if proc.res:
            Cleaner().add_content(os.path.join("videos", identifier), time.time() + int(duration) * Config().get("video_lifetime_multiplier"))
            if proc.res != "err":

                hostname = request.host.split(':')[0]

                rtsp_url, http_url = generate_links(hostname, f"/api/video/{identifier}.{proc.res}")

                page_markup.append(
                    '<anchor>\n'
                    'Play (RTSP)\n'
                    f'<go href="{rtsp_url}" method="get">\n'
                    '</go>\n'
                    '</anchor>\n'
                    '<br/>\n'
                    '<anchor>\n'
                    'Play (HTTP)\n'
                    f'<go href="{http_url}" method="get">\n'
                    '</go>\n'
                    '</anchor>\n'
                    '<br/>\n'
                    '<anchor>\n'
                    'Save (HTTP)\n'
                    f'<go href="{http_url}" method="get">\n'
                    '<postfield name="raw" value="1"/>\n'
                    '</go>\n'
                    '</anchor>'
                )
            else:
                page_markup.append("Couldn't convert video<br/>")

        res = tools.render_template("ConvProgress.wml", {"~1": identifier, "~2": "\n".join(page_markup), "~3": duration})

        return Response(res, mimetype="text/vnd.wap.wml")

    return app
