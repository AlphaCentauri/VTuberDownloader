#!/usr/bin/python3
from __future__ import unicode_literals
import getopt
import sys
import signal
import requests
import json
import re
import iso8601
import time
import pytz
import argparse
import os
import googleapiclient.discovery
import youtube_dl
import subprocess
import operator
from os import error, name
from datetime import datetime
from pytz import timezone, utc
from bs4 import BeautifulSoup
from types import SimpleNamespace

HOLOMEM_EN_NAMES = ['AZKi', 'Akai Haato', 'Usada Pekora', 'Minato Aqua', 'Yuzuki Choco', 'Tokoyami Towa', 'Hoshimachi Suisei', 
                    'Hanasaki Miyabi', 'Anya Melfissa', 'Nakiri Ayame', 'Rikkaroid', 'Himemori Luna', 'Yukoku Roberu', 'Airani Iofifteen', 
                    'Momosuzu Nene', 'Houshou Marine', 'Yozora Mel', 'Shirakami Fubuki', 'Roboco-san', 'Shirogane Noel', 'Kagami Kira', 
                    'Yukihana Lamy', 'Hololive Indonesia', 'Aki Rosenthal', 'Kishido Temma', 'Civia', 'Mano Aloe', 'Inugami Korone', 
                    'Pavolia Reine', 'Akai Haato (Sub)', 'Sakura Miko', 'Kageyama Shien', 'Takanashi Kiara', 'Hololive VTuber Group', 
                    'Omaru Polka', 'Arurandeisu', 'Aki Rosenthal (Sub)', 'Uruha Rushia', 'Mori Calliope', 'Ninomae Ina’nis', 'Astel Leda', 
                    'Gawr Gura', 'Hololive English', 'Ayunda Risu', 'Moona Hoshinova', 'Choco Sub Channel', 'Ookami Mio', 'Tokino Sora', 
                    'Natsuiro Matsuri', 'Tsunomaki Watame', 'Kiryu Coco', 'Tsukishita Kaoru', 'Shishiro Botan', 'Nekomata Okayu', 'Shiranui Flare', 
                    'Oozora Subaru', 'Aragami Oga', 'Holostars Official', 'Murasaki Shion', 'Watson Amelia', 'Kureiji Ollie', 'Kanade Izuru', 'Amane Kanata']

MASTER_LIVE_URL = "https://www.youtube.com/channel/{}/live"

# Channel IDs
MIO_ID = "UCp-5t9SrOQwXMU7iIjQfARg"
FUBUKI_ID = "UCdn5BQ06XqgXoAxIhbqw5Rg"
COCO_ID = "UCS9uQI-jC3DE0L4IpXyvr6w"
INA_ID = "UCMwGHR0BTZuLsmjY_NT5Pwg"
RURUFU_ID = "UCcQsDietWkYakBKbGpCaeLA"
BOTAN_ID = "UCUKD-uaobj9jiqB-VXt71mA"
ROBERU_ID = "UCANDOlYTJT7N5jlRC3zfzVA"
KIARA_ID = "UCHsx4Hqa-1ORjQTh9TYDhww"
LAMY_ID = "UCFKOVgVbGmX65RxO3EtH3iw"
NOEL_ID = "UCdyqAaZDKHXg4Ahi7VENThQ"


class YTDLLogger(object):
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        print(msg)


def jprint(obj):
    # create a formatted string of the Python JSON object
    text = json.dumps(obj, sort_keys=False, indent=4)
    print(text)


def my_hook(d):
    if d['status'] == 'finished':
        print('Finished downloading.')


