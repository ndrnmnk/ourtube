from flask import Blueprint, send_file, redirect
import os

custom_bp = Blueprint("custom", __name__, url_prefix="/")

@custom_bp.route("/", methods=['GET'])
def reroute():
    return redirect("/html")

@custom_bp.route("favicon.ico", methods=['GET'])
def send_icon():
    return send_file(os.path.join("..", "web", "favicon.ico"), mimetype="image/x-icon")