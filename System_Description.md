This system transforms a Raspberry Pi Zero into an automated **Avionics Data Gateway**. It bridges the gap between a cockpit SD card (FlashAir) and a cloud-based analysis platform (FlySto), while providing real-time status alerts directly to the pilot via a Garmin G3X system.

---

## 1. System Overview

The system operates as a state machine that manages three distinct network environments:

* **FlashAir Network:** A private WiFi link to the SD card in the avionics stack.
* **Internet Network:** A link to a mobile hotspot or hangar WiFi for cloud synchronization.
* **Isolated/Idle:** The Pi remains disconnected from all WiFi to save power and reduce interference when not syncing.

---

## 2. The Process Flow

The code follows a linear "Sync Cycle" triggered either by a timer (every 30 minutes) or a manual button press.

1. **WiFi Scan:** The Pi scans the airwaves for the FlashAir SSID and known internet SSIDs.
2. **Download Phase:** If the FlashAir is found, the Pi connects, lists all `.csv` files, and downloads only the ones not already stored in the `/mirror` folder.
3. **Handoff:** Downloaded files are immediately assigned to the `admin` user with full permissions (777) so they are visible via WinSCP for manual retrieval if needed.
4. **Upload Phase:** If new files exist, the Pi switches WiFi to an internet-connected network, logs into FlySto using a browser-session simulation, and uploads the logs.
5. **Clean Up:** The Pi disconnects from all WiFi and returns to an IDLE state.

---

## 3. Physical Interface (GPIO & Logic)

The system uses **Active High** logic ($3.3V$) on the Pi's GPIO pins. Because your level shifter inverts the signal, the Garmin G3X will see a **Ground ($0V$)** signal when the Pi's pins are High, triggering the "Active Low" discrete inputs on the GDU 460.

### GPIO Signal States

| GPIO Pin | Function | Garmin Alert / LED State | Process Stage |
| --- | --- | --- | --- |
| **Pin 9** | **Busy** | **ON** during the entire cycle | Indicated the Pi is currently scanning or moving data. |
| **Pin 10** | **Net/Up** | **ON** during FlySto Phase | Indicates the Pi is currently communicating with the Cloud. |
| **Pin 11** | **Success** | **ON** for 60 seconds after completion | Confirms that at least one new file was moved or uploaded. |
| **Pin 22** | **Input** | **Button Press** | A short press (<3s) starts a sync; a long press (>3s) shuts down the Pi. |

---

## 4. OLED Display Logic

The OLED provides high-fidelity status updates to the pilot:

* **IDLE:** Shows the current count of logs stored on the Pi.
* **SCAN:** Indicates the Pi is searching for WiFi networks.
* **WIFI:** Shows which network the Pi is attempting to join.
* **DL / UP:** Displays the specific filename currently being processed and a progress bar.
* **COMPLETE:** A 5-second confirmation message showing the total files handled in that session.

---

## 5. Garmin G3X Configuration (GDU 460)

To integrate this with your GDU 460, you will need to configure the **Discrete Inputs** in the G3X Configuration Mode:

1. Navigate to the configuration page
2. Set the Input Function to **"User Defined"** or **"Crew Alert."**
3. Set the Active State to **"Low."**
4. Define the Alert Text 
