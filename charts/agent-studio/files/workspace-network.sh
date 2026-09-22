#!/bin/sh
set -eu

# Runs inside the dedicated DinD Pod network namespace, never on the node.
bridge=ws-sandbox
ready=/workspace-network/ready
rm -f "$ready"
iptables -C INPUT -i "$bridge" -j REJECT 2>/dev/null || iptables -I INPUT 1 -i "$bridge" -j REJECT
iptables -t raw -C PREROUTING -i "$bridge" -j DROP 2>/dev/null || iptables -t raw -I PREROUTING 1 -i "$bridge" -j DROP

dockerd-entrypoint.sh "$@" &
daemon_pid=$!
trap 'kill -TERM "$daemon_pid" 2>/dev/null || true; wait "$daemon_pid" || true' EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
until docker info >/dev/null 2>&1; do
  kill -0 "$daemon_pid"
  sleep 1
done

if [ "$WORKSPACE_NETWORK" != none ]; then
  if ! docker network inspect "$WORKSPACE_NETWORK" >/dev/null 2>&1; then
    docker network create --driver bridge \
      --opt com.docker.network.bridge.name="$bridge" \
      --opt com.docker.network.bridge.enable_icc=false \
      "$WORKSPACE_NETWORK" >/dev/null
  fi
  actual=$(docker network inspect --format '{{.Driver}}|{{.Internal}}|{{.EnableIPv6}}|{{index .Options "com.docker.network.bridge.name"}}|{{index .Options "com.docker.network.bridge.enable_icc"}}' "$WORKSPACE_NETWORK")
  if [ "$actual" != "bridge|false|false|ws-sandbox|false" ]; then
    echo 'Workspace network has incompatible isolation settings' >&2
    exit 1
  fi

  # The raw-table guard survives Docker inserting its own FORWARD jumps.
  # Keep it until every egress rule is installed.
  # INPUT also rejects connections to the Docker API and other processes in this Pod.
  if iptables -nL STUDIO-EGRESS >/dev/null 2>&1; then
    iptables -F STUDIO-EGRESS
  else
    iptables -N STUDIO-EGRESS
  fi
  # Docker's embedded resolver forwards queries to the Pod's configured DNS.
  # Permit only DNS to those resolvers before rejecting internal destinations.
  for resolver in $(awk '$1 == "nameserver" { print $2 }' /etc/resolv.conf); do
    case "$resolver" in *:*) continue ;; esac
    iptables -A STUDIO-EGRESS -d "$resolver" -p udp --dport 53 -j RETURN
    iptables -A STUDIO-EGRESS -d "$resolver" -p tcp --dport 53 -j RETURN
  done
  for cidr in 0.0.0.0/8 10.0.0.0/8 100.64.0.0/10 127.0.0.0/8 \
    169.254.0.0/16 172.16.0.0/12 192.0.0.0/24 192.0.2.0/24 \
    192.168.0.0/16 198.18.0.0/15 198.51.100.0/24 203.0.113.0/24 \
    224.0.0.0/4 240.0.0.0/4; do
    iptables -A STUDIO-EGRESS -d "$cidr" -j REJECT
  done
  iptables -A STUDIO-EGRESS -p tcp -m multiport --dports 80,443 -j RETURN
  iptables -A STUDIO-EGRESS -j REJECT
  iptables -C DOCKER-USER -i "$bridge" -j STUDIO-EGRESS 2>/dev/null || iptables -I DOCKER-USER 1 -i "$bridge" -j STUDIO-EGRESS
fi
iptables -t raw -D PREROUTING -i "$bridge" -j DROP
touch "$ready"
wait "$daemon_pid"
