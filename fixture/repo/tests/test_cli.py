import io
import os
import unittest
from contextlib import redirect_stdout

from stock.__main__ import main

HERE = os.path.dirname(os.path.abspath(__file__))


class List(unittest.TestCase):
    def test_list(self):
        out = io.StringIO()
        with redirect_stdout(out):
            main(["list", os.path.join(HERE, "..", "items.csv")])
        self.assertEqual(out.getvalue().splitlines()[0], "bolts: 12")


if __name__ == "__main__":
    unittest.main()
