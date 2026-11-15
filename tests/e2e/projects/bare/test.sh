#!/bin/sh
set -e
[ "$(sh strtools.sh upper abc)" = "ABC" ]
[ "$(sh strtools.sh reverse abc)" = "cba" ]
echo ok
