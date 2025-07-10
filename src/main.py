"""
8251 USART Emulator for RP2040 Pico W - v1.0
Timex/Sinclair 2050 modem replacement with WiFi connectivity
See README.md for complete documentation
"""

import machine
import time
import _thread
from machine import Pin
import gc
import network
import socket
import select
import re

# Debug configuration - Set these to True/False to control logging
DEBUG_ENABLED = True      # Master debug switch
DEBUG_GPIO = False        # GPIO pin state changes and register access
DEBUG_USART = True        # USART register operations
DEBUG_NETWORK = True      # Network operations
DEBUG_HAYES = True        # Hayes AT command processing
DEBUG_INTERFACE = False   # Interface monitoring
DEBUG_SYSTEM = True       # System initialization and memory
DEBUG_VERBOSE = False     # Extra verbose output

# Memory conservation mode - reduces debug output during initialization
MEMORY_CONSERVATIVE = True

# 8251 USART Pin definitions
PIN_D0 = 0
PIN_D1 = 1
PIN_D2 = 2
PIN_D3 = 3
PIN_D4 = 4
PIN_D5 = 5
PIN_D6 = 6
PIN_D7 = 7
PIN_CD = 8      # Control/Data select
PIN_RD = 9      # Read strobe (active low)
PIN_WR = 10     # Write strobe (active low)
PIN_CS = 11     # Chip Select (active low)
PIN_RESET = 12  # Reset (active high)
PIN_TXRDY = 13  # Transmitter Ready output
PIN_RXRDY = 14  # Receiver Ready output
PIN_CLK = 15    # Clock input

# 8251 Register addresses
REG_DATA = 0
REG_STATUS_COMMAND = 1

# 8251 Status Register bits
STATUS_TXRDY = 0x01     # Transmitter Ready
STATUS_RXRDY = 0x02     # Receiver Ready
STATUS_TXE = 0x04       # Transmitter Empty
STATUS_PE = 0x08        # Parity Error
STATUS_OE = 0x10        # Overrun Error
STATUS_FE = 0x20        # Framing Error
STATUS_SYNDET = 0x40    # Sync Detect
STATUS_DSR = 0x80       # Data Set Ready

# Hayes AT command responses
HAYES_OK = "OK"
HAYES_ERROR = "ERROR"
HAYES_CONNECT = "CONNECT"
HAYES_NO_CARRIER = "NO CARRIER"
HAYES_BUSY = "BUSY"
HAYES_NO_ANSWER = "NO ANSWER"

def debug_print(category, message):
    """Print debug message with timestamp if debugging is enabled"""
    if not DEBUG_ENABLED:
        return
    # Check category-specific debug flags
    if ((category == "GPIO" and not DEBUG_GPIO) or
        (category == "USART" and not DEBUG_USART) or
        (category == "NETWORK" and not DEBUG_NETWORK) or
        (category == "HAYES" and not DEBUG_HAYES) or
        (category == "INTERFACE" and not DEBUG_INTERFACE) or
        (category == "SYSTEM" and not DEBUG_SYSTEM)):
        return
    print(f"[{time.ticks_ms():08d}] {category}: {message}")

def debug_verbose(category, message):
    """Print verbose debug message only if verbose debugging is enabled"""
    if DEBUG_VERBOSE:
        debug_print(category, message)

def debug_memory():
    """Print memory usage information"""
    if DEBUG_SYSTEM:
        gc.collect()
        debug_print("SYSTEM", f"Memory: {gc.mem_free()} free, {gc.mem_alloc()} allocated")

def debug_config_summary():
    """Print current debug configuration"""
    if DEBUG_SYSTEM:
        debug_print("SYSTEM", f"Debug: GPIO={DEBUG_GPIO} USART={DEBUG_USART} NET={DEBUG_NETWORK} HAYES={DEBUG_HAYES}")

# Global variables for command interface and system state
usart_instance = None
command_enabled = True
wifi_ssid = None
wifi_password = None

# WiFi persistence settings
WIFI_CONFIG_FILE = 'wifi_config.txt'
AUTO_CONNECT_ENABLED = True

def save_wifi_config(ssid, password):
    """Save WiFi credentials to persistent storage"""
    try:
        with open(WIFI_CONFIG_FILE, 'w') as f:
            f.write(f"{ssid}\n{password}")
        debug_print("SYSTEM", f"WiFi config saved: {ssid}")
        return True
    except Exception as e:
        debug_print("SYSTEM", f"Failed to save WiFi config: {e}")
        return False

def load_wifi_config():
    """Load WiFi credentials from persistent storage"""
    try:
        with open(WIFI_CONFIG_FILE, 'r') as f:
            lines = f.read().strip().split('\n')
            if len(lines) >= 2:
                ssid = lines[0]
                password = lines[1]
                debug_print("SYSTEM", f"WiFi config loaded: {ssid}")
                return ssid, password
            else:
                debug_print("SYSTEM", "Invalid WiFi config file format")
                return None, None
    except OSError:
        debug_print("SYSTEM", "No saved WiFi config found")
        return None, None
    except Exception as e:
        debug_print("SYSTEM", f"Failed to load WiFi config: {e}")
        return None, None

def clear_wifi_config():
    """Clear saved WiFi credentials"""
    try:
        import os
        os.remove(WIFI_CONFIG_FILE)
        debug_print("SYSTEM", "WiFi config cleared")
        return True
    except OSError:
        debug_print("SYSTEM", "No WiFi config file to clear")
        return True
    except Exception as e:
        debug_print("SYSTEM", f"Failed to clear WiFi config: {e}")
        return False

def auto_connect_wifi():
    """Attempt to auto-connect using saved WiFi credentials"""
    global wifi_ssid, wifi_password, usart_instance
    
    if not AUTO_CONNECT_ENABLED:
        debug_print("SYSTEM", "Auto-connect disabled")
        return False
        
    if not usart_instance:
        debug_print("SYSTEM", "USART not initialized, skipping auto-connect")
        return False
    
    ssid, password = load_wifi_config()
    if ssid and password:
        debug_print("SYSTEM", f"Auto-connecting to WiFi: {ssid}")
        if usart_instance.connect_wifi(ssid, password):
            wifi_ssid = ssid
            wifi_password = password
            debug_print("SYSTEM", "Auto-connect successful!")
            return True
        else:
            debug_print("SYSTEM", "Auto-connect failed")
            return False
    else:
        debug_print("SYSTEM", "No saved WiFi credentials for auto-connect")
        return False

