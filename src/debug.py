"""
Debug module for 8251 USART Emulator
Handles all debugging functionality to save memory in main module
"""

import time
import gc

# Debug configuration - Set these to True/False to control logging
DEBUG_ENABLED = True      # Master debug switch
DEBUG_GPIO = False        # GPIO pin state changes and register access
DEBUG_USART = True        # USART register operations
DEBUG_NETWORK = True      # Network operations
DEBUG_HAYES = True        # Hayes AT command processing
DEBUG_INTERFACE = False   # Interface monitoring
DEBUG_SYSTEM = True       # System initialization and memory
DEBUG_VERBOSE = False     # Extra verbose output

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

def toggle_debug_category(category):
    """Toggle a debug category on/off"""
    global DEBUG_GPIO, DEBUG_USART, DEBUG_NETWORK, DEBUG_HAYES, DEBUG_INTERFACE, DEBUG_SYSTEM, DEBUG_VERBOSE
    
    category = category.upper()
    if category == "GPIO":
        DEBUG_GPIO = not DEBUG_GPIO
        return f"GPIO debug: {DEBUG_GPIO}"
    elif category == "USART":
        DEBUG_USART = not DEBUG_USART
        return f"USART debug: {DEBUG_USART}"
    elif category == "NETWORK":
        DEBUG_NETWORK = not DEBUG_NETWORK
        return f"NETWORK debug: {DEBUG_NETWORK}"
    elif category == "HAYES":
        DEBUG_HAYES = not DEBUG_HAYES
        return f"HAYES debug: {DEBUG_HAYES}"
    elif category == "INTERFACE":
        DEBUG_INTERFACE = not DEBUG_INTERFACE
        return f"INTERFACE debug: {DEBUG_INTERFACE}"
    elif category == "SYSTEM":
        DEBUG_SYSTEM = not DEBUG_SYSTEM
        return f"SYSTEM debug: {DEBUG_SYSTEM}"
    elif category == "VERBOSE":
        DEBUG_VERBOSE = not DEBUG_VERBOSE
        return f"VERBOSE debug: {DEBUG_VERBOSE}"
    else:
        return f"Unknown debug category: {category}"

def get_debug_status():
    """Get current debug status for all categories"""
    return {
        "GPIO": DEBUG_GPIO,
        "USART": DEBUG_USART,
        "NETWORK": DEBUG_NETWORK,
        "HAYES": DEBUG_HAYES,
        "INTERFACE": DEBUG_INTERFACE,
        "SYSTEM": DEBUG_SYSTEM,
        "VERBOSE": DEBUG_VERBOSE
    }