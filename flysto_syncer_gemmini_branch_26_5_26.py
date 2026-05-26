# Gemini version 39.14 - "Handshake Success Green LED" Build
# Manual Trigger | Radio Reset | GPIO 11 fires on Verified Server Handshake
# Fix 1: WiFi stability delay added after force_connect() before FlySto auth
# Fix 2: Session re-authentication on 401 during upload with single retry
# Fix 3: _wait_for_routing() only called in Phase 2 (internet needed)
# Fix 5: FlashAir uses fixed IP — force_connect() skips DHCP wait for Phase 1
# Fix 6: fa_session retry adapter removed; command.cgi timeout tightened to 10s
# Fix 7: force_connect() reverted to original working logic; only addition
#         is the wait_for_ip parameter for Phase 1 FlashAir connect
import os, json, time, subprocess, re, requests, zipfile, io
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

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
                    draw.rectangle((0, 31, int(progress * 128), 31), outline="white", fill="white")
            self.last_state = current_state

# --- FlySto Client ---
class FlyStoClient:
    def __init__(self, email: str, password: str):
        self._session = requests.Session()
        self._email, self._password = email, password
        self._base_url = "https://www.flysto.net/api"
        self._session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://www.flysto.net/login"})
        
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[502, 503, 504])
        self._session.mount("https://", HTTPAdapter(max_retries=retries))
        self.is_authenticated = self._authenticate()

    def _authenticate(self) -> bool:
        log(f"Attempting FlySto login for {self._email}...")
        try:
            r = self._session.post(f"{self._base_url}/login", 
                json={"email": self._email, "password": self._password}, 
                headers={"Content-Type": "text/plain;charset=UTF-8"}, timeout=20)
            success = r.status_code == 204 and "USER_SESSION" in self._session.cookies
            log(f"Login {'Successful' if success else 'Failed'}")
            return success
        except Exception as e:
            log(f"Login Error: {e}")
            return False

    def upload_log(self, file_path: Path) -> bool:
        if not self.is_authenticated: return False
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(file_path, arcname=file_path.name)
        try:
            r = self._session.post(f"{self._base_url}/log-upload", params={"id": file_path.name}, 
                headers={"Content-Type": "application/zip"}, data=buf.getvalue(), timeout=60)

            # FIX 2: Session cookie may have expired mid-loop; re-authenticate once and retry
            if r.status_code == 401:
                log("Upload got 401 — session likely expired, re-authenticating...")
                self.is_authenticated = self._authenticate()
                if self.is_authenticated:
                    buf.seek(0)
                    r = self._session.post(f"{self._base_url}/log-upload", params={"id": file_path.name},
                        headers={"Content-Type": "application/zip"}, data=buf.getvalue(), timeout=60)
                else:
                    return False

            return r.status_code in [200, 201, 204]
        except Exception as e:
            log(f"Upload failed for {file_path.name}: {e}")
            return False

