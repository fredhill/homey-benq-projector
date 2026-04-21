import asyncio
import ipaddress
import json
import re
import socket
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from homey.driver import Driver, ListDeviceProperties


# ──────────────────────────────────────────────
# Helpers (module-level so they run cleanly in threads)
# ──────────────────────────────────────────────

def _strip_trailing_commas(text):
    """BenQ sends invalid JSON with trailing commas — strip them."""
    return re.sub(r',\s*([}\]])', r'\1', text)


def _verify_benq(ip, timeout=2):
    """
    Return (True, status_dict) if device at `ip` is a BenQ projector,
    (False, None) otherwise.
    """
    try:
        url = f"http://{ip}/cgi-bin/webctrl.cgi.elf?&t:26,c:12,p:1049576"
        r = requests.post(url, timeout=timeout)
        data = json.loads(_strip_trailing_commas(r.text))[0]
        return ('nPowerStatus' in data), data
    except Exception:
        return False, None


def _get_local_ip():
    """Return the local machine's primary IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def _discover_amx(timeout=2):
    """
    Listen for BenQ AMX Device Discovery broadcasts (UDP port 9131).
    Fast (~2s) but only works if AMX is enabled on the projector.
    """
    found = []
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)
        sock.bind(('', 9131))
        try:
            while True:
                _, addr = sock.recvfrom(1024)
                ip = addr[0]
                if ip not in found:
                    found.append(ip)
        except socket.timeout:
            pass
    except Exception:
        pass
    finally:
        try:
            sock.close()
        except Exception:
            pass
    return found


def _scan_subnet(per_host_timeout=1, max_workers=50):
    """
    Scan the local /24 subnet concurrently for BenQ projectors.
    Slower (~10-20s) but works regardless of AMX setting.
    """
    local_ip = _get_local_ip()
    if not local_ip:
        return []

    network = ipaddress.IPv4Network(f"{local_ip}/24", strict=False)
    found = []

    def check(ip_str):
        ok, _ = _verify_benq(ip_str, timeout=per_host_timeout)
        return ip_str if ok else None

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(check, str(ip)): ip for ip in network.hosts()}
            for future in as_completed(futures, timeout=25):
                try:
                    result = future.result(timeout=0)
                    if result:
                        found.append(result)
                except Exception:
                    pass
    except Exception:
        pass

    return found


# ──────────────────────────────────────────────
# Driver
# ──────────────────────────────────────────────

class BenQSH915Driver(Driver):

    async def on_init(self):
        await super().on_init()
        self.log("BenQ projector driver initialized")

    async def on_pair_list_devices(self, view_data):
        self.log("Starting BenQ projector discovery...")
        loop = asyncio.get_event_loop()

        # Stage 1: AMX UDP (~2s — fast path)
        amx_ips = await loop.run_in_executor(None, _discover_amx, 2)
        self.log(f"AMX discovery: {amx_ips if amx_ips else 'none found'}")

        # Stage 2: Subnet scan only if AMX came up empty
        if amx_ips:
            candidate_ips = amx_ips
        else:
            self.log("No AMX results — scanning subnet (may take ~15s)...")
            candidate_ips = await loop.run_in_executor(None, _scan_subnet, 1, 50)
            self.log(f"Subnet scan: {candidate_ips if candidate_ips else 'none found'}")

        # Verify each candidate and build device list
        devices = []
        for ip in candidate_ips:
            ok, status = await loop.run_in_executor(None, _verify_benq, ip, 3)
            if ok and status:
                name = status.get('acProjectorName', 'BenQ Projector')
                fw = status.get('acProjectorFWVersion', '?')
                self.log(f"Confirmed: {name} at {ip} (FW {fw})")
                devices.append({
                    "name": f"{name} ({ip})",
                    "data": {"id": f"benq-{ip.replace('.', '-')}"},
                    "settings": {
                        "ip_address": ip,
                        "poll_interval": 120,
                        "lamp_warning_hours": 3000,
                        "network_standby": True,
                    },
                })

        # Always provide a fallback so the user can still add manually
        if not devices:
            self.log("No projectors found automatically — adding fallback entry")
            devices.append({
                "name": "BenQ Projector (set correct IP in settings if needed)",
                "data": {"id": "benq-sh915"},
                "settings": {
                    "ip_address": "10.50.0.29",
                    "poll_interval": 120,
                    "lamp_warning_hours": 3000,
                    "network_standby": True,
                },
            })

        return devices


homey_export = BenQSH915Driver
