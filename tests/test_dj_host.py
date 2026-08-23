import unittest
from unittest.mock import patch

from dj_host import DJHost, choose_relative_request, compact_track, fallback_commentary


class FakeSpotify:
    def __init__(self):
        self.volume = 62
        self.volumes = []

    def get_volume(self):
        return self.volume

    def set_volume(self, value):
        self.volumes.append(value)
        self.volume = value


class ImmediateThread:
    def __init__(self, target, args=(), daemon=None):
        self.target = target
        self.args = args

    def start(self):
        self.target(*self.args)


class DJHostTests(unittest.TestCase):
    def test_compact_track_accepts_spotify_and_ui_shapes(self):
        raw = {
            "id": "1",
            "name": "Genesis",
            "artists": [{"name": "Justice"}],
            "album": {"name": "Cross"},
        }
        self.assertEqual(compact_track(raw)["artist"], "Justice")
        self.assertEqual(compact_track(raw)["album"], "Cross")

    def test_relative_request_is_grounded_in_current_session(self):
        result = choose_relative_request(
            "play something heavier",
            {"id": "1", "name": "Genesis", "artist": "Justice"},
            "French electronic music",
        )
        self.assertIn("current track is Genesis by Justice", result)
        self.assertIn("previous request", result)

    def test_absolute_request_is_unchanged(self):
        self.assertEqual(
            choose_relative_request("play Nina Simone", None, "jazz"),
            "play Nina Simone",
        )

    def test_fallback_mentions_current_and_next(self):
        text = fallback_commentary(
            {"name": "A", "artist": "One"},
            {"name": "B", "artist": "Two"},
            "warm",
        )
        self.assertIn("Now playing A by One", text)
        self.assertIn("B by Two", text)

    @patch("dj_host.threading.Thread", ImmediateThread)
    @patch("dj_host.ElevenLabsTTS")
    def test_high_frequency_speaks_and_restores_volume(self, tts_class):
        spotify = FakeSpotify()
        tts_class.return_value.synthesize.return_value = b"mp3"
        config = {
            "elevenlabs_api_key": "test-key",
            "dj_commentary_enabled": True,
            "dj_talking_frequency": "high",
            "dj_duck_volume": 14,
            "dj_voice_id": "voice",
            "dj_tts_model": "eleven_multilingual_v2",
            "dj_personality": "witty",
        }
        host = DJHost(spotify, lambda: config, lambda *_: "A short transition")
        spoke = host.observe(
            {"id": "one", "name": "A", "artist": "One"},
            {"id": "two", "name": "B", "artist": "Two"},
        )
        self.assertTrue(spoke)
        self.assertEqual(spotify.volumes, [14, 62])
        tts_class.return_value.play_mp3.assert_called_once_with(b"mp3")


if __name__ == "__main__":
    unittest.main()
