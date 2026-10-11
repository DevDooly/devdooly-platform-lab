#!/bin/sh
set -eu

# Dynamic Nginx DNS does not expand resolv.conf search domains. Compose uses
# "api"; Kubernetes injects the namespace-qualified Service DNS name instead.
API_UPSTREAM_HOST="${API_UPSTREAM_HOST-api}"
case "$API_UPSTREAM_HOST" in
  ''|*[!A-Za-z0-9.-]*)
    echo 'API_UPSTREAM_HOST must be a DNS hostname without a port or special characters.' >&2
    exit 1
    ;;
esac
if ! printf '%s\n' "$API_UPSTREAM_HOST" | awk -F '[.]' '
  length($0) > 253 { exit 1 }
  {
    for (i = 1; i <= NF; i++) {
      if (length($i) > 63 || $i !~ /^[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?$/) exit 1
    }
  }
'; then
  echo 'API_UPSTREAM_HOST contains an invalid DNS hostname or label.' >&2
  exit 1
fi

DNS_RESOLVERS="$(awk '/^nameserver[[:space:]]/ { if ($2 ~ /:/) printf "[%s] ", $2; else printf "%s ", $2 }' /etc/resolv.conf)"
if [ -z "$DNS_RESOLVERS" ]; then
  echo 'No DNS resolver is available for the API upstream.' >&2
  exit 1
fi
export DNS_RESOLVERS API_UPSTREAM_HOST
envsubst '${DNS_RESOLVERS} ${API_UPSTREAM_HOST}' < /etc/nginx/nginx.conf.template > /tmp/nginx.conf
exec nginx -c /tmp/nginx.conf -g 'daemon off;'
