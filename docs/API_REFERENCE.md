# BenQ HTTP CGI API Reference

This document describes the HTTP API used to control BenQ network projectors. It was reverse-engineered from the projector's web interface firmware JavaScript files.

All commands are HTTP POST requests to `/cgi-bin/webctrl.cgi.elf` on port 80.

---

## How Parameter IDs Work

All parameter IDs follow a simple formula:

```
p = Page_ID + pid_offset
```

**Page IDs:**
| Name | Hex | Decimal |
|------|-----|---------|
| `VIRTUAL_KEYPAD` | `0xD0000` | 851968 |
| `DISPLAY_SETTING` | `0xE0000` | 917504 |
| `PICTURE_SETTING` | `0xF0000` | 983040 |
| `INFORMATION` | `0x100000` | 1048576 |

**Action types (`c:` value):**
| Value | Action |
|-------|--------|
| `c:5` | Write/set a value |
| `c:6` | Read a single value |
| `c:7` | Increment value |
| `c:8` | Decrement value |
| `c:9` | Get range (returns min/max) |
| `c:12` | Bulk read (returns multiple fields) |

---

## Known Quirks

- **Trailing commas:** Responses contain trailing commas before closing brackets (`}, ]`), making them invalid JSON. Strip them before parsing: `re.sub(r',\s*([}\]])', r'\1', response.text)`
- **Malformed HTTP headers:** All responses return non-standard headers. Catch the exception, check for `"header"` in the error string, and treat as success.
- **Input source reads:** Use the bulk status endpoint — direct reads of the source parameter are unreliable.
- **Input switching:** Only works when `nPowerStatus = 0` (fully on).

---

## Master Status Endpoint

Single call returns all projector state. **Use this as your primary polling method.**

```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:12,p:1049576
```

Works in all states including standby.

**Example response:**
```json
{
  "nPowerStatus": 6,
  "cVideoType": 255,
  "nLampHour": 1713,
  "nLampMode": 0,
  "nPWSourceID": 2,
  "nLanguage": 0,
  "nPictureMode": 0,
  "nEIPSourceID": 0,
  "nMiscSetting": 0,
  "nThreeDFormat": 0,
  "acResolution": "NA",
  "acProjectorFWVersion": "V1.02",
  "acProjectorName": "BenQ Projector",
  "acNetWork_FW_Version": "V1.02"
}
```

---

## Status Code Maps

### Power Status (`nPowerStatus`)
| Value | State | Notes |
|-------|-------|-------|
| `0` | On | Fully on, projecting |
| `6` | Standby | Network card on, lamp off |
| `7` | Warming Up | ~90 second warm-up |
| `8` | Cooling Down | ~90 second cool-down |
| Timeout | Off | Projector fully off, web server offline |

### Input Source (`nPWSourceID`)
| Value | Source |
|-------|--------|
| `0` | Computer 1 / YPbPr 1 |
| `1` | Video |
| `2` | S-Video |
| `5` | HDMI 1 |
| `11` | Component 1 |
| `13` | Computer 2 / YPbPr 2 |
| `17` | USB Reader / Flash Drive |
| `18` | Network Display |
| `19` | USB Display |
| `20` | USB Camera |
| `21` | Broadcast |
| `22` | HDMI 2 |

### Lamp Mode (`nLampMode`)
| Value | Mode | Rated Life |
|-------|------|-----------|
| `0` | Normal | ~3,500h |
| `1` | Economic | ~5,000h |
| `2` | SmartEco | ~5,000h |
| `3` | LampSave | ~6,000h |
| `4` | LumenCare | ~5,000h |

### Picture Mode (`nPictureMode`)
| Value | Mode |
|-------|------|
| `0` | Dynamic |
| `1` | Presentation |
| `2` | sRGB |
| `3` | Cinema |
| `4` | 3D |
| `5` | User 1 |
| `6` | User 2 |

