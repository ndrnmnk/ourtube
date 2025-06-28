# Manual Installation

### Use this only if you can't execute `setup.sh`. It usually works on Linux and macOS

1. Install [Python](https://www.python.org/downloads/) and [FFmpeg](https://github.com/BtbN/FFmpeg-Builds/releases).
2. Add them to your system's PATH so it can be accessed from any terminal window. [Here is a tutorial for Windows](https://gist.github.com/ScribbleGhost/752ec213b57eef5f232053e04f9d0d54)
3. Download this repository as zip and extract it. 
4. Download [another repository](https://github.com/ndrnmnk/DeadRTSP). Extract it inside Ourtube's folder like this:
    ```
    ourtube
    ├── launcher.py
    ├── {other files}
    └── DeadRTSP
        ├── main.py
        └── {other files}
    ```
5. In Ourtube's folder, create `videos` and `thumbnails` folders
6. In the Ourtube folder, open a terminal and run this to create python venv: `python -m venv venv`
7. Activate it:
   - on Windows, use `call venv\Scripts\activate`
   - on macOS and Linux, use `source venv/bin/activate`
8. Install requirements: `pip install -r requirements.txt`
9. Move `deadRTSP_video_adjustment.patch` to `deadRTSP` folder
10. If you have `git`, execute `git apply deadRTSP_video_adjustment.patch`  
    If you don't, open `main.py` and edit it like this:  
        1. add `import os` at the beginning of the file  
        2. replace `choose_video` function with this:

```python
def choose_video(request):
    pattern = re.compile(
        r'/video/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-'
        r'[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\.(\w+)'
    )

    match = pattern.search(request)
    uuid = match.group(1)
    ext = match.group(2)

    OURTUBE_PROJECT_ROOT = ".."
    return os.path.join(OURTUBE_PROJECT_ROOT, "videos", uuid, f"result.{ext}")
```
        
11. Done! To launch the project on Windows, execute this in Ourtube's directory:
```commandline
call venv\Scripts\activate
python launcher.py
```
On Linux/macOS:
```commandline
source venv/bin/activate
python launcher.py
```

Next time you want to launch this, just repeat the command from step 11