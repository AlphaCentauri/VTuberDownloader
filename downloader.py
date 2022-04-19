from __future__ import unicode_literals
from requests.exceptions import HTTPError
from os import error, name
from datetime import datetime, timedelta
from pytz import timezone, utc
# from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import sys
import signal
import requests
import json
import re
import iso8601
import time
import pytz
import argparse
import googleapiclient.discovery
import yt_dlp
import smtplib, ssl
import multiprocessing


MASTER_LIVE_URL = "https://www.youtube.com/channel/{}/live"


class YTDLLogger:
    def debug(self, msg):
        # For compatibility with youtube-dl, both debug and info are passed into debug
        # You can distinguish them by the prefix '[debug] '
        if msg.startswith('[debug] '):
            pass
        else:
            self.info(msg)

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        tz = timezone('US/Eastern')
        current_time = datetime.now(tz)
        print("[{}] {}".format(current_time, msg))


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
        'writeinfojson' : True,
        'writethumbnail' : True,
        'writedescription' : True,
        'hls_prefer_native' : True,
        'hls_use_mpegts' : True,
        'nopart' : True,
        'format': 'best',
        'continue': True,
        'nooverwrites': True,
        'quiet': True,
        'no_warnings': True,
        'outtmpl': path,
        'logger': YTDLLogger(),
        'progress_hooks': [my_hook],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            ydl.download(['https://www.youtube.com/watch?v={}'.format(ID)])
        except Exception as e:
            return False
    return True


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


