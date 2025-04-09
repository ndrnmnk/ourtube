import threading
import logging
import time
from youtube.server import create_server
from cleaner import Cleaner


def run_flask_server(db_cleaner):
    """Function to run the Flask server"""
    app = create_server(db_cleaner)
    app.run(host='0.0.0.0', port=5001)


def main():
    """Main launcher function"""
    # Start the cleaner in a separate thread
    db_cleaner = Cleaner()
    threading.Thread(target=db_cleaner.run, daemon=True).start()
    logging.info("Cleaner started")

    # Wait for 1 second to ensure the cleaner initializes properly
    time.sleep(1)

    # Start the Flask server in another thread
    flask_thread = threading.Thread(target=run_flask_server, args=(db_cleaner,), daemon=False)
    flask_thread.start()
    logging.info("Flask server started")

    # Join the Flask thread to prevent the script from exiting
    flask_thread.join()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.critical(f"Unhandled error in main: {e}")