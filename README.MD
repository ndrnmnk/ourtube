This is a port of YouTube to ALL android versions. It's probably against their tos, so use only as the last resort.

To set up the server, do this:

```
git clone https://github.com/ndrnmnk/ourtube  # clone the project
pip install -r youtube/requirements.txt  # install requirements
```

Also, you need to make sure ffmpeg is installed. This is different for every os, so google how to do this.

To launch the server, use ```python3 main.py```

Apk can be found in the Releases tab (check tags if you don't see one). After installing it, go to settings and insert the server ip that gets printed on every server launch.
