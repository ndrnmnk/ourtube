import threading
import logging
import subprocess
import sys
from arp import arp
from server import create_server
from cleaner import Cleaner


def run_flask_server():
    create_server(arp()).run(host='0.0.0.0', port=5001)


def main():
    # Start the cleaner in a separate thread
    db_cleaner = Cleaner()
    # logging.basicConfig(level=10)
    threading.Thread(target=db_cleaner.run).start()
    logging.info("Cleaner started")

    # Launch deadRTSP
    subprocess.Popen(
        [sys.executable, "main.py"],
        cwd="DeadRTSP"
    )
    logging.info("deadRTSP started")

    # Start the Main server in another thread
    flask_thread = threading.Thread(target=run_flask_server)
    flask_thread.start()
    logging.info("Main server started")

    # Join the Main server's thread to prevent the script from exiting
    flask_thread.join()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.critical(f"Unhandled error in main: {e}")