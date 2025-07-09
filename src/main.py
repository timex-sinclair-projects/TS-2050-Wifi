"""
Intel 8251 USART Emulator for Raspberry Pi Pico W
Emulates 8251 behavior for Timex/Sinclair computers
Ports: 73h (data), 77h (control/status)

Hardware Interface:
- 74HC688: 8-bit address comparator for complete port decoding
- 74HC138: Secondary decoder for A2-A0 bits  
- 74LVC245: Bidirectional data bus buffer (5V ↔ 3.3V)
- 74LVC125: Quad level shifter for control signals (5V → 3.3V)

Power Requirements:
- 5V input to VBUS (pin 40) and 74HC688 chips
- 3V3_EN (pin 37) tied to 5V via 10kΩ for reliable regulator enable
- 3V3_OUT (pin 36) powers 74LVC245 & 74LVC125

Complete Address Decoding:
- Port 73h: Responds ONLY to exact address 01110011
- Port 77h: Responds ONLY to exact address 01110111  
- Prevents conflicts with other I/O devices (03h, 13h, etc.)

Note: GPIO assignments avoid WiFi reserved pins (23, 24, 25) on Pico W
"""

import machine
import utime
import _thread
import socket
import network
import select
import json
import os
from collections import deque

class DebugLogger:
    """Comprehensive logging system for 8251 emulator debugging"""
    
    # Log levels
    LOG_NONE = 0
    LOG_ERROR = 1
    LOG_WARNING = 2  
    LOG_INFO = 3
    LOG_DEBUG = 4
    LOG_TRACE = 5
    
    def __init__(self, log_level=LOG_INFO):
        self.log_level = log_level
        self.start_time = utime.ticks_ms()
        self.log_count = 0
        
    def _should_log(self, level):
        return level <= self.log_level
        
    def _timestamp(self):
        """Get timestamp in milliseconds since startup"""
        return utime.ticks_diff(utime.ticks_ms(), self.start_time)
        
    def _log(self, level, category, message, data=None):
        """Internal logging function"""
        if not self._should_log(level):
            return
            
        self.log_count += 1
        timestamp = self._timestamp()
        
        level_names = ["NONE", "ERROR", "WARN", "INFO", "DEBUG", "TRACE"]
        level_name = level_names[min(level, len(level_names)-1)]
        
        log_line = f"[{timestamp:8d}ms] {level_name:5s} {category:8s}: {message}"
        
        if data is not None:
            if isinstance(data, dict):
                data_str = " | ".join([f"{k}={v}" for k, v in data.items()])
            else:
                data_str = str(data)
            log_line += f" | {data_str}"
            
        print(log_line)
        
    def error(self, category, message, data=None):
        self._log(self.LOG_ERROR, category, message, data)
        
    def warning(self, category, message, data=None):
        self._log(self.LOG_WARNING, category, message, data)
        
    def info(self, category, message, data=None):
        self._log(self.LOG_INFO, category, message, data)
        
    def debug(self, category, message, data=None):
        self._log(self.LOG_DEBUG, category, message, data)
        
    def trace(self, category, message, data=None):
        self._log(self.LOG_TRACE, category, message, data)
        
    def log_gpio_state(self, pin_name, pin_number, value, direction=""):
        """Log GPIO pin state changes"""
        data = {"pin": pin_number, "value": value, "dir": direction}
        self.trace("GPIO", f"{pin_name} state", data)
        
    def log_bus_cycle(self, cycle_type, port, data_value=None, success=True):
        """Log Z80 bus cycles"""
        data = {"port": f"0x{port:02X}", "success": success}
        if data_value is not None:
            data["data"] = f"0x{data_value:02X}"
        self.debug("BUS", f"{cycle_type} cycle", data)
        
    def log_8251_operation(self, operation, register, value, state=None):
        """Log 8251 register operations"""
        data = {"reg": register, "value": f"0x{value:02X}"}
        if state:
            data["state"] = state
        self.info("8251", f"{operation}", data)
        
    def log_network_event(self, event, details=None):
        """Log network-related events"""
        self.info("NETWORK", event, details)
        
    def log_at_command(self, command, response=None, success=True):
        """Log AT command processing"""
        data = {"cmd": command[:20], "success": success}  # Truncate long commands
        if response:
            data["resp"] = response[:30]  # Truncate long responses
        self.info("AT_CMD", "Command processed", data)
        
    def set_log_level(self, level):
        """Change logging verbosity at runtime"""
        self.log_level = level
        self.info("LOGGER", f"Log level changed to {level}")

