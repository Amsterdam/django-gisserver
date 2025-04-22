#!/bin/sh

set -e

WFS_SERVER="${WFS_SERVER:-http://host.docker.internal:8000/wfs/}"

cat >/root/properties.xml <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE properties SYSTEM "http://java.sun.com/dtd/properties.dtd">
<properties version="1.0">
  <comment>Test run arguments (ets-wfs20)</comment>
  <entry key="wfs">${WFS_SERVER}?SERVICE=WFS&amp;REQUEST=GetCapabilities</entry>
</properties>
EOF

exec "$@"
