# This feature adds a clear confirmation system. By introducing a tracking flag (`flashair_read_success`), the code can now distinguish between a failed connection and a clean, successful read that simply found no new data.

### Updated Green LED (GPIO 11) Logic Rules

* **Condition 1 (New Uploads):** Fired if FlySto accepts your credentials **and** at least one new log file (`up_count > 0`) is successfully transmitted to the cloud.
* **Condition 2 (No New Logs):** Fired if the native `curl` engine successfully connects to and parses the FlashAir directory loop, notices that your local mirror is already up to date, and finds 0 bytes of outstanding data to pull.

Both situations now latch the system clock via `self.success_time` to keep the Green LED illuminated for exactly 60 seconds before automatically turning off.

### Updated Code


# Gemini version 40.2 - "Dual-Condition Green LED Validation" Build
import os, json, time, subprocess, re, requests, zipfile, io
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

def log(msg):
    print("[" + time.strftime("%H:%M:%S") + "] " + str(msg), flush=True)

# --- OLED Handler ---
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
        current_state = str(mode) + "-" + str(msg) + "-" + str(progress)
        if current_state != self.last_state or force:
            with self.canvas(self.device) as draw:
                draw.text((0, -3), str(mode), fill="white")
                draw.text((0, 15), str(msg)[:18], fill="white")
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
        log("Attempting FlySto login for " + str(self._email) + "...")
        try:
            r = self._session.post(self._base_url + "/login", 
                json={"email": self._email, "password": self._password}, 
                headers={"Content-Type": "text/plain;charset=UTF-8"}, timeout=20)
            success = r.status_code == 204 and "USER_SESSION" in self._session.cookies
            log("Login Successful" if success else "Login Failed")
            return success
        except Exception as e:
            log("Login Error: " + str(e))
            return False

    def upload_log(self, file_path: Path) -> bool:
        if not self.is_authenticated: return False
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
            z.write(file_path, arcname=file_path.name)
        try:
            r = self._session.post(self._base_url + "/log-upload", params={"id": file_path.name}, 
                headers={"Content-Type": "application/zip"}, data=buf.getvalue(), timeout=60)

            if r.status_code == 401:
                log("Upload got 401 — session likely expired, re-authenticating...")
                self.is_authenticated = self._authenticate()
                if self.is_authenticated:
                    buf.seek(0)
                    r = self._session.post(self._base_url + "/log-upload", params={"id": file_path.name},
                        headers={"Content-Type": "application/zip"}, data=buf.getvalue(), timeout=60)
                else:
                    return False

            return r.status_code in [200, 201, 204]
        except Exception as e:
            log("Upload failed for " + str(file_path.name) + ": " + str(e))
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

        os.system("sudo pinctrl set 22 ip pu") 
        for p in [9, 10, 11]: os.system("sudo pinctrl set " + str(p) + " op dl")

    def _load_db(self, path):
        if path.exists():
            try: return json.loads(path.read_text())
            except: return {}
        return {}

    def _save_db(self, path, data):
        path.write_text(json.dumps(data, indent=4))
        os.system("sudo chmod 666 " + str(path))

    def force_connect(self, ssid, password, is_flashair=False):
        log("Force connecting to " + str(ssid) + "...")
        self.oled.update_status("WIFI", "Join " + str(ssid[:12]))
        
        subprocess.run("sudo nmcli connection delete '" + str(ssid) + "' > /dev/null 2>&1", shell=True)
        
        cmd = "sudo nmcli device wifi connect '" + str(ssid) + "' password '" + str(password) + "'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=50)
        
        if "successfully activated" in result.stdout.lower():
            if is_flashair:
                log("Optimizing wireless interface routing metrics for FlashAir...")
                subprocess.run("sudo nmcli connection modify '" + str(ssid) + "' ipv4.route-metric 10 > /dev/null 2>&1", shell=True)
                subprocess.run("sudo nmcli connection up '" + str(ssid) + "' > /dev/null 2>&1", shell=True)
                os.system("sudo iw dev wlan0 set power_save off")
            else:
                log("Optimizing wireless interface routing metrics for Internet...")
                subprocess.run("sudo nmcli connection modify '" + str(ssid) + "' ipv4.route-metric 20 > /dev/null 2>&1", shell=True)
                subprocess.run("sudo nmcli connection up '" + str(ssid) + "' > /dev/null 2>&1", shell=True)

            log("WiFi connected. Waiting for wlan0 IP assignment...")
            for _ in range(15):
                ip_check = subprocess.getoutput("ip -4 addr show wlan0 2>/dev/null")
                if "inet " in ip_check:
                    assigned_ip = ip_check.split("inet ")[1].split("/")[0].strip()
                    log("wlan0 interface ready with IP: " + str(assigned_ip))
                    return True
                time.sleep(1)
        else:
            log("WiFi Connection failed: " + str(result.stderr.strip()))
        return False

    def run_sync_cycle(self):
        if self.is_running: return
        self.is_running, self.manual_req = True, False
       
        os.system("sudo pinctrl set 9 op dh") # Blue Busy ON
        dl_count, up_count = 0, 0
        flashair_read_success = False  # Track clean local directory execution
        
        os.system("sudo rfkill unblock wifi")
        os.system("sudo nmcli radio wifi on")
        os.system("sudo nmcli device wifi rescan > /dev/null 2>&1")
        time.sleep(2) 
                     
        try:
            self.oled.update_status("SCAN", "Searching...")
            initial_scan = subprocess.getoutput("sudo nmcli device wifi list")
            
            # PHASE 1: FlashAir Harvesting
            fa_ssid = self.config['flashair_wifi_ssid']
            if fa_ssid in initial_scan:
                log("!!! NOTICE: Ensure your mobile phone Wi-Fi is turned completely OFF to prevent card locking !!!")
                if self.force_connect(fa_ssid, self.config['flashair_wifi_password'], is_flashair=True):
                    base = self.config['flashair_ip'].rstrip('/')
                    path = self.config['flashair_data_log_dir'].strip('/')
                    
                    fa_host = base.replace("http://", "").replace("https://", "").split(':')[0]
                    log("Waiting for FlashAir routing to stabilise at " + str(fa_host) + "...")
                    route_established = False
                    for _ in range(10):
                        result = subprocess.run(["ping", "-c", "1", "-W", "1", fa_host], capture_output=True)
                        if result.returncode == 0:
                            log("FlashAir routing confirmed.")
                            route_established = True
                            break
                        time.sleep(1)

                    if route_established:
                        target_url = base + "/command.cgi?op=100&DIR=/" + path
                        log("Requesting file directory listing via OS native curl: " + str(target_url))
                        
                        curl_cmd = [
                            "curl", 
                            "--connect-timeout", "4", 
                            "--max-time", "12", 
                            "-A", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X)", 
                            "-s", 
                            target_url
                        ]
                        
                        curl_res = subprocess.run(curl_cmd, capture_output=True, text=True)
                        
                        if curl_res.returncode == 0:
                            flashair_read_success = True  # Verified card communication
                            fa_files = {}
                            for line in curl_res.stdout.splitlines():
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
                            
                            log("Found " + str(len(to_dl)) + " new/modified log files to harvest.")
                            
                            for i, (f, expected_size) in enumerate(to_dl):
                                self.oled.update_status("DL", f, (i+1)/len(to_dl))
                                dl_url = base + "/" + path + "/" + f
                                target = self.mirror_dir / f
                                
                                log("Downloading: " + str(f) + " (" + str(expected_size) + " bytes)")
                                dl_cmd = [
                                    "curl", 
                                    "--connect-timeout", "5", 
                                    "--max-time", "60", 
                                    "-A", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X)", 
                                    "-s", 
                                    "-o", str(target), 
                                    dl_url
                                ]
                                
                                dl_res = subprocess.run(dl_cmd)
                                if dl_res.returncode == 0 and target.exists():
                                    actual_size = target.stat().st_size
                                    log("Successfully harvested " + str(f) + " [" + str(actual_size) + " bytes]")
                                    
                                    self.local_done[f] = {
                                        "timestamp": time.time(),
                                        "size": actual_size
                                    }
                                    self._save_db(self.local_db_path, self.local_done)
                                    dl_count += 1
                                else:
                                    log("Curl file download failed for " + str(f) + " with exit code: " + str(dl_res.returncode))
                        else:
                            log("Curl directory request failed with OS exit code: " + str(curl_res.returncode))
                    else:
                        log("FlashAir routing could not be verified. Skipping download phase.")
            else:
                log("FlashAir SSID '" + str(fa_ssid) + "' not found in initial scan. Skipping download phase.")

            # PHASE 2: FlySto Upload
            log("Explicitly disconnecting from FlashAir to prepare for internet routing...")
            os.system("sudo nmcli dev disconnect wlan0 > /dev/null 2>&1")
            time.sleep(2)

            on_disk = list(self.mirror_dir.glob('*.csv'))
            pending = [f for f in on_disk if f.name not in self.flysto_done]
            
            log("Phase 2 Analysis: Found " + str(len(on_disk)) + " files total on disk, " + str(len(pending)) + " pending FlySto upload.")
            
            if pending:
                log("Executing targeted radio rescan for internet networks...")
                os.system("sudo nmcli device wifi rescan > /dev/null 2>&1")
                time.sleep(3)
                internet_scan = subprocess.getoutput("sudo nmcli device wifi list")
                
                net = None
                for n in self.config['internet_networks']:
                    if n['ssid'] in internet_scan:
                        net = n
                        break
                
                if net:
                    log("Matched target internet network: '" + str(net['ssid']) + "'. Attempting handshake...")
                    if self.force_connect(net['ssid'], net['password'], is_flashair=False):
                        log("Waiting for cloud gateway routing to stabilise...")
                        internet_routed = False
                        for _ in range(10):
                            result = subprocess.run(["ping", "-c", "1", "-W", "1", "8.8.8.8"], capture_output=True)
                            if result.returncode == 0:
                                log("Internet outbound path confirmed.")
                                internet_routed = True
                                break
                            time.sleep(1)

                        if internet_routed:
                            os.system("sudo pinctrl set 10 op dh") # White LED ON
                            
                            client = FlyStoClient(self.config['flysto_email'], self.config['flysto_password'])
                            
                            if client.is_authenticated:
                                for i, f in enumerate(pending):
                                    self.oled.update_status("UP", f.name, (i+1)/len(pending))
                                    log("Uploading: " + str(f.name) + " to FlySto...")
                                    if client.upload_log(f):
                                        self.flysto_done[f.name] = time.time()
                                        self._save_db(self.flysto_db_path, self.flysto_done)
                                        log("Successfully uploaded " + str(f.name))
                                        up_count += 1
                                    else:
                                        log("File " + str(f.name) + " upload declined or broken by server.")
                                
                                # INTERVENTION 1: Green LED activates on valid handshake AND active log generation
                                if up_count > 0 and up_count == len(pending):
                                    log("All new logs synchronized to FlySto. Illuminating Green LED.")
                                    os.system("sudo pinctrl set 11 op dh") 
                                    self.success_time = time.time() 
                            else:
                                log("FlySto API authentication rejected, check your email/password config.")
                            
                            os.system("sudo pinctrl set 10 op dl") # White LED OFF
                        else:
                            log("Connected to Wi-Fi, but could not resolve external WAN ping to 8.8.8.8.")
                    else:
                        log("Failed to switch connection profile to internet network '" + str(net['ssid']) + "'.")
                else:
                    log("None of your configured 'internet_networks' were detected in the fresh Wi-Fi scan.")
            else:
                log("Database confirmation: Local mirror completely synchronized. Nothing to upload.")
                # INTERVENTION 2: Green LED activates for 60s if directory was read cleanly but contained nothing new
                if flashair_read_success:
                    log("FlashAir read verified successfully with 0 outstanding bytes to pull. Illuminating Green LED.")
                    os.system("sudo pinctrl set 11 op dh")
                    self.success_time = time.time()

        except Exception as e:
            log("Sync Cycle Critical Error: " + str(e))
        finally:
            self.is_running = False
            os.system("sudo pinctrl set 9 op dl") # Blue LED OFF
            os.system("sudo nmcli dev disconnect wlan0 > /dev/null 2>&1")
            self.oled.update_status("COMPLETE", "DL:" + str(dl_count) + " UP:" + str(up_count), force=True)
            time.sleep(5)

    def start(self):
        btn_start = None
        log("System Ready. Waiting for Button Press...")

        while True:
            if self.success_time > 0 and (time.time() - self.success_time > 60):
                os.system("sudo pinctrl set 11 op dl")
                self.success_time = 0
                self.oled.update_status("IDLE", "Logs: " + str(len(self.local_done)), force=True)

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
                self.oled.update_status("IDLE", "Logs: " + str(len(self.local_done)))
            time.sleep(0.1)

if __name__ == "__main__":
    SyncOrchestrator().start()