def generic_search(channel_id, youtube_api_key, email_config, stream_archive):
    # TODO: Generic search doesn't support multiple videos, try to fix that
    # TODO: See what it would take to switch to YouTube API only

    streams_to_archive = []

    running = 1
    while(running):
        # print("\rSearching...", end='')
        # Live parsing
        try:
            # # Get soup
            # page = requests.get(MASTER_LIVE_URL.format(channel_id))
            # soup = BeautifulSoup(page.content, 'html.parser')

            # # Scrape page
            # script_text = (soup.find_all("script")[37]).string
            # jprint(script_text)

            # # Primary check if livestream has been posted
            # relevant_json = script_text[script_text.index('=') + 2:-1]

            # # Begin parsing JSON and get live info if it exists
            # data = json.loads(relevant_json)
            # video_id = data["contents"]["twoColumnWatchNextResults"]["results"]["results"]["contents"][0]["videoPrimaryInfoRenderer"]["updatedMetadataEndpoint"]["updatedMetadataEndpoint"]["videoId"]
            # # print("\nFound: {}".format(video_id))

            chrome_options = Options()
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')

            s = Service('/usr/bin/chromedriver')

            # Here chrome webdriver is used
            driver = webdriver.Chrome(service=s, options=chrome_options)
            
            # URL of the website 
            url = MASTER_LIVE_URL.format(channel_id)
            
            # Opening the URL
            driver.get(url)
            
            # Getting current URL
            get_url = driver.current_url

            url_parts = get_url.split('/')
            # print(url_parts)

            if "live" in url_parts:
                raise Exception("No livestream found")

            video_id = url_parts[-1].split('=')[-1]
            # print(video_id)

            # Printing the URL
            # print(get_url)

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

            # print("Video id found: {}".format(video_id))
            # print("Current stream archive: {}".format(stream_archive))
            # print("Title: {}".format(video_title))

            if not re.search(r'\bfree\b', video_title, re.I) and not re.search(r'スケジュール', video_title, re.I) and live_broadcast_content in ("upcoming", "live") and video_id not in stream_archive:
                print("Found stream: {} - {}".format(video_title, video_id), end="")
                stream = (video_id, scheduled_start_time)
                streams_to_archive.append(stream)
                # print(scheduled_start_time)

                if email_config is not False:
                    # Convert time
                    format = "%H:%M:%S"
                    tmptime = iso8601.parse_date(scheduled_start_time)
                    local_time = datetime_from_utc_to_local(tmptime)
                    time_delta = timedelta(minutes=15)
                    alarm_time = local_time - time_delta
                    # print(alarm_time)

                    # Get current time
                    current_time = datetime_from_utc_to_local(datetime.utcnow().replace(tzinfo=pytz.utc))
                    # print(current_time)

                    # Handle case where stream was posted earlier than 15 mins to start
                    if (current_time > alarm_time):
                        alarm_time = (current_time + timedelta(minutes=3)) # Set to 3 mins for now, may change in the future
                    # print(alarm_time)

                    # Setup email
                    port = 465  # For SSL
                    smtp_server = "smtp.gmail.com"
                    sender_email = email_config['sender_email']
                    receiver_email = email_config['receiver_email']
                    password = email_config['password']
                    message = 'Subject: {},{}\n\n[{}][{}]\n{}\nhttps://www.youtube.com/watch?v={}'.format(
                        alarm_time.hour,
                        alarm_time.minute,
                        channel_name,
                        local_time.strftime(format),
                        video_title,
                        video_id
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


def search_holodex(api_params, holodex_api_key, email_config, stream_archive):
    streams_to_archive = []
        
    try:
        users_live_raw = requests.get("https://holodex.net/api/v2/users/live", params=api_params, headers={"X-APIKEY":holodex_api_key})
        
        users_live_raw.raise_for_status()

        users_live = users_live_raw.json()

        if len(users_live) > 0:
            # Sort stream list
            users_live = sort_by_time(users_live)

            # Parse stream list
            for video in users_live:
                # TODO: This will not catch all free chat titles, maybe default to checking start_scheduled time and if it's stupid huge, ignore stream
                if not re.search(r'\bfree\b', video['title'], re.I) and video['status'] in ("upcoming", "live") and video['id'] not in stream_archive and video['channel']['id'] != "UCnUhgh7rNaLnvmya--q0pCw":
                    # Keep terminal pretty
                    print("Found stream: {} - {}".format(video['title'], video['id']))
                    # print("\nFound stream: {} - {}".format(video['title'], video['id']))
                    stream = (video['id'], video['start_scheduled'])
                    streams_to_archive.append(stream)
                    # print(stream)

                    if email_config is not False:
                        # Convert time
                        format = "%H:%M:%S"
                        tmptime = iso8601.parse_date(video['start_scheduled'])
                        local_time = datetime_from_utc_to_local(tmptime)
                        time_delta = timedelta(minutes=15)
                        alarm_time = local_time - time_delta

                        # print(alarm_time)

                        # Get current time
                        current_time = datetime_from_utc_to_local(datetime.utcnow().replace(tzinfo=pytz.utc))
                        # print(current_time)

                        # Handle case where stream was posted earlier than 15 mins to start
                        if (current_time > alarm_time):
                            alarm_time = (current_time + timedelta(minutes=3)) # Set to 3 mins for now, may change in the future
                        # print(alarm_time)

                        # Setup email
                        port = 465  # For SSL
                        smtp_server = "smtp.gmail.com"
                        sender_email = email_config['sender_email']
                        receiver_email = email_config['receiver_email']
                        password = email_config['password']
                        message = 'Subject: {},{}\n\n[{}][{}]\n{}\nhttps://www.youtube.com/watch?v={}'.format(
                            alarm_time.hour,
                            alarm_time.minute,
                            video['channel']['english_name'],
                            local_time.strftime(format),
                            video["title"],
                            video["id"]
                        )

                        # Send email
                        context = ssl.create_default_context()
                        with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
                            server.login(sender_email, password)
                            server.sendmail(sender_email, receiver_email, message.encode("utf-8"))
    
        # print(streams_to_archive)
        # Keep terminal pretty
        # print("")
    except HTTPError as http_err:
        print(f'HTTP error occurred: {http_err}')  # Python 3.6
    except Exception as err:
        print(f'Other error occurred: {err}')  # Python 3.6
    # except Exception as e:
    #     print("Code received: {}".format(users_live_raw.status_code))
    #     print(e)
    #     # sys.exit(2)

    return streams_to_archive


def archive_streams(stream, path):
    if path == None:
        path = "./[%(upload_date)s][%(id)s] %(title)s/[%(uploader)s] %(title)s.%(ext)s"

    running = 1
    while(running):
        start_date = iso8601.parse_date(stream[1])
        utcmoment_naive = datetime.utcnow()
        utcmoment = utcmoment_naive.replace(tzinfo=pytz.utc)
        difference = start_date - utcmoment
        seconds_remaining = difference.total_seconds()
        # print("Time until ID={} begins: {}".format(stream[0], str(difference).split(".")[0]))
        # seconds_remaining = 67
        if seconds_remaining < (60*2):
            if runYTDL(stream[0], path):
                running = 0
            if seconds_remaining > 60:
                time.sleep(1)
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
        print('downloader.py -c <English channel name> [-e]')
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
        print("downloader.py -c <English channel name> [-e]")
        sys.exit(2)

    return arguments


def signal_handler(sig, frame):
    print('Goodbye.')
    sys.exit(0)


def main(argv):
    # TODO: Add handling for members-only videos (command line flag with yt-dl config)
    # TODO: Move to config files for yt-dl ***(NOT POSSIBLE)
    # TODO: Figure out why yt-dl doesn't actually download thumbnail, desc., etc.; only grabbing video stream atm
    # TODO: Multi threading to free up thread to keep checking for videos
    # TODO: Handle recovering streams that premptively end and/or restart streaming on same frame
    # TODO: Handle video going private before starting to avoid spamming download requests
    # TODO: Add debug flags
    # TODO: Handle "ERROR: Private video" in generic search
    # TODO: Handle case where video is caught under 15 mins to start

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
        # print("Using {} as the API key for Holotools.".format(api_keys['Holodex']))
        # print("\rSearching...", end='')
        while (True):
            stream_list = search_holodex(single_user_live_params, api_keys['Holodex'], email_config, stream_archive)
            # stream_list = [('pcEqaCU4_SU', '2021-07-30T03:05:00.000Z')]
            for stream in stream_list:
                if stream[0] not in stream_archive:
                    start_date = iso8601.parse_date(stream[1])
                    utcmoment_naive = datetime.utcnow()
                    utcmoment = utcmoment_naive.replace(tzinfo=pytz.utc)
                    difference = start_date - utcmoment
                    print("Time until ID={} begins: {}".format(stream[0], str(difference).split(".")[0]))

                    stream_archive.append(stream[0])
                    archive_p = multiprocessing.Process(target=archive_streams, args=(stream, output_path))
                    archive_p.start()
            time.sleep(60)
    elif channel_id in channel_ids["youtube_only"].values():
        stream_archive = []
        # print("Using {} as the API key for YouTube.".format(api_keys['YouTube']))
        while(True):
            stream_list = generic_search(channel_id, api_keys['YouTube'], email_config, stream_archive)
            # stream = [('Yon4aCYJVhw', '2021-06-11T13:00:00.000Z')]
            # stream_archive.append(stream_list[0])
            for stream in stream_list:
                if stream[0] not in stream_archive:
                    start_date = iso8601.parse_date(stream[1])
                    utcmoment_naive = datetime.utcnow()
                    utcmoment = utcmoment_naive.replace(tzinfo=pytz.utc)
                    difference = start_date - utcmoment
                    print("Time until ID={} begins: {}".format(stream[0], str(difference).split(".")[0]))

                    stream_archive.append(stream[0])
                    archive_p = multiprocessing.Process(target=archive_streams, args=(stream, output_path))
                    archive_p.start()
            time.sleep(60)
    else:
        sys.exit('INVALID CHANNEL ID!')


if __name__ == "__main__":
    main(sys.argv[1:])
