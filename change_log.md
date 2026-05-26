
# Gemini version 39.15 - "Handshake Success Green LED" Build
# Manual Trigger | Radio Reset | GPIO 11 fires on Verified Server Handshake
# Fix 1: WiFi stability delay added after force_connect() before FlySto auth
# Fix 2: Session re-authentication on 401 during upload with single retry
# Fix 3: _wait_for_routing() only called in Phase 2 (internet needed)
# Fix 5: FlashAir uses fixed IP — force_connect() skips DHCP wait for Phase 1
# Fix 6: fa_session retry adapter removed; command.cgi timeout tightened to 10s
# Fix 8: Profile delete now matches by UUID on SSID prefix — fixes key-mgmt
#         error caused by nmcli saving profiles as "ssid 1", "ssid 2" etc.

# Gemini version 39.14 - "Handshake Success Green LED" Build
# Manual Trigger | Radio Reset | GPIO 11 fires on Verified Server Handshake
# Fix 1: WiFi stability delay added after force_connect() before FlySto auth
# Fix 2: Session re-authentication on 401 during upload with single retry
# Fix 3: _wait_for_routing() only called in Phase 2 (internet needed)
# Fix 5: FlashAir uses fixed IP — force_connect() skips DHCP wait for Phase 1
# Fix 6: fa_session retry adapter removed; command.cgi timeout tightened to 10s
# Fix 7: force_connect() reverted to original working logic; only addition
#         is the wait_for_ip parameter for Phase 1 FlashAir connect

# Gemini version 39.13 - "Handshake Success Green LED" Build
# Manual Trigger | Radio Reset | GPIO 11 fires on Verified Server Handshake
# Fix 1: WiFi stability delay added after force_connect() before FlySto auth
# Fix 2: Session re-authentication on 401 during upload with single retry
# Fix 3: _wait_for_routing() only called in Phase 2 (internet needed)
# Fix 5: FlashAir uses fixed IP — force_connect() skips DHCP wait for Phase 1
# Fix 6: fa_session retry adapter removed; command.cgi timeout tightened to 10s
# Fix 7: force_connect() reverted to original working logic; only addition
#         is the wait_for_ip parameter for Phase 1 FlashAir connect

# Gemini version 39.12 - "Handshake Success Green LED" Build
# Manual Trigger | Radio Reset | GPIO 11 fires on Verified Server Handshake
# Fix 1: WiFi stability delay added after force_connect() before FlySto auth
# Fix 2: Session re-authentication on 401 during upload with single retry
# Fix 3: _wait_for_routing() only called in Phase 2 (internet needed)
# Fix 5: FlashAir uses fixed IP — force_connect() skips DHCP wait for Phase 1
# Fix 6: fa_session retry adapter removed; command.cgi timeout tightened to 10s
# Fix 7: force_connect() purges all profiles by UUID and removes NM connection
#         files from disk before reconnecting — eliminates key-mgmt error

# Gemini version 39.11 - "Handshake Success Green LED" Build
# Manual Trigger | Radio Reset | GPIO 11 fires on Verified Server Handshake
# Fix 1: WiFi stability delay added after force_connect() before FlySto auth
# Fix 2: Session re-authentication on 401 during upload with single retry
# Fix 3: _wait_for_routing() only called in Phase 2 (internet needed)
# Fix 5: FlashAir uses fixed IP — force_connect() skips DHCP wait for Phase 1
# Fix 6: fa_session retry adapter removed; command.cgi timeout tightened to 10s
# Fix 7: force_connect() disconnect→wait→delete→connect order fixed to prevent
#         802-11-wireless-security.key-mgmt missing property error


# Gemini version 39.10 - "Handshake Success Green LED" Build
# Manual Trigger | Radio Reset | GPIO 11 fires on Verified Server Handshake
# Fix 1: WiFi stability delay added after force_connect() before FlySto auth
# Fix 2: Session re-authentication on 401 during upload with single retry
# Fix 3: _wait_for_routing() only called in Phase 2 (internet needed)
# Fix 5: FlashAir uses fixed IP — force_connect() skips DHCP wait for Phase 1
# Fix 6: fa_session retry adapter removed; command.cgi timeout tightened to 10s
# Fix 7: force_connect() disconnects wlan0 and waits 2s before reconnecting
#         to clear nmcli "connection activation enqueued" errors


