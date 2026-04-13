#!/usr/bin/env python2.7
"""
RAMIC Bridge Daemon - Virtuoso Skill Bridge Service (Python 2.7 Version)

This daemon acts as a bridge between Python applications and Virtuoso's Skill interpreter.
It allows Python code to execute Skill commands in Virtuoso through a TCP socket connection.

Architecture:
- Python Client -> TCP Socket -> Bridge Daemon -> Virtuoso Skill Interpreter
- The daemon runs as a child process of Virtuoso and communicates via stdin/stdout
- External clients connect via TCP socket to send Skill commands

Usage: python ramic_bridge_daemon_27.py <host> <port>
Example: python ramic_bridge_daemon_27.py 127.0.0.1 65432

Python 2.7 Compatibility Notes:
- Uses 'print' statement instead of 'print()' function
- Uses 'except Exception, e' instead of 'except Exception as e'
- Uses 'unicode' type for string handling
- Uses 'range()' instead of 'xrange()' for small ranges
"""

import sys
import socket
import os
import fcntl
import json
import signal
import threading
import time
import errno
import traceback

# Python 2.7 compatibility: try to import psutil, fallback to manual PID detection
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Command line arguments for host and port
HOST = sys.argv[1]
PORT = int(sys.argv[2])

# Global timeout control flag
timeout_flag = False

# Get Virtuoso's PID - this is the process we need to send signals to
if PSUTIL_AVAILABLE:
    # Use psutil if available
    current_process = psutil.Process()
    parent_process = current_process.parent()
    # Python 2.7 compatibility: handle None case
    if parent_process and parent_process.parent():
        virtuoso_pid = parent_process.parent().pid
    else:
        virtuoso_pid = os.getppid()
else:
    # Fallback: use /proc filesystem to get parent process info
    def get_grandparent_pid():
        try:
            # Read current process info from /proc
            with open('/proc/self/stat', 'r') as f:
                stat_data = f.read().split()
                # Parent PID is the 4th field (index 3)
                parent_pid = int(stat_data[3])
                
                # Now get the parent's parent PID (grandparent)
                with open('/proc/{0}/stat'.format(parent_pid), 'r') as f2:
                    stat_data2 = f2.read().split()
                    # Grandparent PID is the 4th field (index 3) of parent's stat
                    grandparent_pid = int(stat_data2[3])
                    return grandparent_pid
        except:
            # If /proc is not available, raise an error
            raise Exception("Failed to get Virtuoso PID")
    
    virtuoso_pid = get_grandparent_pid()


# Python 2.7 compatibility: print statement instead of print() function
# print("Virtuoso PID: {0}".format(virtuoso_pid))

# Set stdin to non-blocking mode for reading Virtuoso responses
# Note: Only stdin needs to be non-blocking, stdout should remain blocking
stdin_fd = sys.stdin.fileno()
stdin_fl = fcntl.fcntl(stdin_fd, fcntl.F_GETFL)
fcntl.fcntl(stdin_fd, fcntl.F_SETFL, stdin_fl | os.O_NONBLOCK)

# Keep stdout blocking for reliable writes
stdout_fd = sys.stdout.fileno()
stdout_fl = fcntl.fcntl(stdout_fd, fcntl.F_GETFL)
fcntl.fcntl(stdout_fd, fcntl.F_SETFL, stdout_fl & ~os.O_NONBLOCK)  # Ensure blocking

# Global watchdog timer reference
watchdog_timer = None


def watchdog_callback():
    """
    Watchdog callback function that sends SIGINT signal to Virtuoso process when timeout occurs.
    This prevents the daemon from hanging indefinitely if Virtuoso doesn't respond.
    """
    global timeout_flag
    if not timeout_flag:  # If not set yet, it means timeout occurred
        timeout_flag = True
        try:
            os.kill(virtuoso_pid, signal.SIGINT)
        except Exception:
            pass