### Aspect Ratio
| Value | Ratio |
|-------|-------|
| `0` | Auto |
| `1` | Real |
| `2` | 4:3 |
| `3` | 16:9 |
| `4` | 16:10 |
| `5` | Fill All |
| `6` | Fill to Aspect Ratio |
| `7` | Normal |
| `8` | Wide |
| `9` | Zoom |

---

## Complete Command Reference

### Power

**Power ON:**
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:851977,v:9
```

**Power OFF (5-step sequence, 500ms between each):**
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:6,p:851982
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:851977,v:9
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:6,p:851982
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:851977,v:9
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:6,p:1012
```

**Read power status:**
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:6,p:851982
→ [{"value": 0}]
```

---

### Input Source

**Switch input:**
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:917504,v:{source_id}
```

Examples:
```bash
# HDMI 1
curl -X POST "http://10.50.0.29/cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:917504,v:5"

# HDMI 2
curl -X POST "http://10.50.0.29/cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:917504,v:22"
```

> Read current source via bulk status (`p:1049576`), not via direct query.

---

### Volume

**Set volume (0–10):**
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:917516,v:{0-10}
```

**Read current volume:**
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:6,p:917516
→ [{"value": 5}]
```

**Volume up / down:**
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:7,p:917516   (up)
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:8,p:917516   (down)
```

**Get volume range:**
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:9,p:917516
→ [{"min": 0, "max": 10}]
```

**Toggle mute:**
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:851980,v:12
```

---

### Screen

**Toggle freeze (freeze current frame):**
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:851978,v:10
```

**Toggle ECO Blank (blank screen + reduce lamp power):**
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:851974,v:6
```

> ECO Blank is great for pause automations — it saves real lamp life.

---

### Picture Mode

**Set picture mode:**
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:983040,v:{mode_id}
```

**Read picture mode:** Use bulk status `nPictureMode` field.

**Bulk read all picture settings:**
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:12,p:983057
```

---

### Picture Adjustments (Read/Write)

All use `c:5` to write, `c:6` to read:

| Setting | Parameter ID |
|---------|-------------|
| Brightness | `p:983042` |
| Contrast | `p:983043` |
| Color | `p:983044` |
| Sharpness | `p:983046` |
| BrilliantColor | `p:983047` |
| Color Temperature | `p:983048` |

---

### Lamp Mode

**Set lamp mode:**
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:917513,v:{mode_id}
```

**Read lamp mode:** Use bulk status `nLampMode` field.

---

### Aspect Ratio

**Set aspect ratio:**
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:917505,v:{ratio_id}
```

---

### Display & Power Settings

**Bulk read all display settings:**
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:12,p:917521
```
Returns: `nPWSourceID`, `nAspectRatio`, `nVKeyStone`, `nHKeyStone`, `nAutoPowerOff`, `nBlankTimer`, `nSleepTimer`, `nLampMode`, `nAutoKeyStone`, and more.

**Auto Power Off** (minutes until auto-off with no signal):
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:917509,v:{value}
```
Values: `0`=Disable, `1`=3min, `2`=10min, `3`=15min, `4`=20min, `5`=25min, `6`=30min

**Sleep Timer:**
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:917511,v:{value}
```
Values: `0`=Disable, `1`=30min, `2`=1hr, `3`=2hr, `4`=3hr, `5`=4hr, `6`=8hr, `7`=12hr

