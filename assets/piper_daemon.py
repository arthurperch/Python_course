#!/usr/bin/env python3
"""Persistent piper TTS helper for tutor.py.

Loads the piper voice ONCE and keeps it in memory, serving one-shot synthesis
requests over a tiny binary protocol on stdin/stdout. This removes the ~1.8s
model-load cost that a fresh `piper` process pays on every utterance.

Protocol (binary, so text can contain any characters):
  request:   1 byte rate (length_scale * 10, e.g. 12 = 1.2x slower),
             then 4-byte big-endian length, then that many UTF-8 bytes of text
  response:  4-byte big-endian length, then that many bytes of raw PCM
             (16-bit signed little-endian mono, at the voice's sample rate)
Exits on stdin EOF.
"""
import struct
import sys

from piper import PiperVoice
from piper.config import SynthesisConfig


def main() -> None:
    model = sys.argv[1]
    voice = PiperVoice.load(model)
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    while True:
        rate_byte = stdin.read(1)
        if len(rate_byte) != 1:
            break
        rate = rate_byte[0] / 10.0
        if rate <= 0.0 or rate > 2.5:
            rate = 1.0
        hdr = stdin.read(4)
        if len(hdr) != 4:
            break
        (n,) = struct.unpack(">I", hdr)
        data = stdin.read(n)
        if len(data) != n:
            break
        text = data.decode("utf-8", "replace")
        cfg = SynthesisConfig(length_scale=rate)
        chunks = list(voice.synthesize(text, syn_config=cfg))
        pcm = b"".join(c.audio_int16_bytes for c in chunks)
        stdout.write(struct.pack(">I", len(pcm)))
        stdout.write(pcm)
        stdout.flush()


if __name__ == "__main__":
    main()
