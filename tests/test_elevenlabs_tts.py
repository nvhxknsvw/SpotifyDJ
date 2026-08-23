import unittest
from unittest.mock import Mock, patch

import requests

from elevenlabs_tts import ElevenLabsTTS


class ElevenLabsTests(unittest.TestCase):
    @patch("elevenlabs_tts.requests.get")
    def test_lists_only_female_voices(self, get):
        response = Mock()
        response.json.return_value = {"voices": [
            {"voice_id": "f", "name": "Female", "labels": {"gender": "female"}},
            {"voice_id": "m", "name": "Male", "labels": {"gender": "male"}},
        ]}
        get.return_value = response
        voices = ElevenLabsTTS("key").list_voices(female_only=True)
        self.assertEqual([voice.voice_id for voice in voices], ["f"])
        response.raise_for_status.assert_called_once()

    @patch("elevenlabs_tts.requests.post")
    def test_synthesis_uses_high_quality_model_and_mp3(self, post):
        response = Mock(content=b"audio")
        post.return_value = response
        result = ElevenLabsTTS("key").synthesize(
            "Hello", "voice", "eleven_multilingual_v2"
        )
        self.assertEqual(result, b"audio")
        _, kwargs = post.call_args
        self.assertEqual(kwargs["json"]["model_id"], "eleven_multilingual_v2")
        self.assertEqual(kwargs["params"]["output_format"], "mp3_44100_128")

    @patch("elevenlabs_tts.requests.post")
    def test_synthesize_without_api_key_raises_before_request(self, post):
        with self.assertRaises(ValueError):
            ElevenLabsTTS("").synthesize("hi", "voice")
        post.assert_not_called()

    @patch("elevenlabs_tts.requests.get")
    def test_list_voices_without_api_key_returns_empty_without_request(self, get):
        result = ElevenLabsTTS("").list_voices()
        self.assertEqual(result, [])
        get.assert_not_called()

    @patch("elevenlabs_tts.requests.get")
    def test_list_voices_propagates_http_errors(self, get):
        response = Mock()
        response.raise_for_status.side_effect = requests.HTTPError("401 Unauthorized")
        get.return_value = response
        with self.assertRaises(requests.HTTPError):
            ElevenLabsTTS("key").list_voices()

    @patch("elevenlabs_tts.requests.get")
    def test_voices_sorted_case_insensitively_with_default_name(self, get):
        response = Mock()
        response.json.return_value = {"voices": [
            {"voice_id": "b", "name": "bravo"},
            {"voice_id": "a", "name": "Alpha"},
            {"voice_id": "c"},
        ]}
        get.return_value = response
        voices = ElevenLabsTTS("key").list_voices()
        self.assertEqual([voice.name for voice in voices], ["Alpha", "bravo", "Unnamed voice"])


if __name__ == "__main__":
    unittest.main()