class USART8251Emulator:
    def __init__(self):
        """Initialize the 8251 USART emulator"""
        # Force garbage collection before starting
        gc.collect()
        
        debug_print("SYSTEM", "Initializing 8251 USART Emulator...")
        initial_mem = gc.mem_free()
        debug_print("SYSTEM", f"Initial free memory: {initial_mem} bytes")
        
        # Initialize all attributes
        self.mode_instruction_written = False
        self.command_instruction = 0x00
        self.status_register = STATUS_TXE | STATUS_TXRDY  # Initially ready to transmit
        self.data_register = 0x00
        self.rx_buffer = []
        self.tx_buffer = []
        
        # Network state
        self.connected = False
        self.socket = None
        self.connection_host = None
        self.connection_port = None
        
        # Hayes modem state
        self.command_mode = True
        self.command_buffer = ""
        self.escape_count = 0
        self.last_char_time = 0
        
        # Statistics
        self.total_bytes_rx = 0
        self.total_bytes_tx = 0
        self.register_reads = 0
        self.register_writes = 0
        
        # Initialize hardware systems
        try:
            debug_print("SYSTEM", "Setting up GPIO pins...")
            self.setup_gpio()
            
            debug_print("SYSTEM", "Setting up WiFi...")
            self.setup_wifi()
            
        except Exception as e:
            debug_print("SYSTEM", f"FATAL ERROR during initialization: {e}")
            raise
        
        # Final memory check
        gc.collect()
        final_mem = gc.mem_free()
        used_mem = initial_mem - final_mem
        debug_print("SYSTEM", f"8251 USART Emulator ready - Used {used_mem} bytes, {final_mem} bytes free")

        if final_mem < 30000:  # Less than 30KB free
            debug_print("SYSTEM", "WARNING: Low memory after initialization")
    
    def setup_gpio(self):
        """Initialize all GPIO pins for 8251 interface"""
        try:
            # Data bus pins (bidirectional, start as inputs with pull-down)
            self.data_pins = [Pin(i, Pin.IN, Pin.PULL_DOWN) for i in range(PIN_D0, PIN_D7 + 1)]
            
            # Control pins (inputs with pull-up for active low signals)
            self.cd_pin = Pin(PIN_CD, Pin.IN, Pin.PULL_UP)
            self.rd_pin = Pin(PIN_RD, Pin.IN, Pin.PULL_UP)
            self.wr_pin = Pin(PIN_WR, Pin.IN, Pin.PULL_UP)
            self.cs_pin = Pin(PIN_CS, Pin.IN, Pin.PULL_UP)
            self.reset_pin = Pin(PIN_RESET, Pin.IN, Pin.PULL_DOWN)  # Reset pin (active high)
            
            # Status output pins
            self.txrdy_pin = Pin(PIN_TXRDY, Pin.OUT)
            self.rxrdy_pin = Pin(PIN_RXRDY, Pin.OUT)
            self.clk_pin = Pin(PIN_CLK, Pin.IN)  # Clock input pin
            
            self.update_status_outputs()
            
            # Check reset pin state at startup
            if self.reset_pin.value():
                debug_print("GPIO", "WARNING: Reset pin HIGH at startup!")
            
            debug_print("GPIO", "GPIO pins initialized")
            
        except Exception as e:
            debug_print("GPIO", f"GPIO init failed: {e}")
            raise
    
    def setup_wifi(self):
        """Initialize WiFi interface"""
        try:
            self.wlan = network.WLAN(network.STA_IF)
            self.wlan.active(True)
            debug_print("NETWORK", "WiFi interface initialized")
        except Exception as e:
            debug_print("NETWORK", f"WiFi initialization failed: {e}")
            raise
    
    def connect_wifi(self, ssid, password):
        """Connect to WiFi network"""
        global wifi_ssid, wifi_password
        
        debug_print("NETWORK", f"Connecting to WiFi: {ssid}")
        
        try:
            if self.wlan.isconnected():
                debug_print("NETWORK", "Disconnecting from current WiFi...")
                self.wlan.disconnect()
                time.sleep(1)
            
            self.wlan.connect(ssid, password)
            
            # Wait for connection with timeout
            timeout = 30  # Increased timeout for WiFi connections
            while not self.wlan.isconnected() and timeout > 0:
                time.sleep(0.5)
                timeout -= 1
            
            if self.wlan.isconnected():
                config = self.wlan.ifconfig()
                debug_print("NETWORK", f"WiFi connected! IP: {config[0]}")
                
                # Save credentials to global variables and persistent storage
                global wifi_ssid, wifi_password
                wifi_ssid = ssid
                wifi_password = password
                self._connected_ssid = ssid  # Store for AT+CWJAP? query
                
                # Save to persistent storage
                if save_wifi_config(ssid, password):
                    debug_print("NETWORK", "WiFi credentials saved")
                
                return True
            else:
                debug_print("NETWORK", "WiFi connection failed - timeout")
                return False
                
        except Exception as e:
            debug_print("NETWORK", f"WiFi connection error: {e}")
            return False
    
    def read_data_bus(self):
        """Read 8-bit value from data bus"""
        value = 0
        for i, pin in enumerate(self.data_pins):
            if pin.value():
                value |= (1 << i)
        debug_verbose("GPIO", f"Read data bus: 0x{value:02X}")
        return value
    
    def write_data_bus(self, value):
        """Write 8-bit value to data bus"""
        debug_verbose("GPIO", f"Write data bus: 0x{value:02X}")
        
        # Configure pins as outputs and set values
        for i, pin in enumerate(self.data_pins):
            pin.init(Pin.OUT)
            pin.value((value >> i) & 1)
    
    def release_data_bus(self):
        """Release data bus (set pins back to inputs)"""
        for pin in self.data_pins:
            pin.init(Pin.IN, Pin.PULL_DOWN)
        debug_verbose("GPIO", "Released data bus")
    
    def update_status_outputs(self):
        """Update TxRDY and RxRDY output pins"""
        txrdy = bool(self.status_register & STATUS_TXRDY)
        rxrdy = bool(self.status_register & STATUS_RXRDY)
        
        self.txrdy_pin.value(txrdy)
        self.rxrdy_pin.value(rxrdy)
        
        debug_verbose("GPIO", f"Status outputs: TxRDY={txrdy}, RxRDY={rxrdy}")
    
    def read_register(self, address):
        """Read from 8251 register"""
        self.register_reads += 1
        
        if address == REG_DATA:
            # Read data register
            if self.rx_buffer:
                data = self.rx_buffer.pop(0)
                debug_print("USART", f"Read data register: 0x{data:02X} ('{chr(data) if 32 <= data <= 126 else '.'}')")
                
                # Update RxRDY status
                if not self.rx_buffer:
                    self.status_register &= ~STATUS_RXRDY
                    self.update_status_outputs()
                    
                return data
            else:
                debug_print("USART", "Read data register: no data available")
                return 0x00
                
        elif address == REG_STATUS_COMMAND:
            # Read status register
            debug_print("USART", f"Read status register: 0x{self.status_register:02X}")
            return self.status_register
            
        else:
            debug_print("USART", f"Read from invalid register: {address}")
            return 0x00
    
    def write_register(self, address, value):
        """Write to 8251 register"""
        self.register_writes += 1
        
        if address == REG_DATA:
            # Write data register
            debug_print("USART", f"Write data register: 0x{value:02X} ('{chr(value) if 32 <= value <= 126 else '.'}')")
            self.tx_buffer.append(value)
            self.total_bytes_tx += 1
            
            # Process transmitted data
            self.process_tx_data(value)
            
        elif address == REG_STATUS_COMMAND:
            if not self.mode_instruction_written:
                # First write is mode instruction
                debug_print("USART", f"Write mode instruction: 0x{value:02X}")
                self.mode_instruction_written = True
                # Mode instruction processing would go here
            else:
                # Subsequent writes are command instructions
                debug_print("USART", f"Write command instruction: 0x{value:02X}")
                self.command_instruction = value
                self.process_command_instruction(value)
                
        else:
            debug_print("USART", f"Write to invalid register: {address}")
    
    def process_command_instruction(self, command):
        """Process 8251 command instruction"""
        debug_print("USART", f"Processing command: 0x{command:02X}")
        
        # Command instruction bits:
        # Bit 0: TxEN (Transmit Enable)
        # Bit 1: DTR (Data Terminal Ready)
        # Bit 2: RxEN (Receive Enable)
        # Bit 3: SBRK (Send Break)
        # Bit 4: ER (Error Reset)
        # Bit 5: RTS (Request to Send)
        # Bit 6: IR (Internal Reset)
        # Bit 7: EH (Enter Hunt mode)
        
        if command & 0x40:  # Internal Reset
            debug_print("USART", "Internal reset requested")
            self.status_register = STATUS_TXE | STATUS_TXRDY
            self.mode_instruction_written = False
            
        if command & 0x10:  # Error Reset
            debug_print("USART", "Error reset requested")
            self.status_register &= ~(STATUS_PE | STATUS_OE | STATUS_FE)
        
        self.update_status_outputs()
    
    def process_tx_data(self, data):
        """Process transmitted data for Hayes AT command handling"""
        char = chr(data) if 32 <= data <= 126 else chr(data)
        current_time = time.ticks_ms()
        
        if self.command_mode:
            # In command mode, accumulate AT commands
            if char == '\r' or char == '\n':
                if self.command_buffer.strip():
                    debug_print("HAYES", f"Received command: {self.command_buffer.strip()}")
                    response = self.process_hayes_command(self.command_buffer.strip())
                    self.send_response(response)
                self.command_buffer = ""
            elif char == '\b' or char == '\x7F':  # Backspace or DEL
                if self.command_buffer:
                    self.command_buffer = self.command_buffer[:-1]
            elif len(char) == 1 and ord(char) >= 32:  # Printable character
                self.command_buffer += char
        else:
            # In data mode, pass through to network connection
            if self.connected and self.socket:
                try:
                    self.socket.send(bytes([data]))
                    debug_verbose("NETWORK", f"Sent to network: 0x{data:02X}")
                except Exception as e:
                    debug_print("NETWORK", f"Network send error: {e}")
                    self.disconnect_network()
            
            # Check for escape sequence (++++)
            if char == '+':
                if time.ticks_diff(current_time, self.last_char_time) < 1000:  # Within 1 second
                    self.escape_count += 1
                else:
                    self.escape_count = 1
                    
                if self.escape_count >= 3:
                    debug_print("HAYES", "Escape sequence detected, entering command mode")
                    self.command_mode = True
                    self.escape_count = 0
                    self.send_response("OK")
            else:
                self.escape_count = 0
        
        self.last_char_time = current_time
    
    def process_hayes_command(self, command):
        """Process Hayes AT command and return response"""
        command = command.strip()
        
        if not command.upper().startswith("AT"):
            return HAYES_ERROR
        
        # Remove AT prefix but preserve case for parameters
        cmd = command[2:].strip()
        
        # Convert command portion to uppercase for comparison, but preserve parameter case
        cmd_upper = cmd.upper()
        
        if cmd == "" or cmd == "":
            return HAYES_OK
        elif cmd_upper == "I" or cmd_upper == "I0":
            return "Pico W 8251 USART Emulator v1.0"
        elif cmd_upper == "Z":
            debug_print("HAYES", "Reset command received")
            self.disconnect_network()
            self.command_mode = True
            return HAYES_OK
        elif cmd_upper == "&F":
            debug_print("HAYES", "Factory defaults command")
            return HAYES_OK
        elif cmd_upper == "H" or cmd_upper == "H0":
            debug_print("HAYES", "Hang up command")
            self.disconnect_network()
            return HAYES_OK
        elif cmd_upper.startswith("D"):
            # Dial command - expect format like D192.168.1.100:23
            number = cmd[1:]  # Preserve original case
            return self.process_dial_command(number)
        elif cmd_upper == "O" or cmd_upper == "O0":
            if self.connected:
                self.command_mode = False
                debug_print("HAYES", "Returning to online mode")
                return HAYES_CONNECT
            else:
                return HAYES_NO_CARRIER
        # WiFi AT commands
        elif cmd_upper == "+CWLAP" or cmd_upper == "+CWSCAN":
            return self.process_wifi_scan()
        elif cmd_upper == "+CWJAP?":
            return self.process_wifi_query()
        elif cmd_upper.startswith("+CWJAP="):
            return self.process_wifi_connect(cmd)  # Pass original case
        elif cmd_upper == "+CWQAP":
            return self.process_wifi_disconnect()
        elif cmd_upper == "+CWSTAT":
            return self.process_wifi_status()
        elif cmd_upper == "+CWSAVE":
            return self.process_wifi_save()
        elif cmd_upper.startswith("+CWAUTO"):
            return self.process_wifi_auto(cmd)
        elif cmd_upper == "+CWFORGET":
            return self.process_wifi_forget()
        else:
            debug_print("HAYES", f"Unknown command: {cmd}")
            return HAYES_ERROR
    
    def process_dial_command(self, number):
        """Process dial command to connect to host:port"""
        debug_print("HAYES", f"Processing dial: {number}")
        
        # Parse host:port format
        if ':' in number:
            try:
                host, port_str = number.split(':', 1)
                port = int(port_str)
            except ValueError:
                debug_print("HAYES", f"Invalid dial format: {number}")
                return HAYES_ERROR
        else:
            # Default to telnet port if no port specified
            host = number
            port = 23
        
        if self.connect_network(host, port):
            self.command_mode = False
            return HAYES_CONNECT
        else:
            return HAYES_NO_CARRIER
    
    def connect_network(self, host, port):
        """Connect to network host"""
        if not self.wlan.isconnected():
            debug_print("NETWORK", "Not connected to WiFi")
            return False
        
        debug_print("NETWORK", f"Connecting to {host}:{port}")
        
        try:
            # Try DNS resolution first
            try:
                import socket as socket_module
                addr_info = socket_module.getaddrinfo(host, port)
                if addr_info:
                    resolved_ip = addr_info[0][-1][0]
                    debug_print("NETWORK", f"Resolved {host} to {resolved_ip}")
                else:
                    debug_print("NETWORK", f"DNS failed for {host}")
                    return False
            except Exception as dns_e:
                debug_print("NETWORK", f"DNS error: {dns_e}")
                resolved_ip = host  # Try as IP address
            
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10.0)
            self.socket.connect((resolved_ip, port))
            self.socket.setblocking(False)
            
            self.connected = True
            self.connection_host = host
            self.connection_port = port
            
            debug_print("NETWORK", f"Connected to {host}:{port}")
            return True
            
        except Exception as e:
            debug_print("NETWORK", f"Connection failed: {e}")
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None
            return False
    
    def disconnect_network(self):
        """Disconnect from network"""
        if self.socket:
            try:
                self.socket.close()
                debug_print("NETWORK", "Socket closed")
            except:
                pass
            self.socket = None
        
        self.connected = False
        self.connection_host = None
        self.connection_port = None
        self.command_mode = True
        
        debug_print("NETWORK", "Disconnected from network")
    
    def send_response(self, response):
        """Send Hayes response to host"""
        debug_print("HAYES", f"Sending response: {response}")
        
        # Add response to RX buffer for host to read
        response_bytes = (response + "\r\n").encode('ascii')
        for byte in response_bytes:
            self.rx_buffer.append(byte)
            self.total_bytes_rx += 1
        
        # Set RxRDY status
        self.status_register |= STATUS_RXRDY
        self.update_status_outputs()
    
    def send_multiline_response(self, lines):
        """Send multi-line Hayes response to host"""
        for line in lines:
            self.send_response(line)
    
    def process_wifi_scan(self):
        """Process AT+CWLAP command - scan for WiFi networks"""
        debug_print("HAYES", "WiFi scan requested")
        
        if not self.wlan.active():
            return "ERROR: WiFi not active"
        
        try:
            debug_print("NETWORK", "Scanning for WiFi networks...")
            networks = self.wlan.scan()
            
            if not networks:
                return "No networks found"
            
            # Sort by signal strength (descending)
            networks.sort(key=lambda x: x[3], reverse=True)
            
            response_lines = []
            response_lines.append(f"Found {len(networks)} networks:")
            
            for i, (ssid, bssid, channel, RSSI, authmode, hidden) in enumerate(networks):
                ssid_str = ssid.decode('utf-8') if ssid else "<hidden>"
                
                # Convert authmode to string
                auth_modes = {
                    0: "OPEN",
                    1: "WEP", 
                    2: "WPA_PSK",
                    3: "WPA2_PSK",
                    4: "WPA_WPA2_PSK",
                    5: "WPA2_ENTERPRISE"
                }
                auth_str = auth_modes.get(authmode, f"AUTH{authmode}")
                
                # Format: +CWLAP:(authmode,"ssid",rssi,"mac",channel)
                mac_str = ":".join([f"{b:02x}" for b in bssid])
                line = f'+CWLAP:({authmode},"{ssid_str}",{RSSI},"{mac_str}",{channel},{auth_str})'
                response_lines.append(line)
            
            response_lines.append("OK")
            
            # Send each line as separate response
            for line in response_lines[:-1]:  # All but OK
                self.send_response(line)
            
            return response_lines[-1]  # Return OK
            
        except Exception as e:
            debug_print("NETWORK", f"WiFi scan error: {e}")
            return "ERROR: Scan failed"
    
    def process_wifi_query(self):
        """Process AT+CWJAP? command - query current WiFi connection"""
        debug_print("HAYES", "WiFi connection query")
        
        if not self.wlan.isconnected():
            return '+CWJAP:"",""'
        
        # Note: MicroPython doesn't provide direct access to connected SSID
        # We'll use the stored values from our connection
        if hasattr(self, '_connected_ssid'):
            return f'+CWJAP:"{self._connected_ssid}","connected"'
        else:
            config = self.wlan.ifconfig()
            return f'+CWJAP:"<unknown>","{config[0]}"'
    
    def process_wifi_connect(self, cmd):
        """Process AT+CWJAP="ssid","password" command"""
        debug_print("HAYES", f"WiFi connect command: {cmd}")
        
        # Parse the command: +CWJAP="ssid","password"
        # Use regex to extract quoted strings (case-sensitive)
        pattern = r'\+[Cc][Ww][Jj][Aa][Pp]="([^"]*)"(?:,"([^"]*)")?'
        match = re.match(pattern, cmd)
        
        if not match:
            return "ERROR: Invalid format. Use: AT+CWJAP=\"ssid\",\"password\""
        
        ssid = match.group(1)
        password = match.group(2) if match.group(2) is not None else ""
        
        # Debug output (mask password for security)
        masked_password = password[:2] + "*" * (len(password) - 2) if len(password) > 2 else "*" * len(password)
        debug_print("NETWORK", f"Connecting to WiFi: '{ssid}' with password: '{masked_password}' (case-sensitive)")
        
        if self.connect_wifi(ssid, password):
            self._connected_ssid = ssid  # Store for query command
            return HAYES_OK
        else:
            return "ERROR: Connection failed"
    
    def process_wifi_disconnect(self):
        """Process AT+CWQAP command - disconnect from WiFi"""
        debug_print("HAYES", "WiFi disconnect requested")
        
        try:
            if self.wlan.isconnected():
                # Disconnect network connection first if active
                if self.connected:
                    self.disconnect_network()
                
                self.wlan.disconnect()
                debug_print("NETWORK", "WiFi disconnected")
                
                if hasattr(self, '_connected_ssid'):
                    delattr(self, '_connected_ssid')
                    
                return HAYES_OK
            else:
                return "ERROR: Not connected to WiFi"
                
        except Exception as e:
            debug_print("NETWORK", f"WiFi disconnect error: {e}")
            return "ERROR: Disconnect failed"
    
    def process_wifi_status(self):
        """Process AT+CWSTAT command - show detailed WiFi status"""
        debug_print("HAYES", "WiFi status requested")
        
        try:
            response_lines = []
            
            if self.wlan.isconnected():
                config = self.wlan.ifconfig()
                response_lines.append("+CWSTAT:CONNECTED")
                response_lines.append(f"IP: {config[0]}")
                response_lines.append(f"Subnet: {config[1]}")
                response_lines.append(f"Gateway: {config[2]}")
                response_lines.append(f"DNS: {config[3]}")
                
                if hasattr(self, '_connected_ssid'):
                    response_lines.append(f"SSID: {self._connected_ssid}")
                
            else:
                response_lines.append("+CWSTAT:DISCONNECTED")
                if self.wlan.active():
                    response_lines.append("WiFi interface: ACTIVE")
                else:
                    response_lines.append("WiFi interface: INACTIVE")
            
            response_lines.append("OK")
            
            # Send multi-line response
            for line in response_lines[:-1]:
                self.send_response(line)
            
            return response_lines[-1]
            
        except Exception as e:
            debug_print("NETWORK", f"WiFi status error: {e}")
            return "ERROR: Status query failed"
    
    def process_wifi_save(self):
        """Process AT+CWSAVE command - save current WiFi config"""
        debug_print("HAYES", "WiFi save config requested")
        
        global wifi_ssid, wifi_password
        if wifi_ssid and wifi_password:
            if save_wifi_config(wifi_ssid, wifi_password):
                return "OK: WiFi config saved"
            else:
                return "ERROR: Failed to save config"
        else:
            return "ERROR: No WiFi connection to save"
    
    def process_wifi_auto(self, cmd):
        """Process AT+CWAUTO command - control auto-connect"""
        debug_print("HAYES", f"WiFi auto-connect command: {cmd}")
        
        global AUTO_CONNECT_ENABLED
        
        # Parse AT+CWAUTO=1 or AT+CWAUTO=0
        if "=" in cmd:
            try:
                setting = cmd.split("=")[1].strip()
                if setting == "1":
                    AUTO_CONNECT_ENABLED = True
                    return "OK: Auto-connect enabled"
                elif setting == "0":
                    AUTO_CONNECT_ENABLED = False
                    return "OK: Auto-connect disabled"
                else:
                    return "ERROR: Use AT+CWAUTO=1 or AT+CWAUTO=0"
            except:
                return "ERROR: Invalid format"
        else:
            # Query current setting
            return f"+CWAUTO:{1 if AUTO_CONNECT_ENABLED else 0}"
    
    def process_wifi_forget(self):
        """Process AT+CWFORGET command - clear saved WiFi config"""
        debug_print("HAYES", "WiFi forget config requested")
        
        if clear_wifi_config():
            global wifi_ssid, wifi_password
            wifi_ssid = None
            wifi_password = None
            return "OK: WiFi config cleared"
        else:
            return "ERROR: Failed to clear config"
    
    def handle_network_data(self):
        """Handle incoming network data"""
        if not self.connected or not self.socket:
            return
        
        try:
            # Use select to check for available data
            ready = select.select([self.socket], [], [], 0)
            if ready[0]:
                data = self.socket.recv(1024)
                if data:
                    debug_verbose("NETWORK", f"Received {len(data)} bytes from network")
                    
                    # Add to RX buffer
                    for byte in data:
                        self.rx_buffer.append(byte)
                        self.total_bytes_rx += 1
                    
                    # Set RxRDY status
                    self.status_register |= STATUS_RXRDY
                    self.update_status_outputs()
                else:
                    # Connection closed by remote
                    debug_print("NETWORK", "Connection closed by remote")
                    self.disconnect_network()
                    self.send_response(HAYES_NO_CARRIER)
                    
        except OSError as e:
            if e.errno != 11:  # EAGAIN - no data available
                debug_print("NETWORK", f"Network receive error: {e}")
                self.disconnect_network()
                self.send_response(HAYES_NO_CARRIER)
    
    def monitor_interface(self):
        """Monitor the host interface for register access"""
        last_cs = 1
        last_rd = 1
        last_wr = 1
        last_reset = 0
        reset_processed = False
        
        debug_print("INTERFACE", "Starting interface monitoring...")
        
        try:
            while True:
                # Check for reset with debouncing
                current_reset = self.reset_pin.value()
                
                # Detect rising edge of reset (going from low to high)
                if last_reset == 0 and current_reset == 1 and not reset_processed:
                    debug_print("INTERFACE", "Reset signal asserted")
                    self.status_register = STATUS_TXE | STATUS_TXRDY
                    self.mode_instruction_written = False
                    self.rx_buffer.clear()
                    self.tx_buffer.clear()
                    self.update_status_outputs()
                    reset_processed = True
                    last_reset = current_reset
                    continue
                elif current_reset == 0:
                    # Reset released, allow next reset detection
                    reset_processed = False
                
                last_reset = current_reset
                
                # Skip normal operations while in reset
                if current_reset:
                    time.sleep_us(100)  # Short delay while in reset
                    continue
                
                # Check chip select and control signals
                cs = self.cs_pin.value()
                rd = self.rd_pin.value()
                wr = self.wr_pin.value()
                cd = self.cd_pin.value()
                
                # Detect falling edge of CS (chip selected)
                if last_cs == 1 and cs == 0:
                    debug_verbose("INTERFACE", "Chip selected")
                
                # Detect register access (CS low and RD or WR strobed)
                if cs == 0:  # Chip is selected
                    # Read operation (RD falling edge)
                    if last_rd == 1 and rd == 0:
                        address = REG_STATUS_COMMAND if cd else REG_DATA
                        data = self.read_register(address)
                        self.write_data_bus(data)
                        debug_print("INTERFACE", f"Read from {'STATUS' if cd else 'DATA'} register: 0x{data:02X}")
                    
                    # Write operation (WR falling edge)
                    elif last_wr == 1 and wr == 0:
                        address = REG_STATUS_COMMAND if cd else REG_DATA
                        data = self.read_data_bus()
                        self.write_register(address, data)
                        debug_print("INTERFACE", f"Write to {'COMMAND' if cd else 'DATA'} register: 0x{data:02X}")
                    
                    # Release data bus when not reading
                    elif rd == 1:
                        self.release_data_bus()
                
                # Handle network data
                self.handle_network_data()
                
                # Store previous states
                last_cs = cs
                last_rd = rd
                last_wr = wr
                
                time.sleep_us(10)  # Small delay to prevent excessive polling
                
        except KeyboardInterrupt:
            debug_print("INTERFACE", "Interface monitoring stopped by user")
        except Exception as e:
            debug_print("INTERFACE", f"Interface monitoring error: {e}")
            raise
    
    def get_status_summary(self):
        """Get comprehensive status summary"""
        status = {
            'connected': self.connected,
            'host': self.connection_host,
            'port': self.connection_port,
            'command_mode': self.command_mode,
            'wifi_connected': self.wlan.isconnected(),
            'wifi_ip': self.wlan.ifconfig()[0] if self.wlan.isconnected() else None,
            'rx_buffer_size': len(self.rx_buffer),
            'tx_buffer_size': len(self.tx_buffer),
            'total_bytes_rx': self.total_bytes_rx,
            'total_bytes_tx': self.total_bytes_tx,
            'register_reads': self.register_reads,
            'register_writes': self.register_writes,
            'status_register': self.status_register
        }
        return status

