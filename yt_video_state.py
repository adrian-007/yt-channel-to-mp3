from enum import Enum


class YTVideoState(str, Enum):
    SKIPPED = 'skipped'
    AUDIO_MISSING = 'audio_missing'
    AUDIO_DOWNLOADED = 'audio_downloaded'
    AUDIO_ENCODED = 'audio_encoded'
