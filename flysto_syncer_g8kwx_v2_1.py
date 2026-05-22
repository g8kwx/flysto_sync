# FlySto Sync v40.0 - "Robust Scan" Build
# Fixes applied vs v39.2:
#   FIX 1: WiFi scan is now a live polled scan, not a stale snapshot.
#           scan_for_ssid() triggers a fresh rescan and polls until the
#           target SSID appears (or times out), replacing the single
#           upfront nmcli list call that was shared across both phases.
#   FIX 2: Internet hotspot scan is now done AFTER disconnecting from
#           FlashAir, using a fresh scan — not the original stale one.
#   FIX 3: force_connect() now retries up to MAX_CONNECT_RETRIES times
#           with a brief pause between attempts, and logs each failure.
#   FIX 4: upload_log() bare except replaced with logged Exception catch
#           so failed uploads are visible in the log.
#   FIX 5: WiFi interface reset now polls for link state UP before
#           proceeding, rather than relying on fixed sleep durations.
#   FIX 6: run_sync_cycle() exception handler now logs full traceback.

import os, json, time, subprocess, re, requests, zipfile, io, traceback
from pathlib import Path

# --- Tuning constants (adjust if needed) ---
MAX_CONNECT_RETRIES  = 3    # How many times force_connect() will retry
SCAN_POLL_ATTEMPTS   = 6    # How many times to poll for an SSID
SCAN_POLL_INTERVAL   = 3    # Seconds between each scan poll
IFACE_UP_POLL_MAX    = 10   # Max seconds to wait for wlan0 link UP
# -------------------------------------------

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --- OLED Handler (Flicker-Free) ---
class OLEDController:
    def __init__(self):
        try:
            from luma.oled.device import ssd1306
            from luma.core.interface.serial import i2c
            from luma.core.render import canvas
            serial = i2c(port=1, address=0x3C)
            self.device = ssd1306(serial, width=128, height=32)
            self.canvas = canvas
            self.last_state = None
            log("OLED Initialized.")
        except:
            log("OLED Init Failed.")
            self.device = None

    def update_status(self, mode, msg, progress=None, force=False):
        if not self.device: return
        current_state = f"{mode}-{msg}-{progress}"
        if current_state != self.last_state or force:
            with self.canvas(self.device) as draw:
                draw.text((0, -3), mode, fill="white")
                draw.text((0, 15), msg[:18], fill="white")
                if progress is not None:
                    draw.rectangle((0, 31, int(progress * 128), 31),
                                   outline="white", fill="white")
            self.last_state = current_state


# --- FlySto Client ---
class FlyStoClient:
    def __init__(self, email: str, password: str):
        self._session = requests.Session()
        self._email, self._password = email, password
        self._base_url = "https://www.flysto.net/api"
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.flysto.net/login"
        })
        self.is_authenticated = self._authenticate()

    def _authenticate(self) -> bool:
        log(f"Attempting FlySto login for {self._email}...")
        try:
            r = self._session.post(
                f"{self._base_url}/login",
                json={"email": self._email, "password": self._password},
                headers={"Content-Type": "text/plain;charset=UTF-8"},
                timeout=20
            )
            success = r.status_code == 204 and "USER_SESSION" in self._session.cookies
            log(f"Login {'Successful' if success else f'Failed (HTTP {r.status_code})'}")
            return success
        except Exception as e:
            log(f"Login Error: {e}")
            return False

    def upload_log(self, file_path: Path) -> bool:
        """
        FIX 4: Bare except replaced with logged Exception catch.
        Every failure reason now appears in the log.
        """
        if not self.is_authenticated:
            log(f"Upload skipped (not authenticated): {file_path.name}")
            return False
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(file_path, arcname=file_path.name)
        try:
            r = self._session.post(
                f"{self._base_url}/log-upload",
                params={"id": file_path.name},
                headers={"Content-Type": "application/zip"},
                data=buf.getvalue(),
                timeout=60
            )
            if r.status_code in [200, 201, 204]:
                log(f"Upload OK ({r.status_code}): {file_path.name}")
                return True
            else:
                log(f"Upload rejected (HTTP {r.status_code}): {file_path.name}")
                return False
        except Exception as e:
            # FIX 4: Log the actual reason rather than silently returning False
            log(f"Upload exception for {file_path.name}: {e}")
            return False


