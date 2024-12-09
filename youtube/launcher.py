import threading
import time
from youtube.server import create_server
from youtube.cleaner import start_cleaner


def run_flask_server():
    """
    Function to run the Flask server.
    """
    app = create_server()
    app.run(host='0.0.0.0', port=5000)


def main():
    """
    Main launcher function.
    """
    # Start the cleaner in a separate thread
    cleaner_thread = threading.Thread(target=start_cleaner, daemon=False)
    cleaner_thread.start()
    print("Cleaner started.")

    # Wait for 1 second to ensure the cleaner initializes properly
    time.sleep(1)

    # Start the Flask server in another thread
    flask_thread = threading.Thread(target=run_flask_server, daemon=False)
    flask_thread.start()
    print("Flask server started.")

    # Join the Flask thread to prevent the script from exiting
    flask_thread.join()


if __name__ == "__main__":
    main()
