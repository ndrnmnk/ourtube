from flask import Blueprint, Response, request, send_file, url_for, redirect
from urllib.parse import quote
from utils.cleaner import Cleaner
from utils.config import Config
from utils import tools_web
from utils.arp import arp
from utils import tools_conv
import requests
import logging
import time
import uuid
import os

html_bp = Blueprint("html", __name__, url_prefix="/html")


@html_bp.route('/', methods=['GET'])
def serve_html_homepage():
    return send_file(os.path.join("..", "web", "Home.html"), mimetype="text/html")


@html_bp.route('/search-res', methods=['GET'])
def serve_html_search_res():
    query = request.args.get("q")
    isc = 1 if request.args.get("isc") == "1" else 0
    page = tools_web.validate_int_arg(request.args.to_dict(), "page")
    if not query:
        return Response("Missing query", status=400, mimetype="text/plain")

    sure = request.args.get("sure") == "1"
    if tools_web.is_url(query) and not sure:
        query = quote(query)
        return Response(tools_web.render_template("UrlAction.html", {"~1": query, "~2": uuid.uuid4()}),
                        mimetype="text/html")
    if sure:
        return url_for("html_convert", **request.args)

    # since searching requires UUID, generate one
    identifier = uuid.uuid4()
    results_json = requests.get(
        f"http://127.0.0.1:5001/api/search?i={identifier}&page={page}&th=0&isc={isc}&q={query}").json()

    results_markup = []
    redirect_page = "convert" if request.cookies.get("w") else "settings"
    for video in results_json:
        results_markup.append(
            f'<a href="/html/{redirect_page}?l={video["length"]}&i={identifier}&url={quote(video["video_url"])}">{video["title"]}</a>\n'
            f'<p>By {video["creator"]}</p>\n'
            f'<p>{tools_web.seconds_to_readable(video["length"])}</p>\n'
        )

    swap_dict = {"~1": "<hr>\n".join(results_markup),
                 "~2": f"/html/search-res?isc={isc}&page={max(0, page - 1)}&q={query}",
                 "~3": f"/html/search-res?isc={isc}&page={page + 1}&q={query}",
                 "~4": page
                 }

    res = tools_web.render_template("SearchResults.html", swap_dict)

    return Response(res, mimetype="text/html")


@html_bp.route('/settings', methods=['GET'])
def serve_html_video_settings():
    return Response(tools_web.render_settings_html_template("VideoSettings.html", request), mimetype="text/html")


@html_bp.route('/convert', methods=['GET'])
def html_convert():
    conv_args = request.args.to_dict() | request.cookies.to_dict()

    if not conv_args.get("i"):
        return Response("Missing identifier", status=403, mimetype="text/plain")
    identifier = conv_args["i"]
    swap_list = {}

    if identifier not in Config().conv_tasks:
        temp = tools_conv.handle_conversion(conv_args, arp(request.remote_addr))
        if "error" in temp:
            return Response(temp["error"], mimetype="text/plain")
        duration = temp["duration"]
        swap_list["4"] = f'<meta http-equiv="refresh" content="5;url=/html/convert?l={duration}&i={identifier}">'
    else:
        duration = conv_args["l"]

    proc = Config().conv_tasks[identifier]
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
            rtsp_url, http_url = tools_web.generate_links(request.host.split(':')[0], f"api/playback/{identifier}.{file_ext}")

            links = ""
            if file_ext != "mkv":
                links = links + f'<a href="{http_url}">Play (HTTP)</a><br/>'
            links = links + f'<a href="{rtsp_url}">Play (RTSP)</a>'

            swap_list["~3"] = links
        else:
            swap_list["~3"] = "<p>Msg: error occurred while converting</p>"

        swap_list["~4"] = ""
        Config().del_conv_task(identifier)
    else:
        swap_list["~4"] = '<meta http-equiv="refresh" content="5">'

    return Response(tools_web.render_template("ConvProgress.html", swap_list), mimetype="text/html")


@html_bp.route('/cookie-relay', methods=['GET'])
def cookie_relay():
    if request.args.get("url"):
        resp = redirect(url_for("html.html_convert", **request.args))  # crashes here
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
                resp.set_cookie(item[0], item[1], max_age=60 * 60 * 24 * 365)
        if error:
            return redirect("/html/settings?error=1")
    return resp


@html_bp.route('/cancel', methods=['GET'])
def html_cancel():
    if request.args.get("i"):
        requests.get(f"http://127.0.0.1:5001/api/cancel-conversion?i={request.args.get('i')}")
    return redirect("/html")