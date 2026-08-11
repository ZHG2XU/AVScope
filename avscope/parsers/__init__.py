from __future__ import annotations

from .aac import AacAdtsParser
from .avi import AviParser
from .flv import FlvParser
from .h26x import H264AnnexBParser, H265AnnexBParser
from .matroska import MatroskaParser
from .mpegps import MpegPsParser
from .mpegts import MpegTsParser
from .mp4 import Mp4Parser
from .raw import RawPcmParser, RawYuvParser
from .wav import WavParser


DEFAULT_PARSERS = [
    Mp4Parser(),
    AviParser(),
    FlvParser(),
    MatroskaParser(),
    MpegPsParser(),
    MpegTsParser(),
    WavParser(),
    AacAdtsParser(),
    H264AnnexBParser(),
    H265AnnexBParser(),
    RawPcmParser(),
    RawYuvParser(),
]
