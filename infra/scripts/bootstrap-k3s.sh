#!/usr/bin/env bash
# Fresh K3s only. No package upgrades, Docker/UFW edits or secret output.
set -Eeuo pipefail
set +x
umask 077
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export LC_ALL=C LANG=C LANGUAGE=C

MODE=
NODE_IP=
while [[ $# -gt 0 ]]; do
  case "$1" in
    --check|--apply) [[ -z "$MODE" ]] || { echo 'Choose one mode.' >&2; exit 2; }; MODE="$1"; shift ;;
    --node-ip) [[ $# -ge 2 ]] || exit 2; NODE_IP="$2"; shift 2 ;;
    *) echo 'Usage: sudo bash k3s-bootstrap.sh --check|--apply --node-ip PRIVATE_IPV4' >&2; exit 2 ;;
  esac
done
[[ -n "$MODE" && -n "$NODE_IP" ]] || { echo 'Mode and --node-ip are required.' >&2; exit 2; }
[[ "$EUID" -eq 0 ]] || { echo 'Run this reviewed script with sudo; it never changes sudoers.' >&2; exit 1; }

K3S_VERSION='v1.36.5+k3s1'
K3S_SHA='d73847bcd3c5fccef0115b372e2f9a91f3032dc84bbf71518a4617565294d313'
INSTALLER_SHA='46177d4c99440b4c0311b67233823a8e8a2fc09693f6c89af1a7161e152fbfad'
CHECKSUM_LIST_SHA='ee5fa48dfc2f3d3e521170bfb52c5dd44365ac734c23857a664c27109ae2ce9a'
RELEASE_URL='https://github.com/k3s-io/k3s/releases/download/v1.36.5%2Bk3s1'
INSTALLER_URL='https://raw.githubusercontent.com/k3s-io/k3s/v1.36.5%2Bk3s1/install.sh'
DATA_DIR='/var/lib/devdooly-platform-lab/k3s'
STORAGE_DIR='/var/lib/devdooly-platform-lab/storage'
BACKUP=
START_REQUESTED=false

die() { printf 'STOP: %s\n' "$1" >&2; on_error 1; }
on_error() {
  local status="$1"
  trap - ERR
  if [[ "$START_REQUESTED" == true ]]; then systemctl stop k3s >/dev/null 2>&1 || true; fi
  printf 'K3s preparation failed. New files are retained; no uninstall or firewall restore was run.\n' >&2
  [[ -z "$BACKUP" ]] || printf 'Private review directory: %s\n' "$BACKUP" >&2
  exit "$status"
}
trap 'on_error "$?"' ERR

for tool in python3 curl sha256sum ip ss systemctl ufw docker tar install stat df awk grep timeout sysctl uname date bash cmp iptables-save ip6tables-save; do
  command -v "$tool" >/dev/null || die "Missing prerequisite command: $tool"
done
[[ -r /etc/os-release && -d /run/systemd/system ]] || die 'Expected Ubuntu with systemd.'
. /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 22.04 ]] || die 'This reviewed bootstrap targets Ubuntu 22.04 only.'
[[ "$(uname -m)" == x86_64 ]] || die 'Only the pinned amd64 release is allowed.'
[[ "$(sysctl -n net.ipv4.ip_forward)" == 1 ]] || die 'IP forwarding is not already enabled; review separately.'

for existing in /etc/rancher/k3s /var/lib/rancher/k3s /run/k3s /etc/kubernetes \
  /var/lib/kubelet /etc/cni/net.d /var/lib/cni /var/lib/devdooly-platform-lab "$DATA_DIR" "$STORAGE_DIR" \
  /usr/local/bin/k3s /usr/local/bin/k3s-uninstall.sh /usr/local/bin/k3s-killall.sh \
  /etc/systemd/system/k3s.service /etc/systemd/system/k3s.service.env \
  /etc/systemd/system/k3s.service.d /etc/default/k3s /etc/sysconfig/k3s; do
  [[ ! -e "$existing" && ! -L "$existing" ]] || die "Existing Kubernetes path requires review: $existing"
done
command -v k3s >/dev/null && die 'Existing k3s executable found in PATH.'
[[ -z "$(systemctl list-unit-files 'k3s*' --no-legend --no-pager)" ]] || die 'Existing K3s systemd unit found.'
for parent in /etc/rancher /var/lib/devdooly-platform-lab /var/backups/devdooly-platform-lab; do
  [[ ! -L "$parent" ]] || die "Symlinked destination parent: $parent"
  if [[ -e "$parent" ]]; then
    [[ "$(stat -c %u "$parent")" == 0 ]] || die "Destination parent is not root-owned: $parent"
    [[ "$(stat -c %a "$parent")" =~ ^[0-7]*[0145][0145]$ ]] || die "Destination parent is group/other writable: $parent"
  fi
