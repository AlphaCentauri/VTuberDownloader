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
import smtplib, ssl
import multiprocessing
from os import error, name
from datetime import datetime, timedelta
from pytz import timezone, utc
from bs4 import BeautifulSoup
from types import SimpleNamespace


MASTER_LIVE_URL = "https://www.youtube.com/channel/{}/live"


class YTDLLogger(object):
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        print(msg)


def datetime_from_utc_to_local(utc_datetime):
    now_timestamp = time.time()
    offset = datetime.fromtimestamp(now_timestamp) - datetime.utcfromtimestamp(now_timestamp)
    return utc_datetime + offset


def jprint(obj):
    # create a formatted string of the Python JSON object
    text = json.dumps(obj, sort_keys=False, indent=4)
    print(text)


def my_hook(d):
    if d['status'] == 'finished':
        print('Finished downloading.')


def runYTDL(ID, path):
    ydl_opts = {
        'add-metadata' : '',
        'writeinfojson' : '',
        'writethumbnail' : '',
        'write-description' : '',
        'format': 'best',
        'continue': '',
        'ignoreerrors': '',
        'nooverwrites': '',
        'outtmpl': path,
        'logger': YTDLLogger(),
        'progress_hooks': [my_hook],
    }

    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download(['https://www.youtube.com/watch?v={}'.format(ID)])
        except Exception as e:
            print("ERROR: {}".format(e))
            return False
    return True


def generic_search(channel_id, youtube_api_key, email_config):
    # TODO: Generic search doesn't support multiple videos, try to fix that

    streams_to_archive = []

    running = 1
    while(running):
        print("\rSearching...", end='')
        # Live parsing
        try:
            # Get soup
            page = requests.get(MASTER_LIVE_URL.format(channel_id))
            soup = BeautifulSoup(page.content, 'html.parser')

            # Scrape page
            script_text = (soup.find_all("script")[37]).string

            # Primary check if livestream has been posted
            relevant_json = script_text[script_text.index('=') + 2:-1]

            # Begin parsing JSON and get live info if it exists
            data = json.loads(relevant_json)
            video_id = data["contents"]["twoColumnWatchNextResults"]["results"]["results"]["contents"][0]["videoPrimaryInfoRenderer"]["updatedMetadataEndpoint"]["updatedMetadataEndpoint"]["videoId"]
            # print("\nFound: {}".format(video_id))

            # YouTube API call from found video_id
            # os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
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
            video_title =  video["snippet"]["title"]
            channel_name = video["snippet"]["channelTitle"]

            print("\nFound stream: {} - {}".format(video_title, video_id), end="")

            if live_broadcast_content in ("upcoming", "live"):
                stream = (video_id, scheduled_start_time)
                streams_to_archive.append(stream)

                if email_config is not False:
                    # Convert time
                    format = "%H:%M:%S"
                    tmptime = iso8601.parse_date(scheduled_start_time)
                    local_time = datetime_from_utc_to_local(tmptime)
                    time_delta = timedelta(minutes=15)
                    alarm_time = local_time - time_delta

                    # Setup email
                    port = 465  # For SSL
                    smtp_server = "smtp.gmail.com"
                    sender_email = email_config['sender_email']
                    receiver_email = email_config['receiver_email']
                    password = email_config['password']
                    message = 'Subject: {},{}\n\n[{}][{}]'.format(
                        alarm_time.hour,
                        alarm_time.minute,
                        channel_name,
                        local_time.strftime(format)
                    )

                    # Send email
                    context = ssl.create_default_context()
                    with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
                        server.login(sender_email, password)
                        server.sendmail(sender_email, receiver_email, message.encode('utf-8'))

        except Exception as e:
            print("ERROR: {}".format(e))

        if len(streams_to_archive) > 0:
            running = 0
        else:
            time.sleep(60)
    # print(streams_to_archive)
    # Keep terminal pretty
    print("")
    return streams_to_archive

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


