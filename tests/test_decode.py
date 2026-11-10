import io

import numpy as np
import pytest

from app.stt import AudioError, decode_bytes
from evals.common import array_to_wav


def wav_bytes(seconds: float, rate: int = 16000) -> bytes:
    return array_to_wav((np.sin(np.linspace(0, 200 * seconds, int(rate * seconds))) * 0.3).astype(np.float32), rate)


def encode(codec: str, fmt: str, seconds: float = 1.0) -> bytes:
    import av

    buf = io.BytesIO()
    out = av.open(buf, "w", format=fmt)
    stream = out.add_stream(codec, rate=48000)
    stream.layout = "mono"
    pcm = (np.sin(np.linspace(0, 400 * seconds, int(48000 * seconds))) * 0.3 * 32767).astype(np.int16)
    frame = av.AudioFrame.from_ndarray(pcm.reshape(1, -1), format="s16", layout="mono")
    frame.sample_rate = 48000
    resampler = av.AudioResampler(format=stream.codec_context.format.name, layout="mono", rate=48000)
    for f in resampler.resample(frame):
        for packet in stream.encode(f):
            out.mux(packet)
    for packet in stream.encode(None):
        out.mux(packet)
    out.close()
    return buf.getvalue()


def test_wav_decodes_to_16k_mono():
    audio = decode_bytes(wav_bytes(1.0, 22050))
    assert audio.dtype == np.float32 and abs(len(audio) - 16000) < 200 and float(np.abs(audio).max()) > 0.1


@pytest.mark.parametrize("codec,fmt", [("libopus", "webm"), ("libopus", "ogg")])
def test_browser_formats_decode(codec, fmt):
    audio = decode_bytes(encode(codec, fmt))
    assert abs(len(audio) - 16000) < 800


def test_decoding_stops_past_the_limit():
    with pytest.raises(AudioError, match="longer than"):
        decode_bytes(wav_bytes(5.0), max_seconds=2)
    assert len(decode_bytes(wav_bytes(1.5), max_seconds=2)) > 20000


def test_a_small_compressed_upload_cannot_expand_past_the_limit():
    data = encode("libopus", "webm", seconds=6.0)
    with pytest.raises(AudioError, match="longer than"):
        decode_bytes(data, max_seconds=3)


def test_containers_outside_the_whitelist_are_refused():
    flac = encode("flac", "flac")
    with pytest.raises(AudioError, match="unsupported audio container"):
        decode_bytes(flac)


def test_garbage_is_an_audio_error():
    with pytest.raises(AudioError):
        decode_bytes(b"this is not audio at all" * 20)
    with pytest.raises(AudioError):
        decode_bytes(b"")