# Command interface functions
def cmd_pins(args):
    """PINS command - show pin configuration and expected states"""
    print("8251 USART PIN CONFIGURATION:")
    print("-" * 40)
    print("Data Bus:")
    print("  GP0-GP7  = D0-D7 (bidirectional)")
    print("")
    print("Control Inputs (from host):")
    print("  GP8  = C/D (Control/Data select)")
    print("  GP9  = RD (Read strobe, active LOW)")
    print("  GP10 = WR (Write strobe, active LOW)")
    print("  GP11 = CS (Chip Select, active LOW)")
    print("  GP12 = RESET (Reset, active HIGH)")
    print("")
    print("Status Outputs (to host):")
    print("  GP13 = TxRDY (Transmitter Ready)")
    print("  GP14 = RxRDY (Receiver Ready)")
    print("")
    print("Clock Input:")
    print("  GP15 = CLK (Clock input)")
    print("")
    print("NORMAL IDLE STATE:")
    print("  CS=1, RD=1, WR=1, RESET=0, C/D=X")
    print("")
    print("TROUBLESHOOTING:")
    print("- If getting reset loops: Check GP12 is not floating")
    print("- GP12 should be connected to GND or controlled by host")
    print("- Use GPIO command to check current pin states")

def cmd_connect(args):
    """CONNECT command - connect to host"""
    if not usart_instance:
        print("ERROR: USART not initialized")
        return
    
    if len(args) < 2:
        print("USAGE: CONNECT <host> <port>")
        return
    
    host = args[0]
    try:
        port = int(args[1])
    except ValueError:
        print(f"ERROR: Invalid port: {args[1]}")
        return
    
    if usart_instance.connect_network(host, port):
        print(f"CONNECTED to {host}:{port}")
    else:
        print(f"CONNECTION FAILED to {host}:{port}")

