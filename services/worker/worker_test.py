import unittest

from services.worker import worker


class WorkerTest(unittest.TestCase):
    def test_batch_size_is_respected(self):
        self.assertEqual(len(worker.process_batch(3)), 3)

    def test_records_use_the_shared_greeter(self):
        records = worker.process_batch(1, names=["nightly"])
        self.assertEqual(records[0], {"item": "nightly", "message": "hello, nightly!"})

    def test_main_returns_zero(self):
        self.assertEqual(worker.main(["--batch", "2"]), 0)


if __name__ == "__main__":
    unittest.main()
