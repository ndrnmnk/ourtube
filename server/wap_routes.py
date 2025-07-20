from flask import Blueprint, Response, request, send_file
from urllib.parse import quote
from utils.cleaner import Cleaner
from utils.config import Config
from utils.arp import arp
from utils import tools_web, tools_conv
import requests
import time
import uuid
import os

wap_bp = Blueprint("wap", __name__, url_prefix="/wap")

@wap_bp.route('/', methods=['GET'])
def serve_wap_homepage():
    if request.args.get("i"):
        requests.get(f"http://127.0.0.1:5001/api/cancel-conversion?i={request.args.get('i')}")
    return send_file(os.path.join("..", "web", "Home.wml"), mimetype="text/vnd.wap.wml")

@wap_bp.route('/search-res', methods=['GET'])
def serve_wap_search_res():
    query = request.args.get("q")
    try:
        page = tools_web.validate_int_arg(request.args.to_dict(), "page")
    except ValueError:
        page = 0
    isc = 1 if request.args.get("isc") == "1" else 0
    if not query:
        return Response("Missing query", status=400, mimetype="text/plain")

    sure = request.args.get("sure") == "1"
    if tools_web.is_url(query) and not sure:
        query = quote(query)
        return Response(tools_web.render_template("UrlAction.wml", {"~1": query}), mimetype="text/vnd.wap.wml")

    # since searching requires UUID, generate one
    identifier = uuid.uuid4()
    results_json = requests.get \
        (f"http://127.0.0.1:5001/api/search?i={identifier}&page={page}&th=0&maxres=5&isc={isc}&q={query}").json()

    results_markup = []
    for video in results_json:
        results_markup.append(
            f'<a href="settings?l={video["length"]}&amp;url={quote(video["video_url"])}">'
            f'{video["title"]}'
            '</a><br/>'
            f'By {video["creator"]}<br/>'
            f'{tools_web.seconds_to_readable(video["length"])}<br/>'
        )


    swap_dict = {"~1": "---<br/>".join(results_markup), "~6": page, "~4": query, "~2": isc, "~3": max(0, page -1), "~5": page +1}
    res = tools_web.render_template("SearchResults.wml", swap_dict)

    return Response(res, mimetype="text/vnd.wap.wml")

@wap_bp.route('/settings', methods=['GET'])
def serve_wap_video_settings():
    url = request.args.get("url")
    if not url:
        return Response("Missing url", status=400, mimetype="text/plain")

    swap_dict = {}
    if not request.args.get("l"):
        swap_dict["~3"] = tools_conv.get_video_length(url)
    if not request.args.get("i"):
        swap_dict["~2"] = uuid.uuid4()
    res = tools_web.render_error_settings_wml("VideoSettings.wml", request, swap_dict)

    return Response(res, mimetype="text/vnd.wap.wml")

@wap_bp.route('/convert', methods=['GET'])
def wap_convert():
    identifier = request.args.get("i")
    duration = request.args.get("l")

    if not identifier:
        return Response("Missing identifier", status=403, mimetype="text/plain")
    elif not duration:
        return Response("Missing duration", status=400, mimetype="text/plain")

    if request.args.get("url"):
        res = tools_conv.handle_conversion(request.args.to_dict(), arp(request.remote_addr))
        if "error" in res:
            return Response(tools_web.render_error_settings_wml("InvalidInput.wml", request, {"~1": res["error"]}), mimetype="text/vnd.wap.wml")

    proc = Config().conv_tasks[identifier]
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

            rtsp_url, http_url = tools_web.generate_links(hostname, f"/api/playback/{identifier}.{proc.res}")

            page_markup.append(
                '<anchor>\n'
                'Play (RTSP)\n'
                f'<go href="{rtsp_url}" method="get">\n'
                '</go>\n'
                '</anchor>\n'
                '<br/>\n'
            )

            if proc.res != "mkv":
                page_markup.append(
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
            Config().del_conv_task(identifier)
        else:
            page_markup.append("Couldn't convert video<br/>")

    res = tools_web.render_template("ConvProgress.wml", {"~1": identifier, "~2": "\n".join(page_markup), "~3": duration})

    return Response(res, mimetype="text/vnd.wap.wml")