def cmd_disconnect(args):
    """DISCONNECT command"""
    if not usart_instance:
        print("ERROR: USART not initialized")
        return
    usart_instance.disconnect_network()
    print("DISCONNECTED")

def cmd_at(args):
    """AT command - send Hayes command"""
    if not usart_instance:
        print("ERROR: USART not initialized")
        return
    
    if not args:
        print("USAGE: AT <command>")
        return
    
    command = "AT" + " ".join(args)
    response = usart_instance.process_hayes_command(command)
    print(f"COMMAND: {command}")
    print(f"RESPONSE: {response}")

def cmd_reconnect(args):
    """RECONNECT command - reconnect to last WiFi network"""
    global wifi_ssid, wifi_password
    
    if not usart_instance:
        print("ERROR: USART not initialized")
        return
    
    # First try current session credentials
    if wifi_ssid and wifi_password:
        print(f"Reconnecting to {wifi_ssid} (from current session)...")
        if usart_instance.connect_wifi(wifi_ssid, wifi_password):
            print("Reconnected successfully!")
            return
        else:
            print("Reconnection failed")
    
    # Try saved credentials if session credentials don't work
    ssid, password = load_wifi_config()
    if ssid and password:
        print(f"Reconnecting to {ssid} (from saved config)...")
        if usart_instance.connect_wifi(ssid, password):
            wifi_ssid = ssid
            wifi_password = password
            print("Reconnected successfully!")
        else:
            print("Reconnection failed")
    else:
        print("No saved WiFi credentials found")
        print("Use: WIFI <ssid> <password> to connect first")