done

# These exact ports must be unused; 80/443 and existing application ports are untouched.
for port in 6443 6444 10248 10249 10250 10256 10257 10258 10259 10010; do
  [[ -z "$(ss -H -lnt "sport = :$port")" ]] || die "Required TCP port is already occupied: $port"
done
[[ -z "$(ss -H -lnu 'sport = :8472')" ]] || die 'VXLAN UDP 8472 is already occupied.'
ufw status | grep -q '^Status: active$' || die 'Expected existing active UFW; do not expose a new API without review.'
ufw status verbose | grep -q 'Default: deny (incoming)' || die 'Expected existing UFW incoming deny policy.'
systemctl is-active --quiet docker || die 'Expected existing Docker to be active.'
systemctl is-active --quiet containerd || die 'Expected existing containerd to be active.'
[[ "$(df -Pk /var/lib | awk 'NR==2 {print $4}')" -ge 52428800 ]] || die 'Less than 50GiB free under /var/lib.'
[[ "$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)" -ge 8388608 ]] || die 'Less than 8GiB currently available RAM.'

# No shell expansion of the supplied address. No full Docker inspect or environment reads.
python3 - "$NODE_IP" <<'PY'
import ipaddress, json, subprocess, sys
node = ipaddress.ip_address(sys.argv[1])
private = [ipaddress.ip_network(c) for c in ['10.0.0.0/8','172.16.0.0/12','192.168.0.0/16']]
assert node.version == 4 and any(node in n for n in private), 'Expected a private IPv4 node address'
addresses = json.loads(subprocess.check_output(['ip','-j','-4','address','show'], text=True))
assert str(node) in [a['local'] for i in addresses for a in i.get('addr_info',[])], 'Node IP not assigned locally'
targets = [ipaddress.ip_network(c) for c in ['10.42.0.0/16','10.43.0.0/16']]
observed = []
for route in json.loads(subprocess.check_output(['ip','-j','-4','route','show','table','all'], text=True)):
    dst=route.get('dst')
    if dst and dst != 'default':
        observed.append(ipaddress.ip_network(dst, strict=False))
networks = subprocess.check_output(['docker','network','ls','-q'], text=True).split()
for network in networks:
    value = subprocess.check_output(['docker','network','inspect','--format',
      '{{json .IPAM.Config}}',network], text=True)
    for item in json.loads(value) or []:
        parsed=ipaddress.ip_network(item['Subnet'], strict=False)
        if parsed.version == 4:
            observed.append(parsed)
assert not any(t.overlaps(n) for t in targets for n in observed), 'Lab CIDR conflicts with an existing route/Docker subnet'
PY
printf 'Preflight passed: fresh Ubuntu amd64 target, ports/CIDRs/resources and existing Docker/UFW checked.\n'
if [[ "$MODE" == --check ]]; then
  printf 'Read-only check completed. No downloads, backups or host changes performed.\n'
  exit 0
fi

# From this point --apply writes only new Lab paths, new K3s binary/unit and private backups.
install -d -o root -g root -m 0700 /var/backups/devdooly-platform-lab
BACKUP="/var/backups/devdooly-platform-lab/$(date -u +%Y%m%dT%H%M%SZ)-$$"
install -d -o root -g root -m 0700 "$BACKUP"
if [[ -e /etc/rancher ]]; then
  tar -cpf "$BACKUP/rancher-before.tar" -C / etc/rancher
else
  printf 'ABSENT\n' > "$BACKUP/rancher-before.txt"
fi
tar -cpf "$BACKUP/systemd-before.tar" -C / etc/systemd/system
tar -cpf "$BACKUP/ufw-before.tar" -C / etc/ufw etc/default/ufw
ip -j address show > "$BACKUP/ip-address-before.json"
ip -j route show table all > "$BACKUP/routes-before.json"
ss -lntup > "$BACKUP/listeners-before.txt"
ufw status verbose > "$BACKUP/ufw-before.txt"
systemctl list-units --type=service --all --no-pager > "$BACKUP/services-before.txt"
iptables-save > "$BACKUP/iptables-before.txt"
ip6tables-save > "$BACKUP/ip6tables-before.txt"
if command -v nft >/dev/null; then nft list ruleset > "$BACKUP/nft-before.txt"; fi
docker ps --no-trunc --format '{{.ID}} {{.State}}' > "$BACKUP/docker-before.txt"
docker ps -q --no-trunc > "$BACKUP/docker-running-ids.txt"

curl --proto '=https' --tlsv1.2 -fsSL --retry 2 --connect-timeout 20 --max-time 600 \
  "$RELEASE_URL/sha256sum-amd64.txt" -o "$BACKUP/sha256sum-amd64.txt"
