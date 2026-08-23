import unittest
from unittest.mock import Mock, patch

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


if __name__ == "__main__":
    unittest.main()
