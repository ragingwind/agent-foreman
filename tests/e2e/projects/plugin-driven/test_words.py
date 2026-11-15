import unittest

from words import count


class Count(unittest.TestCase):
    def test_spaces(self):
        self.assertEqual(count("  one two\nthree "), 3)


if __name__ == "__main__":
    unittest.main()