def search_for_streams(api_params, holodex_api_key, email_config):
    streams_to_archive = []

    running = 1
    while(running):
        print("\rSearching...", end='')
        users_live = requests.get("https://holodex.net/api/v2/users/live", params=api_params, headers={"X-APIKEY":holodex_api_key}).json()
        # jprint(users_live)

        if len(users_live) > 0:
            # Sort stream list
            users_live = sort_by_time(users_live)

            # Parse stream list
            for video in users_live:
                # TODO: This will not catch all free chat titles, maybe default to checking start_scheduled time and if it's stupid huge, ignore stream
                if not re.search(r'\bfree chat\b', video["title"], re.I):
                    # Keep terminal pretty
                    print("\nFound stream: {} - {}".format(video["title"], video["id"]), end="")
                    if video["status"] in ("upcoming", "live"):
                        stream = (video["id"], video["start_scheduled"])
                        streams_to_archive.append(stream)

                        if email_config is not False:
                            # Convert time
                            format = "%H:%M:%S"
                            tmptime = iso8601.parse_date(video["start_scheduled"])
                            local_time = datetime_from_utc_to_local(tmptime)
                            time_delta = timedelta(minutes=15)
                            alarm_time = local_time - time_delta

                            # Setup email
                            port = 465  # For SSL
                            smtp_server = "smtp.gmail.com"
                            sender_email = email_config['sender_email']
                            receiver_email = email_config['receiver_email']
                            password = email_config['password']
                            message = 'Subject: {},{}\n\n[{}][{}]'.format(
                                alarm_time.hour,
                                alarm_time.minute,
                                video["channel"]["english_name"],
                                local_time.strftime(format)
                            )

                            # Send email
                            context = ssl.create_default_context()
                            with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
                                server.login(sender_email, password)
                                server.sendmail(sender_email, receiver_email, message)

        if len(streams_to_archive) > 0:
            running = 0
        else:
            time.sleep(60)
    # print(streams_to_archive)
    # Keep terminal pretty
    print("")
    return streams_to_archive


def search_for_streams_p(api_params, holodex_api_key, email_config, stream_archive):
    streams_to_archive = []
        
    users_live = requests.get("https://holodex.net/api/v2/users/live", params=api_params, headers={"X-APIKEY":holodex_api_key}).json()
    # jprint(users_live)

    if len(users_live) > 0:
        # Sort stream list
        users_live = sort_by_time(users_live)

        # Parse stream list
        for video in users_live:
            # TODO: This will not catch all free chat titles, maybe default to checking start_scheduled time and if it's stupid huge, ignore stream
            if not re.search(r'\bfree\b', video['title'], re.I) and video['status'] in ("upcoming", "live") and video['id'] not in stream_archive:
                # Keep terminal pretty
                print("\nFound stream: {} - {}".format(video['title'], video['id']), end="")
                # print("\nFound stream: {} - {}".format(video['title'], video['id']))
                stream = (video['id'], video['start_scheduled'])
                streams_to_archive.append(stream)

                if email_config is not False:
                    # Convert time
                    format = "%H:%M:%S"
                    tmptime = iso8601.parse_date(video['start_scheduled'])
                    local_time = datetime_from_utc_to_local(tmptime)
                    time_delta = timedelta(minutes=15)
                    alarm_time = local_time - time_delta

                    # Setup email
                    port = 465  # For SSL
                    smtp_server = "smtp.gmail.com"
                    sender_email = email_config['sender_email']
                    receiver_email = email_config['receiver_email']
                    password = email_config['password']
                    message = 'Subject: {},{}\n\n[{}][{}]'.format(
                        alarm_time.hour,
                        alarm_time.minute,
                        video['channel']['english_name'],
                        local_time.strftime(format)
                    )

                    # Send email
                    context = ssl.create_default_context()
                    with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
                        server.login(sender_email, password)
                        server.sendmail(sender_email, receiver_email, message)
    
    # print(streams_to_archive)
    # Keep terminal pretty
    # print("")
    return streams_to_archive


def archive_streams(stream_list, path):
    if path == None:
        path = "./[%(upload_date)s][%(id)s] %(title)s/[%(uploader)s] %(title)s.%(ext)s"

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
                print("\rTime until ID={} begins: {}".format(stream[0], str(difference).split(".")[0]), end="")
                # seconds_remaining = -10
                if seconds_remaining < (60*5):
                    if runYTDL(stream[0], path):
                        print("ytdl passed")
                        run_inner = 0
                    else:
                        print("ytdl failed")
                else:
                    time.sleep(1)
        running = 0


