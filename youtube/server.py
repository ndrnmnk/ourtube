from flask import Flask, Response, request, send_file, jsonify
from urllib.parse import unquote
from youtube import tools
import asyncio
import sqlite3
import time
import os


def create_server():
    app = Flask(__name__)

    @app.route('/convert', methods=['GET'])
    def convert_video():
        youtube_url = request.args.get('url')
        identifier = request.args.get('i')
        width = request.args.get('w')
        height = request.args.get('h')
        length = request.args.get('l')

        if not youtube_url:
            return {"error": "youtube_url is required"}, 400
        if not identifier:
            return {"error": "identifier not found"}, 403
        if not width:
            width = 480
        if not height:
            height = 320
        if not length:
            length = 300
        else:
            length = float(length)

        try:
            # Validate and download video
            orientation = tools.download_video(youtube_url, identifier, width, height)
            conn = sqlite3.connect('data.db')
            cur = conn.cursor()
            cur.execute("INSERT INTO data (expires_at, path) VALUES (?, ?)", (time.time() + length*2, f"youtube/thumbnails/{identifier}"))
            conn.commit()
            cur.close()
            conn.close()
            # Return path to the reformatted video
            return {"status": "success", "video_url": f"/video/{os.path.basename(identifier)}", "orientation": orientation}
        except Exception as e:
            print(f"Error during conversion: {e}")
            return {"error": str(e)}, 500

    @app.route('/search', methods=['GET'])
    def search():
        raw_query = request.args.get('q')
        identifier = request.args.get('i')
        th = request.args.get('th')
        if not raw_query:
            return jsonify({'error': 'No query provided'}), 400
        if not identifier:
            return jsonify({'error': 'You need an identifier to continue'}), 403
        if th == "0":
            th = False
        else:
            th = True
        query = unquote(raw_query)  # Decode the query
        res = asyncio.run(tools.search_youtube(query, identifier, th))
        if th:
            conn = sqlite3.connect('data.db')
            cur = conn.cursor()
            cur.execute("INSERT INTO data (expires_at, path) VALUES (?, ?)", (time.time() + 300, f"youtube/thumbnails/{identifier}"))
            conn.commit()
            cur.close()
            conn.close()
        return res

    @app.route('/thumbnail/<identifier>/<idx>')
    def serve_image(identifier, idx):
        try:
            # Path to the directory where images are stored
            image_path = f"thumbnails/{identifier}/{idx}.jpg"
            print(os.path.exists(image_path))  # prints True
            return send_file(image_path, mimetype='image/jpg')
        except FileNotFoundError:
            return "Image not found", 404

    @app.route('/video/<identifier>')
    def stream_video(identifier):
        file_path = f"youtube/videos/{identifier}.mp4"

        try:
            # Open the video file
            video_file = open(file_path, 'rb')
        except FileNotFoundError:
            return "Video not found", 404

        # Handle byte-range requests for streaming
        range_header = request.headers.get('Range', None)
        if not range_header:
            # Serve the entire file if no Range header is provided
            return Response(video_file.read(), mimetype="video/mp4")

        # Parse the Range header
        size = os.path.getsize(file_path)
        byte_range = range_header.strip().split('=')[-1]
        start, end = byte_range.split('-')

        start = int(start)
        end = int(end) if end else size - 1

        video_file.seek(start)
        data = video_file.read(end - start + 1)

        # Build the response
        response = Response(data, 206, mimetype="video/mp4")
        response.headers.add("Content-Range", f"bytes {start}-{end}/{size}")
        response.headers.add("Accept-Ranges", "bytes")

        return response

    return app


if __name__ == "__main__":
    app = create_server()
    app.run(host='0.0.0.0', port=5000)
