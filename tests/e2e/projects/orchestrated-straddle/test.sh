#!/bin/sh
set -e
[ "$(printf 'a,b,c\n1,2,3\n' | sh pick.sh 2 | tr '\n' ' ')" = "b 2 " ]
echo ok
