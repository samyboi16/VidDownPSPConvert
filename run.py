import webbrowser
from threading import Timer
from app import app  # Import your Flask app instance from app.py

def open_browser():
    webbrowser.open_new("http://127.0.0.1:5000/")

if __name__ == "__main__":
    # Wait 1.5 seconds for Flask to boot up, then open the browser
    Timer(1.5, open_browser).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