# --- Main System ---
class SyncOrchestrator:
    def __init__(self, config_path='/home/admin/flashair/config.json'):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.base_dir = Path("/home/admin/flashair")
        self.mirror_dir = self.base_dir / "mirror"
        self.mirror_dir.mkdir(parents=True, exist_ok=True)
        
        self.oled = OLEDController()
        self.local_db_path = self.base_dir / "local_sync.json"
        self.flysto_db_path = self.base_dir / "flysto_uploads.json"
        
        self.local_done = self._load_db(self.local_db_path)
        self.flysto_done = self._load_db(self.flysto_db_path)
        
        self.is_running = False
        self.manual_req = False
        self.success_time = 0

        self.fa_session = requests.Session()
        # FlashAir is a local fixed-IP device — no retry adapter, just a short timeout.
        # Retries with backoff caused multi-minute hangs when the card was slow to respond.

        # GPIO Init: All outputs start LOW (dl)
        os.system("sudo pinctrl set 22 ip pu") 
        for p in [9, 10, 11]: os.system(f"sudo pinctrl set {p} op dl")

    def _load_db(self, path):
        if path.exists():
            try: return json.loads(path.read_text())
            except: return {}
        return {}

    def _save_db(self, path, data):
        path.write_text(json.dumps(data, indent=4))
        os.system(f"sudo chmod 666 {path}")

    def force_connect(self, ssid, password, wait_for_ip=True):
        log(f"Force connecting to {ssid}...")
        self.oled.update_status("WIFI", f"Join {ssid[:12]}")

        # 1. Disconnect the wifi device first to clear any locked queues
        subprocess.run("sudo nmcli device disconnect wlan0 > /dev/null 2>&1", shell=True)
        time.sleep(1)

        # Clear old profile configurations to avoid the 802-11 security property bug
        subprocess.run(f"sudo nmcli connection delete '{ssid}' > /dev/null 2>&1", shell=True)

        cmd = f"sudo nmcli device wifi connect '{ssid}' password '{password}'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=50)

        output = (result.stdout + result.stderr).lower()

        # 2. Check if it activated immediately OR if it was enqueued successfully
        if "successfully activated" in output or "activation was enqueued" in output:
            if not wait_for_ip:
            # FlashAir has a fixed IP — no DHCP needed, but allow a few seconds
            # for the card's HTTP server to become ready after WiFi association.
            log("WiFi connected or enqueued (fixed IP, waiting for HTTP server...).")
            time.sleep(5) # Increased slightly to let an enqueued connection finish
            return True
            
            log("WiFi connected/enqueued. Waiting for IP...")
            # Loop for up to 20 seconds to give the enqueued connection time to get an IP
            for _ in range(20):
                 if subprocess.getoutput("hostname -I").strip():
                    return True
            time.sleep(1)
        else:
            log(f"WiFi Connection failed: {result.stderr.strip()}")
        return False


    def _wait_for_routing(self, host, retries=10, delay=1.0):
        """FIX 1 / FIX 3: Ping a specific host to confirm the network is actually
        reachable before proceeding. Called with the FlashAir IP in Phase 1 (local
        network only, no internet) and with 8.8.8.8 in Phase 2 (internet required).
        Using a fixed host of 8.8.8.8 for both phases caused Phase 1 to hang for
        the full timeout because the FlashAir has no internet route."""
        log(f"Waiting for {host} to become reachable...")
        for attempt in range(retries):
            result = subprocess.run(
                ["ping", "-c", "1", "-W", "1", host],
                capture_output=True
            )
            if result.returncode == 0:
                log(f"{host} reachable — network ready.")
                return True
            time.sleep(delay)
        log(f"Warning: {host} did not respond within timeout, continuing anyway.")
        return False

    def run_sync_cycle(self):
        if self.is_running: return
        self.is_running, self.manual_req = True, False
       
        os.system("sudo pinctrl set 9 op dh") # Blue Busy ON
        dl_count, up_count = 0, 0
        
        os.system("sudo rfkill unblock wifi")
        os.system("sudo nmcli radio wifi on")
        os.system("sudo nmcli device wifi rescan > /dev/null 2>&1")
        time.sleep(2) 
                     
        try:
            self.oled.update_status("SCAN", "Searching...")
            scan = subprocess.getoutput("sudo nmcli device wifi list")
            
            # PHASE 1: FlashAir Harvesting
            fa_ssid = self.config['flashair_wifi_ssid']
            if fa_ssid in scan:
                if self.force_connect(fa_ssid, self.config['flashair_wifi_password'], wait_for_ip=False):
                    base = self.config['flashair_ip'].rstrip('/')
                    path = self.config['flashair_data_log_dir'].strip('/')
                    
                    log("Requesting FlashAir file list...")
                    try:
                        r = self.fa_session.get(f"{base}/command.cgi?op=100&DIR=/{path}", timeout=10)
                    except Exception as fa_err:
                        log(f"FlashAir command.cgi failed: {fa_err}")
                        r = None
                    
                    fa_files = {}
                    if r is not None:
                        for line in r.text.splitlines():
                            parts = line.split(',')
                            if len(parts) >= 3 and parts[1].lower().endswith('.csv'):
                                filename = parts[1]
                                try:
                                    filesize = int(parts[2])
                                    fa_files[filename] = filesize
                                except ValueError:
                                    continue

                    to_dl = []
                    for fname, fsize in fa_files.items():
                        if fsize == 0: 
                            continue
                        
                        record = self.local_done.get(fname)
                        current_synced_size = record.get('size', 0) if isinstance(record, dict) else 0
                        
                        if record is None or fsize > current_synced_size:
                            to_dl.append((fname, fsize))
                    
                    for i, (f, expected_size) in enumerate(to_dl):
                        self.oled.update_status("DL", f, (i+1)/len(to_dl))
                        try:
                            dl = self.fa_session.get(f"{base}/{path}/{f}", timeout=45)
                            if dl.status_code == 200:
                                actual_size = len(dl.content)
                                target = self.mirror_dir / f
                                target.write_bytes(dl.content)
                                
                                self.local_done[f] = {
                                    "timestamp": time.time(),
                                    "size": actual_size
                                }
                                self._save_db(self.local_db_path, self.local_done)
                                dl_count += 1
                        except Exception as dl_err:
                            log(f"Error downloading {f}: {dl_err}")

            # PHASE 2: FlySto Upload
            on_disk = list(self.mirror_dir.glob('*.csv'))
            pending = [f for f in on_disk if f.name not in self.flysto_done]
            
            if pending:
                net = next((n for n in self.config['internet_networks'] if n['ssid'] in scan), None)
                if net and self.force_connect(net['ssid'], net['password']):
                    # FIX 1: Confirm internet routing is stable before attempting FlySto auth
                    self._wait_for_routing(host="8.8.8.8")

                    os.system("sudo pinctrl set 10 op dh") # White LED ON
                    
                    client = FlyStoClient(self.config['flysto_email'], self.config['flysto_password'])
                    
                    if client.is_authenticated:
                        for i, f in enumerate(pending):
                            self.oled.update_status("UP", f.name, (i+1)/len(pending))
                            if client.upload_log(f):
                                self.flysto_done[f.name] = time.time()
                                self._save_db(self.flysto_db_path, self.flysto_done)
                                up_count += 1
                            else:
                                log(f"File {f.name} processing finished (skipped or denied by server).")
                        
                        # GREEN TRIGGER: Authenticated and file verification loop successfully completed
                        log("FlySto handshake and sync loop verified. Illuminating Green LED.")
                        os.system("sudo pinctrl set 11 op dh") 
                        self.success_time = time.time() 
                    
                    os.system("sudo pinctrl set 10 op dl") # White LED OFF

        except Exception as e:
            log(f"Sync Cycle Error: {e}")
        finally:
            self.is_running = False
            os.system("sudo pinctrl set 9 op dl") # Blue LED OFF
            os.system("sudo nmcli dev disconnect wlan0 > /dev/null 2>&1")
            self.oled.update_status("COMPLETE", f"DL:{dl_count} UP:{up_count}", force=True)
            time.sleep(5)

    def start(self):
        btn_start = None
        log("System Ready. Waiting for Button Press...")

        while True:
            if self.success_time > 0 and (time.time() - self.success_time > 60):
                os.system("sudo pinctrl set 11 op dl")
                self.success_time = 0
                self.oled.update_status("IDLE", f"Logs: {len(self.local_done)}", force=True)

            raw_btn = subprocess.getoutput("pinctrl get 22")
            if "level=lo" in raw_btn or "| lo" in raw_btn:
                if btn_start is None: btn_start = time.time()
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