**Direct Power On** (projector powers on when plugged in):
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:917512,v:{0|1}
```

**Quick Cooling** (faster fan cooldown):
```
POST /cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:917514,v:{0|1}
```

---

## Complete Parameter ID Table

| Function | `p:` | `c:` | `v:` | Notes |
|----------|------|------|------|-------|
| **STATUS** | | | | |
| Bulk status | `1049576` | `12` | — | Returns all fields |
| Power status | `851982` | `6` | — | Single value |
| Network config | `1049577` | `12` | — | IP/MAC/subnet |
| All display settings | `917521` | `12` | — | Bulk read |
| All picture settings | `983057` | `12` | — | Bulk read |
| **POWER** | | | | |
| Power ON | `851977` | `5` | `9` | |
| Power OFF step 1 | `851982` | `6` | — | |
| Power OFF step 2 | `851977` | `5` | `9` | |
| Power OFF step 3 | `851982` | `6` | — | |
| Power OFF step 4 | `851977` | `5` | `9` | |
| Power OFF step 5 | `1012` | `6` | — | Final step |
| **INPUT** | | | | |
| Source select | `917504` | `5` | source_id | 5=HDMI1, 22=HDMI2 |
| **VOLUME** | | | | |
| Volume read | `917516` | `6` | — | Returns 0–10 |
| Volume set | `917516` | `5` | 0–10 | |
| Volume up | `917516` | `7` | — | Increment |
| Volume down | `917516` | `8` | — | Decrement |
| Volume range | `917516` | `9` | — | Returns min/max |
| Mute toggle | `851980` | `5` | `12` | |
| **SCREEN** | | | | |
| Freeze toggle | `851978` | `5` | `10` | |
| ECO Blank toggle | `851974` | `5` | `6` | Blanks + saves power |
| **PICTURE** | | | | |
| Picture mode | `983040` | `5/6` | mode_id | 0=Dynamic, 3=Cinema |
| Brightness | `983042` | `5/6` | 0–100 | |
| Contrast | `983043` | `5/6` | value | |
| Sharpness | `983046` | `5/6` | value | |
| Color Temperature | `983048` | `5/6` | value | |
| **DISPLAY** | | | | |
| Aspect ratio | `917505` | `5/6` | ratio_id | 0=Auto, 2=4:3, 3=16:9 |
| Lamp mode | `917513` | `5/6` | mode_id | 0=Normal, 1=Economic |
| Auto power off | `917509` | `5/6` | value | 0=Disable |
| Sleep timer | `917511` | `5/6` | value | 0=Disable |
| Direct power on | `917512` | `5/6` | 0/1 | |
| Quick cooling | `917514` | `5/6` | 0/1 | |

---

## Quick Test Commands

```bash
PROJECTOR=10.50.0.29

# Full status (start here)
curl -s -X POST "http://$PROJECTOR/cgi-bin/webctrl.cgi.elf?&t:26,c:12,p:1049576"

# Power on
curl -s -X POST "http://$PROJECTOR/cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:851977,v:9"

# Switch to HDMI 1 (projector must be ON)
curl -s -X POST "http://$PROJECTOR/cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:917504,v:5"

# Get volume
curl -s -X POST "http://$PROJECTOR/cgi-bin/webctrl.cgi.elf?&t:26,c:6,p:917516"

# All display settings
curl -s -X POST "http://$PROJECTOR/cgi-bin/webctrl.cgi.elf?&t:26,c:12,p:917521"

# Set Cinema picture mode
curl -s -X POST "http://$PROJECTOR/cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:983040,v:3"

# Toggle ECO Blank
curl -s -X POST "http://$PROJECTOR/cgi-bin/webctrl.cgi.elf?&t:26,c:5,p:851974,v:6"

# Watch status during power cycle (polls every 10s)
while true; do
  curl -s -X POST "http://$PROJECTOR/cgi-bin/webctrl.cgi.elf?&t:26,c:12,p:1049576" | \
  python3 -c "
import sys, json, re
text = re.sub(r',\s*([}\]])', r'\1', sys.stdin.read())
d = json.loads(text)[0]
print(f'Power:{d[\"nPowerStatus\"]} Lamp:{d[\"nLampHour\"]}h Source:{d[\"nPWSourceID\"]} Mode:{d[\"nLampMode\"]}')
"
  sleep 10
done
```

---

## Security Note

BenQ projectors have no HTTP authentication on this interface. Keep your projector on a trusted local network. Do not expose port 80 to the internet.

*Tested on BenQ SH915 firmware V1.02. Parameter IDs are mathematically derived from firmware source and should be consistent across BenQ projectors using the same web interface platform (approximately 2012–2019).*
