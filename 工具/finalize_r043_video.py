# -*- coding: utf-8 -*-
"""为R043规范化视频合成可复现的扫帚擦石与木门音效。"""
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 32000
DURATION_S = 8


def synthesize_effects():
    """返回8秒双声道浮点音轨；事件内容由固定随机种子复现。"""
    rng = np.random.default_rng(43)
    count = SAMPLE_RATE * DURATION_S
    audio = rng.normal(0, 0.00035, (count, 2))

    def add_broom(start, duration, pan):
        length = int(duration * SAMPLE_RATE)
        t = np.arange(length) / SAMPLE_RATE
        noise = rng.normal(0, 1, length + 32)
        smooth = np.convolve(noise, np.ones(24) / 24, mode="valid")
        grit = noise[:length] - smooth[:length]
        envelope = np.sin(np.pi * t / duration) ** 1.4
        envelope *= 0.72 + 0.28 * np.sin(2 * np.pi * 2.6 * t) ** 2
        swish = 0.055 * grit * envelope
        index = int(start * SAMPLE_RATE)
        audio[index:index + length, 0] += swish * (1 - pan)
        audio[index:index + length, 1] += swish * pan

    # 扫帚由巷子左侧向右侧移动，1—2秒只保留很低的环境底声。
    for start, duration, pan in ((0.20, 0.70, 0.30), (2.35, 0.80, 0.40),
                                 (3.20, 0.85, 0.60), (4.30, 0.80, 0.70)):
        add_broom(start, duration, pan)

    # 画外木院门轻响，不要求远端已关闭院门产生额外可见运动。
    start = 6.25
    length = int(1.05 * SAMPLE_RATE)
    t = np.arange(length) / SAMPLE_RATE
    phase = 2 * np.pi * (155 * t - 28 * t ** 2) + 0.45 * np.sin(2 * np.pi * 5 * t)
    creak = (np.sin(phase) + 0.32 * np.sin(2.03 * phase)) * np.sin(np.pi * t / 1.05) ** 2
    index = int(start * SAMPLE_RATE)
    audio[index:index + length, 0] += 0.017 * creak
    audio[index:index + length, 1] += 0.014 * creak

    start = 7.18
    length = int(0.42 * SAMPLE_RATE)
    t = np.arange(length) / SAMPLE_RATE
    knock = (np.sin(2 * np.pi * 112 * t) + 0.45 * np.sin(2 * np.pi * 231 * t)) * np.exp(-13 * t)
    index = int(start * SAMPLE_RATE)
    audio[index:index + length, 0] += 0.085 * knock
    audio[index:index + length, 1] += 0.070 * knock

    return np.tanh(audio).astype(np.float32), SAMPLE_RATE


def write_effect_wav(path):
    """把合成音轨写成16位PCM WAV，供FFmpeg与原环境底声混合。"""
    path = Path(path)
    audio, sample_rate = synthesize_effects()
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(pcm.tobytes())
