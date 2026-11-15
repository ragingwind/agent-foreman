import unittest

from tip import split


class Split(unittest.TestCase):
    def test_three_ways(self):
        self.assertEqual(split(30, 3, 10), 11.0)


if __name__ == "__main__":
    unittest.main()
