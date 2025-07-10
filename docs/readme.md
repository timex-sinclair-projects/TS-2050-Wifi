# 8251 USART Emulator for Raspberry Pi Pico W

**Timex/Sinclair 2050 Modem Replacement v1.0**

Emulates the Intel 8251 USART to replace the Timex/Sinclair 2050 modem with modern WiFi connectivity. Connects to telnet, SSH, and other TCP services over WiFi instead of dial-up phone lines.

## Hardware Connections

### 8251 USART Interface Pins:

- **GP0-GP7**: Data bus D0-D7 (bidirectional)
- **GP8**: C/D (Control/Data select)
- **GP9**: RD (Read strobe, active LOW)
- **GP10**: WR (Write strobe, active LOW)
- **GP11**: CS (Chip Select, active LOW)
- **GP12**: RESET (Reset, active HIGH)
- **GP13**: TxRDY (Transmitter Ready output)
- **GP14**: RxRDY (Receiver Ready output)
- **GP15**: CLK (Clock input)

### Normal Idle State:

- CS=1, RD=1, WR=1, RESET=0, C/D=X

## Complete Getting Started Tutorial

### First Time Setup (New Device)

1. **Power on your Pico W** - You'll see:

```
8251 USART Emulator v1.0
Timex/Sinclair 2050 WiFi Replacement
Memory: 45000 bytes available

Quick Start:
1. WIFI YourSSID YourPassword
2. RECONNECT (for saved networks)
3. CONNECT hostname port
4. AT Dhostname:port
5. Type HELP for commands

8251 USART EMULATOR READY
HELP for commands | QUIT to exit
> 
```

1. **Connect to your WiFi network:**

```
> WIFI MyNetwork MyPassword123
Connecting to WiFi: MyNetwork
WiFi connected! IP: 192.168.1.150
Credentials saved for auto-reconnect
> 
```

1. **Connect to a remote host (example: classic BBS):**

```
> CONNECT bbs.fozztexx.com 23
CONNECTED to bbs.fozztexx.com:23
```

1. **You're now connected!** The BBS login screen will appear. Your Timex/Sinclair computer can now communicate as if connected to a real modem.
2. **When done, disconnect:**

```
> DISCONNECT
DISCONNECTED
> 
```

### Using Hayes AT Commands (Alternative Method)

You can also use traditional modem commands:

```
> AT +CWJAP="MyNetwork","MyPassword123"
COMMAND: AT+CWJAP="MyNetwork","MyPassword123"
RESPONSE: OK

> AT Dbbs.fozztexx.com:23
COMMAND: ATDbbs.fozztexx.com:23
RESPONSE: CONNECT

> AT H
COMMAND: ATH
RESPONSE: OK
```

### Subsequent Power-Ons (Auto-Connect)

When you power on the device after initial setup:

```
8251 USART Emulator v1.0
Timex/Sinclair 2050 WiFi Replacement
[00001234] SYSTEM: Attempting auto-connect...
[00002156] NETWORK: Connecting to WiFi: MyNetwork
[00004523] NETWORK: WiFi connected! IP: 192.168.1.150
[00004525] SYSTEM: Auto-connect successful!
Memory: 43000 bytes available

8251 USART EMULATOR READY
HELP for commands | QUIT to exit
> 
```

**The device automatically reconnects to your saved WiFi network!**

### Quick Reconnection if Auto-Connect Fails

If the auto-connect fails (network temporarily down, etc.):

```
> RECONNECT
Reconnecting to MyNetwork (from saved config)...
Reconnected successfully!
> 
```

### Managing WiFi Networks

#### Check current WiFi status:

```
> WIFI_STATUS
WIFI STATUS:
Status: CONNECTED
IP Address: 192.168.1.150
Subnet: 255.255.255.0
Gateway: 192.168.1.1
DNS: 8.8.8.8
Session SSID: MyNetwork
Saved SSID: MyNetwork
Auto-connect: Enabled
```

#### Scan for available networks:

```
> AT +CWLAP
COMMAND: AT+CWLAP
RESPONSE: Found 8 networks:
+CWLAP:(3,"MyNetwork",-45,"aa:bb:cc:dd:ee:ff",6,WPA2_PSK)
+CWLAP:(3,"NeighborWifi",-67,"11:22:33:44:55:66",11,WPA2_PSK)
+CWLAP:(0,"FreeWifi",-72,"99:88:77:66:55:44",1,OPEN)
...
OK
```

#### Connect to a different network:

```
> WIFI NewNetwork NewPassword456
Connecting to WiFi: NewNetwork
WiFi connected! IP: 192.168.0.100
Credentials saved for auto-reconnect
```

