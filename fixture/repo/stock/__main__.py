import argparse
import sys

from stock.core import read_items


def main(argv=None):
    parser = argparse.ArgumentParser(prog="stock", description="Show what is on the shelf.")
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("list", help="list the items of a CSV file")
    show.add_argument("file")
    args = parser.parse_args(argv)
    for item in read_items(args.file):
        print(f"{item['name']}: {item['count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
