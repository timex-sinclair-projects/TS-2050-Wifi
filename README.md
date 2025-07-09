# Intel 8251 WiFi Modem Emulator for Timex/Sinclair Computers

A modern WiFi modem that emulates the Intel 8251 USART for vintage Timex/Sinclair computers, replacing traditional modems with network connectivity.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Platform](https://img.shields.io/badge/platform-Raspberry%20Pi%20Pico%20W-green.svg)
![Language](https://img.shields.io/badge/language-MicroPython-yellow.svg)

## 🎯 Overview

This project transforms a **Raspberry Pi Pico W** into a **WiFi modem** that perfectly emulates an **Intel 8251 USART** from the perspective of vintage Z80-based computers. It provides modern network connectivity while maintaining complete hardware compatibility with original software.

### Key Features

- ✅ **Complete 8251 USART emulation** with proper state machine
- ✅ **WiFi connectivity** replacing traditional phone line modems  
- ✅ **Hayes AT command compatibility** for vintage software
- ✅ **Telnet and SSH support** for connecting to modern services
- ✅ **50 host shortcuts** with persistent storage (phonebook)
- ✅ **Hardware-accurate timing** for Z80 bus compatibility
- ✅ **Comprehensive debug logging** for development and troubleshooting
- ✅ **Complete address decoding** (responds only to ports 73h and 77h)

## 🏗️ Hardware Design

### System Architecture

```
Timex/Sinclair Computer (Z80, 5V TTL)
            ↕ 
    ┌─────────────────┐
    │ Level Shifting  │ ← 74HC688 + 74LVC245 + 74LVC125
    │ & Bus Interface │
    └─────────────────┘
            ↕
    Raspberry Pi Pico W (3.3V CMOS)
            ↕
        WiFi Network
            ↕
    Internet (Telnet/SSH servers, BBSs)
```

### Required Components

| Component | Description | Quantity | Approx Cost |
|-----------|-------------|----------|-------------|
| **Raspberry Pi Pico W** | Main microcontroller with WiFi | 1 | $6.00 |
| **74HC688** | 8-bit address comparator (5V) | 2 | $1.50 |
| **74LVC245** | Bidirectional bus transceiver | 1 | $0.75 |
| **74LVC125** | Quad 3-state buffer | 1 | $0.60 |
| **Resistors** | 10kΩ pullups, power connections | ~15 | $0.50 |
| **Capacitors** | Power supply filtering and decoupling | ~10 | $1.00 |
| **PCB/Breadboard** | Circuit construction | 1 | $2.00 |
| | | **Total** | **~$12.35** |

### Circuit Design

#### Address Decoding (Complete 8-bit)
```
Z80 Address Bus A7-A0 → 74HC688 #1 → Exact match for 73h (01110011)
                     → 74HC688 #2 → Exact match for 77h (01110111)
```

#### Level Shifting (5V ↔ 3.3V)
```
Z80 Data Bus (5V) ↔ 74LVC245 ↔ Pico W GPIO0-7 (3.3V)
Z80 Control (5V)  → 74LVC125 → Pico W GPIO10-15 (3.3V)
```

#### Power Distribution
```
5V System Power → Pico W VBUS + 74HC688 chips (TTL logic)
                → 3V3_EN via 10kΩ (regulator enable)
                → 3V3_OUT → 74LVC chips (CMOS logic)
```

## 🔧 Pin Assignments

### Pico W GPIO Mapping
```
GPIO 0-7:   Data bus (D0-D7) via 74LVC245
GPIO 10:    /RD signal from 74LVC125  
GPIO 11:    /WR signal from 74LVC125
GPIO 12:    Port 73h select from 74HC688 #1
GPIO 13:    Port 77h select from 74HC688 #2
GPIO 14:    74LVC245 direction control (DIR)
GPIO 15:    74LVC245 output enable (/OE)

Power:
Pin 36:     3V3_OUT → 74LVC245, 74LVC125
Pin 37:     3V3_EN ← 5V via 10kΩ (regulator enable)
Pin 40:     VBUS ← 5V system power
```

### Address Decoding Logic
```
Port 73h (Data):        74HC688 #1 compares A7-A0 with 01110011
Port 77h (Control):     74HC688 #2 compares A7-A0 with 01110111
Enable:                 Z80 /IORQ signal

Result: Responds ONLY to exact ports, prevents conflicts
```

## 💻 Software Installation

### 1. Install MicroPython on Pico W
```bash
# Download latest MicroPython firmware for Pico W
# Flash using drag-and-drop method
```

### 2. Upload the Emulator Code
```bash
# Copy main.py to Pico W using Thonny or rshell
# File will auto-run on power-up
```

### 3. Hardware Assembly
- Construct circuit according to schematic
- Connect to Timex/Sinclair I/O bus
- Apply 5V power to system

## 🚀 Usage

### Initial Setup

1. **Power on** the system
2. **Connect WiFi** from Timex/Sinclair:
   ```
   AT+CWJAP="YourWiFi","YourPassword"
   ```
3. **Test connection**:
   ```
   AT
   ATI
   ```

### Connecting to Remote Hosts

#### Direct Connection
```
ATDT hostname:port
ATDT towel.blinkenlights.nl:23    # Famous Towel Day server
ATDT mud.example.com:4000         # MUD server  
ATDT bbs.retrobattlestations.com:23  # Retro BBS
```

#### Using Shortcuts (Phonebook)
```
AT&Z0=towel.blinkenlights.nl:23,Towel Day BBS    # Store shortcut 0
AT&Z1=bbs.retrobattlestations.com:23,Retro BBS   # Store shortcut 1
AT&V                                             # View all shortcuts
ATDS0                                            # Dial shortcut 0
ATDS1                                            # Dial shortcut 1
```

#### Disconnect
```
ATH        # Hang up connection
+++        # Escape to command mode (if needed)
```

## 📋 Complete AT Command Reference

### Basic Commands
| Command | Description | Example |
|---------|-------------|---------|
| `AT` | Test command | `AT` → `OK` |
| `ATI` | Show version | `ATI` → `Pico W 8251 WiFi Modem v1.0` |
| `ATI1` | Show version + shortcuts | `ATI1` → Version + `Shortcuts: 5/50` |
| `AT?` | Help | `AT?` → Command list |

### Connection Commands  
| Command | Description | Example |
|---------|-------------|---------|
| `ATDT host:port` | Dial host directly | `ATDT towel.blinkenlights.nl:23` |
| `ATDS0-49` | Dial stored shortcut | `ATDS0` |
| `ATH` | Hang up | `ATH` → `NO CARRIER` |
| `ATA` | Answer (not supported) | `ATA` → `NO CARRIER` |

### WiFi Commands
| Command | Description | Example |
|---------|-------------|---------|
| `AT+CWJAP="ssid","pass"` | Connect to WiFi | `AT+CWJAP="MyWiFi","password123"` |
| `AT+CWJAP?` | Check WiFi status | `AT+CWJAP?` → `Connected to MyWiFi` |

### Shortcut Management
| Command | Description | Example |
|---------|-------------|---------|
| `AT&Z0=host:port,desc` | Store shortcut | `AT&Z0=bbs.com:23,My BBS` |
| `AT&V` | View all shortcuts | `AT&V` → List all stored numbers |
| `AT&F0` | Delete shortcut | `AT&F0` → Delete shortcut 0 |
| `AT&R` | Reset all shortcuts | `AT&R` → Clear phonebook |

### Debug Commands
| Command | Description | Example |
|---------|-------------|---------|
| `ATLOG0-5` | Set log level | `ATLOG5` → Maximum verbosity |
| `+++` | Escape to command mode | `+++` → `OK` |

## 🐛 Debugging Features

### Comprehensive Logging System

The emulator includes detailed logging visible in Thonny for debugging:

```
[    1234ms] INFO  INIT    : Starting 8251 USART Emulator
[    2105ms] DEBUG BUS     : Z80 READ from port 0x73
[    2106ms] INFO  8251    : Data register read | data=0x41 | char=A
[    3000ms] INFO  AT_CMD  : Executing command | cmd=ATDT example.com:23
[    4200ms] INFO  NETWORK : Connected successfully
```

### Log Categories
- **INIT** - Initialization and startup
- **GPIO** - Pin state changes and hardware
- **BUS** - Z80 bus operations and timing  
- **8251** - USART register operations
- **AT_CMD** - AT command processing
- **NETWORK** - WiFi and socket operations
- **STATUS** - Periodic system status

### Log Levels
```
ATLOG0 - No logging
ATLOG1 - Errors only
ATLOG2 - Warnings + errors  
ATLOG3 - Info (default)
ATLOG4 - Debug details
ATLOG5 - Trace everything
```

## 🔌 Hardware Compatibility

### Tested Systems
- **Timex/Sinclair 1000** (Z80 @ 3.25MHz)
- **Timex/Sinclair 2068** (Z80 @ 3.5MHz)
- **Generic Z80 systems** using ports 73h/77h

### Electrical Specifications
- **Supply Voltage**: 5V (system) → 3.3V (internal)
- **Logic Levels**: TTL compatible (5V) ↔ CMOS (3.3V)
- **Bus Timing**: Z80 @ 4MHz maximum (250ns cycle)
- **Current Draw**: ~200mA typical (WiFi active)

### Signal Integrity
- **Propagation Delay**: <50ns total (hardware + software)
- **Address Decoding**: Complete 8-bit for conflict prevention
- **Level Shifting**: Bidirectional with proper tri-state control

## 🌐 Network Features

### Supported Protocols
- **Telnet** (port 23) - Traditional terminal access
- **SSH** (port 22) - Secure terminal access  
- **Custom TCP** - Any TCP-based service
- **Raw sockets** - Direct TCP connections

### Connection Types
- **Bulletin Board Systems (BBSs)** - Retro online communities
- **MUD servers** - Multi-User Dungeons
- **Modern services** - Any TCP-based service
- **IoT devices** - Network-connected hardware
- **Terminal servers** - Remote system access

## 📁 File Structure

```
├── main.py              # Main emulator code
├── README.md           # This file
├── docs/
│   ├── schematic.pdf   # Complete circuit schematic
│   ├── pcb-layout.pdf  # Suggested PCB layout
│   └── bom.csv         # Bill of materials
├── examples/
│   ├── basic-test.py   # Simple test program
│   └── bbs-connect.py  # BBS connection example
└── LICENSE             # MIT License
```

## 🤝 Contributing

Contributions are welcome! Please:

1. **Fork** the repository
2. **Create** a feature branch (`git checkout -b feature/amazing-feature`)
3. **Commit** your changes (`git commit -m 'Add amazing feature'`)
4. **Push** to the branch (`git push origin feature/amazing-feature`)
5. **Open** a Pull Request

### Development Guidelines
- Follow existing code style and commenting
- Test on real hardware when possible
- Update documentation for new features
- Add logging for new operations

## 🐛 Known Issues & Limitations

- **Z80 timing**: Very fast Z80 systems (>6MHz) may need timing adjustments
- **Large transfers**: Continuous high-speed data may cause buffer overruns
- **SSH encryption**: Limited by Pico W processing power for complex encryption
- **Concurrent connections**: Single connection only (true to original 8251)

## 🔮 Future Enhancements

- [ ] **Hardware flow control** (RTS/CTS)
- [ ] **Multiple baud rates** simulation
- [ ] **File transfer protocols** (XMODEM, YMODEM, ZMODEM)
- [ ] **Terminal emulation** improvements
- [ ] **Web interface** for configuration
- [ ] **SD card storage** for offline data

## 📞 Support & Contact

- **GitHub Issues**: For bugs and feature requests
- **Discussions**: For general questions and community chat
- **Wiki**: Additional documentation and examples

