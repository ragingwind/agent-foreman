import unittest

from invoice import total


class Total(unittest.TestCase):
    def test_tax(self):
        self.assertEqual(total([(2, 5.0), (1, 2.5)], 0.1), 13.75)


if __name__ == "__main__":
    unittest.main()
