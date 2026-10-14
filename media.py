"""Xử lý audio: track phát giọng bot, phát hiện người nói (VAD), chuyển định dạng."""
import asyncio
import fractions
import io
import time
import wave
from typing import Optional

import av
import numpy as np
from aiortc import MediaStreamTrack
from aiortc.mediastreams import MediaStreamError
from av import AudioFrame

SAMPLE_RATE = 48000
FRAME_MS = 20
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000      # 960
FRAME_BYTES = FRAME_SAMPLES * 2                     # mono s16
AUDIO_PTIME = FRAME_MS / 1000.0


class BotVoiceTrack(MediaStreamTrack):
    """Track audio gửi đi: phát PCM do TTS tạo ra, không có thì phát im lặng (đúng nhịp 20ms)."""
    kind = "audio"

    def __init__(self):
        super().__init__()
        self._buf = bytearray()
        self._start: Optional[float] = None
        self._timestamp = 0
        self._idle = asyncio.Event()
        self._idle.set()

    @property
    def is_speaking(self) -> bool:
        return len(self._buf) > 0

    def speak(self, pcm_s16_mono_48k: bytes):
        if not pcm_s16_mono_48k:
            return
        self._buf.extend(pcm_s16_mono_48k)
        self._idle.clear()

    def stop_speaking(self):
        """Barge-in: người kia chen ngang -> im ngay."""
        self._buf.clear()
        self._idle.set()

    async def wait_done(self, timeout: float = 60.0):
        try:
            await asyncio.wait_for(self._idle.wait(), timeout)
        except asyncio.TimeoutError:
            pass

    async def recv(self):
        if self.readyState != "live":
            raise MediaStreamError
        if self._start is None:
            self._start = time.time()
            self._timestamp = 0
        else:
            self._timestamp += FRAME_SAMPLES
            wait = self._start + (self._timestamp / SAMPLE_RATE) - time.time()
            if wait > 0:
                await asyncio.sleep(wait)

        if self._buf:
            chunk = bytes(self._buf[:FRAME_BYTES])
            del self._buf[:FRAME_BYTES]
            if len(chunk) < FRAME_BYTES:
                chunk += b"\x00" * (FRAME_BYTES - len(chunk))
            if not self._buf:
                self._idle.set()
        else:
            chunk = b"\x00" * FRAME_BYTES

        frame = AudioFrame(format="s16", layout="mono", samples=FRAME_SAMPLES)
        frame.planes[0].update(chunk)
        frame.sample_rate = SAMPLE_RATE
        frame.pts = self._timestamp
        frame.time_base = fractions.Fraction(1, SAMPLE_RATE)
        return frame



class FrameResampler16k:
    """AudioFrame bất kỳ (opus giải mã ra 48k stereo...) -> numpy int16 mono 16kHz."""

    def __init__(self):
        self._rs = av.AudioResampler(format="s16", layout="mono", rate=16000)

    def __call__(self, frame: AudioFrame) -> np.ndarray:
        out = []
        for f in self._rs.resample(frame):
            out.append(f.to_ndarray().reshape(-1))
        if not out:
            return np.zeros(0, dtype=np.int16)
        return np.concatenate(out).astype(np.int16)