def runYTDL(ID):
    ydl_opts = {
        'add-metadata' : '',
        'writeinfojson' : '',
        'writethumbnail' : '',
        'write-description' : '',
        'format': 'best',
        'continue': '',
        'ignoreerrors': '',
        'nooverwrites': '',
        'outtmpl': '/mnt/mofumofu/V-Tubers/[%(upload_date)s][%(id)s] %(title)s/[%(uploader)s] %(title)s.%(ext)s',
        'logger': YTDLLogger(),
        'progress_hooks': [my_hook],
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download(['https://www.youtube.com/watch?v={}'.format(ID)])
        except Exception as e:
            print(e)
            return False
    return True

    # print("")
    # try:
    #     '''
    #     youtube-dl https://www.youtube.com/channel/UCp-5t9SrOQwXMU7iIjQfARg 
    #     --add-metadata 
    #     --write-info-json 
    #     --write-thumbnail 
    #     --write-description 
    #     --download-archive "/mnt/mofumofu/V-Tubers/ホロライブ/Members/HoloJP/大神ミオ/Public_Archive/public.archive" 
    #     -ciw 
    #     -f bestvideo[ext=mp4]+bestaudio[ext=m4a] 
    #     --merge-output-format mp4 
    #     -o "/mnt/mofumofu/V-Tubers/ホロライブ/Members/HoloJP/大神ミオ/Public_Archive/[%(upload_date)s] %(title)s/[%(uploader)s][%(upload_date)s] %(title)s (%(id)s).%(ext)s"
    #     '''
    #     subprocess.check_output(['youtube-dl', 'https://www.youtube.com/watch?v={}'.format(ID)])
    #     return True
    # except subprocess.CalledProcessError as e:
    #     # print("ERROR CAUGHT")
    #     print(e)
    #     return False


def generic_search(youtube_api_key):
    streams_to_archive = []

    running = 1
    while(running):
        print("\rSearching...", end='')
        # Live parsing
        try:
            # Get soup
            page = requests.get(MASTER_LIVE_URL.format(RURUFU_ID))
            soup = BeautifulSoup(page.content, 'html.parser')

            # Scrape page
            script_text = (soup.find_all("script")[37]).string

            # Primary check if livestream has been posted
            relevant_json = script_text[script_text.index('=') + 2:-1]

            # Begin parsing JSON and get live info if it exists
            data = json.loads(relevant_json)
            video_id = data["contents"]["twoColumnWatchNextResults"]["results"]["results"]["contents"][0]["videoPrimaryInfoRenderer"]["updatedMetadataEndpoint"]["updatedMetadataEndpoint"]["videoId"]
            print("\nFound: {}".format(video_id))

            # YouTube API call from found video_id
            os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
            DEVELOPER_KEY = youtube_api_key
            api_service_name = "youtube"
            api_version = "v3"
            youtube = googleapiclient.discovery.build(api_service_name, api_version, developerKey = DEVELOPER_KEY)
            request = youtube.videos().list(
                part="snippet,status,contentDetails,liveStreamingDetails",
                hl="ja",
                id=video_id,
                fields="items(id,snippet,contentDetails,status/embeddable,liveStreamingDetails)"
            )
            response = request.execute()

            # Check video
            video = response["items"][0]
            # jprint(video)
            scheduled_start_time = video["liveStreamingDetails"]["scheduledStartTime"]
            live_broadcast_content = video["snippet"]["liveBroadcastContent"]

            if live_broadcast_content in ("upcoming", "live"):
                if len(streams_to_archive) == 0:
                    stream = (video_id, scheduled_start_time)
                    # print(stream)
                    streams_to_archive.append(stream)
                    running = 0
                    return streams_to_archive
        except Exception as e:
            print("\n{}".format(e))

        time.sleep(10)


def sort_by_time(stream_list):
    # Master timestamp
    utcmoment_naive = datetime.utcnow()
    utcmoment = utcmoment_naive.replace(tzinfo=pytz.utc)

    # Create dict with id and duration till start
    temp = dict()
    idx = 0
    for stream in stream_list:
        start_date = iso8601.parse_date(stream["start_scheduled"])
        seconds_remaining = (start_date - utcmoment).total_seconds()
        temp[idx] = seconds_remaining
        idx = idx + 1

    # Sort dict
    temp_sorted = dict(sorted(temp.items(), key=lambda item: item[1]))
    
    # Reconstruct dictionary and return
    final_list = []
    final_keys = temp_sorted.keys()
    for val in final_keys:
        final_list.append(stream_list[val])
    return final_list


def search_for_streams(api_params, holodex_api_key):
    streams_to_archive = []

    running = 1
    while(running):
        print("\rSearching...", end='')
        users_live = requests.get("https://holodex.net/api/v2/users/live", params=api_params, headers={"X-APIKEY":holodex_api_key}).json()
        # jprint(users_live)

        if len(users_live) > 0:
            # Keep terminal pretty
            print("")

            # Sort stream list
            users_live = sort_by_time(users_live)

            # Parse stream list
            for video in users_live:
                if not re.search(r'\bfree chat\b', video["title"], re.I):
                    print("Found stream: {} - {}".format(video["title"], video["id"]))
                    if video["status"] == "upcoming" or video["status"] == "live":
                        # if len(streams_to_archive) == 0:
                            stream = (video["id"], video["start_scheduled"])
                            streams_to_archive.append(stream)
            running = 0
        else:
            time.sleep(60)
    # print(streams_to_archive)
    return streams_to_archive


def archive_streams(stream_list):
    running = 1
    while(running):
        difference = 0
        for stream in stream_list:
            run_inner = 1
            while (run_inner):
                start_date = iso8601.parse_date(stream[1])
                utcmoment_naive = datetime.utcnow()
                utcmoment = utcmoment_naive.replace(tzinfo=pytz.utc)
                difference = start_date - utcmoment
                seconds_remaining = difference.total_seconds()
                print("\rTime until ID={} begins: {}".format(stream[0], str(difference).split(".")[0]), end='')
                # seconds_remaining = -10
                if seconds_remaining < (60*5):
                    if runYTDL(stream[0]):
                        print("ytdl passed")
                        run_inner = 0
                    else:
                        print("ytdl failed")
                else:
                    time.sleep(1)
        running = 0       


def parse_command_line(channels):
    parser = argparse.ArgumentParser(description='Python script for monitoring a VTuber\'s channel and automatically downloading videos when they go live.')
    parser.add_argument('-o', '--output', help='File path output for youtube-dl')    
    required_args = parser.add_argument_group('required arguments')
    required_args.add_argument('-c', '--channel', help='VTuber\'s English first name, case insensitive. (ex: Mio, Fubuki, etc.)', required=True)

    args = vars(parser.parse_args())

    if args['channel'] == None:
        print('chuubas.py -c <English channel name>')
        sys.exit(2)
    if args['output'] is not None:
        output_path = args['output']

    input_val = args['channel'].lower()
    if input_val in channels["holodex_supported"].keys():
        return channels["holodex_supported"][input_val]
    elif input_val in channels["youtube_only"].keys():
        return channels["youtube_only"][input_val]
    else:
        print('chuubas.py -c <English channel name>')
        sys.exit(2)


def signal_handler(sig, frame):
    print('\nGoodbye.')
    sys.exit(0)


def main(argv):
    # TODO: Add support for several videos
    # TODO: Sort videos by time and start with video with shortest remaining time to start
    # TODO: Add handling for members-only videos (command line flag with yt-dl config)
    # TODO: Move to config files for yt-dl (not possible)

    signal.signal(signal.SIGINT, signal_handler)

    try:
        with open('API_KEYS.json') as f:
            api_keys = json.load(f)
    except Exception as e:
        print("Error reading API keys JSON file...does it exist? Are you running inside project directory?")
        sys.exit(2)

    try:
        with open('vtubers.json') as f:
            channel_ids = json.load(f)
    except Exception as e:
        print("Error reading VTubers JSON file...are you running inside project directory?")
        sys.exit(2)

    channel_id = parse_command_line(channel_ids)

    print("======< The sun never sets on the VTuber Empire >======")

    single_user_live_params = {
        "channels": "{}".format(channel_id)
    }

    if channel_id in channel_ids["holodex_supported"].values():
        while (True):
            stream_list = search_for_streams(single_user_live_params, api_keys['Holodex'])
            # stream_list = [('xH5k29Boh7c', '2021-06-11T13:00:00.000Z')]
            archive_streams(stream_list)
            sys.exit(0)
    elif channel_id == channel_ids["youtube_only"].values():
        while(True):
            stream_list = generic_search(api_keys['YouTube'])
            # stream = [('Yon4aCYJVhw', '2021-06-11T13:00:00.000Z')]
            archive_streams(stream_list)
    else:
        sys.exit('INVALID CHANNEL ID!')


if __name__ == "__main__":
    main(sys.argv[1:])