# --- Main System ---
class SyncOrchestrator:
    def __init__(self, config_path='/home/admin/flashair/config.json'):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        self.base_dir  = Path("/home/admin/flashair")
        self.mirror_dir = self.base_dir / "mirror"
        self.mirror_dir.mkdir(parents=True, exist_ok=True)
        self.oled = OLEDController()
        self.local_db_path  = self.base_dir / "local_sync.json"
        self.flysto_db_path = self.base_dir / "flysto_uploads.json"
        self.local_done  = self._load_db(self.local_db_path)
        self.flysto_done = self._load_db(self.flysto_db_path)
        self.is_running  = False
        self.manual_req  = False
        self.success_time = 0
        # GPIO Init
        os.system("sudo pinctrl set 22 ip pu")
        for p in [9, 10, 11]:
            os.system(f"sudo pinctrl set {p} op dl")

    def _load_db(self, path):
        if path.exists():
            try:
                return json.loads(path.read_text())
            except:
                return {}
        return {}

    def _save_db(self, path, data):
        path.write_text(json.dumps(data, indent=4))
        os.system(f"sudo chmod 666 {path}")

    def _wait_for_interface_up(self, iface="wlan0") -> bool:
        """
        FIX 5: Poll until the interface reports 'state UP', rather than
        relying on fixed sleep durations which are too short on a Pi Zero.
        Returns True when UP, False on timeout.
        """
        log(f"Waiting for {iface} link UP...")
        for _ in range(IFACE_UP_POLL_MAX):
            state = subprocess.getoutput(f"ip link show {iface}")
            if "state UP" in state:
                log(f"{iface} is UP.")
                return True
            time.sleep(1)
        log(f"Timeout waiting for {iface} UP.")
        return False

    def scan_for_ssid(self, ssid: str) -> bool:
        """
        FIX 1 & 2: Replaces the single upfront stale 'nmcli device wifi list'
        with a live polled scan. Triggers a fresh rescan each poll cycle and
        checks the result. Returns True as soon as the SSID is found.
        """
        log(f"Scanning for SSID: '{ssid}'...")
        for attempt in range(1, SCAN_POLL_ATTEMPTS + 1):
            os.system("sudo nmcli device wifi rescan > /dev/null 2>&1")
            time.sleep(SCAN_POLL_INTERVAL)
            scan_result = subprocess.getoutput("sudo nmcli device wifi list")
            if ssid in scan_result:
                log(f"SSID '{ssid}' found on attempt {attempt}.")
                return True
            log(f"  Attempt {attempt}/{SCAN_POLL_ATTEMPTS}: '{ssid}' not yet visible.")
        log(f"SSID '{ssid}' not found after {SCAN_POLL_ATTEMPTS} attempts.")
        return False

    def force_connect(self, ssid: str, password: str) -> bool:
        """
        FIX 3: Retries the connection up to MAX_CONNECT_RETRIES times.
        FIX 5: Uses _wait_for_interface_up() instead of bare sleeps.
        Each failure is logged with its reason.
        """
        for attempt in range(1, MAX_CONNECT_RETRIES + 1):
            log(f"Connecting to '{ssid}' (attempt {attempt}/{MAX_CONNECT_RETRIES})...")
            self.oled.update_status("WIFI", f"Join {ssid[:12]}")
            # Delete any stale profile then cycle the interface
            os.system(f"sudo nmcli connection delete '{ssid}' > /dev/null 2>&1")
            os.system("sudo ip link set wlan0 down")
            time.sleep(1)
            os.system("sudo ip link set wlan0 up")
            # FIX 5: Wait for interface to be genuinely UP before associating
            if not self._wait_for_interface_up():
                log(f"  Interface failed to come up on attempt {attempt}.")
                continue
            cmd = (f"sudo nmcli device wifi connect '{ssid}' "
                   f"password '{password}' name '{ssid}'")
            try:
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=50
                )
                stdout = result.stdout.lower()
                stderr = result.stderr.lower()
                if "successfully activated" in stdout:
                    log(f"  WiFi associated. Waiting for IP address...")
                    for _ in range(15):
                        if subprocess.getoutput("hostname -I").strip():
                            log(f"  IP acquired. Connected to '{ssid}'.")
                            return True
                        time.sleep(1)
                    log(f"  Associated but no IP on attempt {attempt}.")
                else:
                    # FIX 3: Log the actual nmcli error message
                    reason = (result.stderr.strip() or result.stdout.strip())[:120]
                    log(f"  nmcli failed on attempt {attempt}: {reason}")
            except subprocess.TimeoutExpired:
                log(f"  nmcli timed out on attempt {attempt}.")
            if attempt < MAX_CONNECT_RETRIES:
                log("  Pausing before retry...")
                time.sleep(3)
        log(f"All {MAX_CONNECT_RETRIES} connection attempts to '{ssid}' failed.")
        return False

    def run_sync_cycle(self):
        if self.is_running:
            return
        self.is_running, self.manual_req = True, False
        os.system("sudo pinctrl set 9 op dh")   # Blue Busy ON
        dl_count, up_count = 0, 0

        # Radio Reset Sequence
        os.system("sudo rfkill unblock wifi")
        os.system("sudo nmcli radio wifi on")

        try:
            # ----------------------------------------------------------------
            # PHASE 1: FlashAir Harvesting
            # FIX 1: scan_for_ssid() does a live polled scan rather than
            #        checking a single stale nmcli list snapshot.
            # ----------------------------------------------------------------
            self.oled.update_status("SCAN", "FlashAir...")
            fa_ssid = self.config['flashair_wifi_ssid']

            if self.scan_for_ssid(fa_ssid):
                if self.force_connect(fa_ssid, self.config['flashair_wifi_password']):
                    base = self.config['flashair_ip'].rstrip('/')
                    path = self.config['flashair_data_log_dir'].strip('/')
                    try:
                        r = requests.get(
                            f"{base}/command.cgi?op=100&DIR=/{path}", timeout=15
                        )
                        files = re.findall(r'([^,\s]+\.[cC][sS][vV])', r.text)
                        to_dl = [f for f in files if f not in self.local_done]
                        log(f"FlashAir: {len(files)} files on card, "
                            f"{len(to_dl)} new to download.")
                        for i, f in enumerate(to_dl):
                            self.oled.update_status("DL", f, (i + 1) / len(to_dl))
                            try:
                                dl = requests.get(
                                    f"{base}/{path}/{f}", timeout=45
                                )
                                if dl.status_code == 200:
                                    target = self.mirror_dir / f
                                    target.write_bytes(dl.content)
                                    self.local_done[f] = time.time()
                                    self._save_db(self.local_db_path, self.local_done)
                                    dl_count += 1
                                    log(f"  Downloaded: {f}")
                                else:
                                    log(f"  Download failed (HTTP {dl.status_code}): {f}")
                            except Exception as e:
                                log(f"  Download exception for {f}: {e}")
                    except Exception as e:
                        log(f"FlashAir directory listing failed: {e}")
                else:
                    log("Could not connect to FlashAir — skipping harvest phase.")
            else:
                log("FlashAir SSID not found — skipping harvest phase.")

            # Disconnect from FlashAir before scanning for internet
            os.system("sudo nmcli dev disconnect wlan0 > /dev/null 2>&1")
            time.sleep(2)

            # ----------------------------------------------------------------
            # PHASE 2: FlySto Upload
            # FIX 2: Scan for the hotspot AFTER disconnecting from FlashAir,
            #        using a fresh scan rather than the original stale one.
            # ----------------------------------------------------------------
            on_disk = list(self.mirror_dir.glob('*.csv'))
            pending = [f for f in on_disk if f.name not in self.flysto_done]
            log(f"Upload queue: {len(pending)} file(s) pending.")

            if pending:
                self.oled.update_status("SCAN", "Hotspot...")
                net = None
                for network in self.config['internet_networks']:
                    # FIX 2: Fresh live scan for each candidate network
                    if self.scan_for_ssid(network['ssid']):
                        net = network
                        break

                if net:
                    if self.force_connect(net['ssid'], net['password']):
                        os.system("sudo pinctrl set 10 op dh")  # White LED ON
                        client = FlyStoClient(
                            self.config['flysto_email'],
                            self.config['flysto_password']
                        )
                        if client.is_authenticated:
                            for i, f in enumerate(pending):
                                self.oled.update_status(
                                    "UP", f.name, (i + 1) / len(pending)
                                )
                                if client.upload_log(f):
                                    self.flysto_done[f.name] = time.time()
                                    self._save_db(
                                        self.flysto_db_path, self.flysto_done
                                    )
                                    up_count += 1
                            # GREEN TRIGGER: only if server confirmed at least one
                            if up_count > 0:
                                log(f"FlySto confirmed {up_count} file(s). "
                                    f"Setting Green LED.")
                                os.system("sudo pinctrl set 11 op dh")
                                self.success_time = time.time()
                        else:
                            log("FlySto authentication failed — upload skipped.")
                        os.system("sudo pinctrl set 10 op dl")  # White LED OFF
                    else:
                        log("Could not connect to any internet network — "
                            "upload skipped.")
                else:
                    log("No internet network found — upload skipped.")
            else:
                log("Nothing pending upload.")

        except Exception as e:
            # FIX 6: Log full traceback, not just the exception message
            log(f"Sync Cycle Error: {e}")
            log(traceback.format_exc())

        finally:
            self.is_running = False
            os.system("sudo pinctrl set 9 op dl")   # Blue LED OFF
            os.system("sudo nmcli dev disconnect wlan0 > /dev/null 2>&1")
            self.oled.update_status(
                "COMPLETE", f"DL:{dl_count} UP:{up_count}", force=True
            )
            log(f"Cycle complete. DL:{dl_count} UP:{up_count}")
            time.sleep(5)

    def start(self):
        btn_start = None
        log("System Ready. Waiting for Button Press...")
        while True:
            # Green LED Success Timeout (60 s)
            if self.success_time > 0 and (time.time() - self.success_time > 60):
                os.system("sudo pinctrl set 11 op dl")
                self.success_time = 0
                self.oled.update_status(
                    "IDLE", f"Logs: {len(self.local_done)}", force=True
                )

            # Button GPIO 22 logic
            raw_btn = subprocess.getoutput("pinctrl get 22")
            if "level=lo" in raw_btn or "| lo" in raw_btn:
                if btn_start is None:
                    btn_start = time.time()
                if (time.time() - btn_start) > 3.0:
                    self.oled.update_status("OFF", "SHUTDOWN...", force=True)
                    os.system("sudo poweroff")
                    return
            else:
                if btn_start is not None:
                    if (time.time() - btn_start) < 3.0 and not self.is_running:
                        log("Manual Sync Requested.")
                        self.manual_req = True
                    btn_start = None

            if self.manual_req:
                self.run_sync_cycle()

            if not self.is_running:
                self.oled.update_status("IDLE", f"Logs: {len(self.local_done)}")

            time.sleep(0.1)


if __name__ == "__main__":
    SyncOrchestrator().start()
