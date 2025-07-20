from flask import Flask
from .api_routes import api_bp
from .html_routes import html_bp
from .wap_routes import wap_bp
from .custom_routes import custom_bp

def create_server():
    app = Flask(__name__)
    app.url_map.strict_slashes = False

    app.register_blueprint(api_bp)
    app.register_blueprint(html_bp)
    app.register_blueprint(wap_bp)
    app.register_blueprint(custom_bp)

    return app
