#!/bin/sh
set -eu
DNS_RESOLVERS="$(awk '/^nameserver[[:space:]]/ { if ($2 ~ /:/) printf "[%s] ", $2; else printf "%s ", $2 }' /etc/resolv.conf)"
if [ -z "$DNS_RESOLVERS" ]; then
  echo 'No DNS resolver is available for the API upstream.' >&2
  exit 1
fi
export DNS_RESOLVERS
envsubst '${DNS_RESOLVERS}' < /etc/nginx/nginx.conf.template > /tmp/nginx.conf
exec nginx -c /tmp/nginx.conf -g 'daemon off;'