def cmd_wifi(args):
    """WIFI command - connect to WiFi"""
    global wifi_ssid, wifi_password
    
    if not usart_instance:
        print("ERROR: USART not initialized")
        return
    
    if len(args) < 2:
        print("USAGE: WIFI <ssid> <password>")
        print("OTHER: RECONNECT | WIFI_STATUS | FORGET_WIFI | AUTO_CONNECT on/off")
        return
    
    ssid = args[0]
    password = args[1]
    
    print(f"Connecting to WiFi: {ssid}")
    if usart_instance.connect_wifi(ssid, password):
        wifi_ssid = ssid
        wifi_password = password
        config = usart_instance.wlan.ifconfig()
        print(f"WiFi connected! IP: {config[0]}")
        print("Credentials saved for auto-reconnect")
    else:
        print("WiFi connection failed")
    """RECONNECT command - reconnect to last WiFi network"""
    global wifi_ssid, wifi_password
    
    if not usart_instance:
        print("ERROR: USART not initialized")
        return
    
    # First try current session credentials
    if wifi_ssid and wifi_password:
        print(f"Reconnecting to {wifi_ssid} (from current session)...")
        if usart_instance.connect_wifi(wifi_ssid, wifi_password):
            print("Reconnected successfully!")
            return
        else:
            print("Reconnection failed")
    
    # Try saved credentials if session credentials don't work
    ssid, password = load_wifi_config()
    if ssid and password:
        print(f"Reconnecting to {ssid} (from saved config)...")
        if usart_instance.connect_wifi(ssid, password):
            wifi_ssid = ssid
            wifi_password = password
            print("Reconnected successfully!")
        else:
            print("Reconnection failed")
    else:
        print("No saved WiFi credentials found")
        print("Use: WIFI <ssid> <password> to connect first")

