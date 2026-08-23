"""Small ElevenLabs TTS client and cross-platform audio player.

No key is stored here. The GUI persists it in the existing user-only config at
``~/.spotify-ai-dj/config.json``.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass

import requests


ELEVENLABS_API = "https://api.elevenlabs.io/v1"


@dataclass(frozen=True)
class Voice:
    voice_id: str
    name: str
    gender: str = ""
    category: str = ""
    preview_url: str = ""


class ElevenLabsTTS:
    def __init__(self, api_key: str, timeout: int = 30):
        self.api_key = api_key.strip()
        self.timeout = timeout

    @property
    def headers(self) -> dict[str, str]:
        return {"xi-api-key": self.api_key, "Content-Type": "application/json"}

    def list_voices(self, female_only: bool = False) -> list[Voice]:
        """Return voices available to the account, including premade voices."""
        if not self.api_key:
            return []
        params = {"page_size": 100, "include_total_count": "false"}
        if female_only:
            params["gender"] = "female"
        response = requests.get(
            f"{ELEVENLABS_API.replace('/v1', '/v2')}/voices",
            headers=self.headers,
            params=params,
            timeout=self.timeout,
        )
        response.raise_for_status()
        voices = []
        for item in response.json().get("voices", []):
            labels = item.get("labels") or {}
            gender = str(labels.get("gender", ""))
            if female_only and gender.lower() != "female":
                continue
            voices.append(Voice(
                voice_id=item["voice_id"],
                name=item.get("name") or "Unnamed voice",
                gender=gender,
                category=item.get("category") or "",
                preview_url=item.get("preview_url") or "",
            ))
        return sorted(voices, key=lambda voice: voice.name.lower())

    def synthesize(
        self,
        text: str,
        voice_id: str,
        model_id: str = "eleven_multilingual_v2",
    ) -> bytes:
        if not self.api_key:
            raise ValueError("Add an ElevenLabs API key in Settings to enable DJ speech.")
        response = requests.post(
            f"{ELEVENLABS_API}/text-to-speech/{voice_id}",
            headers=self.headers,
            params={"output_format": "mp3_44100_128"},
            json={
                "text": text,
                "model_id": model_id,
                "voice_settings": {
                    "stability": 0.42,
                    "similarity_boost": 0.78,
                    "style": 0.25,
                    "use_speaker_boost": True,
                },
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.content

    @staticmethod
    def play_mp3(audio: bytes) -> None:
        """Play an MP3 synchronously so volume restoration is deterministic."""
        path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as handle:
                handle.write(audio)
                path = handle.name
            if sys.platform == "darwin":
                command = ["afplay", path]
            elif sys.platform == "win32":
                escaped = path.replace("'", "''")
                command = [
                    "powershell", "-NoProfile", "-Command",
                    "Add-Type -AssemblyName presentationCore; "
                    f"$p=New-Object System.Windows.Media.MediaPlayer; $p.Open('{escaped}'); "
                    "$p.Play(); while(-not $p.NaturalDuration.HasTimeSpan){Start-Sleep -Milliseconds 50}; "
                    "Start-Sleep -Milliseconds $p.NaturalDuration.TimeSpan.TotalMilliseconds; $p.Close()",
                ]
            else:
                command = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path]
            subprocess.run(command, check=True)
        finally:
            if path:
                try:
                    os.unlink(path)
                except OSError:
                    pass

    def speak(self, text: str, voice_id: str, model_id: str) -> None:
        self.play_mp3(self.synthesize(text, voice_id, model_id))
