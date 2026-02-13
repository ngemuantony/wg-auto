#!/usr/bin/env bash
set -euo pipefail

WG_INTERFACE=${WG_INTERFACE:-wg0}
WG_BIN=${WG_BIN:-wg}

usage() {
  echo "Usage:"
  echo "  add <public_key> <allowed_ips>"
  echo "  remove <public_key>"
  echo "  list"
  exit 1
}

cmd="${1:-}"

if [[ -z "$cmd" ]]; then
  usage
fi

case "$cmd" in
  add)
    PUBLIC_KEY="${2:-}"
    ALLOWED_IPS="${3:-}"

    if [[ -z "$PUBLIC_KEY" || -z "$ALLOWED_IPS" ]]; then
      usage
    fi

    $WG_BIN set "$WG_INTERFACE" peer "$PUBLIC_KEY" allowed-ips "$ALLOWED_IPS"
    ;;

  remove)
    PUBLIC_KEY="${2:-}"

    if [[ -z "$PUBLIC_KEY" ]]; then
      usage
    fi

    $WG_BIN set "$WG_INTERFACE" peer "$PUBLIC_KEY" remove
    ;;

  list)
    $WG_BIN show "$WG_INTERFACE"
    ;;

  *)
    usage
    ;;
esac

#-------------------------------------------------------------------------------------------------------------------------------------
#CREATED AND MANTAINED BY:      DEVELOPER ANTONY
#                               developerantony98@gmail.com
#                  GitHub:      ngemuantony
#                  YouTube:     tispadmin
#                  Linkedin:    ngemuantony
#                  TikTok:      tispadmin                   

#-------------------------------------------------------------------------------------------------------------------------------------