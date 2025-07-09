# 8251 Emulator Debug Logging Guide

## Comprehensive Logging System

The 8251 emulator now includes detailed logging to help you trace and debug all operations in Thonny. Every operation is logged with timestamps, categories, and relevant data.

## Log Levels

```
Level 0 (NONE):   No logging
Level 1 (ERROR):  Critical errors only
Level 2 (WARN):   Warnings + errors  
Level 3 (INFO):   General information + above (DEFAULT)
Level 4 (DEBUG):  Debug details + above
Level 5 (TRACE):  All low-level details + above
```

## Changing Log Level

### From Timex/Sinclair Computer
```
ATLOG5    - Set to maximum verbosity (trace everything)
ATLOG4    - Debug level (good for development)
ATLOG3    - Info level (default)
ATLOG1    - Errors only
ATLOG0    - Disable all logging
```

### In Code (if needed)
```python
logger.set_log_level(logger.LOG_TRACE)  # Maximum verbosity
```

## Log Categories

### INIT - Initialization
```
[    1234ms] INFO  INIT    : Starting 8251 USART Emulator
[    1250ms] INFO  INIT    : Configuring GPIO pins
[    1267ms] INFO  INIT    : Setting up WiFi interface
```

### GPIO - Pin State Changes
```
[    2100ms] TRACE GPIO    : Port 73h interrupt triggered
[    2101ms] TRACE GPIO    : D0 = 1 | pin=0 | value=1
[    2102ms] TRACE GPIO    : D1 = 0 | pin=1 | value=0
```

### BUS - Z80 Bus Operations
```
[    2105ms] DEBUG BUS     : Handling I/O cycle | port=0x73 | type=DATA
[    2106ms] DEBUG BUS     : Z80 READ from port 0x73
[    2107ms] DEBUG BUS     : Sending data to Z80 | port=0x73 | data=0x4F
[    2110ms] TRACE BUS     : Read cycle completed | duration_ms=3
```

### 8251 - USART Emulation
```
[    2200ms] INFO  8251    : Data register read | data=0x41 | char=A | rx_remaining=5
[    2300ms] INFO  8251    : Control register write | data=0x37 | binary=00110111 | current_state=2
[    2301ms] INFO  8251    : Mode instruction received | mode=0x37 | new_state=MODE_INSTRUCTION
```

### AT_CMD - AT Command Processing
```
[    3000ms] INFO  AT_CMD  : Executing command | cmd=ATDT towel.blinkenlights.nl:23
[    3001ms] INFO  AT_CMD  : Dial command | target=towel.blinkenlights.nl:23
[    3002ms] INFO  AT_CMD  : Command result | cmd=ATDT towel | response=CONNECT
```

### NETWORK - Network Operations
```
[    4000ms] INFO  NETWORK : Attempting connection | target=towel.blinkenlights.nl:23
[    4050ms] DEBUG NETWORK : Parsed connection | host=towel.blinkenlights.nl | port=23
[    4200ms] INFO  NETWORK : Connected successfully | host=towel.blinkenlights.nl | port=23
[    4300ms] DEBUG NETWORK : Received data | bytes=12
[    4301ms] TRACE NETWORK : Queued byte | data=0x48 | char=H
```

### STATUS - Periodic Status
```
[   30000ms] INFO  STATUS  : Periodic status | wifi=True | connection=True | cmd_mode=False | rx_buffer=0 | tx_buffer=0 | 8251_state=3 | log_count=1247
```

## Example Debug Session

### 1. Start with Maximum Logging
```
From Timex/Sinclair: ATLOG5
Response: Log level set to 5
```

### 2. Connect to WiFi
```
AT+CWJAP="MyWiFi","password123"

Expected logs:
[   10000ms] INFO  AT_CMD  : Executing command | cmd=AT+CWJAP="MyWiFi","password123"
[   10001ms] INFO  NETWORK : Connecting to WiFi | ssid=MyWiFi
[   12000ms] INFO  NETWORK : WiFi connected | ip=192.168.1.100
```

