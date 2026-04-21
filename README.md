# BenQ Network Projector for Homey

Control your BenQ network-enabled projector directly from [Homey](https://homey.app). Power on/off, switch inputs, monitor lamp hours, and build powerful automations — all over your local network, no extra hardware required.

[![Homey App](https://img.shields.io/badge/Homey-App-brightgreen)](https://homey.app)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

---

## ✨ Features

- **Power control** — turn on/off from any Homey Flow or device card
- **Input switching** — switch between HDMI 1, HDMI 2, and other sources
- **Volume control** — adjust or mute audio
- **Lamp hours monitoring** — track usage with Homey Insights
- **Lamp life warnings** — get notified before your lamp needs replacing
- **ECO Blank** — blank the screen to save lamp life during pauses
- **Picture mode** — switch between Dynamic, Cinema, Presentation, and more
- **Status monitoring** — warming up, cooling down, and standby states all tracked
- **Auto-discovery** — finds your projector automatically on the local network

---

## 📺 Compatible Projectors

### Confirmed Working
| Model | Firmware | Notes |
|-------|---------|-------|
| BenQ SH915 | V1.02 | Fully tested |

### Likely Compatible
BenQ network projectors from approximately 2012–2019 that use the same web interface platform are likely compatible. This includes most models in the SH, SW, MH, MW, TH, and W series that have a **LAN Control** option in their settings menu.

> **Does your projector work?** Please [open an issue](../../issues/new?template=compatibility_report.md) and let us know! Every report helps expand the compatibility list.

### Requirements
- BenQ projector with **LAN Control** enabled (check your projector's Network Settings menu)
- Projector connected to your local network via Ethernet or WiFi
- Homey Self-Hosted Server, Homey Pro (2023/2026), or Homey Pro mini

---

## 🚀 Installation

### From the Homey App Store *(coming soon)*
Search for **BenQ Network Projector** in the Homey app.

### Manual Installation (Developer)
```bash
# Clone the repository
git clone https://github.com/fredhill/homey-benq-projector.git
cd homey-benq-projector

# Install Python dependencies (required after cloning)
npx homey app dependencies install

# Run locally against your Homey
npx homey app run
```

> ⚠️ **Important:** Always run `npx homey app dependencies install` after cloning or pulling changes. This builds the Python virtual environments that Homey needs to run the app. These are not stored in the repository.

---

## 🔧 Projector Setup

Before adding the device in Homey, make sure your projector is configured correctly:

1. On your projector, go to **Menu → System Setup → Network Settings**
2. Enable **LAN Control** (sometimes called Network Control)
3. Enable **Network Standby** if you want to be able to wake the projector remotely
4. Note the projector's **IP address** (shown in Network Settings)
5. Recommended: Set a **static IP** in your router for the projector so it doesn't change

### Network Standby Setting

This setting controls whether the projector's network card stays powered when the projector is "off":

| Setting | Behaviour |
|---------|-----------|
| **Network Standby ON** | Projector remains reachable when off. Enables remote wake-up. Recommended. |
| **Network Standby OFF** | Projector goes fully offline when off. App cannot detect state or wake remotely. |

If you don't see a Network Standby option, your projector may power off completely — the app will still work for control when the projector is on, but won't be able to detect the off state.

---

## 📱 Adding to Homey

1. Open the **Homey app** on iOS or Android
2. Go to **Devices → Add Device**
3. Search for **BenQ Network Projector**
4. The app will automatically scan your network for BenQ projectors
5. Select your projector from the list, or enter the IP address manually
6. Done! Your projector appears as a Homey device

---

## 🔄 Automation Examples

### Cinema lighting
```
When: BenQ Projector turned on
Then: Set living room lights to 20% warm white
      Set TV backlight on
```

### Automatic shutdown
```
When: Time is 11:30 PM
And:  BenQ Projector is on
Then: Turn off BenQ Projector
```

### Lamp life reminder
```
When: BenQ Projector lamp hours exceeds 3000
Then: Send push notification "Order a replacement lamp — 3000/3500 hours used"
```

### ECO Blank on pause *(saves real lamp life!)*
```
When: Plex media paused
Then: Enable ECO Blank on BenQ Projector
```
```
When: Plex media resumed  
Then: Disable ECO Blank on BenQ Projector
```

### Gaming setup
```
When: Xbox detected as on
And:  BenQ Projector is on
Then: Switch BenQ Projector input to HDMI 1
      Set picture mode to Dynamic
      Set lights to gaming preset
```

---

## 🎛️ Flow Cards

### Triggers
- Projector turned on
- Projector turned off
- Projector started warming up
- Projector started cooling down
- Lamp hours exceeded threshold *(tag: lamp_hours)*
- Input source changed *(tag: source_name)*

### Conditions
- Projector is on / off / warming / cooling / in standby
- Current input is [source]
- Lamp hours is less than [number]

### Actions
- Turn on projector
- Turn off projector
- Switch to HDMI 1 / HDMI 2 / [source]
- Set volume to [level]
- Mute / unmute
- Enable / disable ECO Blank
- Set picture mode to [mode]
- Set lamp mode to [Normal / Economic / SmartEco]

---

## ⚙️ Device Settings

| Setting | Description | Default |
|---------|-------------|---------|
| IP Address | Your projector's local IP address | Auto-detected |
| Status Check Interval | How often to poll projector status (seconds) | 120 |
| Network Standby Mode | Enable if projector stays reachable when off | Off |
| Lamp Warning Threshold | Hours at which to trigger lamp warning flow | 3000 |

---

## 🔍 Technical Notes

This app communicates with BenQ projectors using their built-in HTTP CGI interface (`/cgi-bin/webctrl.cgi.elf`). This interface is available on BenQ network projectors and does not require any additional hardware, serial cables, or bridge devices.

The interface was reverse-engineered from the projector's web interface JavaScript firmware files. Full API documentation is available in [docs/API_REFERENCE.md](docs/API_REFERENCE.md) for developers interested in extending the app or adding compatibility for other models.

### Known Quirks
- BenQ projectors return non-standard HTTP headers. This is expected behaviour and handled automatically.
- The projector's web interface displays cached data when in standby — always use the app's device card for accurate status.
- Input switching only works when the projector is fully powered on.

---

## 🤝 Contributing

Contributions are welcome! Here's how you can help:

### Report Projector Compatibility
If you have a BenQ network projector, please test the app and [report whether it works](../../issues/new?template=compatibility_report.md). Include:
- Your projector model number
- Firmware version (found in projector's Information menu)
- Which features work or don't work
- Any error messages from the Homey app log (`npx homey app log`)

### Code Contributions
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Run `npx homey app validate` to check for issues
5. Submit a pull request

### Development Setup
```bash
git clone https://github.com/fredhill/homey-benq-projector.git
cd homey-benq-projector
npm install -g homey          # Install Homey CLI
npx homey app dependencies install  # Build Python dependencies
npx homey login               # Log in to your Homey account
npx homey app run             # Run against your Homey
```

**Logs:**
```bash
npx homey app log             # View real-time app logs
```

---

## 📋 Changelog

### v1.0.0 *(in development)*
- Initial release
- Power on/off control
- Status monitoring (on / warming / cooling / standby)
- Lamp hours tracking with Homey Insights
- Lamp life warning flow cards
- Input switching (HDMI 1, HDMI 2, and more)
- Volume control and mute
- ECO Blank toggle
- Picture mode switching
- Auto-discovery on local network
- Confirmed compatible: BenQ SH915

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgements

- The Homey developer community for SDK documentation and support
- BenQ for building network control into their projectors
- Everyone who tests the app and reports compatibility

---

*Built with the [Homey Python Apps SDK](https://apps.developer.homey.app)*
