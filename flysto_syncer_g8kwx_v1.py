# Gemini version 39 - Final Cockpit Build
# Manual Trigger Only | GPIO 11 fires on Login | Force WiFi Reset
import os, json, time, subprocess, re, requests, zipfile, io
from pathlib import Path

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
            return r.status_code in [200, 201, 204]
        except: return False

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

    def force_connect(self, ssid, password):
        log(f"Force connecting to {ssid}...")
        self.oled.update_status("WIFI", f"Join {ssid[:12]}")
        
        # Aggressive reset for Pi Zero stability
        os.system(f"sudo nmcli connection delete '{ssid}' > /dev/null 2>&1")
        os.system("sudo ip link set wlan0 down")
        time.sleep(1)
        os.system("sudo ip link set wlan0 up")
        time.sleep(2)

        cmd = f"sudo nmcli device wifi connect '{ssid}' password '{password}' name '{ssid}'"
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=45)
        
        if "successfully activated" in result.stdout.lower():
            log("WiFi connected. Waiting for IP...")
            for _ in range(15):
                if subprocess.getoutput("hostname -I").strip():
                    return True
                time.sleep(1)
        return False

    def run_sync_cycle(self):
        if self.is_running: return
        self.is_running, self.manual_req = True, False
        dl_count, up_count = 0, 0
        
        os.system("sudo pinctrl set 9 op dh") # Busy Alert ON
        
        try:
            self.oled.update_status("SCAN", "Searching...")
            scan = subprocess.getoutput("sudo iwlist wlan0 scan")
            
            # PHASE 1: FlashAir Harvesting
            fa_ssid = self.config['flashair_wifi_ssid']
            if fa_ssid in scan:
                if self.force_connect(fa_ssid, self.config['flashair_wifi_password']):
                    base = self.config['flashair_ip'].rstrip('/')
                    path = self.config['flashair_data_log_dir'].strip('/')
                    
                    r = requests.get(f"{base}/command.cgi?op=100&DIR=/{path}", timeout=15)
                    files = re.findall(r'([^,\s]+\.[cC][sS][vV])', r.text)
                    to_dl = [f for f in files if f not in self.local_done]
                    
                    for i, f in enumerate(to_dl):
                        self.oled.update_status("DL", f, (i+1)/len(to_dl))
                        dl = requests.get(f"{base}/{path}/{f}", timeout=45)
                        if dl.status_code == 200:
                            target = self.mirror_dir / f
                            target.write_bytes(dl.content)
                            self.local_done[f] = time.time()
                            self._save_db(self.local_db_path, self.local_done)
                            dl_count += 1

            # PHASE 2: FlySto Upload
            on_disk = list(self.mirror_dir.glob('*.csv'))
            pending = [f for f in on_disk if f.name not in self.flysto_done]
            
            if pending:
                # Find available internet network from config
                net = next((n for n in self.config['internet_networks'] if n['ssid'] in scan), None)
                if net and self.force_connect(net['ssid'], net['password']):
                    os.system("sudo pinctrl set 10 op dh") # Net Transmission Alert ON
                    
                    client = FlyStoClient(self.config['flysto_email'], self.config['flysto_password'])
                    
                    if client.is_authenticated:
                        # TRIGGER: Login Success Signal
                        log("Internet Verified. Setting GPIO 11 HIGH.")
                        os.system("sudo pinctrl set 11 op dh") 
                        self.success_time = time.time() # Start 60s panel alert

                        for i, f in enumerate(pending):
                            self.oled.update_status("UP", f.name, (i+1)/len(pending))
                            if client.upload_log(f):
                                self.flysto_done[f.name] = time.time()
                                self._save_db(self.flysto_db_path, self.flysto_done)
                                up_count += 1
                    
                    os.system("sudo pinctrl set 10 op dl") # Net Alert OFF

        except Exception as e:
            log(f"Sync Cycle Error: {e}")
        finally:
            self.is_running = False
            os.system("sudo pinctrl set 9 op dl") # Busy Alert OFF
            os.system("sudo nmcli dev disconnect wlan0 > /dev/null 2>&1")
            self.oled.update_status("COMPLETE", f"DL:{dl_count} UP:{up_count}", force=True)
            time.sleep(5)

    def start(self, interval=31536000): # Default to 1 year (Pure Manual)
        last_sync = time.time()
        btn_start = None
        log("System Ready. Waiting for Button Press...")

        while True:
            # Success Alert Timeout (60s)
            if self.success_time > 0 and (time.time() - self.success_time > 60):
                os.system("sudo pinctrl set 11 op dl")
                self.success_time = 0
                self.oled.update_status("IDLE", f"Logs: {len(self.local_done)}", force=True)

            # Button 22 Logic
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
                last_sync = time.time()
            
            if not self.is_running:
                self.oled.update_status("IDLE", f"Logs: {len(self.local_done)}")
            time.sleep(0.1)

if __name__ == "__main__":
    SyncOrchestrator().start()