curl --proto '=https' --tlsv1.2 -fsSL --retry 2 --connect-timeout 20 --max-time 600 \
  "$RELEASE_URL/k3s" -o "$BACKUP/k3s"
curl --proto '=https' --tlsv1.2 -fsSL --retry 2 --connect-timeout 20 --max-time 120 \
  "$INSTALLER_URL" -o "$BACKUP/install.sh"
printf '%s  %s\n' "$CHECKSUM_LIST_SHA" "$BACKUP/sha256sum-amd64.txt" | sha256sum --check --status
printf '%s  %s\n' "$K3S_SHA" "$BACKUP/k3s" | sha256sum --check --status
printf '%s  %s\n' "$INSTALLER_SHA" "$BACKUP/install.sh" | sha256sum --check --status
[[ "$(awk '$2=="k3s" {print $1}' "$BACKUP/sha256sum-amd64.txt")" == "$K3S_SHA" ]] || die 'Release checksum entry mismatch.'
bash -n "$BACKUP/install.sh"

# Original /etc/rancher and systemd/UFW state are backed up before creation.
if [[ ! -d /etc/rancher ]]; then install -d -o root -g root -m 0755 /etc/rancher; fi
install -d -o root -g root -m 0700 /etc/rancher/k3s /var/lib/devdooly-platform-lab "$DATA_DIR" "$STORAGE_DIR"
cat > "$BACKUP/config.yaml" <<EOF
data-dir: "$DATA_DIR"
default-local-storage-path: "$STORAGE_DIR"
write-kubeconfig-mode: "0600"
secrets-encryption: true
bind-address: "$NODE_IP"
advertise-address: "$NODE_IP"
node-ip: "$NODE_IP"
tls-san:
  - "127.0.0.1"
cluster-cidr: "10.42.0.0/16"
service-cidr: "10.43.0.0/16"
disable:
  - traefik
  - servicelb
EOF
install -o root -g root -m 0600 "$BACKUP/config.yaml" /etc/rancher/k3s/config.yaml
install -o root -g root -m 0755 "$BACKUP/k3s" /usr/local/bin/k3s

# Skip the installer's start path, which otherwise rebuilds iptables rules.
# Empty environment prevents inherited tokens, remote-runtime or proxy settings.
env -i PATH="$PATH" HOME=/root \
  INSTALL_K3S_VERSION="$K3S_VERSION" INSTALL_K3S_SKIP_DOWNLOAD=true \
  INSTALL_K3S_SKIP_ENABLE=true INSTALL_K3S_SKIP_START=true \
  INSTALL_K3S_SYMLINK=skip INSTALL_K3S_SKIP_SELINUX_RPM=true \
  INSTALL_K3S_BIN_DIR=/usr/local/bin INSTALL_K3S_SYSTEMD_DIR=/etc/systemd/system \
  INSTALL_K3S_EXEC=server sh "$BACKUP/install.sh" > "$BACKUP/installer.log" 2>&1
sha256sum /etc/rancher/k3s/config.yaml /etc/systemd/system/k3s.service \
  /etc/systemd/system/k3s.service.env /usr/local/bin/k3s > "$BACKUP/installed-sha256.txt"
[[ "$(stat -c %a /etc/rancher/k3s/config.yaml)" == 600 ]] || die 'K3s config must remain 0600.'
systemctl daemon-reload
systemctl enable k3s > "$BACKUP/enable.log" 2>&1
START_REQUESTED=true
timeout 180 systemctl start k3s > "$BACKUP/start.log" 2>&1

systemctl is-active --quiet docker || die 'Existing Docker is no longer active; investigate private backups.'
systemctl is-active --quiet containerd || die 'Existing containerd is no longer active; investigate private backups.'
while IFS= read -r container_id; do
  [[ -z "$container_id" ]] && continue
  [[ "$(docker inspect --format '{{.State.Running}}' "$container_id")" == true ]] || die 'An existing container stopped; investigate without deleting data.'
done < "$BACKUP/docker-running-ids.txt"
docker ps --no-trunc --format '{{.ID}} {{.State}}' > "$BACKUP/docker-after.txt"
ufw status verbose > "$BACKUP/ufw-after.txt"
cmp --silent "$BACKUP/ufw-before.txt" "$BACKUP/ufw-after.txt" || die 'UFW policy unexpectedly changed.'
printf 'New K3s service started. Private audit directory: %s\n' "$BACKUP"
printf 'Pod API/DNS/egress, node readiness and existing application HTTP checks remain required.\n'
printf 'No UFW edits, Docker restarts, Helm replacement or application data backups were performed.\n'
