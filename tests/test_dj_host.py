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

    def test_never_frequency_never_schedules_speech(self):
        spotify = FakeSpotify()
        config = {
            "elevenlabs_api_key": "test-key",
            "dj_commentary_enabled": True,
            "dj_talking_frequency": "never",
        }
        host = DJHost(spotify, lambda: config, lambda *_: "line")
        for i in range(10):
            self.assertFalse(
                host.observe({"id": str(i), "name": "A", "artist": "One"}, None)
            )

    @patch("dj_host.threading.Thread", ImmediateThread)
    @patch("dj_host.ElevenLabsTTS")
    def test_normal_frequency_waits_until_third_track_change(self, tts_class):
        spotify = FakeSpotify()
        tts_class.return_value.synthesize.return_value = b"mp3"
        config = {
            "elevenlabs_api_key": "test-key",
            "dj_commentary_enabled": True,
            "dj_talking_frequency": "normal",
            "dj_duck_volume": 14,
        }
        host = DJHost(spotify, lambda: config, lambda *_: "line")
        self.assertFalse(host.observe({"id": "1", "name": "A", "artist": "X"}, None))
        self.assertFalse(host.observe({"id": "2", "name": "B", "artist": "X"}, None))
        self.assertTrue(host.observe({"id": "3", "name": "C", "artist": "X"}, None))
        tts_class.return_value.play_mp3.assert_called_once()

    def test_commentary_disabled_blocks_speech_regardless_of_frequency(self):
        spotify = FakeSpotify()
        config = {
            "elevenlabs_api_key": "test-key",
            "dj_commentary_enabled": False,
            "dj_talking_frequency": "high",
        }
        host = DJHost(spotify, lambda: config, lambda *_: "line")
        for i in range(5):
            self.assertFalse(
                host.observe({"id": str(i), "name": "A", "artist": "X"}, None)
            )

    @patch("dj_host.ElevenLabsTTS")
    def test_missing_api_key_skips_synthesis_and_never_ducks_volume(self, tts_class):
        spotify = FakeSpotify()
        config = {"elevenlabs_api_key": "  ", "dj_duck_volume": 10}
        host = DJHost(spotify, lambda: config, lambda *_: "line")
        host._speak_for_transition({"name": "A", "artist": "X"}, {}, config)
        tts_class.assert_not_called()
        self.assertEqual(spotify.volumes, [])
        self.assertFalse(host._speaking)

    @patch("dj_host.ElevenLabsTTS")
    def test_commentary_generator_error_falls_back_and_still_speaks(self, tts_class):
        spotify = FakeSpotify()
        tts_class.return_value.synthesize.return_value = b"mp3"
        config = {"elevenlabs_api_key": "key", "dj_duck_volume": 10}
        logs = []

        def bad_generator(*_args):
            raise RuntimeError("boom")

        host = DJHost(spotify, lambda: config, bad_generator, log=logs.append)
        host._speak_for_transition(
            {"name": "A", "artist": "One"}, {"name": "B", "artist": "Two"}, config
        )
        self.assertTrue(any("Commentary AI fallback" in m for m in logs))
        line_used = tts_class.return_value.synthesize.call_args[0][0]
        self.assertIn("Now playing A by One", line_used)
        tts_class.return_value.play_mp3.assert_called_once_with(b"mp3")
        self.assertFalse(host._speaking)

    @patch("dj_host.ElevenLabsTTS")
    def test_synthesis_error_leaves_volume_untouched_and_releases_lock(self, tts_class):
        spotify = FakeSpotify()
        tts_class.return_value.synthesize.side_effect = RuntimeError("network down")
        config = {"elevenlabs_api_key": "key", "dj_duck_volume": 10}
        host = DJHost(spotify, lambda: config, lambda *_: "line")
        host._speak_for_transition({"name": "A", "artist": "X"}, {}, config)
        self.assertEqual(spotify.volumes, [])
        self.assertFalse(host._speaking)


if __name__ == "__main__":
    unittest.main()
