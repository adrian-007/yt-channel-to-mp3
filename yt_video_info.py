import dateutil.parser
from yt_video_state import YTVideoState
from datetime import datetime


class YTVideoInfo:
    def __init__(self, video_id, published_at, title, description, state=YTVideoState.AUDIO_MISSING):
        self.video_id = video_id
        self.published_at = published_at if isinstance(published_at, datetime) else dateutil.parser.isoparse(
            published_at)
        self.title = title
        self.description = description
        self.state = state

    def __eq__(self, other):
        return self.video_id == other.video_id

    def audio_filename(self):
        date_prefix = self.published_at.strftime('%Y%m%d_%H%M%S')

        def safe_char(c):
            return c if c.isalnum() or c == '-' else '_'

        safe_title = "".join(safe_char(c) for c in self.title).strip("_")

        return f'{date_prefix}_{self.video_id}_{safe_title}'

    def to_json(self):
        return {
            "video_id": self.video_id,
            "published_at": self.published_at.isoformat(),
            "title": self.title,
            "description": self.description,
            "state": self.state
        }

    @staticmethod
    def from_json(json_string):
        return YTVideoInfo(
            video_id=json_string['video_id'],
            published_at=json_string['published_at'],
            title=json_string['title'],
            description=json_string['description'],
            state=YTVideoState(json_string['state'])
        )
