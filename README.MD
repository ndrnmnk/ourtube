This is a port of YouTube to ALL android versions. It's probably against their tos, so use only as the last resort.

### To set up the server, do this:

```
git clone https://github.com/ndrnmnk/ourtube  # clone the project
cd ourtube; python3 -m venv venv
pip install -r youtube/requirements.txt  # install requirements
```

Also, you need to make sure ffmpeg is installed. This is different for every OS and PC, so google how to do this.

You can adjust server settings in `config.yaml`, but default ones usually work fine.

To launch the server, use `python3 launcher.py`

### To set up client app, do this:

- Apk can be found in the `Releases` tab (check `tags` if you don't see one). Install it.

- Go to Ourtube settings and insert the server ip (it's printed on every server launch). Don't forget to save the settings

- You should be able to watch videos! It's also recommended to play around with other settings