def archive_streams_p(stream, path):
    if path == None:
        path = "./[%(upload_date)s][%(id)s] %(title)s/[%(uploader)s] %(title)s.%(ext)s"

    running = 1
    while(running):
        start_date = iso8601.parse_date(stream[1])
        utcmoment_naive = datetime.utcnow()
        utcmoment = utcmoment_naive.replace(tzinfo=pytz.utc)
        difference = start_date - utcmoment
        seconds_remaining = difference.total_seconds()
        print("\nTime until ID={} begins: {}".format(stream[0], str(difference).split(".")[0]), end="")
        # seconds_remaining = -10
        if seconds_remaining < (60*2):
            if runYTDL(stream[0], path):
                print("ytdl passed")
                running = 0
            else:
                print("ytdl failed")
        else:
            time.sleep(1)


def parse_command_line(channels):
    arguments = dict()
    parser = argparse.ArgumentParser(description='Python script for monitoring a VTuber\'s channel and automatically downloading videos when they go live.')
    parser.add_argument('-o', '--output', help='File path output for youtube-dl')
    parser.add_argument('-e', '--email', help='Enable email mode', action='store_true')
    required_args = parser.add_argument_group('required arguments')
    required_args.add_argument('-c', '--channel', help='VTuber\'s English first name, case insensitive. (ex: Mio, Fubuki, etc.)', required=True)

    args = vars(parser.parse_args())

    if args['channel'] == None:
        print('downloader.py -c <English channel name>')
        sys.exit(2)
    if args['output'] is not None:
        arguments['output'] = args['output']
    else:
        arguments['output'] = None

    arguments['email'] = args['email']

    input_val = args['channel'].lower()
    if input_val in channels['holodex_supported'].keys():
        arguments['channel_id'] = channels['holodex_supported'][input_val]
    elif input_val in channels['youtube_only'].keys():
        arguments['channel_id'] = channels['youtube_only'][input_val]
    else:
        print("downloader.py -c <English channel name>")
        sys.exit(2)

    return arguments


def signal_handler(sig, frame):
    print('\nGoodbye.')
    sys.exit(0)


def main(argv):
    # TODO: Add handling for members-only videos (command line flag with yt-dl config)
    # TODO: Move to config files for yt-dl ***(NOT POSSIBLE)
    # TODO: Figure out why yt-dl doesn't actually download thumbnail, desc., etc.; only grabbing video stream atm
    # TODO: Multi threading to free up thread to keep checking for videos

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

    arguments = parse_command_line(channel_ids)
    channel_id = arguments['channel_id']
    output_path = arguments['output']
    email_config = arguments['email'] 

    if arguments['email'] is True:
        try:
            with open('EMAIL.json') as f:
                email_config = json.load(f)
        except Exception as e:
            print("Error reading email config...does it exist? Are you running inside project directory?")
            sys.exit(2)

    print("======< The sun never sets on the VTuber Empire >======")

    single_user_live_params = {
        "channels": "{}".format(channel_id)
    }

    # TODO: Redundany check on supported channel list, try to only handle this in arg parser
    if channel_id in channel_ids["holodex_supported"].values():
        stream_archive = []
        # TODO: Print this only once for now until I can build an actual CLI
        print("\rSearching...", end='')
        while (True):
            stream_list = search_for_streams_p(single_user_live_params, api_keys['Holodex'], email_config, stream_archive)
            # stream_list = [('xH5k29Boh7c', '2021-06-11T13:00:00.000Z')]
            for stream in stream_list:
                if stream[0] not in stream_archive:
                    stream_archive.append(stream[0])
                    archive_p = multiprocessing.Process(target=archive_streams_p, args=(stream, output_path))
                    archive_p.start()
                # archive_streams(stream, output_path)
            time.sleep(60)
    elif channel_id in channel_ids["youtube_only"].values():
        while(True):
            stream_list = generic_search(channel_id, api_keys['YouTube'], email_config)
            # stream = [('Yon4aCYJVhw', '2021-06-11T13:00:00.000Z')]
            archive_streams(stream_list, output_path)
    else:
        sys.exit('INVALID CHANNEL ID!')


if __name__ == "__main__":
    main(sys.argv[1:])