def cmd_forget_wifi(args):
    """FORGET_WIFI command - clear saved WiFi credentials"""
    global wifi_ssid, wifi_password
    
    if clear_wifi_config():
        wifi_ssid = None
        wifi_password = None
        print("Saved WiFi credentials cleared")
    else:
        print("Failed to clear WiFi credentials")

def cmd_wifi_status(args):
    """WIFI_STATUS command - show detailed WiFi status"""
    if not usart_instance:
        print("ERROR: USART not initialized")
        return
    
    print("WIFI STATUS:")
    print("-" * 30)
    
    # Current connection
    if usart_instance.wlan.isconnected():
        config = usart_instance.wlan.ifconfig()
        print(f"Status: CONNECTED")
        print(f"IP Address: {config[0]}")
        print(f"Subnet: {config[1]}")
        print(f"Gateway: {config[2]}")
        print(f"DNS: {config[3]}")
        
        if hasattr(usart_instance, '_connected_ssid'):
            print(f"SSID: {usart_instance._connected_ssid}")
    else:
        print("Status: DISCONNECTED")
    
    # Session credentials
    if wifi_ssid:
        print(f"Session SSID: {wifi_ssid}")
    else:
        print("Session SSID: None")
    
    # Saved credentials
    saved_ssid, _ = load_wifi_config()
    if saved_ssid:
        print(f"Saved SSID: {saved_ssid}")
    else:
        print("Saved SSID: None")
    
    print(f"Auto-connect: {'Enabled' if AUTO_CONNECT_ENABLED else 'Disabled'}")

