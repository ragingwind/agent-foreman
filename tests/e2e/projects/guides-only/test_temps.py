import unittest

from temps import summary


class Summary(unittest.TestCase):
    def test_three(self):
        self.assertEqual(summary([1.0, 3.0, 2.0]), (1.0, 3.0, 2.0))


if __name__ == "__main__":
    unittest.main()
