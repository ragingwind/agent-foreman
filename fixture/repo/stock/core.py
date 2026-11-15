import csv


def read_items(path):
    """The items of a CSV file with the columns name and count, in file order."""
    with open(path, newline="", encoding="utf-8") as f:
        return [{"name": row["name"], "count": int(row["count"])} for row in csv.DictReader(f)]
