import unittest

from scaler import scale


class Scale(unittest.TestCase):
    def test_double(self):
        self.assertEqual(scale(100, 2, 4), 200)

    def test_no_servings(self):
        with self.assertRaises(ValueError):
            scale(1, 0, 2)


if __name__ == "__main__":
    unittest.main()
