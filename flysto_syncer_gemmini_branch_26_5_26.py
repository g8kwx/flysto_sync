
### Updated Production Code

# Gemini version 42.4 - "Universal Synchronized Feedback" Build
import os, json, time, subprocess, requests, zipfile, io
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

def log(msg):
    print("[" + time.strftime("%H:%M:%S") + "] " + str(msg), flush=True)

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
        
        self.local_db_path = self.base_dir / "local_sync.json"
        self.flysto_db_path = self.base_dir / "flysto_uploads.json"
        
        self.local_done = self._load_db(self.local_db_path)
        self.flysto_done = self._load_db(self.flysto_db_path)
        
        self.is_running = False
        self.manual_req = False
        
        # Diagnostic LED properties
        self.success_time = 0
        self.green_led_active = False
        self.last_countdown_log = 0
        self.trigger_green_led = False

        # Hardware GPIO Setup via pinctrl
        os.system("sudo pinctrl set 22 ip pu") 
        for p in [9, 10, 11]: os.system("sudo pinctrl set " + str(p) + " op dl")

    def _load_db(self, path):
        if path.exists():
            try: return json.loads(path.read_text())
            except Exception as e: 
                log("Database read error for " + path.name + ", fallback to empty state: " + str(e))
                return {}
        return {}

    def _save_db(self, path, data):
        tmp_path = path.with_suffix('.tmp')
        try:
            tmp_path.write_text(json.dumps(data, indent=4))
            os.replace(tmp_path, path)
            os.system("sudo chmod 666 " + str(path))
        except Exception as e:
            log("Critical failure saving database " + path.name + ": " + str(e))

    def force_connect(self, ssid, password, is_flashair=False):
        log("Force connecting to " + str(ssid) + "...")
        
        subprocess.run(["sudo", "nmcli", "connection", "delete", ssid], capture_output=True)
        
        cmd = ["sudo", "nmcli", "device", "wifi", "connect", ssid, "password", password]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=50)
        
        if "successfully activated" in result.stdout.lower():
            if is_flashair:
                log("Optimizing wireless interface routing metrics for FlashAir...")
                subprocess.run(["sudo", "nmcli", "connection", "modify", ssid, "ipv4.route-metric", "10"], capture_output=True)
                subprocess.run(["sudo", "nmcli", "connection", "up", ssid], capture_output=True)
                os.system("sudo iw dev wlan0 set power_save off")
            else:
                log("Optimizing wireless interface routing metrics for Internet...")
                subprocess.run(["sudo", "nmcli", "connection", "modify", ssid, "ipv4.route-metric", "20"], capture_output=True)
                subprocess.run(["sudo", "nmcli", "connection", "up", ssid], capture_output=True)

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
        self.trigger_green_led = False
       
        os.system("sudo pinctrl set 9 op dh") # Blue Busy ON
        dl_count, up_count = 0, 0
                     
        try:
            os.system("sudo rfkill unblock wifi")
            os.system("sudo nmcli radio wifi on")
            os.system("sudo nmcli device wifi rescan > /dev/null 2>&1")
            time.sleep(2) 
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
                                log("FlySto login authenticated. Queueing Green LED activation for cycle completion.")
                                self.trigger_green_led = True

                                for i, f in enumerate(pending):
                                    log("Uploading: " + str(f.name) + " to FlySto...")
                                    if client.upload_log(f):
                                        self.flysto_done[f.name] = time.time()
                                        self._save_db(self.flysto_db_path, self.flysto_done)
                                        log("Successfully uploaded " + str(f.name))
                                        up_count += 1
                                    else:
                                        log("File " + str(f.name) + " upload denied or broken by server (Green LED will still trigger).")
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
                # FIX: Unconditionally queue the green LED here since there is nothing outstanding to upload.
                log("Database confirmation: Local mirror completely synchronized. Nothing to upload. Queueing Green LED activation.")
                self.trigger_green_led = True

        except Exception as e:
            log("Sync Cycle Critical Error: " + str(e))
        finally:
            self.is_running = False
            os.system("sudo pinctrl set 9 op dl") # Blue LED OFF
            os.system("sudo nmcli dev disconnect wlan0 > /dev/null 2>&1")
            log("Cycle complete. Harvested: " + str(dl_count) + " | Uploaded: " + str(up_count))
            time.sleep(5)

        # DEFERRED EXECUTION: Turn on the Green LED only AFTER the entire orchestrator has completed
        if self.trigger_green_led:
            log("Sync orchestrator completed successfully. Illuminating Green LED for a clean 60 seconds.")
            os.system("sudo pinctrl set 11 op dh")
            self.success_time = time.time()
            self.green_led_active = True
            self.last_countdown_log = time.time()
            self.trigger_green_led = False

    def start(self):
        btn_start = None
        log("System Ready. Waiting for Button Press...")

        while True:
            # Handle precise green LED timeout and diagnostics
            if self.green_led_active:
                elapsed = time.time() - self.success_time
                if elapsed > 60:
                    os.system("sudo pinctrl set 11 op dl")
                    self.success_time = 0
                    self.green_led_active = False
                    log("Success timeout reached. Green LED command fired to turn OFF.")
                elif time.time() - self.last_countdown_log > 10:
                    log("Green LED active status: " + str(max(0, 60 - int(elapsed))) + "s remaining.")
                    self.last_countdown_log = time.time()

            # Read GPIO state cleanly
            raw_btn = subprocess.getoutput("pinctrl get 22")
            if "level=lo" in raw_btn or "| lo" in raw_btn:
                if btn_start is None: btn_start = time.time()
                if (time.time() - btn_start) > 3.0:
                    log("Shutdown threshold reached. Exiting script and powering down.")
                    os.system("sudo poweroff")
                    return
            else:
                if btn_start is not None:
                    if (time.time() - btn_start) < 3.0 and not self.is_running:
                        log("Manual Sync Requested via button press.")
                        self.manual_req = True
                    btn_start = None

            if self.manual_req:
                self.run_sync_cycle()
            
            time.sleep(0.1)

if __name__ == "__main__":
    SyncOrchestrator().start()