def cmd_auto_connect(args):
    """AUTO_CONNECT command - toggle auto-connect feature"""
    global AUTO_CONNECT_ENABLED
    
    if not args:
        print(f"Auto-connect is currently: {'Enabled' if AUTO_CONNECT_ENABLED else 'Disabled'}")
        print("Usage: AUTO_CONNECT on|off")
        return
    
    setting = args[0].lower()
    if setting in ['on', 'enable', 'true', '1']:
        AUTO_CONNECT_ENABLED = True
        print("Auto-connect enabled")
    elif setting in ['off', 'disable', 'false', '0']:
        AUTO_CONNECT_ENABLED = False
        print("Auto-connect disabled")
    else:
        print("Usage: AUTO_CONNECT on|off")
    """WIFI command - connect to WiFi"""
    if not usart_instance:
        print("ERROR: USART not initialized")
        return
    
    if len(args) < 2:
        print("USAGE: WIFI <ssid> <password>")
        print("EXAMPLE: WIFI MyNetwork MyPassword123")
        return
    
    ssid = args[0]
    password = args[1]
    
    print(f"Connecting to WiFi: {ssid}")
    if usart_instance.connect_wifi(ssid, password):
        config = usart_instance.wlan.ifconfig()
        print(f"WiFi connected! IP: {config[0]}")
    else:
        print("WiFi connection failed")

def cmd_status(args):
    """STATUS command - show system status"""
    if not usart_instance:
        print("ERROR: USART not initialized")
        return
    
    status = usart_instance.get_status_summary()
    
    print("8251 USART EMULATOR STATUS:")
    print("-" * 40)
    print(f"WiFi Connected: {status['wifi_connected']}")
    if status['wifi_ip']:
        print(f"WiFi IP: {status['wifi_ip']}")
    
    print(f"Network Connected: {status['connected']}")
    if status['connected']:
        print(f"Connected to: {status['host']}:{status['port']}")
    
    print(f"Command Mode: {status['command_mode']}")
    print(f"RX Buffer: {status['rx_buffer_size']} bytes")
    print(f"TX Buffer: {status['tx_buffer_size']} bytes")
    print(f"Total RX: {status['total_bytes_rx']} bytes")
    print(f"Total TX: {status['total_bytes_tx']} bytes")
    print(f"Register Reads: {status['register_reads']}")
    print(f"Register Writes: {status['register_writes']}")
    print(f"Status Register: 0x{status['status_register']:02X}")
    
    # Memory status
    gc.collect()
    free_mem = gc.mem_free()
    alloc_mem = gc.mem_alloc()
    total_mem = free_mem + alloc_mem
    print(f"Memory: {free_mem} free / {total_mem} total ({(free_mem/total_mem)*100:.1f}% free)")

def cmd_memory(args):
    """MEMORY command - show memory usage"""
    gc.collect()
    free = gc.mem_free()
    alloc = gc.mem_alloc()
    total = free + alloc
    
    print("MEMORY USAGE:")
    print("-" * 20)
    print(f"Free:      {free:6d} bytes ({(free/total)*100:.1f}%)")
    print(f"Allocated: {alloc:6d} bytes ({(alloc/total)*100:.1f}%)")
    print(f"Total:     {total:6d} bytes")

def cmd_gpio(args):
    """GPIO command - show GPIO states"""
    if not usart_instance:
        print("ERROR: USART not initialized")
        return
    
    print("GPIO PIN STATES:")
    print("-" * 20)
    cs_val = usart_instance.cs_pin.value()
    rd_val = usart_instance.rd_pin.value()
    wr_val = usart_instance.wr_pin.value()
    cd_val = usart_instance.cd_pin.value()
    reset_val = usart_instance.reset_pin.value()
    txrdy_val = usart_instance.txrdy_pin.value()
    rxrdy_val = usart_instance.rxrdy_pin.value()
    
    print(f"CS:    {cs_val} {'(SELECTED)' if cs_val == 0 else '(NOT SELECTED)'}")
    print(f"RD:    {rd_val} {'(READING)' if rd_val == 0 else '(IDLE)'}")
    print(f"WR:    {wr_val} {'(WRITING)' if wr_val == 0 else '(IDLE)'}")
    print(f"C/D:   {cd_val} {'(STATUS/CMD)' if cd_val == 1 else '(DATA)'}")
    print(f"RESET: {reset_val} {'(RESET ACTIVE!)' if reset_val == 1 else '(NORMAL)'}")
    print(f"TxRDY: {txrdy_val}")
    print(f"RxRDY: {rxrdy_val}")
    
    # Data bus
    data_value = 0
    for i, pin in enumerate(usart_instance.data_pins):
        if pin.value():
            data_value |= (1 << i)
    print(f"Data Bus: 0x{data_value:02X}")
    
    # Warning if reset is stuck high
    if reset_val == 1:
        print("")
        print("WARNING: Reset pin is HIGH!")
        print("This will cause continuous reset cycles.")
        print("Check if GP12 is connected to 3.3V or floating.")
        print("Expected: GP12 should be LOW (0V) during normal operation.")

def cmd_debug(args):
    """DEBUG command - toggle debug categories"""
    global DEBUG_GPIO, DEBUG_USART, DEBUG_NETWORK, DEBUG_HAYES, DEBUG_INTERFACE, DEBUG_SYSTEM, DEBUG_VERBOSE
    
    if not args:
        print("DEBUG CATEGORIES:")
        print(f"  GPIO: {DEBUG_GPIO}")
        print(f"  USART: {DEBUG_USART}")
        print(f"  NETWORK: {DEBUG_NETWORK}")
        print(f"  HAYES: {DEBUG_HAYES}")
        print(f"  INTERFACE: {DEBUG_INTERFACE}")
        print(f"  SYSTEM: {DEBUG_SYSTEM}")
        print(f"  VERBOSE: {DEBUG_VERBOSE}")
        print("USAGE: DEBUG <category> to toggle")
        return
    
    category = args[0].upper()
    if category == "GPIO":
        DEBUG_GPIO = not DEBUG_GPIO
        print(f"GPIO debug: {DEBUG_GPIO}")
    elif category == "USART":
        DEBUG_USART = not DEBUG_USART
        print(f"USART debug: {DEBUG_USART}")
    elif category == "NETWORK":
        DEBUG_NETWORK = not DEBUG_NETWORK
        print(f"NETWORK debug: {DEBUG_NETWORK}")
    elif category == "HAYES":
        DEBUG_HAYES = not DEBUG_HAYES
        print(f"HAYES debug: {DEBUG_HAYES}")
    elif category == "INTERFACE":
        DEBUG_INTERFACE = not DEBUG_INTERFACE
        print(f"INTERFACE debug: {DEBUG_INTERFACE}")
    elif category == "SYSTEM":
        DEBUG_SYSTEM = not DEBUG_SYSTEM
        print(f"SYSTEM debug: {DEBUG_SYSTEM}")
    elif category == "VERBOSE":
        DEBUG_VERBOSE = not DEBUG_VERBOSE
        print(f"VERBOSE debug: {DEBUG_VERBOSE}")
    else:
        print(f"Unknown debug category: {category}")