class UtteranceDetector:
    """
    VAD năng lượng + noise floor thích nghi. Nhận từng đoạn int16 16k; khi người
    nói xong (im lặng >= silence_ms) trả về toàn bộ câu (int16 array) — nếu không thì None.

    Sửa lỗi "bot chờ rất lâu sau khi người kia nói xong": trước đây noise floor khởi điểm 200
    nên nếu nền thực tế ồn hơn ~600 RMS (mic bật AGC, quán ồn...) thì tiếng ồn bị coi là tiếng nói
    mãi mãi, không bao giờ đủ im lặng để chốt câu -> chờ tới max_utt_s. Giờ:
      - 0,5s đầu đo noise floor thật rồi mới chạy VAD (các frame đó được phát lại, không mất tiếng).
      - Nếu vẫn bị kẹt (chốt vì quá dài chứ không phải vì im lặng) thì tự nâng noise floor.
      - last_info ghi lại vì sao chốt câu để log chẩn đoán.
    """

    WARMUP_FRAMES = 25   # ~0.5s đầu (frame 20ms)

    def __init__(self, sample_rate=16000, silence_ms=600, min_speech_ms=300,
                 max_utt_s=12.0, start_ms=120, min_threshold=250.0):
        self.min_threshold = float(min_threshold)   # sàn ngưỡng tiếng nói (trước đây cố định 450 -> bỏ sót giọng nhỏ)
        self.sr = sample_rate
        self.silence_ms = silence_ms
        self.min_speech_ms = min_speech_ms
        self.max_samples = int(max_utt_s * sample_rate)
        self.start_ms = start_ms
        self.noise = 200.0              # RMS nền ban đầu (được đo lại sau warm-up)
        self._speech: list[np.ndarray] = []
        self._pre: list[np.ndarray] = []   # đệm đầu câu để không mất phụ âm đầu
        self._in_speech = False
        self._voiced_ms = 0.0
        self._silent_ms = 0.0
        self._speech_ms = 0.0
        self.voiced_run_ms = 0.0        # độ dài đoạn đang nói liên tục (dùng cho barge-in)
        self._warm: list[np.ndarray] = []
        self._warm_done = False
        self._recent_rms: list[float] = []
        self.last_info: dict = {}

    def _threshold(self):
        return max(self.noise * 2.5, self.min_threshold)

    @staticmethod
    def _rms(samples):
        return float(np.sqrt(np.mean(samples.astype(np.float64) ** 2)))

    def feed(self, samples: np.ndarray):
        if samples.size == 0:
            return None
        if not self._warm_done:
            self._warm.append(samples)
            if len(self._warm) < self.WARMUP_FRAMES:
                return None
            rmss = [self._rms(s) for s in self._warm]
            # percentile 25: nếu người kia đang nói một phần thì vẫn lấy mức "im" làm nền
            self.noise = float(min(max(np.percentile(rmss, 25), 50.0), 1000.0))
            warm, self._warm, self._warm_done = self._warm, [], True
            out = None
            for s in warm:
                r = self._step(s)
                if r is not None:
                    out = r
            return out
        return self._step(samples)

    def _step(self, samples: np.ndarray):
        ms = samples.size * 1000.0 / self.sr
        rms = self._rms(samples)
        voiced = rms > self._threshold()
        self._recent_rms.append(rms)
        if len(self._recent_rms) > 50:
            self._recent_rms.pop(0)

        if voiced:
            self.voiced_run_ms += ms
        else:
            self.voiced_run_ms = 0.0
            if not self._in_speech:   # chỉ cập nhật noise floor khi không ai nói
                self.noise = 0.95 * self.noise + 0.05 * rms

        if not self._in_speech:
            self._pre.append(samples)
            if sum(p.size for p in self._pre) > self.sr * 0.3:
                self._pre.pop(0)
            self._voiced_ms = self._voiced_ms + ms if voiced else 0.0
            if self._voiced_ms >= self.start_ms:
                self._in_speech = True
                self._speech = list(self._pre)
                self._pre = []
                self._silent_ms = 0.0
                self._speech_ms = self._voiced_ms
            return None

        self._speech.append(samples)
        if voiced:
            self._silent_ms = 0.0
            self._speech_ms += ms
        else:
            self._silent_ms += ms
        total = sum(s.size for s in self._speech)
        by_silence = self._silent_ms >= self.silence_ms
        if by_silence or total >= self.max_samples:
            utt = np.concatenate(self._speech)
            enough = self._speech_ms >= self.min_speech_ms
            if not by_silence and self._recent_rms:
                # Bị kẹt (không thấy im lặng) -> coi mức hiện tại là nền, lần sau chốt nhanh hơn.
                med = float(np.median(self._recent_rms))
                if med > self.noise:
                    self.noise = min(med, 2500.0)
            self.last_info = {
                "total_s": total / self.sr,
                "speech_s": self._speech_ms / 1000.0,
                "reason": "im lặng" if by_silence else "QUÁ DÀI (không thấy im lặng)",
                "noise": self.noise,
                "thr": self._threshold(),
            }
            self.reset()
            return utt if enough else None
        return None

    def reset(self):
        self._speech, self._pre = [], []
        self._in_speech = False
        self._voiced_ms = self._silent_ms = self._speech_ms = 0.0

    @property
    def in_speech(self):
        return self._in_speech

def pcm16_to_wav(samples: np.ndarray, sr=16000) -> bytes:
    bio = io.BytesIO()
    with wave.open(bio, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(samples.astype(np.int16).tobytes())
    return bio.getvalue()


def decode_audio_to_pcm48k(data: bytes) -> bytes:
    """mp3/wav/… (từ TTS) -> PCM s16 mono 48k (bytes) để phát vào BotVoiceTrack."""
    container = av.open(io.BytesIO(data))
    rs = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
    out = bytearray()
    for frame in container.decode(audio=0):
        for f in rs.resample(frame):
            out += f.to_ndarray().tobytes()
    for f in rs.resample(None):
        out += f.to_ndarray().tobytes()
    container.close()
    return bytes(out)