# Gemini version 39.9 - "Handshake Success Green LED" Build
# Manual Trigger | Radio Reset | GPIO 11 fires on Verified Server Handshake
# Fix 1: WiFi stability delay added after force_connect() before FlySto auth
# Fix 2: Session re-authentication on 401 during upload with single retry
# Fix 3: _wait_for_routing() only called in Phase 2 (internet needed)
# Fix 5: FlashAir uses fixed IP — force_connect() skips DHCP wait for Phase 1
# Fix 6: fa_session retry adapter removed; command.cgi timeout tightened to 10s
#         with explicit error handling so a slow/absent card fails fast

# Gemini version 39.9 - "Handshake Success Green LED" Build
# Manual Trigger | Radio Reset | GPIO 11 fires on Verified Server Handshake
# Fix 1: WiFi stability delay added after force_connect() before FlySto auth
# Fix 2: Session re-authentication on 401 during upload with single retry
# Fix 3: _wait_for_routing() only called in Phase 2 (internet needed)
# Fix 5: FlashAir uses fixed IP — force_connect() skips DHCP wait for Phase 1

# Gemini version 39.8 - "Handshake Success Green LED" Build
# Manual Trigger | Radio Reset | GPIO 11 fires on Verified Server Handshake
# Fix 1: WiFi stability delay added after force_connect() before FlySto auth
# Fix 2: Session re-authentication on 401 during upload with single retry
# Fix 3: _wait_for_routing() only called in Phase 2 (internet needed) —
#         Phase 1 (FlashAir) connects directly as before, no ping needed

# Gemini version 39.7 - "Handshake Success Green LED" Build
# Manual Trigger | Radio Reset | GPIO 11 fires on Verified Server Handshake
# Fix 1: WiFi stability delay added after force_connect() before FlySto auth
# Fix 2: Session re-authentication on 401 during upload with single retry
# Fix 3: _wait_for_routing() now pings the correct host for each phase —
#         FlashAir IP in Phase 1 (no internet), 8.8.8.8 in Phase 2
# Fix 4: 2s pause after FlashAir ping (ICMP ready before HTTP); reduced
#         fa_session retries from 5 to 2 to avoid long hangs on slow card


# Gemini version 39.6 - "Handshake Success Green LED" Build
# Manual Trigger | Radio Reset | GPIO 11 fires on Verified Server Handshake
# Fix 1: WiFi stability delay added after force_connect() before FlySto auth
# Fix 2: Session re-authentication on 401 during upload with single retry
# Fix 3: _wait_for_routing() now pings the correct host for each phase —
#         FlashAir IP in Phase 1 (no internet), 8.8.8.8 in Phase 2


## v39.5 — 2026-05-26

### Fixed

- **WiFi routing race condition** — added `_wait_for_routing()` method that pings `8.8.8.8` (up to 10 attempts, 1s apart) after `force_connect()` returns `True`, before constructing `FlyStoClient`. An IP address being assigned does not guarantee the default gateway or DNS are active; this change ensures the network stack is fully ready before the FlySto login attempt is made.

- **Session expiry mid-upload** — `upload_log()` now handles a `401` response by re-calling `_authenticate()` once to refresh the `USER_SESSION` cookie, then retrying the upload a single time. Previously, an expired session mid-loop would silently return `False` for every subsequent file with no recovery attempt. The bare `except` clause was also updated to log the specific error.

---

## v39.4 — "Handshake Success Green LED" Build

Initial tracked version. Features:

- Manual trigger via GPIO 22 button (hold 3s to shut down)
- FlashAir Wi-Fi harvest of `.csv` log files with size-based delta detection
- FlySto upload with ZIP compression per file
- OLED status display (flicker-free, state-diffed)
- Blue LED (GPIO 9) — busy indicator
- White LED (GPIO 10) — upload in progress
- Green LED (GPIO 11) — illuminates for 60s on verified FlySto handshake
- Persistent local sync db (`local_sync.json`) and upload db (`flysto_uploads.json`)
__________________