def read_until_delimiter(start_ok=b'\x02', start_err=b'\x15', end=b'\x1e'):
    """
    Read data from Virtuoso's stdout until specific delimiters are found.

    Args:
        start_ok: Byte marker for successful response start (STX - Start of Text)
        start_err: Byte marker for error response start (NAK - Negative Acknowledgment)
        end: Byte marker for response end (RS - Record Separator)

    Returns:
        Bytearray containing the response from Virtuoso

    Protocol:
        - Virtuoso responses start with STX (0x02) for success or NAK (0x15) for error
        - Responses end with RS (0x1E)
        - This function handles the binary protocol between daemon and Virtuoso
    """
    result = bytearray()

    # Normalize delimiters for Python 3 (sys.stdin.read returns str)
    delim_ok = start_ok.decode('latin1') if isinstance(start_ok, bytes) else start_ok
    delim_err = start_err.decode('latin1') if isinstance(start_err, bytes) else start_err
    delim_end = end.decode('latin1') if isinstance(end, bytes) else end

    # Wait for start marker
    while True:
        try:
            ch = sys.stdin.read(1)
            if ch in [delim_ok, delim_err]:
                break
        except IOError as e:
            if e.errno == errno.EAGAIN or e.errno == errno.EWOULDBLOCK:
                if timeout_flag:
                    return "\x15TimeoutError"
                time.sleep(0.001)
                continue
            else:
                raise
        if timeout_flag:
            return "\x15TimeoutError"

    if isinstance(ch, bytes):
        result.extend(ch)
    else:
        result.extend(ch.encode('latin1'))

    # Read content until end marker
    while True:
        try:
            ch = sys.stdin.read(1)
            if timeout_flag:
                return "\x15TimeoutError"
            if not ch:
                continue
            if ch == delim_end:
                break
            if isinstance(ch, bytes):
                result.extend(ch)
            else:
                result.extend(ch.encode('latin1'))
        except IOError as e:
            if e.errno == errno.EAGAIN or e.errno == errno.EWOULDBLOCK:
                if timeout_flag:
                    return "\x15TimeoutError"
                time.sleep(0.001)
                continue
            else:
                raise

    return result

def handle_external_connection(conn, addr):
    """
    Handle incoming TCP connections from Python clients.
    
    Args:
        conn: TCP socket connection object
        addr: Client address tuple (host, port)
    
    Protocol:
        1. Receive JSON request with 'skill' code and 'timeout' value
        2. Send skill code to Virtuoso via stdout
        3. Start watchdog timer for timeout protection
        4. Wait for Virtuoso response
        5. Send response back to client
    """
    global watchdog_timer, timeout_flag
    
    try:
        # Receive JSON formatted request data
        data = conn.recv(1024*1024)
        # Python 2.7 compatibility: data is already string, no need to decode
        request_data = json.loads(data)
        
        skill_code = request_data["skill"]
        timeout_seconds = request_data["timeout"]
        
        # Reset timeout flag
        timeout_flag = False
        
        # Send skill script to Virtuoso
        # Ensure skill_code is a str for sys.stdout.write (Python 3)
        if isinstance(skill_code, bytes):
            skill_code = skill_code.decode('utf-8')

        # Clear stdin buffer before writing (non-blocking read until empty)

        while True:
            try:
                ch = sys.stdin.read(1)
                if not ch:  # No more data
                    break
            except IOError as e:
                if e.errno == errno.EAGAIN or e.errno == errno.EWOULDBLOCK:
                    break  # No data available
                else:
                    break  # Other error, stop clearing

        sys.stdout.write(skill_code)
        sys.stdout.flush()
        
        # Start watchdog timer
        watchdog_timer = threading.Timer(timeout_seconds, watchdog_callback)
        watchdog_timer.daemon = True
        watchdog_timer.start()
        
        # Wait for Virtuoso response
        returnData = read_until_delimiter()
        
        # If normal return, set timeout flag to True to stop watchdog
        if not timeout_flag:
            timeout_flag = True
        
        # Cancel watchdog timer
        watchdog_timer.cancel()
        
        # Python 3 compatible response sending
        if isinstance(returnData, bytearray):
            conn.sendall(bytes(returnData))
        elif isinstance(returnData, str):
            conn.sendall(returnData.encode('utf-8'))
        else:
            conn.sendall(returnData)
            
    except ValueError as e:
        error_msg = "\x15JSONDecodeError: {0}".format(str(e))
        conn.sendall(error_msg.encode('utf-8'))
    except Exception as e:
        traceback.print_exc()
        error_msg = "\x15{0}".format(str(e))
        conn.sendall(error_msg.encode('utf-8'))
    finally:
        # Ensure watchdog timer is cleaned up
        timeout_flag = True
        if watchdog_timer:
            watchdog_timer.cancel()
        conn.shutdown(socket.SHUT_RDWR)
        conn.close()

def start_server():
    """
    Start the TCP server to accept client connections.
    The server runs indefinitely, handling one connection at a time.
    """
    # Python 2.7 compatibility: don't use context manager for socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # Socket options for address reuse
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        s.bind((HOST, PORT))
        s.listen(1)
        while True:
            conn, addr = s.accept()
            handle_external_connection(conn, addr)
    finally:
        s.close()

# Start the server
if __name__ == "__main__":
    start_server() 