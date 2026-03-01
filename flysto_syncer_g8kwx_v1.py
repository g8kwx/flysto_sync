#Gemini version 36.
import os, json, time, subprocess, re, requests, zipfile, io
from pathlib import Path

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

# --- OLED Handler (Fixed for Flicker) ---
class OLEDController:
    def __init__(self):
        try:
            from luma.oled.device import ssd1306
            from luma.core.interface.serial import i2c
            from luma.core.render import canvas
            serial = i2c(port=1, address=0x3C)
            self.device = ssd1306(serial, width=128, height=32)
            self.canvas = canvas
            self.last_state = None # Track the last thing drawn
            log("OLED Initialized.")
        except: self.device = None

    def update_status(self, mode, msg, progress=None, force=False):
        if not self.device: return
        
        # Create a unique fingerprint for the current screen content
        current_state = f"{mode}-{msg}-{progress}"
        
        # Only draw if the content changed or we force it (like at startup)
        if current_state != self.last_state or force:
            with self.canvas(self.device) as draw:
                draw.text((0, -3), mode, fill="white")
                draw.text((0, 15), msg[:18], fill="white")
                if progress is not None:
                    draw.rectangle((0, 31, int(progress * 128), 31), outline="white", fill="white")
            self.last_state = current_state

# ... [FlyStoClient and SyncOrchestrator classes remain the same as v35] ...

    def start(self, interval=1800):
        last_sync = 0
        btn_start = None
        log("System Active. Monitoring for Flicker-Free IDLE...")

        while True:
            # 60-second Garmin Success Alert Timeout
            if self.success_time > 0 and (time.time() - self.success_time > 60):
                os.system("sudo pinctrl set 10 op dl")
                os.system("sudo pinctrl set 11 op dl")
                self.success_time = 0
                # Force a refresh once when timeout hits to clear any old state
                self.oled.update_status("IDLE", f"Logs: {len(self.local_done)}", force=True)

            raw_btn = subprocess.getoutput("pinctrl get 22")
            if "level=lo" in raw_btn or "| lo" in raw_btn:
                if btn_start is None: btn_start = time.time()
                if (time.time() - btn_start) > 3.0:
                    self.oled.update_status("OFF", "SHUTDOWN...", force=True)
                    subprocess.Popen(['sudo', 'poweroff'])
                    return
            else:
                if btn_start is not None:
                    if (time.time() - btn_start) < 3.0 and not self.is_running:
                        self.manual_req = True
                    btn_start = None

            if (time.time() - last_sync > interval) or self.manual_req:
                self.run_sync_cycle()
                last_sync = time.time()
                # Force refresh after sync finishes
                self.oled.update_status("IDLE", f"Logs: {len(self.local_done)}", force=True)
            
            # This is where the pulse was happening. Now it only updates on change.
            if not self.is_running:
                self.oled.update_status("IDLE", f"Logs: {len(self.local_done)}")
            
            time.sleep(0.1)

# --- FlySto Client (Proven Version) ---
class FlyStoClient:
    def __init__(self, email: str, password: str):
        self._session = requests.Session()
        self._email = email
        self._password = password
        self._base_url = "https://www.flysto.net/api"
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://www.flysto.net/login"
        })
        self.is_authenticated = self._authenticate()

    def _authenticate(self) -> bool:
        log(f"Authenticating FlySto for {self._email}...")
        try:
            response = self._session.post(
                f"{self._base_url}/login", 
                json={"email": self._email, "password": self._password}, 
                headers={"Content-Type": "text/plain;charset=UTF-8"},
                timeout=20
            )
            success = response.status_code == 204 and "USER_SESSION" in self._session.cookies
            log(f"FlySto Auth {'Success' if success else 'Failed'}")
            return success
        except: return False

    def upload_log(self, file_path: Path) -> bool:
        if not self.is_authenticated: return False
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.write(file_path, arcname=file_path.name)
        try:
            response = self._session.post(
                f"{self._base_url}/log-upload", 
                params={"id": file_path.name}, 
                headers={"Content-Type": "application/zip"}, 
                data=zip_buffer.getvalue(),
                timeout=60
            )
            return response.status_code in [200, 201, 204]
        except: return False

