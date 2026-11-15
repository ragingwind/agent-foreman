#!/bin/sh
# strtools.sh reverse|upper TEXT
case "$1" in
  reverse) printf '%s' "$2" | rev ;;
  upper) printf '%s' "$2" | tr '[:lower:]' '[:upper:]' ;;
  *) echo "usage: strtools.sh reverse|upper TEXT" >&2; exit 2 ;;
esac
