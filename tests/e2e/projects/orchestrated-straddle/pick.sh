#!/bin/sh
# pick.sh N: the Nth comma-separated column of each line on stdin.
cut -d, -f"$1"
