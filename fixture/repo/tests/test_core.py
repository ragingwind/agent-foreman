import os
import tempfile
import unittest

from stock.core import read_items


class ReadItems(unittest.TestCase):
    def test_rows_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "items.csv")
            with open(path, "w") as f:
                f.write("name,count\nbolts,12\nnuts,0\n")
            self.assertEqual(read_items(path), [{"name": "bolts", "count": 12}, {"name": "nuts", "count": 0}])


if __name__ == "__main__":
    unittest.main()
