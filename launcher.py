import threading
import logging
import subprocess
import sys
from utils.arp import arp
from server import create_server
from utils.cleaner import Cleaner
from utils.config import Config


def run_flask_server():
    create_server().run(host='0.0.0.0', port=5001)


if __name__ == "__main__":
    try:
        Config().arp = arp()
        logging.basicConfig(level=Config().get("log_level", 40))

        threading.Thread(target=Cleaner().run, daemon=True).start()
        logging.info("Cleaner started")

        # Launch deadRTSP
        if Config().get("rtsp"):
            subprocess.Popen([sys.executable, "main.py"], cwd="DeadRTSP")
            logging.info("deadRTSP started")
        else:
            logging.error("RTSP is disabled. Clients that have RTSP enabled will fail")

        # Start the main server in another thread
        flask_thread = threading.Thread(target=run_flask_server)
        flask_thread.start()
        logging.info("Main server started")

        # Join the Main thread to prevent the script from exiting
        flask_thread.join()
    except Exception as e:
        logging.critical(f"Unhandled error in main: {e}")