# --- Main System ---
class SyncOrchestrator:
    def __init__(self, config_path='config.json'):
        with open(config_path, 'r') as f:
            self.config = json.load(f)
        
        self.base_dir = Path("/home/admin/flashair")
        self.mirror_dir = self.base_dir / "mirror"
        self.local_db_p = self.base_dir / "local_sync.json"
        self.flysto_db_p = self.base_dir / "flysto_uploads.json"
        
        self.mirror_dir.mkdir(parents=True, exist_ok=True)
        os.system(f"sudo chown -R admin:admin {self.base_dir}")

        self.oled = OLEDController()
        self.local_done = self._load_db(self.local_db_p)
        self.flysto_done = self._load_db(self.flysto_db_p)
        
        self.is_running = False
        self.manual_req = False
        self.success_time = 0

        # GPIO INIT: Active High logic (Pins 9, 10, 11 start LOW/OFF)
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

    def connect_wifi(self, ssid, pw):
        self.oled.update_status("WIFI", f"Join {ssid[:10]}")
        os.system(f"sudo nmcli dev disconnect wlan0 > /dev/null 2>&1")
        os.system(f"sudo nmcli conn delete '{ssid}' > /dev/null 2>&1")
        cmd = f"sudo nmcli dev wifi connect '{ssid}' password '{pw}' name '{ssid}'"
        subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
        
        for _ in range(15):
            if "192.168" in subprocess.getoutput("hostname -I"):
                time.sleep(5)
                return True
            time.sleep(1)
        return False

    def run_sync_cycle(self):
        if self.is_running: return
        self.is_running, self.manual_req = True, False
        dl_count, up_count = 0, 0
        
        # Pin 9 HIGH = Alerting Garmin that Sync is BUSY
        os.system("sudo pinctrl set 9 op dh") 
        
        try:
            self.oled.update_status("SCAN", "Searching...")
            scan = subprocess.check_output(['sudo', 'iwlist', 'wlan0', 'scan'], text=True)
            
            # PHASE 1: FlashAir
            if self.config['flashair_wifi_ssid'] in scan:
                if self.connect_wifi(self.config['flashair_wifi_ssid'], self.config['flashair_wifi_password']):
                    base = self.config['flashair_ip'].rstrip('/')
                    path = self.config['flashair_data_log_dir'].strip('/')
                    r = requests.get(f"{base}/command.cgi?op=100&DIR=/{path}", timeout=20)
                    files = re.findall(r'([^,\s]+\.[cC][sS][vV])', r.text)
                    to_dl = [f for f in files if f not in self.local_done]
                    
                    for i, f in enumerate(to_dl):
                        self.oled.update_status("DL", f, (i+1)/len(to_dl))
                        dl = requests.get(f"{base}/{path}/{f}", timeout=45)
                        if dl.status_code == 200:
                            target = self.mirror_dir / f
                            target.write_bytes(dl.content)
                            os.system(f"sudo chmod 666 {target}")
                            self.local_done[f] = time.time()
                            self._save_db(self.local_db_p, self.local_done)
                            dl_count += 1

            # PHASE 2: FlySto
            on_disk = list(self.mirror_dir.glob('*.csv'))
            pending = [f for f in on_disk if f.name not in self.flysto_done]
            
            if pending:
                net = next((n for n in self.config['internet_networks'] if n['ssid'] in scan), None)
                if net and self.connect_wifi(net['ssid'], net['password']):
                    # Pin 10 HIGH = Garmin Alert: Internet Upload Active
                    os.system("sudo pinctrl set 10 op dh") 
                    client = FlyStoClient(self.config['flysto_email'], self.config['flysto_password'])
                    if client.is_authenticated:
                        for i, f in enumerate(pending):
                            self.oled.update_status("UP", f.name, (i+1)/len(pending))
                            if client.upload_log(f):
                                self.flysto_done[f.name] = time.time()
                                self._save_db(self.flysto_db_p, self.flysto_done)
                                up_count += 1
                    os.system("sudo pinctrl set 10 op dl") # Return to LOW

            if dl_count > 0 or up_count > 0:
                # Pin 11 HIGH = Garmin Alert: Sync Success
                os.system("sudo pinctrl set 11 op dh")
                self.success_time = time.time()
                os.system(f"sudo chown -R admin:admin {self.base_dir}")

        finally:
            self.is_running = False
            os.system("sudo pinctrl set 9 op dl") # Busy return to LOW
            os.system("sudo nmcli dev disconnect wlan0")
            # DISPLAY FINAL COMPLETED MESSAGE
            self.oled.update_status("COMPLETE", f"DL:{dl_count} UP:{up_count}")
            time.sleep(5) # Hold completion message on OLED

    def start(self, interval=1800):
        last_sync = 0
        btn_start = None
        while True:
            # 60-second Garmin Success Alert Timeout
            if self.success_time > 0 and (time.time() - self.success_time > 60):
                os.system("sudo pinctrl set 10 op dl") # Ensure Net Alert is off
                os.system("sudo pinctrl set 11 op dl") # Turn off Success Alert
                self.success_time = 0

            raw_btn = subprocess.getoutput("pinctrl get 22")
            if "level=lo" in raw_btn or "| lo" in raw_btn:
                if btn_start is None: btn_start = time.time()
                if (time.time() - btn_start) > 3.0:
                    self.oled.update_status("OFF", "SHUTDOWN...")
                    subprocess.Popen(['sudo', 'poweroff'])
                    return
            else:
                if btn_start is not None:
                    if (time.time() - btn_start) < 3.0 and not self.is_running:
                        self.manual_req = True
                    btn_start = None

            if (time.time() - last_sync > interval) or self.manual_req:
                self.run_sync_cycle()
                last_sync = time.time()
            
            if not self.is_running:
                self.oled.update_status("IDLE", f"Logs: {len(self.local_done)}")
            time.sleep(0.1)

if __name__ == "__main__":
    SyncOrchestrator().start()