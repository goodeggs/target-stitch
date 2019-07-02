import unittest
import target_stitch
from target_stitch import StitchHandler, TargetStitchException, DEFAULT_STITCH_URL, ourSession, finish_requests
import io
import os
import json
import asyncio

def load_sample_lines(filename):
    with open('tests/' + filename) as fp:
        return [line for line in fp]

def token():
    token = os.getenv('TARGET_STITCH_TEST_TOKEN')
    if not token:
        raise Exception('Integration tests require TARGET_STITCH_TEST_TOKEN environment variable to be set')
    return token

class IntegrationTest(unittest.TestCase):
    def setUp(self):
        handler = StitchHandler(token(),
                                DEFAULT_STITCH_URL,
                                target_stitch.DEFAULT_MAX_BATCH_BYTES,
                                target_stitch.DEFAULT_MAX_BATCH_RECORDS)
        out = io.StringIO()
        self.target_stitch = target_stitch.TargetStitch(
            [handler], out, 4000000, 20000, 100000)

class TestRecordWithNullKeyProperty(IntegrationTest):

    def test(self):
        queue = load_sample_lines('record_missing_key_property.json')
        pattern = ('Error persisting data for table '
                   '"test_record_missing_key_property": '
                   'Record is missing key property id')
        with self.assertRaisesRegex(TargetStitchException, pattern):
            self.target_stitch.consume(queue)

class TestNoToken(unittest.TestCase):

    def setUp(self):
        token = None
        handler = StitchHandler(token,
                                DEFAULT_STITCH_URL,
                                target_stitch.DEFAULT_MAX_BATCH_BYTES,
                                target_stitch.DEFAULT_MAX_BATCH_RECORDS)
        out = io.StringIO()
        self.target_stitch = target_stitch.TargetStitch(
            [handler], out, 4000000, 20000, 100000)

    def test(self):
        queue = load_sample_lines('record_missing_key_property.json')
        pattern = 'Not Authorized'
        with self.assertRaisesRegex(TargetStitchException, pattern):
            self.target_stitch.consume(queue)

class AsyncPushToGate(unittest.TestCase):
    def setUp(self):
        token = None
        handler = StitchHandler(token,
                                DEFAULT_STITCH_URL,
                                target_stitch.DEFAULT_MAX_BATCH_BYTES,
                                2)
        self.out = io.StringIO()
        self.target_stitch = target_stitch.TargetStitch(
            [handler], self.out, 4000000, 2, 100000)
        self.queue = [json.dumps({"type": "SCHEMA", "stream": "chicken_stream",
                                  "key_properties": ["id"],
                                  "schema": {"type": "object",
                                             "properties": {"id": {"type": "integer"},
                                                            "name": {"type": "string"}}}})]
        make_fake_session(0, 200, {"status" : "you did it!"})

    # 2 requests both with state. in order.
    def test_2_requests_in_order(self):
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 1, "name": "Mike"}}))
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 1 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 2, "name": "Paul"}}))
        #will flush here after 2 records
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 2 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 3, "name": "Harrsion"}}))
        self.queue.append(json.dumps({"type":"STATE", "value":{"bookmarks":{"chicken_stream":{"id": 3 }}}}))
        self.queue.append(json.dumps({"type": "RECORD", "stream": "chicken_stream", "record": {"id": 4, "name": "Cathy"}}))
        #will flush here after 2 records

        self.target_stitch.consume(self.queue)
        finish_requests()

        emitted_state = list(map(json.loads, self.out.getvalue().strip().split('\n')))
        self.assertEqual(len(emitted_state), 2)
        self.assertEqual( emitted_state[0], {'bookmarks': {'chicken_stream': {'id': 1}}})
        self.assertEqual( emitted_state[1], {'bookmarks': {'chicken_stream': {'id': 3}}})


def make_fake_session(sleep_time, status, result_body):
    target_stitch.ourSession = FakeSession(sleep_time, status, result_body)

class FakeResponse:
    def __init__(self, sleep_time, status, result_body):
        self.status = status
        self.sleep_time = sleep_time
        self.result_body = result_body

    async def json(self):
        await asyncio.sleep(self.sleep_time)
        return self.result_body

class FakePost:
    def __init__(self, sleep_time, status, result_body):
        self.sleep_time = sleep_time
        self.status = status
        self.result_body = result_body

    async def __aenter__(self):
        return FakeResponse(self.sleep_time, self.status, self.result_body)

    async def __aexit__(self, exc_type, exc, tb):
        await asyncio.sleep(1)

class FakeSession:
    def __init__(self, sleep_time, status, result_body):
        self.sleep_time = sleep_time
        self.status = status
        self.result_body = result_body

    def post(self, url, *, data, **kwargs):
        return FakePost(self.sleep_time, self.status, self.result_body)

if __name__== "__main__":
    test1 = AsyncPushToGate()
    test1.setUp()
    test1.test_2_requests_in_order()



# set MAX_BATCH_RECORDs =1
# consume schema
# consume 1 record.
#         this will cause a flush()
#         this will cause StitchHandler.handle_batch()
#         will serialize the record
#         will call send()
#              asyncio.run_coroutine_threadsafe(post_coroutine)
#              future.add_done_callback( functools.partial(self.flush_states, state_writer))



# 2 requests last has state. first does not. in order
# 2 requests both with state. out of order return
# 2 requests both with state. in order. first errors
# 2 requests both with state. in order second errors
# 2 requests both with state. out of order. first errors
# 2 requests both with state. out of order. second errors
