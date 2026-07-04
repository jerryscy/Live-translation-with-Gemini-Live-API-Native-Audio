"""DeepFilterNet denoiser for incoming microphone audio.

The Gemini Live API expects 16 kHz, 16-bit little-endian mono PCM. DeepFilterNet
runs at 48 kHz, so each incoming chunk is:

    16 kHz PCM (int16) -> float32 -> resample to 48 kHz -> DeepFilterNet
                       -> resample back to 16 kHz -> int16 PCM

The model is loaded once and reused. Denoising can be turned on/off at runtime
via the ``enabled`` flag so the UI can do a live A/B comparison without
restarting the session — when disabled, ``process()`` returns the original PCM
untouched (zero added latency).

DeepFilterNet keeps internal recurrent state across calls, so we feed it the
stream chunk-by-chunk. Chunks shorter than one FFT hop are buffered until enough
samples accumulate, which keeps the denoiser stable on the small (~e.g. 4096
byte) buffers the browser sends.
"""

import os
import threading
from typing import Optional

import numpy as np
import torch
import torchaudio

# DeepFilterNet is imported lazily inside load() so importing this module never
# triggers the (slow) model download / torch import at process import time.

LIVE_API_SAMPLE_RATE = 16000
INT16_MAX = 32768.0


class DeepFilterDenoiser:
    def __init__(self, model_name: str = "DeepFilterNet2", enabled: bool = True):
        self.model_name = model_name
        self.enabled = enabled

        self._model = None
        self._df_state = None
        self._df_sr = 48000  # DeepFilterNet native rate; corrected after load()
        self._lock = threading.Lock()

        # Leftover 48 kHz float samples that didn't fill a processing block.
        self._residual = np.zeros(0, dtype=np.float32)

        # Resamplers (created after we know the DF sample rate).
        self._up: Optional[torchaudio.transforms.Resample] = None
        self._down: Optional[torchaudio.transforms.Resample] = None

    # ------------------------------------------------------------------
    # Model lifecycle
    # ------------------------------------------------------------------
    def load(self) -> None:
        """Load the DeepFilterNet model. Safe to call once at startup."""
        if self._model is not None:
            return
        from df.enhance import init_df  # heavy import, kept local

        model, df_state, name = init_df(model_base_dir=self.model_name)
        self._model = model
        self._df_state = df_state
        self._df_sr = df_state.sr()
        self._up = torchaudio.transforms.Resample(LIVE_API_SAMPLE_RATE, self._df_sr)
        self._down = torchaudio.transforms.Resample(self._df_sr, LIVE_API_SAMPLE_RATE)
        print(f"[denoiser] Loaded {name} @ {self._df_sr} Hz (enabled={self.enabled})")

    def reset(self) -> None:
        """Clear streaming state (residual + model recurrent state)."""
        with self._lock:
            self._residual = np.zeros(0, dtype=np.float32)
            try:
                if self._df_state is not None:
                    self._df_state.reset()
            except Exception:
                pass

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            if enabled and not self.enabled:
                # Reset streaming state when (re)enabling so stale residual /
                # recurrent state doesn't leak across the toggle.
                self._residual = np.zeros(0, dtype=np.float32)
            self.enabled = enabled
        print(f"[denoiser] enabled = {enabled}")

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------
    def process(self, pcm16: bytes) -> bytes:
        """Denoise one chunk of 16 kHz int16 PCM, returning 16 kHz int16 PCM.

        When disabled (or not yet loaded) the input bytes are returned as-is.
        """
        if not self.enabled or self._model is None or not pcm16:
            return pcm16

        with self._lock:
            if not self.enabled:  # re-check under lock
                return pcm16
            try:
                return self._denoise_locked(pcm16)
            except Exception as exc:  # never break the audio path on a denoise error
                print(f"[denoiser] error, passing audio through: {exc}")
                return pcm16

    def _denoise_locked(self, pcm16: bytes) -> bytes:
        from df.enhance import enhance

        # int16 -> float32 in [-1, 1]
        x = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / INT16_MAX
        if x.size == 0:
            return pcm16

        # Upsample 16k -> 48k
        up = self._up(torch.from_numpy(x).unsqueeze(0)).squeeze(0).numpy()

        # Accumulate with any residual and process in whole hop-sized blocks so
        # DeepFilterNet's STFT gets stable frame boundaries.
        buf = np.concatenate([self._residual, up])
        hop = self._df_state.hop_size()
        n_frames = buf.shape[0] // hop
        if n_frames == 0:
            # Not enough for a frame yet — keep buffering, emit silence-free
            # passthrough of the original (avoids audible dropouts on tiny chunks).
            self._residual = buf
            return pcm16

        usable = n_frames * hop
        block = buf[:usable]
        self._residual = buf[usable:].copy()

        enhanced = enhance(
            self._model, self._df_state, torch.from_numpy(block).unsqueeze(0)
        )
        enhanced = enhanced.squeeze(0)

        # Downsample 48k -> 16k
        out = self._down(enhanced.unsqueeze(0)).squeeze(0).numpy()

        # float32 -> int16
        out = np.clip(out, -1.0, 1.0)
        return (out * INT16_MAX).astype(np.int16).tobytes()