#### Clear saved credentials:

```
> FORGET_WIFI
Saved WiFi credentials cleared

> AUTO_CONNECT off
Auto-connect disabled
```

### Common Connection Examples

#### Classic BBS Systems:

```
> CONNECT bbs.fozztexx.com 23          # FozzTexx BBS
> CONNECT telnet.battlebbs.com 23      # BattleBBS  
> CONNECT bbs.retrobattlestations.com 23  # Retro Battle Stations
```

#### Fun Internet Services:

```
> CONNECT towel.blinkenlights.nl 23    # Star Wars ASCII art
> CONNECT telehack.com 23              # Simulated vintage internet
```

#### Using Hayes AT Commands:

```
> AT Dtowel.blinkenlights.nl:23        # Connect with dial command
> AT H                                 # Hang up when done
> +++                                  # Escape to command mode (if connected)
> AT O                                 # Return to online mode
```

### Troubleshooting Common Issues

#### WiFi Connection Problems:

```
> AT +CWLAP                           # Scan for networks first
> WIFI_STATUS                         # Check current status
> RECONNECT                           # Try reconnecting
> FORGET_WIFI                         # Clear and start over if needed
```

#### Network Connection Problems:

```
> CONNECT 8.8.8.8 53                 # Test with IP address first
> CONNECT google.com 80               # Test DNS resolution
```

#### Memory Issues:

```
> MEMORY                              # Check available memory
> DEBUG VERBOSE                       # Turn off verbose debugging
```

#### Reset/Hardware Issues:

```
> GPIO                                # Check pin states
> PINS                                # Show pin configuration
```

### Advanced Configuration

#### Disable auto-connect:

```
> AUTO_CONNECT off
Auto-connect disabled

> AT +CWAUTO=0
COMMAND: AT+CWAUTO=0
RESPONSE: OK: Auto-connect disabled
```

#### Enable debugging for troubleshooting:

```
> DEBUG NETWORK                       # Toggle network debugging
> DEBUG HAYES                         # Toggle AT command debugging
```

#### Save current WiFi config manually:

```
> AT +CWSAVE
COMMAND: AT+CWSAVE
RESPONSE: OK: WiFi config saved
```

## Interactive Commands Quick Reference

### WiFi Management

- `WIFI <ssid> <password>` - Connect to WiFi network and save credentials
- `RECONNECT` - Reconnect to last used or saved network
- `WIFI_STATUS` - Show detailed WiFi connection status
- `FORGET_WIFI` - Clear saved WiFi credentials
- `AUTO_CONNECT on|off` - Enable/disable auto-connect on startup

### Network Connections

- `CONNECT <host> <port>` - Connect to telnet/SSH host (supports DNS)
- `DISCONNECT` - Disconnect current connection

### Hayes AT Commands

- `AT <command>` - Send Hayes AT command

### System Commands

- `STATUS` - Show comprehensive system status
- `MEMORY` - Show memory usage
- `GPIO` - Show current GPIO pin states
- `PINS` - Show pin configuration and troubleshooting
- `DEBUG <category>` - Toggle debug categories (GPIO, USART, NETWORK, HAYES, INTERFACE, SYSTEM, VERBOSE)
- `HELP` - Show quick command reference
- `QUIT` / `EXIT` / `BYE` - Exit command interface

## Hayes AT Commands Supported

### Basic Modem Commands

- `ATI` or `ATI0` - Information (shows emulator version)
- `ATZ` - Reset modem state
- `ATH` or `ATH0` - Hang up (disconnect)
- `ATD<number>` - Dial (connect to host:port, e.g., `ATD192.168.1.100:23`)
- `ATO` or `ATO0` - Return to online mode
- `AT&F` - Factory defaults
- `+++` - Escape to command mode (when connected)

### WiFi AT Commands

- `AT+CWLAP` - List/scan available WiFi networks
- `AT+CWSCAN` - Alias for AT+CWLAP
- `AT+CWJAP?` - Query current WiFi connection
- `AT+CWJAP="ssid","password"` - Connect to WiFi network
- `AT+CWQAP` - Disconnect from WiFi
- `AT+CWSTAT` - Show detailed WiFi status
- `AT+CWSAVE` - Save current WiFi configuration
- `AT+CWAUTO=1|0` - Enable/disable auto-connect on startup
- `AT+CWFORGET` - Clear saved WiFi configuration

## WiFi Persistence Features

### Auto-Connect Behavior

