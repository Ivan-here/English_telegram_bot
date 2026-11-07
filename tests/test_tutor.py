import base64
import json
import unittest
from unittest.mock import patch

import httpx

from english_bot.config import Settings
from english_bot.tutor import QuotaExceeded, Tutor


class TutorTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tutor = Tutor(Settings('token', 'key', 'chat-model', 'audio-model', ':memory:', frozenset()))
        await self.tutor.client.aclose()
        self.requests = []
        self.status = 200
        self.parts = [{'text': 'Hello!'}]
        self.finish = 'STOP'

        def handle(request):
            self.requests.append(request)
            return httpx.Response(self.status, json={'candidates': [{'finishReason': self.finish, 'content': {'parts': self.parts}}]})

        self.tutor.client = httpx.AsyncClient(base_url='https://generativelanguage.googleapis.com/v1beta/', transport=httpx.MockTransport(handle))

    async def asyncTearDown(self):
        await self.tutor.close()

    async def test_history_and_feedback(self):
        history = [{'role': 'user', 'content': 'I go yesterday'}, {'role': 'assistant', 'content': 'Where?'}]
        self.parts = [{'text': 'private thinking', 'thought': True}, {'text': 'Try: I went yesterday.'}]
        self.assertEqual(await self.tutor.respond(history, 'A2', feedback=True), 'Try: I went yesterday.')
        body = json.loads(self.requests[0].content)
        self.assertEqual([c['role'] for c in body['contents']], ['user', 'model', 'user'])
        self.assertIn('A2', body['systemInstruction']['parts'][0]['text'])
        self.assertEqual(len(history), 2)

    async def test_ogg_transcription(self):
        self.parts = [{'text': '[NO_SPEECH]'}]
        self.assertEqual(await self.tutor.transcribe(b'ogg test'), '')
        body = json.loads(self.requests[0].content)
        audio = body['contents'][0]['parts'][1]['inlineData']
        self.assertEqual(audio['mimeType'], 'audio/ogg')
        self.assertEqual(base64.b64decode(audio['data']), b'ogg test')
        self.assertTrue(str(self.requests[0].url).endswith('models/audio-model:generateContent'))

    async def test_quota_failure(self):
        self.status = 429
        with self.assertRaises(QuotaExceeded):
            await self.tutor.respond([{'role': 'user', 'content': 'Hello'}], 'B1')
        self.assertEqual(len(self.requests), 1)

    async def test_incomplete_response_is_rejected(self):
        self.finish = 'MAX_TOKENS'
        with self.assertRaises(ValueError):
            await self.tutor.respond([{'role': 'user', 'content': 'Hello'}], 'B1')

    async def test_speech_is_local_and_makes_no_gemini_request(self):
        with patch.object(self.tutor.speaker, "synthesise", return_value=b"mp3 audio") as synthesise:
            self.assertEqual(await self.tutor.speech("Hello"), b"mp3 audio")
            synthesise.assert_called_once_with("Hello")
        self.assertEqual(self.requests, [])

    async def test_coaching_includes_original_examples_review_and_lesson_history(self):
        session = {
            "source": [{"role": "user", "content": "I has a plan."}],
            "review": "Use I have. Practice: rewrite your sentence.",
            "history": [{"role": "user", "content": "I have a plan."}, {"role": "assistant", "content": "Correct. Try she."}],
        }
        await self.tutor.coach(session, "She has a plan.", "B2")
        body = json.loads(self.requests[0].content)
        self.assertIn("I has a plan.", body["contents"][0]["parts"][0]["text"])
        self.assertEqual(body["contents"][1]["parts"][0]["text"], session["review"])
        self.assertEqual(body["contents"][-1]["parts"][0]["text"], "She has a plan.")
        self.assertEqual([turn["role"] for turn in body["contents"]], ["user", "model", "user", "model", "user"])
        self.assertIn("B2", body["systemInstruction"]["parts"][0]["text"])