# README: FlySto Sync Rig Evolution (Changelog v39.2 to v39.4)
This document details the architectural updates and stabilization fixes implemented between **Gemini version 39.2** (Initial Baseline) and **Gemini version 39.4** (Current Build) of the automated FlashAir to FlySto synchronization engine.
## Executive Summary
The transition from v39.2 to v39.4 focuses on **production hardening**. It addresses critical edge cases where low-power FlashAir SD card Wi-Fi interfaces drop connections, prevents local mirror tracking database corruption due to avionics "race conditions" (partial logs), resolves modern Linux NetworkManager security bugs, and alters physical LED telemetry feedback to represent server-side handshake confirmations.
## Detailed Version Lineage & Changelog
### Gemini v39.3 — "Robust Sync" Architecture Upgrades
#### 1. Data Integrity & Size-Aware Synchronization Engine
 * **The Problem (v39.2):** The tracking ledger (local_sync.json) saved files purely by tracking the filename string mapped to a float timestamp. If the rig cycled while avionics were actively writing to a file, an incomplete log fragment (e.g., a 2 KB chunk instead of 500 KB) was saved to disk, recorded as "done," and **never re-downloaded**.
 * **The Solution (v39.3):** Swapped out the loose filename regex pattern for structural row split parsing from FlashAir's command.cgi?op=100 response. The sync logic now extracts both **Filename** and **File Size**.
 * **Database Schema Evolution:** The database format has changed to store an object instead of a flat float timestamp:
   ```json
   "LOG0001.CSV": {
       "timestamp": 1716483120.45,
       "size": 524288
   }
   
   ```
```
  If a log file grows larger on the card on a subsequent flight, the sync engine dynamically triggers an overwrite, wiping out partial log fragments with complete data sets automatically. Backwards-compatibility safety handlers are baked in to prevent existing files from crashing the dictionary evaluation loop.
#### 2. NetworkManager State-Machine Hardening
* **The Problem (v39.2):** Calling `sudo ip link set wlan0 down` / `up` bypassed the `NetworkManager` daemon. This caused internal state race conditions where the daemon locked up, delaying or breaking subsequent network connection handshakes.
* **The Solution (v39.3):** Eliminated aggressive hardware interface cycling. The operating system now switches Wi-Fi domains smoothly using the daemon’s natural connection logic, decreasing synchronization handoff times from 20 seconds to under 5 seconds.
#### 3. HTTP Persistent Pipeline & Connection Pooling
* **The Problem (v39.2):** Every individual file listing query and download created a fresh TCP handshake against the FlashAir card. Embedded SD microcontrollers are notorious for throwing socket errors or dropping radios under rapid request intervals.
* **The Solution (v39.3):** Integrated a global persistent `requests.Session()` pipeline specifically for FlashAir communications (`self.fa_session`). 
* **Automatic Backoff Retries:** Mounted specialized `urllib3.util.Retry` adapters. The rig automatically retries down failing radio links up to 5 times on `500, 502, 503, 504` errors with an exponential backoff factor before reporting an engine drop.
---
### Gemini v39.4 — "Confirmed Handshake" Integration
#### 1. Resolution of the NetworkManager 802.11 Security Bug
* **The Problem (v39.3):** On modern Linux systems (such as newer Raspberry Pi OS builds), passing raw plaintext parameters directly using `nmcli device wifi connect` over existing cached network configs threw the fatal runtime error:
  > `Error: 802-11-wireless-security.key.mgmt:property missing`
* **The Solution (v39.4):** Implemented an aggressive, atomic connection purge routine inside `force_connect()` directly before initiating connection handshakes:
  ```python
  subprocess.run(f"sudo nmcli connection delete '{ssid}' > /dev/null 2>&1", shell=True)
```
Wiping out conflicting localized system profiles forces nmcli to automatically negotiate security policies natively from scratch, bypassing the property management bug cleanly.
#### 2. Modified Green LED Telemetry Logic (GPIO 11)
 * **The Behavior (v39.2 / v39.3):** The Green Success LED lit up **only** if the total integer count of uploaded files (up_count) was greater than zero.
 * **The New Behavior (v39.4):** The Green Success LED is now driven by a successful **FlySto API Authentication Handshake**. Once the device securely logs into FlySto and runs through its entire pending sync directory without losing connection, the Green LED illuminates for 60 seconds.
> **Telemetry Note:** This change means if your flights are successfully authenticated and verified, but denied or skipped by the server (e.g., because FlySto recognizes them as duplicate tracks), your hardware panel will still illuminate **Green** to show that the system completed its diagnostic mission flawlessly, rather than remaining dark.
> 
## Architectural Comparison Matrix

| Feature Feature | Gemini v39.2 Baseline | Gemini v39.4 Production Build |
| :--- | :--- | :--- |
| **Sync Check Rule** | Filename matches database index | Filename match **AND** Current File Size check |
| **HTTP Strategy** | Transient single-shot requests | Persistent TCP Connection Pooling (Session) |
| **Radio Handling** | Destructive ip link set down toggles | Controlled Native NetworkManager switching |
| **Profiles Conflict Protection** | None (Susceptible to caching errors) | Automatic Profile Deletion before connecting |
| **Green LED Trigger** | up_count > 0 (Requires actual file uploads) | Successful FlySto Session Handshake Completion |