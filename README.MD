This is a port of YouTube to ALL android versions. It's probably against their tos, so use only as the last resort.

### To set up the server, do this:

```
git clone https://github.com/ndrnmnk/ourtube  # clone the project
cd ourtube; python3 -m venv venv; source venv/bin/activate
pip install -r youtube/requirements.txt  # install requirements
```

Also, you need to make sure ffmpeg is installed. This is different for every OS and PC, so google how to do this.

You can adjust server settings in `config.yaml`, but default ones usually work fine.

To launch the server, use `python3 launcher.py`

### To set up client app, do this:

- Download and install the app from the `Releases` tab (check `tags` if you don't see it)

- Insert the server ip (it's printed on every server launch)

- You should be able to watch videos! It's also recommended to play around with other settings, especially on J2ME

### Notes about J2ME client

Most java phones support `h263` codec, which only allows certain screen resolutions.
That`s the reason videos don't get scaled to phone screen size.

If your phone supports `mpeg4` codec and `AAC` audio, there is an options for that, 
with which everything should work correctly.
