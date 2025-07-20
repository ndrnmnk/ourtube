import os
import re
import uuid

from utils.config import Config

def generate_links(host, path):
    http_link = f"http://{host}:5001/{path}"
    if Config().get("rtsp"):
        rtsp_link = f"rtsp://{host}:8554/{path}"
    else:
        rtsp_link = http_link

    return rtsp_link, http_link

def validate_int_arg(request, arg_name):
    val = request.get(arg_name)
    max_limit = 200 if arg_name == "fps" else 9999
    try:
        t = int(val)
        if max_limit > t:
            return t
        else:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError(f"Invalid value for '{arg_name}': {val}")

def is_valid_uuid(s):
    try:
        u = uuid.UUID(s)
        return u.version == 4
    except ValueError:
        return False

def seconds_to_readable(seconds):
    if seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes:02}:{secs:02}"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours:02}:{minutes:02}:{secs:02}"

def progress_bar_gen(progress_str):
    # Convert to integer
    try:
        p_int = int(progress_str.replace("Progress: ", "").replace("%", ""))
    except ValueError:
        p_int = 1

    # Progress bar is 10 characters long without []
    p_dec = p_int // 10
    return '[' + '#'*p_dec + '_'*(10-p_dec) + ']'

def render_template(filename, replacements):
    with open(os.path.join("web", filename)) as wap_file:
        template = wap_file.read()
    for key, value in replacements.items():
        template = template.replace(key, str(value))
    return template

def is_url(query):
    pattern = re.compile("^https?://\\S*\\.\\S+$")
    match = re.search(pattern, query)
    if match:
        return True
    else:
        return False

def render_error_settings_wml(template, request, swap_dict=None):
    if swap_dict is None:
        swap_dict = {}
    swap_dict["~0"] = request.args.get('url')
    swap_dict["~2"] =  request.args.get('i') or swap_dict["~2"]
    swap_dict["~3"] = request.args.get('l') or swap_dict["~3"]
    swap_dict["~4"] = request.args.get('dtype') or "2"
    swap_dict["~#"] = request.args.get('ap') or "2"
    swap_dict["~5"] = request.args.get('w') or "128"
    swap_dict["~6"] = request.args.get('h') or "96"
    swap_dict["~7"] = request.args.get('fps') or "12"
    swap_dict["~8"] = request.args.get('sm') or "1"
    swap_dict["~9"] = request.args.get('fp') or "1"
    swap_dict["~q"] = request.args.get('mono') or "1"
    res = render_template(template, swap_dict)
    return res

def render_settings_html_template(template, request):
    swap_dict = {}
    if request.args.get("url"):
        swap_dict["~1"] = request.args.get("url")
        swap_dict["~2"] = request.args.get("l")
        swap_dict["~3"] = request.args.get("i")
    else:
        swap_dict["~1"] = ""
        swap_dict["~2"] = ""
        swap_dict["~3"] = ""

    swap_dict["~4"] = request.cookies.get("w") or "128"
    swap_dict["~5"] = request.cookies.get("h") or "96"
    swap_dict["~6"] = request.cookies.get("fps") or "10"

    dtypes = ["Android", "Generic new", "J2ME phone", "Symbian", "Windows PDA", "Win95-era PC", "XVid device", "iPhone", "macOS device", "iPod", "IoT device"]
    selected_dtype = int(request.cookies.get('dtype')) if request.cookies.get('dtype') else 2
    dtype_markup = generate_html_select("dtype", dtypes, selected_dtype)

    sms = ["Stretch (keep AR)", "Crop", "Force stretch", "None"]
    selected_sm = int(request.cookies.get('sm')) if request.cookies.get('sm') else 1
    sm_markup = generate_html_select("sm", sms, selected_sm)

    selected_ap = int(request.cookies.get('ap')) if request.cookies.get('ap') else 0
    ap_markup = generate_html_select("ap", ["High", "Mid", "Low"], selected_ap)

    swap_dict["~7"] = sm_markup
    swap_dict["~8"] = dtype_markup
    swap_dict["~q"] = ap_markup

    selected_rtsp = int(request.cookies.get("fp")) if request.cookies.get("fp") else 0
    swap_dict["~9"] = generate_html_select("fp", ["Off", "On", "Video only"], selected_rtsp)

    temp = "checked" if request.cookies.get("mono") == "1" else ""
    swap_dict["~@"] = f'<input type="checkbox" name="mono" value="1" {temp}> Always mono audio'

    if request.args.get("error"):
        swap_dict["~0"] = "<b>Invalid input. Text fields only accept integers above 0</b>"
    else:
        swap_dict["~0"] = ""

    return render_template(template, swap_dict)

def generate_html_select(name, options, selected):
    markup = f'<select name="{name}">\n'
    for i in range(len(options)):
        if i != selected:
            markup = markup + f"<option value={i}>{options[i]}</option>\n"
        else:
            markup = markup + f"<option value={i} selected>{options[i]}</option>\n"
    markup = markup + "</select>"
    return markup