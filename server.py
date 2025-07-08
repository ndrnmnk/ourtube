import requests
from flask import Flask, Response, request, send_file, jsonify, stream_with_context, redirect, url_for
import flask.json as json
import logging
import time
import uuid
import os
from config import Config
from cleaner import Cleaner
from arp import arp
import tools
import tools_web

conv_tasks = {}

def handle_conversion(request_args, client_arp, self_arp):
    identifier = request_args.get("i")
    video_url = request_args.get("url")

    if not identifier or not video_url:
        return {"error": "Missing parameters"}

    try:
        dtype = tools_web.validate_int_arg(request_args, 'dtype')
        width = tools_web.validate_int_arg(request_args, 'w')
        height = tools_web.validate_int_arg(request_args, 'h')
        fps = tools_web.validate_int_arg(request_args, 'fps')
        sm = tools_web.validate_int_arg(request_args, 'sm')
        ap = tools_web.validate_int_arg(request_args, 'ap')
        duration = int(request_args.get("l", 0))
        mono = request_args.get("mono") == "1"
        fp = request_args.get("fp") == "1"
    except ValueError as e:
        # logging.error(e)
        return {"error": str(e)}

    if not duration:
        duration = tools.get_video_length(video_url)

    if width < height:
        width, height = height, width

    if self_arp or client_arp:
        video_url = "https://www.youtube.com/watch?v=XA8I5AG_7to"

    Cleaner().remove_content_at(os.path.join("videos", identifier))
    conv_tasks[identifier] = tools.VideoProcessor(video_url, identifier, dtype, ap, mono, sm, width, height, fps, fp, duration)
    conv_tasks[identifier].start_conversion()

    return {"identifier": identifier, "duration": duration}


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
        temp = handle_conversion(request.args.to_dict(), client_arp, self_arp)

        identifier = temp["identifier"]
        duration = temp["duration"]

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
                rtsp_url, http_url = tools_web.generate_links(request.host.split(':')[0], f"api/video/{identifier}.{file_ext}")
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
        query = request.args.get('q')
        identifier = request.args.get('i')
        th = request.args.get('th')
        try:
            max_res = int(request.args.get('maxres'))
        except:
            max_res = 10
        page = tools_web.validate_int_arg(request.args.to_dict(), "page")
        isc = request.args.get('isc') == "1"  # isc stands for "is SoundCloud"
        if th:
            Cleaner().remove_content_at(os.path.join("thumbnails", identifier))
            Cleaner().add_content(os.path.join("thumbnails", identifier), time.time() + Config().get("thumbnail_lifetime"))

        required = {"query": query, "identifier": identifier}
        for field, value in required.items():
            if not value:
                return jsonify({"error": f"{field} is required"}), 400 if field == "query" else 403
        if not tools_web.is_valid_uuid(identifier):
            return jsonify({"error": "Not a valid uuid."}), 403

        if not isc:
            res = tools.search(query, page, max_res)
        else:
            res = tools.search_sc(query, page, max_res)
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
        if not tools_web.is_valid_uuid(identifier):
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
            "wmv": "video/x-ms-wmv",
            "mpg": "video/mpeg",
            "wav": "audio/x-wav",
            "mp3": "audio/mpeg"
        }
        mt = mime_types.get(ext.lower(), "application/octet-stream")

        # Handle byte-range requests for streaming
        range_header = request.headers.get('Range', None)
        if not range_header or raw:
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
            return jsonify({"error": "Invalid range"}), 416  # HTTP 416 Range Not Satisfiable

        # Open the video file and generate a streaming response
        try:
            response = Response(generate(file_path, start, end), status=206, mimetype=mt)
            response.headers.add("Content-Range", f"bytes {start}-{end}/{size}")
            response.headers.add("Accept-Ranges", "bytes")
            response.headers.add("Content-Length", str(end - start + 1))
            response.headers.add("Connection", "keep-alive")
            return response
        except FileNotFoundError:
            logging.warning(f"Video not found: {file_path}")
            return jsonify({"error": "Video not found"}), 404

    @app.route('/wap', methods=['GET'])
    def serve_wap_homepage():
        if request.args.get("i"):
            requests.get(f"http://127.0.0.1:5001/api/cancel-conversion?i={request.args.get('i')}")
        return send_file(os.path.join("web", "Home.wml"), mimetype="text/vnd.wap.wml")

    @app.route('/wap/search-res', methods=['GET'])
    def serve_wap_search_res():
        query = request.args.get("q")
        page = tools_web.validate_int_arg(request.args.to_dict(), "page")
        isc = 1 if request.args.get("isc") == "1" else 0
        if not query:
            return Response("Missing query", status=400, mimetype="text/plain")

        sure = request.args.get("sure") == "1"
        if tools_web.is_url(query) and not sure:
            return Response(tools_web.render_template("UrlAction.wml", {"~1": query}), mimetype="text/vnd.wap.wml")

        # since searching requires UUID, generate one
        identifier = uuid.uuid4()
        results_json = requests.get(f"http://127.0.0.1:5001/api/search?i={identifier}&page={page}&th=0&maxres=5&isc={isc}&q={query}").json()

        results_markup = []
        for video in results_json:
            results_markup.append(
                f'<a href="settings?l={video["length"]}&amp;url={video["video_url"]}">'
                f'{video["title"]}'
                '</a><br/>'
                f'By {video["creator"]}<br/>'
                f'{tools_web.seconds_to_readable(video["length"])}<br/>'
            )


        swap_dict = {"~1": "---<br/>".join(results_markup), "~6": str(page), "~4": query, "~2": str(isc), "~3": str(max(0, page-1)), "~5": str(page+1)}
        res = tools_web.render_template("SearchResults.wml", swap_dict)

        return Response(res, mimetype="text/vnd.wap.wml")

    @app.route('/wap/settings', methods=['GET'])
    def serve_wap_video_settings():
        url = request.args.get("url")
        if not url:
            return Response("Missing url", status=400, mimetype="text/plain")

        swap_dict = {}
        if not request.args.get("l"):
            swap_dict["~3"] = tools.get_video_length(url)
        if not request.args.get("i"):
            swap_dict["~2"] = str(uuid.uuid4())
        res = tools_web.render_error_settings_wml("VideoSettings.wml", request, swap_dict)

        return Response(res, mimetype="text/vnd.wap.wml")

    @app.route('/wap/convert', methods=['GET'])
    def wap_convert():
        identifier = request.args.get("i")
        duration = request.args.get("l")

        if not identifier:
            return Response("Missing identifier", status=403, mimetype="text/plain")
        elif not duration:
            return Response("Missing duration", status=400, mimetype="text/plain")

        if request.args.get("url"):
            res = handle_conversion(request.args.to_dict(), arp(request.remote_addr), self_arp)
            if "error" in res:
                return Response(tools_web.render_error_settings_wml("InvalidInput.wml", request, {"~1": res["error"]}), mimetype="text/vnd.wap.wml")

        proc = conv_tasks[identifier]
        page_markup = [tools_web.progress_bar_gen(proc.progress) + "<br/>"]

        cancel_anchor = (
            '<anchor>\n'
            'Cancel\n'
            f'<go href="/wap?i={identifier}" method="get">\n'
            '</go>\n'
            '</anchor>\n'
            '<br/>\n'
        )

        page_markup.append(cancel_anchor)

        if proc.new_msg:
            proc.new_msg = False
            page_markup.append(proc.msg + "<br/>")

        if proc.res:
            Cleaner().add_content(os.path.join("videos", identifier), time.time() + int(duration) * Config().get("video_lifetime_multiplier"))
            if proc.res != "err":

                hostname = request.host.split(':')[0]

                rtsp_url, http_url = tools_web.generate_links(hostname, f"/api/video/{identifier}.{proc.res}")

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

        res = tools_web.render_template("ConvProgress.wml", {"~1": identifier, "~2": "\n".join(page_markup), "~3": duration})

        return Response(res, mimetype="text/vnd.wap.wml")

    @app.route('/html', methods=['GET'])
    def serve_html_homepage():
        return send_file(os.path.join("web", "Home.html"), mimetype="text/html")

    @app.route('/html/search-res', methods=['GET'])
    def serve_html_search_res():
        query = request.args.get("q")
        isc = 1 if request.args.get("isc") == "1" else 0
        page = tools_web.validate_int_arg(request.args.to_dict(), "page")
        if not query:
            return Response("Missing query", status=400, mimetype="text/plain")

        sure = request.args.get("sure") == "1"
        if tools_web.is_url(query) and not sure:
            return Response(tools_web.render_template("UrlAction.html", {"~1": query, "~2": str(uuid.uuid4())}), mimetype="text/html")
        if sure:
            return url_for("html_convert", **request.args)

        # since searching requires UUID, generate one
        identifier = uuid.uuid4()
        results_json = requests.get(f"http://127.0.0.1:5001/api/search?i={identifier}&page={page}&th=0&isc={isc}&q={query}").json()

        results_markup = []
        redirect_page = "convert" if request.cookies.get("w") else "settings"
        for video in results_json:
            results_markup.append(
                f'<a href="/html/{redirect_page}?l={video["length"]}&i={identifier}&url={video["video_url"]}">{video["title"]}</a>\n'
                f'<p>By {video["creator"]}</p>\n'
                f'<p>{tools_web.seconds_to_readable(video["length"])}</p>\n'
            )

        swap_dict = {"~1": "<hr>\n".join(results_markup),
                     "~2": f"/html/search-res?isc={isc}&page={max(0, page - 1)}&q={query}",
                     "~3": f"/html/search-res?isc={isc}&page={page + 1}&q={query}",
                     "~4": str(page)}

        res = tools_web.render_template("SearchResults.html", swap_dict)

        return Response(res, mimetype="text/html")

    @app.route('/html/settings', methods=['GET'])
    def serve_html_video_settings():
        return Response(tools_web.render_settings_html_template("VideoSettings.html", request), mimetype="text/html")

    @app.route('/html/convert', methods=['GET'])
    def html_convert():
        conv_args = request.args.to_dict() | request.cookies.to_dict()
        if not conv_args.get("i"):
            return Response("Missing identifier", status=403, mimetype="text/plain")
        identifier = conv_args["i"]
        swap_list = {}

        if identifier not in conv_tasks:
            temp = handle_conversion(conv_args, arp(request.remote_addr), self_arp)
            if "error" in temp:
                return Response(temp["error"], mimetype="text/plain")
            duration = temp["duration"]
            swap_list["4"] = f'<meta http-equiv="refresh" content="5;url=/html/convert?l={duration}&i={identifier}">'
        else:
            duration = conv_args["l"]


        proc = conv_tasks[identifier]
        progress = proc.progress
        progress_bar = tools_web.progress_bar_gen(progress)
        progress = progress.replace("Progress: ", "").replace("%", "")
        swap_list["~1"] = progress_bar
        swap_list["~2"] = progress

        swap_list["~3"] = f'<a href="/html/cancel?i={identifier}">Cancel</a>'
        if proc.new_msg:
            swap_list["~3"] = "<p>" + proc.msg + "</p>"

        if proc.res:
            file_ext = proc.res
            Cleaner().add_content(os.path.join("videos", identifier),
                                  time.time() + int(duration) * Config().get("video_lifetime_multiplier"))
            if file_ext != "err":
                rtsp_url, http_url = tools_web.generate_links(request.host.split(':')[0], f"api/video/{identifier}.{file_ext}")
                if proc.allow_streaming:
                    links = ""
                else:
                    links = f'<a href="{rtsp_url}">Watch (RTSP)</a><br/>'
                links = links + f'<a href="{http_url}">Watch (HTTP)</a>'
                swap_list["~3"] = links
            else:
                swap_list["~3"] = "<p>Msg: error occurred while converting video</p>"

            swap_list["~4"] = ""
        else:
            swap_list["~4"] = '<meta http-equiv="refresh" content="5">'

        return Response(tools_web.render_template("ConvProgress.html", swap_list), mimetype="text/html")

    @app.route('/html/cookie-relay', methods=['GET'])
    def cookie_relay():
        if request.args.get("url"):
            resp = redirect(url_for("html_convert", **request.args))
        else:
            resp = redirect("/html")
        if request.args.get("save-cookies") == "1":
            resp.set_cookie("fp", "0", max_age=60 * 60 * 24 * 365)
            resp.set_cookie("mono", "0", max_age=60 * 60 * 24 * 365)
            error = False
            for item in request.args.items():
                if item[0] not in ("save-cookies", "url", "l", "i"):
                    try:
                        if item[0] in ("w", "h", "fps"):
                            if int(item[1]) <= 0:
                                error = True
                    except Exception as e:
                        logging.info(f"User entered invalid parameter: {e}")
                        error = True
                    resp.set_cookie(item[0], item[1], max_age=60*60*24*365)
            if error:
                return redirect("/html/settings?error=1")
        return resp

    @app.route('/html/cancel', methods=['GET'])
    def html_cancel():
        if request.args.get("i"):
            requests.get(f"http://127.0.0.1:5001/api/cancel-conversion?i={request.args.get('i')}")
        return redirect("/html")

    @app.route('/favicon.ico', methods=['GET'])
    def send_icon():
        return send_file(os.path.join("web", "favicon.ico"), mimetype="image/x-icon")

    return app