### 3. Store and Dial Shortcut
```
AT&Z0=towel.blinkenlights.nl:23,Towel Day
ATDS0

Expected logs:
[   15000ms] INFO  AT_CMD  : Store shortcut | index=0 | host=towel.blinkenlights.nl:23
[   16000ms] INFO  AT_CMD  : Dial shortcut | index=0
[   16001ms] INFO  NETWORK : Attempting connection | target=towel.blinkenlights.nl:23
```

### 4. Monitor Data Transfer
```
When typing on remote host:

[   20000ms] DEBUG NETWORK : Received data | bytes=1
[   20001ms] TRACE NETWORK : Queued byte | data=0x48 | char=H
[   20002ms] TRACE 8251    : RXRDY set for network data
[   20010ms] DEBUG BUS     : Z80 READ from port 0x73
[   20011ms] INFO  8251    : Data register read | data=0x48 | char=H | rx_remaining=0
```

## Debugging Common Issues

### No Bus Activity
```
Look for:
- GPIO configuration messages
- Missing interrupt triggers
- Pin state changes

If you see GPIO setup but no BUS messages:
- Check hardware connections
- Verify 74HC688 address patterns
- Check /IORQ signal
```

### 8251 State Machine Issues
```
Look for:
- Mode instruction sequence
- Command instruction sequence
- State transitions

Proper sequence should be:
1. Mode instruction received
2. Command instruction received  
3. Entering operational state
```

### Network Connection Problems
```
Look for:
- WiFi connection status
- Socket connection attempts
- Error messages in NETWORK category

Common issues:
- WiFi not connected
- DNS resolution failures
- Firewall blocking connections
```

### Data Transfer Issues
```
Look for:
- NETWORK bytes received/sent
- 8251 buffer status
- BUS read/write operations

Data flow should be:
Network → RX Buffer → Z80 reads data register
Z80 writes data register → TX Buffer → Network
```

## Performance Monitoring

### Log Message Rate
```
High-traffic scenarios may generate 100+ log messages per second
Consider reducing log level during normal operation:
- ATLOG3 for general monitoring
- ATLOG4 for debugging
- ATLOG5 only for detailed analysis
```

### Buffer Status
```
Monitor buffer levels in periodic status messages:
- rx_buffer: Should be 0 when Z80 is reading data
- tx_buffer: Should be 0 when network is sending data
- High buffer counts indicate flow control issues
```

## Custom Debug Commands

### Status Check
```python
# Add to AT command handler if needed
elif command == "ATSTAT":
    # Custom status command
    status = {
        "uptime": utime.ticks_diff(utime.ticks_ms(), self.start_time),
        "log_count": logger.log_count,
        "rx_bytes": len(self.rx_buffer),
        "tx_bytes": len(self.tx_buffer)
    }
    return f"Status: {status}"
```

### Pin State Check
```python
elif command == "ATGPIO":
    # Check all GPIO states
    states = []
    for i in range(8):
        states.append(f"D{i}={self.data_pins[i].value()}")
    return " ".join(states)
```

## Tips for Effective Debugging

### 1. Start Simple
```
Begin with ATLOG3 (INFO level)
Only increase to TRACE when needed
Too much logging can overwhelm the console
```

### 2. Focus on Categories
```
If debugging network: Look for NETWORK logs
If debugging hardware: Look for BUS and GPIO logs  
If debugging 8251: Look for 8251 logs
```

### 3. Watch for Patterns
```
Successful operations show predictable patterns
Failures often show incomplete sequences
Timing issues appear as timeouts or missing events
```

### 4. Use Timestamps
```
All logs include millisecond timestamps
Use these to identify timing-sensitive issues
Look for gaps that indicate blocked operations
```

This comprehensive logging system should give you complete visibility into your 8251 emulator's operation and help identify any hardware or software issues quickly!