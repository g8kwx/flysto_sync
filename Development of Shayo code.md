>> Careful most of this was created by Gemini - it may be not totally true.

To understand the evolution of your system, it’s helpful to see how we moved from a desktop-style script to a hardened, cockpit-integrated appliance. While Shayo's original code provided a great foundation for API interaction, **Version 35** has been "ruggedized" for the specific constraints of aviation hardware and Raspberry Pi architecture.

Here are the key improvements and architectural shifts:

---

### 1. Robust WiFi State Management

* **The Problem:** The original code assumes a persistent internet connection.
* **The Improvement:** Version 35 uses a **"Patient WiFi"** logic. It actively manages the `nmcli` (Network Manager) to hop between the isolated FlashAir network and the Internet hotspot. It includes a DHCP "warm-up" wait (15 seconds) to ensure the server is ready before attempting a request.

### 2. Hardware-Level Cockpit Integration

* **Discrete Alerts (GPIO 9, 10, 11):** We added an **Active High** signaling system specifically designed to drive an inverting level shifter. This allows the Pi to talk to a 12V Garmin G3X system, triggering cockpit CAS messages (Crew Alerting System) for "Busy," "Uploading," and "Success."
* **OLED Feedback:** We integrated `luma.oled` to provide real-time visual telemetry (filenames, progress bars, and "Complete" statuses) .
* **Physical Control (GPIO 22):** Added a multi-function button for manual sync triggers and safe hardware shutdowns to prevent SD card corruption.

### 3. File System "Visibility" & Permissions

* **The Problem:** In Linux, files created by a background script are often invisible or "locked" to the `admin` user in WinSCP.
* **The Improvement:** Version 35 enforces **Absolute Pathing** and **Recursive Permissions**. Every time a file lands, the script executes a `chmod 666` and `chown admin:admin`. This ensures the pilot can always see and move files via WinSCP without permission errors.

### 4. Browser-Mimicking Session Handling

* **Authentication Logic:**  Version 35 was enhanced with specific **User-Agent** headers and **Referer** strings to bypass modern web firewalls that often block "Python-Requests" signatures. It maintains a persistent `requests.Session()` to carry cookies from the login gate to the upload gate.

### 5. Data Integrity & Sync Efficiency

* **The Problem:** Re-uploading the same 50MB log file every time the Pi boots.
* **The Improvement:** The database intois split into two distinct tracking files:
1. `local_sync.json`: Tracks what has moved from the **SD Card → Pi**.
2. `flysto_uploads.json`: Tracks what has moved from the **Pi → Cloud**.
This "Double-Buffer" ensures that if the internet fails halfway through, the Pi knows exactly where it left off.

---

### Summary of Logical Flow (V35 vs. Original)

| Feature | Shayo Original | Version 35 (Final) |
| --- | --- | --- |
| **Connectivity** | Assumes Internet is ON | Handshakes FlashAir then Hotspot |
| **Paths** | Relative (Script Folder) | Absolute (`/home/admin/flashair`) |
| **Permissions** | Default System | Forced `admin:admin` & `777` |
| **UI** | Terminal Only | OLED + GPIO Garmin Integration |
| **Hardware** | No GPIO support | Button, 3-Channel Alerts, Shutdown |
| **Zipping** | Standard | Memory-Buffered (io.BytesIO) |

### The "Garmin Signal" Logic

While the original script used an 'hat' LCD module, V35's output is designed to interface and create messages on the G3x display:

* **Pi Pin 11 (Success) goes HIGH (3.3V)** $\rightarrow$ **Level Shifter Inverts to 0V (Ground)** $\rightarrow$ **Garmin G3X Senses "Active Low"** $\rightarrow$ **Pilot sees "SYNC OK" message.**
