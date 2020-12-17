import logging
from yt_channel_to_mp3 import YouTubeChannelToMP3

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)

    try:
        YouTubeChannelToMP3()
    except Exception as e:
        logging.error(f'Fatal exception: {e.with_traceback()}')
