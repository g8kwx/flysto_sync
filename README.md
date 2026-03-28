This system, **FlySto Sync v39.2**, acts as a rugged, "on-demand" data bridge. It is specifically designed to transfer flight data logs from a Garmin avionics suite (via a FlashAir SD card) to the FlySto cloud platform using a Raspberry Pi Zero as the orchestrator.

### 1. Hardware Interface Logic

The system uses a single physical button for control and three colored LEDs for real-time pilot feedback.

| Interface | Pin | Color | Function |
| --- | --- | --- | --- |
| **Control Button** | **GPIO 22** | — | **Short Press:** Start Sync Cycle<br>

<br>**Long Press (>3s):** System Shutdown |
| **Busy LED** | **GPIO 9** | **Blue** | **Solid:** System is active, scanning, or downloading from the SD card. |
| **Transfer LED** | **GPIO 10** | **White** | **Solid:** Actively transmitting data packets to the FlySto servers. |
| **Status LED** | **GPIO 11** | **Green** | **Solid:** FlySto login verified and Internet connection confirmed. |

---

### 2. The Process Flow (The "Sync Cycle")

When you press the button, the system executes the following sequence:

#### **Step 1: Initiation & Harvest (Blue LED ON)**

* The Pi scans for the **FlashAir WiFi** signal.
* To ensure a clean connection, it **deletes** any old WiFi profiles and resets the wireless driver.
* It connects to the SD card and compares the files on the card to the files already saved on the Pi's internal storage (`local_sync.json`).
* Any new flight logs are downloaded to a local "mirror" folder.

#### **Step 2: Internet Handshake (Green LED ON)**

* The Pi switches roles and scans for your **Internet Hotspot** (e.g., your S21 phone).
* It performs another "aggressive" reset to force a connection to the hotspot.
* **The Critical Moment:** The Pi attempts to log into the FlySto API.
* **As soon as the login is authenticated, and a sucessful upload of at least one file the Green LED (GPIO 11) turns ON.** This tells you immediately that your hotspot is working and the upload is complete.

#### **Step 3: Cloud Upload (White LED ON)**

* The Pi identifies which logs haven't been uploaded yet by checking `flysto_uploads.json`.
* It compresses each log into a `.zip` file (as required by FlySto) and transmits it.
* **The White LED (GPIO 10) stays ON** while data is actually moving through the air.

#### **Step 4: Completion & Idle**

* Once finished, the Pi disconnects from the WiFi to stay "silent" and cool.
* The OLED displays the final count (e.g., `DL:2 UP:2`).
* All LEDs turn off after a **60-second "Success" timeout**, and the system returns to its low-power **IDLE** state, waiting for the next button press.

---

### 3. Safety and Reliability Features

* **Nuke-on-Connect:** By deleting the WiFi profile before every connection, the system avoids the "Security Property Missing" error that often plagues Pi Zeros when switching between different types of networks (WPA2 vs WPA3).
* **Headless Recovery:** If the internet is not found or the login fails, the Green and White LEDs will remain off, and the Blue LED will extinguish after the attempt, allowing you to try again without rebooting.
* **Persistence:** Every successful step is logged in JSON databases. If the battery dies mid-upload, the Pi knows exactly where it left off and won't download or upload duplicate data.
* ** Reliability:** It's importat to disable BT on the Pi since the radio chip uses the same chip and antenna for WiFi and BT. Timing conflicts and partial downloads may be a problem if BT is left switched on.