- WiFi credentials are **automatically saved** when connecting successfully
- Device **auto-reconnects on startup** by default (can be disabled)
- Credentials stored in `wifi_config.txt` on flash memory
- **Survives power cycles** - no need to re-enter credentials

### Manual Control

- Use `FORGET_WIFI` or `AT+CWFORGET` to clear saved credentials
- Use `AUTO_CONNECT off` or `AT+CWAUTO=0` to disable auto-connect
- Use `RECONNECT` for quick reconnection attempts
- Use `WIFI_STATUS` to check current and saved network information

## Debug System

The emulator includes comprehensive debugging with the following categories:

### Debug Categories (Toggle with `DEBUG <category>`)

- **GPIO** - Pin state changes and register access (disabled by default)
- **USART** - USART register operations and data flow
- **NETWORK** - Network connection status and data transfer
- **HAYES** - Hayes AT command processing
- **INTERFACE** - Host interface monitoring (disabled by default)
- **SYSTEM** - Initialization, memory usage, system status
- **VERBOSE** - Extra detailed output for troubleshooting (disabled by default)

### Memory Optimization

Some debug categories are disabled by default to conserve memory. Enable only what you need for troubleshooting:

```
> DEBUG GPIO                          # Enable GPIO debugging
> DEBUG VERBOSE                       # Enable verbose output
```

## Typical Usage Workflow

### Daily Use (After Initial Setup)

1. **Power on** → Automatic WiFi connection
2. **Connect to service**: `CONNECT bbs.fozztexx.com 23`
3. **Use your Timex/Sinclair** as normal
4. **Disconnect when done**: `DISCONNECT` or `AT H`

### Changing Networks

1. **Connect to new network**: `WIFI NewSSID NewPassword`
2. **Credentials automatically saved** for next startup
3. **Old credentials replaced**

### Traveling/Mobile Use

1. **Scan for networks**: `AT +CWLAP`
2. **Connect to hotel/public WiFi**: `WIFI HotelWiFi password123`
3. **Forget when leaving**: `FORGET_WIFI`

## Troubleshooting Guide

### WiFi Issues

**Problem**: Auto-connect fails on startup **Solution**:

```
> WIFI_STATUS                         # Check what's saved
> RECONNECT                           # Try manual reconnect
> AT +CWLAP                           # Scan for available networks
```

**Problem**: Can't connect to saved network **Solution**:

```
> FORGET_WIFI                         # Clear old credentials
> WIFI NetworkName NewPassword        # Re-enter credentials
```

### Network Connection Issues

**Problem**: Can't connect to hostname **Solution**:

```
> CONNECT 8.8.8.8 53                 # Test with IP first
> DEBUG NETWORK                      # Enable network debugging
> CONNECT hostname port               # Try again with debugging
```

**Problem**: Connection drops frequently **Solution**:

```
> WIFI_STATUS                         # Check signal strength
> RECONNECT                           # Reestablish WiFi
```

### Memory Issues

**Problem**: Memory allocation errors **Solution**:

```
> MEMORY                              # Check available memory
> DEBUG VERBOSE                       # Disable verbose debugging
> DEBUG GPIO                          # Disable GPIO debugging
```

### Hardware Issues

**Problem**: Reset loops or erratic behavior **Solution**:

```
> GPIO                                # Check pin states
> PINS                                # Review hardware connections
```

Verify GP12 (RESET) is not floating and properly connected to GND.

## Technical Details

### 8251 Register Emulation

- **Data Register** (Address 0): Handles transmitted/received data
- **Status/Command Register** (Address 1): Status reads, command/mode writes
- Full status register bit emulation (TxRDY, RxRDY, TxE, errors)
- Proper mode and command instruction processing

### Network Features

- Automatic DNS resolution for hostnames
- Non-blocking socket operations with proper timeout handling
- Network data buffering and flow control
- Support for telnet, SSH, and other TCP services

### Memory Management

- Optimized for Pico W's limited RAM
- Automatic garbage collection
- Configurable debug output to reduce memory usage
- Flash storage for WiFi credentials

## Compatible Systems

Designed for **Timex/Sinclair computers** with the **2050 modem interface**, but should work with any system that uses the Intel 8251 USART interface with the same pinout and timing.

## File Structure

When running, the emulator creates:

- `wifi_config.txt` - Saved WiFi credentials (automatically managed)

## Version Information

**Version**: 1.0
 **Hardware**: Raspberry Pi Pico W
 **Firmware**: MicroPython
 **Memory Usage**: ~25-30KB (optimized for Pico W)

For technical support and updates, refer to the project documentation and hardware troubleshooting section above.