# Global logger instance
logger = DebugLogger(DebugLogger.LOG_DEBUG)  # Start with DEBUG level

class Intel8251Emulator:
    """Intel 8251 USART Emulator with WiFi modem functionality"""
    
    # GPIO Pin Definitions (Pico W compatible - avoiding WiFi pins 23,24,25)
    DATA_DIR_PIN = 14      # 74LVC245 direction control
    DATA_OE_PIN = 15       # 74LVC245 output enable
    PORT_73H_PIN = 12      # 74HC688 #1 P=Q output (port 73h select)
    PORT_77H_PIN = 13      # 74HC688 #2 P=Q output (port 77h select)  
    WR_PIN = 11            # Z80 Write signal (via 74LVC125)
    RD_PIN = 10            # Z80 Read signal (via 74LVC125)
    
    # Data bus pins (GPIO 0-7) - avoids WiFi reserved pins
    DATA_BUS_BASE = 0
    
    # 8251 States
    STATE_RESET = 0
    STATE_MODE_INSTRUCTION = 1
    STATE_COMMAND_INSTRUCTION = 2
    STATE_OPERATIONAL = 3
    
    # Status register bits
    STATUS_TXRDY = 0x01    # Transmitter ready
    STATUS_RXRDY = 0x02    # Receiver ready
    STATUS_TXE = 0x04      # Transmitter empty
    STATUS_PE = 0x08       # Parity error
    STATUS_OE = 0x10       # Overrun error
    STATUS_FE = 0x20       # Framing error
    STATUS_SYNDET = 0x40   # Sync detect
    STATUS_DSR = 0x80      # Data set ready
    
    # Command register bits
    CMD_TXEN = 0x01       # Transmit enable
    CMD_DTR = 0x02        # Data terminal ready
    CMD_RXEN = 0x04       # Receive enable
    CMD_SBRK = 0x08       # Send break
    CMD_ER = 0x10         # Error reset
    CMD_RTS = 0x20        # Request to send
    CMD_IR = 0x40         # Internal reset
    CMD_EH = 0x80         # Enter hunt mode
    
    def __init__(self):
        """Initialize the 8251 emulator"""
        logger.info("INIT", "Starting 8251 USART Emulator")
        
        self.state = self.STATE_RESET
        self.mode_instruction = 0
        self.command_instruction = 0
        self.status_register = self.STATUS_TXE | self.STATUS_TXRDY
        
        # Data buffers
        self.rx_buffer = deque((), 1024)  # Receive buffer
        self.tx_buffer = deque((), 1024)  # Transmit buffer
        
        # Network connection
        self.wifi_connected = False
        self.socket_connection = None
        self.at_command_mode = True
        self.at_buffer = ""
        
        # Host shortcuts (phonebook)
        self.shortcuts = {}  # Dict: {index: {"host": "hostname:port", "desc": "description"}}
        self.shortcuts_file = "shortcuts.json"
        self.load_shortcuts()
        
        # Initialize hardware
        logger.info("INIT", "Configuring GPIO pins")
        self.setup_gpio()
        
        logger.info("INIT", "Setting up WiFi interface")
        self.setup_wifi()
        
        # Start background tasks
        logger.info("INIT", "Starting background threads")
        _thread.start_new_thread(self.network_handler, ())
        _thread.start_new_thread(self.bus_monitor, ())
        
        logger.info("INIT", "8251 USART Emulator initialized successfully")
    
    def setup_gpio(self):
        """Configure GPIO pins for bus interface"""
        logger.debug("GPIO", "Setting up control pins")
        
        # Control pins
        self.data_dir = machine.Pin(self.DATA_DIR_PIN, machine.Pin.OUT)
        self.data_oe = machine.Pin(self.DATA_OE_PIN, machine.Pin.OUT)
        self.port_73h = machine.Pin(self.PORT_73H_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
        self.port_77h = machine.Pin(self.PORT_77H_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
        self.rd = machine.Pin(self.RD_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
        self.wr = machine.Pin(self.WR_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
        
        logger.debug("GPIO", "Setting up data bus pins")
        # Data bus pins - external 10kΩ pullups recommended
        self.data_pins = []
        for i in range(8):
            # Note: External pullups preferred over internal for signal integrity
            pin = machine.Pin(self.DATA_BUS_BASE + i, machine.Pin.IN)
            self.data_pins.append(pin)
            logger.trace("GPIO", f"Data pin GPIO{self.DATA_BUS_BASE + i} configured")
        
        # Configure unused pins to prevent floating inputs
        self.setup_unused_pins()
        
        # Default state: disable outputs, set direction to input
        self.data_oe.value(1)    # Disable (active low)
        self.data_dir.value(0)   # A→B (Z80 to Pico)
        logger.debug("GPIO", "74LVC245 configured", {"dir": "A→B", "oe": "disabled"})
        
        # Set up interrupts on 74HC688 decoder outputs (active low)
        logger.debug("GPIO", "Setting up interrupt handlers")
        self.port_73h.irq(trigger=machine.Pin.IRQ_FALLING, handler=self.port_73h_handler)
        self.port_77h.irq(trigger=machine.Pin.IRQ_FALLING, handler=self.port_77h_handler)
        
        logger.info("GPIO", "All GPIO pins configured successfully")
    
    def setup_unused_pins(self):
        """Configure unused GPIO pins to prevent floating inputs"""
        unused_pins = [8, 9, 16, 17, 18, 19, 20, 21, 22, 26, 27, 28]
        
        logger.debug("GPIO", f"Configuring {len(unused_pins)} unused pins with pulldowns")
        configured_count = 0
        
        for pin_num in unused_pins:
            try:
                # Configure as input with internal pulldown (lowest power)
                pin = machine.Pin(pin_num, machine.Pin.IN, machine.Pin.PULL_DOWN)
                logger.trace("GPIO", f"GPIO{pin_num} configured with pulldown")
                configured_count += 1
            except Exception as e:
                logger.error("GPIO", f"Could not configure GPIO{pin_num}", {"error": str(e)})
                
        logger.info("GPIO", f"Configured {configured_count}/{len(unused_pins)} unused pins")
    
    def setup_wifi(self):
        """Initialize WiFi connection"""
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        print("WiFi interface ready")
    
    def port_73h_handler(self, pin):
        """Interrupt handler for port 73h (data register) from 74HC688 #1"""
        logger.trace("BUS", "Port 73h interrupt triggered")
        self.handle_io_cycle(is_data_port=True)
    
    def port_77h_handler(self, pin):
        """Interrupt handler for port 77h (control/status register) from 74HC688 #2"""
        logger.trace("BUS", "Port 77h interrupt triggered")
        self.handle_io_cycle(is_data_port=False)
    
    def handle_io_cycle(self, is_data_port=True):
        """Handle Z80 I/O cycle for specific port"""
        port = 0x73 if is_data_port else 0x77
        port_name = "DATA" if is_data_port else "CTRL"
        
        logger.debug("BUS", f"Handling I/O cycle", {"port": f"0x{port:02X}", "type": port_name})
        
        # Check which operation (read or write)
        rd_state = self.rd.value()
        wr_state = self.wr.value()
        
        logger.trace("BUS", "Control signals", {"RD": rd_state, "WR": wr_state})
        
        if not rd_state:  # Read operation (active low)
            logger.debug("BUS", f"Z80 READ from port 0x{port:02X}")
            
            if is_data_port:
                data = self.read_data_register()
            else:
                data = self.read_status_register()
                
            logger.debug("BUS", f"Sending data to Z80", {"port": f"0x{port:02X}", "data": f"0x{data:02X}"})
            self.drive_data_to_z80(data)
            
            # Wait for read cycle to complete
            cycle_start = utime.ticks_ms()
            while not self.rd.value():
                if utime.ticks_diff(utime.ticks_ms(), cycle_start) > 10:  # 10ms timeout
                    logger.error("BUS", "Read cycle timeout")
                    break
                utime.sleep_us(1)
                
            cycle_time = utime.ticks_diff(utime.ticks_ms(), cycle_start)
            logger.trace("BUS", f"Read cycle completed", {"duration_ms": cycle_time})
            self.release_data_bus()
            
        elif not wr_state:  # Write operation (active low)
            logger.debug("BUS", f"Z80 WRITE to port 0x{port:02X}")
            
            # Set up to read from Z80
            self.data_dir.value(0)   # A→B (Z80 to Pico)
            self.data_oe.value(0)    # Enable
            logger.trace("BUS", "74LVC245 configured for Z80→Pico")
            utime.sleep_us(1)        # Settling time
            
            data = self.read_data_from_z80()
            logger.debug("BUS", f"Received data from Z80", {"port": f"0x{port:02X}", "data": f"0x{data:02X}"})
            
            if is_data_port:
                self.write_data_register(data)
            else:
                self.write_control_register(data)
                
            # Wait for write cycle to complete
            cycle_start = utime.ticks_ms()
            while not self.wr.value():
                if utime.ticks_diff(utime.ticks_ms(), cycle_start) > 10:  # 10ms timeout
                    logger.error("BUS", "Write cycle timeout")
                    break
                utime.sleep_us(1)
                
            cycle_time = utime.ticks_diff(utime.ticks_ms(), cycle_start)
            logger.trace("BUS", f"Write cycle completed", {"duration_ms": cycle_time})
            self.data_oe.value(1)  # Disable
        else:
            logger.warning("BUS", "Invalid I/O cycle - neither RD nor WR active", {"RD": rd_state, "WR": wr_state})
    
    def drive_data_to_z80(self, data):
        """Drive data onto the Z80 bus"""
        # Configure data pins as outputs
        for i, pin in enumerate(self.data_pins):
            pin.init(machine.Pin.OUT)
            pin.value((data >> i) & 1)
        
        # Set 74LVC245 direction: B→A (Pico to Z80)
        self.data_dir.value(1)
        self.data_oe.value(0)  # Enable outputs
    
    def read_data_from_z80(self):
        """Read data from the Z80 bus"""
        data = 0
        for i, pin in enumerate(self.data_pins):
            if pin.value():
                data |= (1 << i)
        return data
    
    def release_data_bus(self):
        """Release the data bus (high-Z state)"""
        self.data_oe.value(1)  # Disable 74LVC245 outputs
        
        # Set data pins back to inputs
        for pin in self.data_pins:
            pin.init(machine.Pin.IN, machine.Pin.PULL_UP)
    
    def read_data_register(self):
        """Read from 8251 data register (port 73h)"""
        if self.state != self.STATE_OPERATIONAL:
            logger.warning("8251", "Data read in non-operational state", {"state": self.state})
            return 0xFF
            
        if len(self.rx_buffer) > 0:
            data = self.rx_buffer.popleft()
            # Update RXRDY status
            if len(self.rx_buffer) == 0:
                self.status_register &= ~self.STATUS_RXRDY
                logger.debug("8251", "RX buffer empty - clearing RXRDY")
            
            logger.info("8251", "Data register read", {
                "data": f"0x{data:02X}", 
                "char": chr(data) if 32 <= data <= 126 else ".",
                "rx_remaining": len(self.rx_buffer)
            })
            return data
        else:
            logger.debug("8251", "Data register read - no data available")
            return 0xFF
    
    def write_data_register(self, data):
        """Write to 8251 data register (port 73h)"""
        if self.state != self.STATE_OPERATIONAL:
            logger.warning("8251", "Data write in non-operational state", {"state": self.state, "data": f"0x{data:02X}"})
            return
            
        if self.command_instruction & self.CMD_TXEN:
            self.tx_buffer.append(data)
            # Clear TXRDY and TXE temporarily
            old_status = self.status_register
            self.status_register &= ~(self.STATUS_TXRDY | self.STATUS_TXE)
            
            logger.info("8251", "Data register write", {
                "data": f"0x{data:02X}", 
                "char": chr(data) if 32 <= data <= 126 else ".",
                "tx_buffered": len(self.tx_buffer),
                "status_change": f"0x{old_status:02X}→0x{self.status_register:02X}"
            })
            
            # Process AT commands or send to network
            if self.at_command_mode:
                self.process_at_command(data)
            else:
                self.send_to_network(data)
        else:
            logger.warning("8251", "Data write with TX disabled", {"data": f"0x{data:02X}"})
    
    def read_status_register(self):
        """Read from 8251 status register (port 77h)"""
        logger.debug("8251", "Status register read", {
            "status": f"0x{self.status_register:02X}",
            "TXRDY": bool(self.status_register & self.STATUS_TXRDY),
            "RXRDY": bool(self.status_register & self.STATUS_RXRDY), 
            "TXE": bool(self.status_register & self.STATUS_TXE),
            "DSR": bool(self.status_register & self.STATUS_DSR)
        })
        return self.status_register
    
    def write_control_register(self, data):
        """Write to 8251 control register (port 77h)"""
        logger.info("8251", "Control register write", {
            "data": f"0x{data:02X}", 
            "binary": f"{data:08b}",
            "current_state": self.state
        })
        
        if self.state == self.STATE_RESET:
            # Any write puts us in mode instruction state
            self.state = self.STATE_MODE_INSTRUCTION
            self.mode_instruction = data
            logger.info("8251", "Mode instruction received", {
                "mode": f"0x{data:02X}",
                "new_state": "MODE_INSTRUCTION"
            })
            
        elif self.state == self.STATE_MODE_INSTRUCTION:
            # Second write is command instruction
            self.state = self.STATE_COMMAND_INSTRUCTION
            self.command_instruction = data
            logger.info("8251", "Command instruction received", {
                "cmd": f"0x{data:02X}",
                "TXEN": bool(data & self.CMD_TXEN),
                "RXEN": bool(data & self.CMD_RXEN),
                "DTR": bool(data & self.CMD_DTR),
                "RTS": bool(data & self.CMD_RTS),
                "new_state": "COMMAND_INSTRUCTION"
            })
            
            # Process command bits
            if data & self.CMD_IR:  # Internal reset
                logger.info("8251", "Internal reset requested")
                self.internal_reset()
            else:
                self.state = self.STATE_OPERATIONAL
                self.update_status_from_command()
                logger.info("8251", "Entering operational state")
                
        elif self.state == self.STATE_COMMAND_INSTRUCTION:
            self.command_instruction = data
            self.state = self.STATE_OPERATIONAL
            self.update_status_from_command()
            logger.info("8251", "Updated to operational state")
            
        elif self.state == self.STATE_OPERATIONAL:
            # Update command instruction
            if data & self.CMD_IR:  # Internal reset
                logger.info("8251", "Internal reset from operational state")
                self.internal_reset()
            else:
                old_cmd = self.command_instruction
                self.command_instruction = data
                self.update_status_from_command()
                logger.debug("8251", "Command updated", {
                    "old_cmd": f"0x{old_cmd:02X}",
                    "new_cmd": f"0x{data:02X}"
                })
    
    def internal_reset(self):
        """Perform internal reset"""
        old_state = self.state
        self.state = self.STATE_MODE_INSTRUCTION
        self.command_instruction = 0
        self.status_register = self.STATUS_TXE | self.STATUS_TXRDY
        self.rx_buffer.clear()
        self.tx_buffer.clear()
        
        logger.info("8251", "Internal reset completed", {
            "old_state": old_state,
            "new_state": self.state,
            "status": f"0x{self.status_register:02X}",
            "buffers_cleared": True
        })
    
    def update_status_from_command(self):
        """Update status register based on command register"""
        # Update DSR based on network connection
        if self.socket_connection:
            self.status_register |= self.STATUS_DSR
        else:
            self.status_register &= ~self.STATUS_DSR
            
        # TXRDY and TXE depend on transmit enable and buffer status
        if self.command_instruction & self.CMD_TXEN:
            if len(self.tx_buffer) < 512:  # Buffer not full
                self.status_register |= self.STATUS_TXRDY
            if len(self.tx_buffer) == 0:
                self.status_register |= self.STATUS_TXE
        else:
            self.status_register &= ~(self.STATUS_TXRDY | self.STATUS_TXE)
    
    def process_at_command(self, data):
        """Process AT commands"""
        char = chr(data)
        
        if char == '\r' or char == '\n':
            if self.at_buffer:
                response = self.execute_at_command(self.at_buffer.strip())
                self.send_response(response)
                self.at_buffer = ""
        elif char == '\b' or char == '\x7f':  # Backspace
            if self.at_buffer:
                self.at_buffer = self.at_buffer[:-1]
        elif char.isprintable():
            self.at_buffer += char.upper()
    
    def load_shortcuts(self):
        """Load host shortcuts from flash memory"""
        try:
            if self.shortcuts_file in os.listdir():
                with open(self.shortcuts_file, 'r') as f:
                    self.shortcuts = json.load(f)
                print(f"Loaded {len(self.shortcuts)} shortcuts")
            else:
                self.shortcuts = {}
        except Exception as e:
            print(f"Error loading shortcuts: {e}")
            self.shortcuts = {}
    
    def save_shortcuts(self):
        """Save host shortcuts to flash memory"""
        try:
            with open(self.shortcuts_file, 'w') as f:
                json.dump(self.shortcuts, f)
            return True
        except Exception as e:
            print(f"Error saving shortcuts: {e}")
            return False
    
    def add_shortcut(self, index, host, description=""):
        """Add or update a host shortcut"""
        if 0 <= index <= 49:
            self.shortcuts[str(index)] = {
                "host": host,
                "desc": description[:32]  # Limit description length
            }
            return self.save_shortcuts()
        return False
    
    def delete_shortcut(self, index):
        """Delete a host shortcut"""
        if str(index) in self.shortcuts:
            del self.shortcuts[str(index)]
            return self.save_shortcuts()
        return False
    
    def get_shortcut(self, index):
        """Get a host shortcut by index"""
        return self.shortcuts.get(str(index))
    
    def list_shortcuts(self):
        """Return formatted list of all shortcuts"""
        if not self.shortcuts:
            return "No shortcuts stored"
        
        result = "STORED NUMBERS:\n"
        for index in sorted(self.shortcuts.keys(), key=int):
            shortcut = self.shortcuts[index]
            host = shortcut["host"]
            desc = shortcut.get("desc", "")
            if desc:
                result += f"{index:2}: {host} ({desc})\n"
            else:
                result += f"{index:2}: {host}\n"
        
        return result.rstrip()
    

        print(f"AT Command: {command}")
        
        if command == "AT":
            return "OK"
        elif command.startswith("ATDT"):
            # Dial command - treat as hostname:port
            target = command[4:].strip()
            return self.connect_to_host(target)
        elif command == "ATH" or command == "ATH0":
            # Hang up
            return self.disconnect()
        elif command == "ATA":
            # Answer (not applicable for client)
            return "NO CARRIER"
        elif command.startswith("AT+CWJAP="):
            # WiFi connect (custom command)
            # Format: AT+CWJAP="ssid","password"
            return self.wifi_connect_command(command)
        elif command == "AT+CWJAP?":
            # Check WiFi status
            if self.wifi_connected:
                return f"OK\nConnected to {self.wlan.config('essid')}"
            else:
                return "NO WIFI"
        elif command == "ATI":
            # Identification
            return "Pico W 8251 WiFi Modem v1.0"
        elif command == "+++":
            # Escape to command mode
            self.at_command_mode = True
            return "OK"
        else:
            return "ERROR"
    
    def wifi_connect_command(self, command):
        """Handle WiFi connection command"""
        try:
            # Parse AT+CWJAP="ssid","password"
            parts = command.split('"')
            if len(parts) >= 4:
                ssid = parts[1]
                password = parts[3]
                return self.connect_wifi(ssid, password)
            else:
                return "ERROR"
        except:
            return "ERROR"
    
    def connect_wifi(self, ssid, password):
        """Connect to WiFi network"""
        try:
            self.wlan.connect(ssid, password)
            
            # Wait for connection
            timeout = 10
            while timeout > 0:
                if self.wlan.status() < 0 or self.wlan.status() >= 3:
                    break
                timeout -= 1
                utime.sleep(1)
            
            if self.wlan.status() == 3:  # Connected
                self.wifi_connected = True
                ip = self.wlan.ifconfig()[0]
                return f"CONNECT {ip}"
            else:
                return "NO CARRIER"
        except Exception as e:
            return "ERROR"
    
    def connect_to_host(self, target):
        """Connect to remote host"""
        if not self.wifi_connected:
            logger.warning("NETWORK", "Connection attempt without WiFi")
            return "NO CARRIER"
            
        try:
            logger.info("NETWORK", f"Attempting connection", {"target": target})
            
            # Parse hostname:port
            if ':' in target:
                host, port = target.rsplit(':', 1)
                port = int(port)
            else:
                host = target
                port = 23  # Default telnet port
                
            logger.debug("NETWORK", f"Parsed connection", {"host": host, "port": port})
            
            # Create socket connection
            self.socket_connection = socket.socket()
            self.socket_connection.settimeout(10)
            self.socket_connection.connect((host, port))
            
            self.at_command_mode = False
            logger.info("NETWORK", f"Connected successfully", {"host": host, "port": port})
            return "CONNECT"
            
        except Exception as e:
            logger.error("NETWORK", f"Connection failed", {"target": target, "error": str(e)})
            if self.socket_connection:
                self.socket_connection.close()
                self.socket_connection = None
            return "NO CARRIER"
    
    def disconnect(self):
        """Disconnect from remote host"""
        if self.socket_connection:
            logger.info("NETWORK", "Disconnecting from remote host")
            self.socket_connection.close()
            self.socket_connection = None
            
        self.at_command_mode = True
        logger.info("NETWORK", "Returned to command mode")
        return "NO CARRIER"
    
    def send_response(self, response):
        """Send AT command response to computer"""
        logger.debug("AT_CMD", f"Sending response", {"response": response})
        for char in response + "\r\n":
            self.rx_buffer.append(ord(char))
        
        # Set RXRDY flag
        self.status_register |= self.STATUS_RXRDY
        logger.trace("8251", "RXRDY set for AT response")
    
    def send_to_network(self, data):
        """Send data to network connection"""
        if self.socket_connection:
            try:
                self.socket_connection.send(bytes([data]))
                # Restore TXRDY status
                self.status_register |= (self.STATUS_TXRDY | self.STATUS_TXE)
                logger.trace("NETWORK", f"Data sent", {"data": f"0x{data:02X}", "char": chr(data) if 32 <= data <= 126 else "."})
            except Exception as e:
                logger.error("NETWORK", f"Send failed", {"error": str(e)})
                self.disconnect()
                self.send_response("NO CARRIER")
    
    def network_handler(self):
        """Background thread to handle network data"""
        logger.info("NETWORK", "Network handler thread started")
        
        while True:
            if self.socket_connection and not self.at_command_mode:
                try:
                    # Check for incoming data
                    ready = select.select([self.socket_connection], [], [], 0.1)
                    if ready[0]:
                        data = self.socket_connection.recv(256)
                        if data:
                            logger.debug("NETWORK", f"Received data", {"bytes": len(data)})
                            for byte in data:
                                if len(self.rx_buffer) < 1024:
                                    self.rx_buffer.append(byte)
                                    logger.trace("NETWORK", f"Queued byte", {"data": f"0x{byte:02X}", "char": chr(byte) if 32 <= byte <= 126 else "."})
                            
                            # Set RXRDY flag
                            if len(self.rx_buffer) > 0:
                                self.status_register |= self.STATUS_RXRDY
                        else:
                            # Connection closed
                            logger.info("NETWORK", "Remote host closed connection")
                            self.disconnect()
                            self.send_response("NO CARRIER")
                            
                except Exception as e:
                    logger.error("NETWORK", f"Network handler error", {"error": str(e)})
                    self.disconnect()
                    self.send_response("NO CARRIER")
            
            utime.sleep_ms(10)
    
    def bus_monitor(self):
        """Background thread to monitor bus status"""
        while True:
            # Update status register periodically
            self.update_status_from_command()
            utime.sleep_ms(50)

# Main execution
def main():
    """Main program entry point"""
    print("=" * 60)
    print("Intel 8251 USART Emulator for Raspberry Pi Pico W")
    print("=" * 60)
    
    try:
        logger.info("MAIN", "Starting 8251 emulator")
        emulator = Intel8251Emulator()
        
        logger.info("MAIN", "8251 Emulator running successfully")
        print("8251 Emulator running")
        print("Hardware: Dual 74HC688 + 74LVC245 + 74LVC125")
        print("Power: 5V→VBUS, 3V3_EN→5V via 10kΩ, 3V3_OUT→LVC chips")
        print("Complete 8-bit address decoding: ONLY ports 73h & 77h")
        print("Data bus: GPIO0-7 (avoids WiFi pins 23-25)")
        print("")
        print("Debug Logging Features:")
        print("- Current log level:", logger.log_level)
        print("- Use ATLOG0-5 to change verbosity (0=none, 5=trace)")
        print("- All operations logged to Thonny console")
        print("")
        print("Commands:")
        print("- Help: AT?")
        print("- Connect WiFi: AT+CWJAP=\"ssid\",\"password\"")
        print("- Store shortcut: AT&Z0=hostname:port,description")
        print("- Dial shortcut: ATDS0")
        print("- Dial host: ATDT hostname:port")
        print("- View shortcuts: AT&V")
        print("- Hang up: ATH")
        print("- Debug level: ATLOG0-5")
        print("")
        print("Logging Legend:")
        print("  ERROR(1) - Critical errors only") 
        print("  WARN(2)  - Warnings + errors")
        print("  INFO(3)  - General info + above")
        print("  DEBUG(4) - Debug info + above")
        print("  TRACE(5) - All details + above")
        print("")
        print("Ready for Z80 bus operations...")
        
        # Keep main thread alive and provide status updates
        last_status_time = utime.ticks_ms()
        
        while True:
            current_time = utime.ticks_ms()
            
            # Print status every 30 seconds
            if utime.ticks_diff(current_time, last_status_time) > 30000:
                logger.info("STATUS", "Periodic status", {
                    "wifi": emulator.wifi_connected,
                    "connection": bool(emulator.socket_connection),
                    "cmd_mode": emulator.at_command_mode,
                    "rx_buffer": len(emulator.rx_buffer),
                    "tx_buffer": len(emulator.tx_buffer),
                    "8251_state": emulator.state,
                    "log_count": logger.log_count
                })
                last_status_time = current_time
                
            utime.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("MAIN", "Shutdown requested by user")
        print("Shutting down...")
    except Exception as e:
        logger.error("MAIN", f"Fatal error", {"error": str(e)})
        print(f"Fatal error: {e}")
    finally:
        logger.info("MAIN", "8251 emulator stopped")

if __name__ == "__main__":
    main()