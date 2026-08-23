"""Track-aware DJ commentary, speaking cadence, and music ducking."""

from __future__ import annotations

import threading
from typing import Callable, Optional

from elevenlabs_tts import ElevenLabsTTS


FREQUENCY_TRACK_INTERVALS = {
    "never": 0,
    "low": 5,
    "normal": 3,
    "high": 1,
}


def compact_track(track: Optional[dict]) -> dict:
    if not track:
        return {}
    artists = track.get("artists") or []
    artist = track.get("artist") or (artists[0].get("name", "") if artists else "")
    album = track.get("album") or {}
    if isinstance(album, dict):
        album = album.get("name", "")
    return {
        "id": track.get("id", ""),
        "name": track.get("name", ""),
        "artist": artist,
        "album": album,
    }


def fallback_commentary(current: dict, next_track: dict, personality: str) -> str:
    current_name = current.get("name") or "this one"
    artist = current.get("artist") or "the artist"
    if next_track:
        return (
            f"Now playing {current_name} by {artist}. Up next, "
            f"{next_track.get('name')} by {next_track.get('artist')}."
        )
    return f"You're listening to {current_name} by {artist}."


class DJHost:
    """Observes track changes and performs commentary without blocking the UI."""

    def __init__(
        self,
        spotify,
        config_loader: Callable[[], dict],
        commentary_generator: Callable[[dict, dict, str], str],
        log: Callable[[str], None] = print,
    ):
        self.spotify = spotify
        self.config_loader = config_loader
        self.commentary_generator = commentary_generator
        self.log = log
        self._last_track_id = ""
        self._changes_since_talk = 0
        self._speaking = False
        self._lock = threading.Lock()

    def observe(self, current: Optional[dict], next_track: Optional[dict]) -> bool:
        current = compact_track(current)
        next_track = compact_track(next_track)
        track_id = current.get("id")
        if not track_id or track_id == self._last_track_id:
            return False
        self._last_track_id = track_id
        self._changes_since_talk += 1

        config = self.config_loader()
        if not config.get("dj_commentary_enabled", True):
            return False
        interval = FREQUENCY_TRACK_INTERVALS.get(
            str(config.get("dj_talking_frequency", "normal")).lower(), 3
        )
        if not interval or self._changes_since_talk < interval:
            return False
        self._changes_since_talk = 0
        threading.Thread(
            target=self._speak_for_transition,
            args=(current, next_track, config),
            daemon=True,
        ).start()
        return True

    def speak_welcome(self, current: Optional[dict]) -> bool:
        """
        Speak an immediate greeting for a freshly started session (e.g. the
        Begin button), bypassing the normal talking-frequency gate — the
        listener just pressed a button, they expect to hear from the DJ now.
        """
        current = compact_track(current)
        if not current.get("id"):
            return False
        config = self.config_loader()
        if not config.get("dj_commentary_enabled", True):
            return False
        self._last_track_id = current["id"]
        self._changes_since_talk = 0
        threading.Thread(
            target=self._speak_for_transition,
            args=(current, {}, config),
            daemon=True,
        ).start()
        return True

    def _speak_for_transition(self, current: dict, next_track: dict, config: dict) -> None:
        with self._lock:
            if self._speaking:
                return
            self._speaking = True
        original_volume = -1
        try:
            api_key = str(config.get("elevenlabs_api_key", "")).strip()
            if not api_key:
                return
            personality = str(config.get("dj_personality", "Warm and concise"))
            try:
                line = self.commentary_generator(current, next_track, personality).strip()
            except Exception as exc:
                self.log(f"Commentary AI fallback: {exc}")
                line = fallback_commentary(current, next_track, personality)
            if not line:
                return
            line = line[:420]
            tts = ElevenLabsTTS(api_key)
            audio = tts.synthesize(
                line,
                str(config.get("dj_voice_id", "21m00Tcm4TlvDq8ikWAM")),
                str(config.get("dj_tts_model", "eleven_multilingual_v2")),
            )
            original_volume = self.spotify.get_volume()
            duck_volume = max(0, min(100, int(config.get("dj_duck_volume", 18))))
            if original_volume >= 0:
                self.spotify.set_volume(min(original_volume, duck_volume))
            self.log(f'DJ: "{line}"')
            tts.play_mp3(audio)
        except Exception as exc:
            self.log(f"DJ voice error: {exc}")
        finally:
            if original_volume >= 0:
                try:
                    self.spotify.set_volume(original_volume)
                except Exception as exc:
                    self.log(f"Could not restore Spotify volume: {exc}")
            self._speaking = False


def choose_relative_request(request: str, current: Optional[dict], previous_request: str) -> str:
    """Ground short relative commands in what is playing and the prior request."""
    lowered = request.lower()
    relative_words = (
        "heavier", "lighter", "faster", "slower", "harder", "softer",
        "darker", "brighter", "more like", "less like", "same vibe",
    )
    if not any(word in lowered for word in relative_words):
        return request
    track = compact_track(current)
    context = []
    if previous_request:
        context.append(f'previous request was "{previous_request}"')
    if track:
        context.append(f"current track is {track['name']} by {track['artist']}")
    return f"{request}. Context: {'; '.join(context)}." if context else request
