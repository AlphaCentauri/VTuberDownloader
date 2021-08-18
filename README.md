# VTuberDownloader
Python script for monitoring a VTuber's channel and automatically downloading videos when they go live.

# Setup
This project relies on [Holodex](https://holodex.stoplight.io/) and [YouTube](https://developers.google.com/youtube/v3/getting-started) APIs for parsing of channel and video information. See the attached hyperlinks for how to generate these keys.

Once obtained, place them inside `API_KEYS.TEMPLATE` and rename the file extension to `.json`.

Dependency installation: **TODO** (setup venv)

# Usage
`./downloader.py -c <vtuber's English name (see supported list)> [-e]`