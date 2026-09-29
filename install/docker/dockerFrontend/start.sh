#!/bin/bash
mkdir -p /data/log/nginx
sed -i 's/APP_ROOT/${APP_ROOT}/' /etc/nginx/conf.d/default.conf 2>/dev/null || true
nginx -g "daemon off;"
