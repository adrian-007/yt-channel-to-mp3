import os
import json
import subprocess
import logging
import argparse
import configparser
import googleapiclient.discovery
import googleapiclient.errors
from yt_video_info import YTVideoInfo
from yt_video_state import YTVideoState
from shutil import copyfile
from pytube import YouTube


class YouTubeChannelToMP3:
    _config_file_name = 'config.ini'
    _video_info_cache_file_name = 'video_info_cache.json'
    _temp_dir_name = 'tmp'
    _episodes_dir_name = 'episodes'

    def __init__(self):
        self._logger = logging.getLogger(__name__)
        self._logger.setLevel(logging.DEBUG)

        self._videos_info_list = []

        self._configure_app()
        self._process_config()
        self._load_video_info_from_cache()
        self._init_service()
        self._list_channel_videos()
        self._save_video_info_to_cache()
        self._process_videos()

    def _configure_app(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('-d', '--working-directory')
        args = parser.parse_args()

        if args.working_directory is not None:
            os.makedirs(args.working_directory, exist_ok=True)
            os.chdir(args.working_directory)

        self._logger.info(f'Current working directory: {os.getcwd()}')

        os.makedirs(self._temp_dir_name, exist_ok=True)
        os.makedirs(self._episodes_dir_name, exist_ok=True)

    def _process_config(self):
        config = configparser.ConfigParser()

        self._logger.info('Reading configuration file')
        config.read(YouTubeChannelToMP3._config_file_name)

        if 'main' not in config:
            raise Exception(f'No main section in {YouTubeChannelToMP3._config_file_name} found')

        main_config = config['main']

        if 'yt-api-key' not in main_config:
            raise Exception("'yt-api-key' not configured")

        self._yt_api_key = main_config['yt-api-key']
        if len(self._yt_api_key) == 0:
            raise Exception("'yt-api-key' cannot be empty")

        if 'channel-id' not in main_config:
            raise Exception("'channel-id' not configured")

        self._channel_id = main_config['channel-id']
        if len(self._channel_id) == 0:
            raise Exception("'channel-id' cannot be empty")

    def _load_video_info_from_cache(self):
        try:
            with open(YouTubeChannelToMP3._video_info_cache_file_name, "r") as cache_file:
                cache_objects = json.load(cache_file)
                for cache_object in cache_objects:
                    try:
                        self._videos_info_list.append(YTVideoInfo.from_json(cache_object))
                    except:
                        self._logger.error(f'Failed to deserialize video info object: {cache_object}')
        except:
            self._logger.warning('Failed to load video info cache')

    def _save_video_info_to_cache(self):
        if os.path.exists(YouTubeChannelToMP3._video_info_cache_file_name):
            copyfile(YouTubeChannelToMP3._video_info_cache_file_name,
                     YouTubeChannelToMP3._video_info_cache_file_name + ".backup")

        with open(YouTubeChannelToMP3._video_info_cache_file_name, "w") as cache_file:
            objects = []
            for video_info in self._videos_info_list:
                try:
                    objects.append(video_info.to_json())
                except:
                    self._logger.error(f'Failed to serialize video info object: {video_info}')

            json.dump(objects, cache_file, indent=2, ensure_ascii=False)

    def _init_service(self):
        self._youtube = googleapiclient.discovery.build(
            serviceName='youtube',
            version='v3',
            developerKey=self._yt_api_key,
            cache_discovery=False
        )

    def _list_channel_videos(self):
        response = self._youtube.channels().list(
            part='snippet, contentDetails',
            id=self._channel_id
        ).execute()

        try:
            self._upload_playlist_id = response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        except:
            raise Exception("Failed to get uploads playlist ID")

        next_page_token = None

        while True:
            max_results = 100
            if next_page_token is None:
                response = self._youtube.playlistItems().list(
                    part="snippet,contentDetails",
                    maxResults=max_results,
                    playlistId=self._upload_playlist_id
                ).execute()
            else:
                response = self._youtube.playlistItems().list(
                    part="snippet,contentDetails",
                    maxResults=max_results,
                    playlistId=self._upload_playlist_id,
                    pageToken=next_page_token
                ).execute()

            if 'items' not in response:
                raise Exception("Playlist does not contain any video info")

            for item in response['items']:
                try:
                    details = item['contentDetails']
                    snippet = item['snippet']

                    video_info = YTVideoInfo(
                        video_id=details['videoId'],
                        published_at=snippet['publishedAt'],
                        title=snippet['title'],
                        description=snippet['description']
                    )

                    if video_info not in self._videos_info_list:
                        self._videos_info_list.insert(0, video_info)
                        self._logger.info(f'Found new video: {video_info.title}')
                finally:
                    pass

            next_page_token = response['nextPageToken'] if 'nextPageToken' in response else None

            if next_page_token is None:
                break

    def _process_videos(self):
        for video_info in self._videos_info_list:
            if video_info.state == YTVideoState.SKIPPED:
                continue

            # Sanity check - file missing, but video is supposedly downloaded
            if video_info.state == YTVideoState.AUDIO_DOWNLOADED:
                if not os.path.exists(f'{self._temp_dir_name}/{video_info.audio_filename()}'):
                    video_info.state = YTVideoState.AUDIO_MISSING

            if video_info.state == YTVideoState.AUDIO_MISSING:
                self._logger.info(f'Downloading audio of {video_info.title}')
                if self._download_audio_file(video_info.video_id, video_info.audio_filename()):
                    video_info.state = YTVideoState.AUDIO_DOWNLOADED
                    self._save_video_info_to_cache()

            if video_info.state == YTVideoState.AUDIO_DOWNLOADED:
                self._logger.info(f'Encoding audio of {video_info.title}')
                if self._convert_audio_file_to_mp3(video_info.audio_filename()):
                    video_info.state = YTVideoState.AUDIO_ENCODED
                    self._save_video_info_to_cache()

    def _download_audio_file(self, video_id, audio_filename):
        temp_path = f'{self._temp_dir_name}/{audio_filename}.tmp'
        target_path = f'{self._temp_dir_name}/{audio_filename}'

        try:
            yt = YouTube(f'http://youtube.com/watch?v={video_id}')
            audio_streams = yt.streams.filter(only_audio=True, audio_codec='opus').order_by('abr').desc()
            if len(audio_streams) == 0:
                raise Exception(f'No audio streams are available for {video_id}')

            audio_stream = audio_streams.first()

            with open(temp_path, 'wb') as audio_file_stream:
                audio_stream.stream_to_buffer(audio_file_stream)

            copyfile(temp_path, target_path)
            return True
        except KeyboardInterrupt:
            if os.path.exists(target_path):
                os.remove(target_path)
            raise
        except:
            if os.path.exists(target_path):
                os.remove(target_path)
            return False
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def _convert_audio_file_to_mp3(self, audio_filename):
        working_directory = os.getcwd()
        audio_file_path = f'{working_directory}/{self._temp_dir_name}/{audio_filename}'
        temp_output_path = f'{working_directory}/{self._temp_dir_name}/{audio_filename}.mp3.tmp'
        target_file_path = f'{working_directory}/{self._episodes_dir_name}/{audio_filename}.mp3'

        try:
            if os.path.exists(temp_output_path):
                os.remove(temp_output_path)
            if os.path.exists(target_file_path):
                os.remove(target_file_path)

            self._logger.info(f"Starting conversion of {audio_filename}")

            completed_process = subprocess.run(
                ['ffmpeg', '-y', '-i', audio_file_path, '-b:a', '192k', '-f', 'mp3', temp_output_path],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

            if completed_process.returncode != 0:
                raise Exception(
                    f"Conversion failed with code {completed_process.returncode}.\n{completed_process.stdout}")

            copyfile(temp_output_path, target_file_path)
            os.remove(audio_file_path)
            self._logger.info(f'Conversion completed, output saved to {target_file_path}')
            return True
        except Exception as e:
            self._logger.error(e)
            if os.path.exists(target_file_path):
                os.remove(target_file_path)
            return False
        finally:
            if os.path.exists(temp_output_path):
                os.remove(temp_output_path)
