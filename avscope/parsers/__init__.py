from __future__ import annotations

from .aac import AacAdtsParser
from .h26x import H264AnnexBParser, H265AnnexBParser
from .mp4 import Mp4Parser
from .raw import RawPcmParser, RawYuvParser
from .wav import WavParser


DEFAULT_PARSERS = [
    Mp4Parser(),
    WavParser(),
    AacAdtsParser(),
    H264AnnexBParser(),
    H265AnnexBParser(),
    RawPcmParser(),
    RawYuvParser(),
]
