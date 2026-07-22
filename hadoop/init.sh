#!/bin/bash
# Patches Debian apt sources to the archive mirror (stretch packages are past
# EOL and the regular mirrors no longer serve them), installs python3 so
# Hadoop Streaming can execute Python mappers/reducers, then hands off to
# the container's real entrypoint.

sed -i 's|http://deb.debian.org/debian|http://archive.debian.org/debian|g'    /etc/apt/sources.list
sed -i 's|http://security.debian.org|http://archive.debian.org/debian-security|g' /etc/apt/sources.list

apt-get -o Acquire::Check-Valid-Until=false update -qq
apt-get install -y --no-install-recommends python3 python3-pip
rm -rf /var/lib/apt/lists/*

exec /run.sh