def cmd_help(args):
    """HELP command - show available commands"""
    print("8251 USART EMULATOR - QUICK REFERENCE:")
    print("=" * 45)
    print("WiFi: WIFI <ssid> <pass> | RECONNECT | FORGET_WIFI")
    print("Connect: CONNECT <host> <port> | DISCONNECT") 
    print("AT Commands: AT <cmd> (see README for full list)")
    print("System: STATUS | MEMORY | GPIO | PINS | DEBUG <cat>")
    print("Control: QUIT | HELP")
    print("")
    print("Examples:")
    print("  WIFI MyNet MyPass")
    print("  RECONNECT") 
    print("  CONNECT bbs.fozztexx.com 23")
    print("  AT D192.168.1.1:23")
    print("  AT +CWLAP")
    print("")
    print("See README.md for complete command reference")

def cmd_quit(args):
    """QUIT command - exit command interface"""
    global command_enabled
    command_enabled = False
    print("Exiting command interface...")
    return False

# Command lookup table
COMMANDS = {
    'CONNECT': cmd_connect,
    'DISCONNECT': cmd_disconnect,
    'AT': cmd_at,
    'WIFI': cmd_wifi,
    'RECONNECT': cmd_reconnect,
    'FORGET_WIFI': cmd_forget_wifi,
    'WIFI_STATUS': cmd_wifi_status,
    'AUTO_CONNECT': cmd_auto_connect,
    'STATUS': cmd_status,
    'MEMORY': cmd_memory,
    'GPIO': cmd_gpio,
    'PINS': cmd_pins,
    'DEBUG': cmd_debug,
    'HELP': cmd_help,
    'QUIT': cmd_quit,
    'EXIT': cmd_quit,
    'BYE': cmd_quit,
    '?': cmd_help
}

def process_command(command_line):
    """Process a command from the console"""
    command_line = command_line.strip()
    if not command_line:
        return True  # Continue
    
    parts = command_line.split()
    command = parts[0].upper()
    args = parts[1:] if len(parts) > 1 else []
    
    # Handle quit/exit commands directly
    if command in ['QUIT', 'EXIT', 'BYE']:
        print("Goodbye!")
        return False  # Exit
    
    if command in COMMANDS:
        try:
            result = COMMANDS[command](args)
            # Some commands may return False to indicate exit
            if result is False:
                return False
        except Exception as e:
            print(f"COMMAND ERROR: {e}")
            debug_print("SYSTEM", f"Command '{command}' failed: {e}")
    else:
        print(f"UNKNOWN COMMAND: {command}")
        print("Type HELP for available commands")
    
    return True  # Continue

def command_interface():
    """Interactive command interface"""
    print("\n8251 USART EMULATOR READY")
    print("HELP for commands | QUIT to exit")
    
    try:
        while command_enabled:
            try:
                command_line = input("> ")
                if not process_command(command_line):
                    break
            except EOFError:
                print("\nGoodbye!")
                break
            except KeyboardInterrupt:
                print("\nUse QUIT to exit...")
                continue
    except Exception as e:
        debug_print("SYSTEM", f"Command interface error: {e}")
    
    debug_print("SYSTEM", "Command interface terminated")

def core1_main():
    """Main function for core 1 (USART emulation)"""
    global usart_instance
    
    debug_print("SYSTEM", "Core1: Starting USART emulator...")
    
    try:
        usart_instance = USART8251Emulator()
        debug_print("SYSTEM", "Core1: USART emulator ready")
    except Exception as e:
        debug_print("SYSTEM", f"Core1: FATAL ERROR: {e}")
        return
    
    # Monitor interface
    debug_print("SYSTEM", "Core1: Starting interface monitoring...")
    try:
        usart_instance.monitor_interface()
    except KeyboardInterrupt:
        debug_print("SYSTEM", "Core1: Stopped by user")
    except Exception as e:
        debug_print("SYSTEM", f"Core1: FATAL ERROR: {e}")
        raise

def main():
    """Main program"""
    global command_enabled
    
    debug_print("SYSTEM", "8251 USART Emulator starting...")
    debug_config_summary()
    
    print("8251 USART Emulator v1.0")
    print("Timex/Sinclair 2050 WiFi Replacement")
    
    debug_memory()
    
    # Launch USART emulation on second core
    debug_print("SYSTEM", "Starting Core1 thread...")
    try:
        _thread.start_new_thread(core1_main, ())
        debug_print("SYSTEM", "Core1 thread started")
    except Exception as e:
        debug_print("SYSTEM", f"FATAL: Could not start Core1: {e}")
        return
    
    # Wait for USART to initialize
    timeout = 50
    while usart_instance is None and timeout > 0:
        time.sleep(0.1)
        timeout -= 1
    
    if usart_instance is None:
        debug_print("SYSTEM", "ERROR: USART failed to initialize")
        return
    
    debug_print("SYSTEM", "USART initialized, starting interface...")
    
    # Try auto-connect to saved WiFi network
    if AUTO_CONNECT_ENABLED:
        debug_print("SYSTEM", "Attempting auto-connect...")
        auto_connect_wifi()
    
    # Check memory status
    gc.collect()
    free_mem = gc.mem_free()
    if free_mem < 20000:
        print(f"WARNING: Low memory ({free_mem} bytes)")
    else:
        print(f"Memory: {free_mem} bytes available")
    
    print("\nQuick Start:")
    print("1. WIFI YourSSID YourPassword")
    print("2. RECONNECT (for saved networks)")
    print("3. CONNECT hostname port")
    print("4. AT Dhostname:port")
    print("5. Type HELP for commands")
    
    # Main core runs the command interface
    try:
        command_interface()
    except KeyboardInterrupt:
        debug_print("SYSTEM", "Shutdown requested")
        print("\nShutdown requested by user")
        command_enabled = False
    except Exception as e:
        debug_print("SYSTEM", f"FATAL: {e}")
        raise
    finally:
        debug_print("SYSTEM", "8251 USART Emulator terminating")

if __name__ == "__main__":
    main()