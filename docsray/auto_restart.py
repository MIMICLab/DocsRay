#!/usr/bin/env python3
"""
Auto-restart wrapper for DocsRay servers - FIXED VERSION
Monitors and automatically restarts web_demo or mcp_server on crashes
"""

import subprocess
import sys
import time
import os
from pathlib import Path
import logging
from datetime import datetime
import signal
import socket
import errno
import shutil

try:
    import psutil  # pure‑Python, fallback when lsof is absent
except ImportError:
    psutil = None

USE_LSOF = shutil.which("lsof") is not None
# --- Watchdog settings ---
PROCESS_WATCHDOG_TIMEOUT = 600  # Seconds with no child activity → force kill

# Setup logging
log_dir = Path.home() / ".docsray" / "logs"
log_dir.mkdir(parents=True, exist_ok=True)

def setup_logging(service_name):
    """Setup logging for the wrapper"""
    log_file = log_dir / f"{service_name}_wrapper_{datetime.now().strftime('%Y%m%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

# -----------------------------------------------------------
# Helper utilities to free ports held by zombie processes
# -----------------------------------------------------------
def get_port_from_args(cmd: list, default: int = 44665) -> int:
    """Return port number parsed from '--port N' in command list."""
    if "--port" in cmd:
        try:
            idx = cmd.index("--port")
            return int(cmd[idx + 1])
        except (ValueError, IndexError):
            pass
    return default


def kill_port_holders(port: int):
    """
    Ensure <port> is free.
    1) Prefer 'lsof' if available (POSIX fast path).
    2) Fallback to psutil if lsof is missing.
    """
    # --- Fast path: lsof ---
    if USE_LSOF:
        try:
            out = subprocess.check_output(
                ["lsof", "-t", f"-i:{port}"], text=True
            ).strip()
            for pid in out.splitlines():
                try:
                    os.kill(int(pid), signal.SIGKILL)
                except ProcessLookupError:
                    continue
        except subprocess.CalledProcessError:
            # lsof returns non‑zero if no process found
            return
        except FileNotFoundError:
            # Should not happen because we checked, but continue to psutil
            pass

    # --- Fallback: psutil ---
    if psutil is None:
        return  # No way to inspect ports on this platform

    for proc in psutil.process_iter(['pid']):
        try:
            # connections()는 메서드로 직접 호출
            connections = proc.connections()
            for conn in connections:
                if conn.status == psutil.CONN_LISTEN and conn.laddr.port == port:
                    os.kill(proc.pid, signal.SIGKILL)  # proc.pid 사용
                    break
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.Error):
            continue

class SimpleServiceMonitor:
    """Simple but working service monitor"""
    
    def __init__(self, service_name, command_args, max_retries=5, retry_delay=5):
        self.service_name = service_name
        self.command_args = command_args
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.logger = setup_logging(service_name)
        self.retry_count = 0
        
    def run(self):
        """Main run loop - keeps restarting the service"""
        self.logger.info(f"🚀 Starting {self.service_name} monitor")
        self.logger.info(f"Command: {' '.join(self.command_args)}")
        self.logger.info(f"Max retries: {self.max_retries}, Retry delay: {self.retry_delay}s")
        
        while self.retry_count < self.max_retries:
            try:
                # Set environment variable to indicate auto-restart mode
                env = os.environ.copy()
                env['DOCSRAY_AUTO_RESTART'] = '1'
                
                # Ensure port is free before starting new process
                port_to_free = get_port_from_args(self.command_args)
                kill_port_holders(port_to_free)
                
                self.logger.info(f"Starting {self.service_name} (attempt {self.retry_count + 1}/{self.max_retries})")
                
                # Run the service
                process = subprocess.Popen(
                    self.command_args,
                    env=env
                )
                
                # --- Wait with watchdog ---
                start_ts = time.time()
                exit_code = None
                while True:
                    exit_code = process.poll()
                    if exit_code is not None:
                        # Child exited normally or via os._exit
                        break

                    # Hung‑process watchdog
                    if time.time() - start_ts > PROCESS_WATCHDOG_TIMEOUT:
                        self.logger.error("Watchdog timeout – child appears hung, terminating…")
                        process.terminate()
                        try:
                            exit_code = process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            self.logger.error("Graceful terminate failed – killing…")
                            process.kill()
                            exit_code = process.wait(timeout=5)
                        # Mark forced kill with special code
                        exit_code = 99
                        break

                    time.sleep(5)
                
                self.logger.info(f"{self.service_name} exited with code: {exit_code}")
                
                # Check exit code
                if exit_code == 0:
                    # Normal exit
                    self.logger.info("Service exited normally")
                    break
                elif exit_code == 42:
                    # Restart requested
                    self.logger.info("Service requested restart")
                    self.retry_count = 0  # Reset retry count
                elif exit_code == 99:
                    # Forced kill because watchdog detected a hang
                    self.logger.error("Service hung – watchdog forced termination (code 99)")
                    self.retry_count += 1
                else:
                    # Crash
                    self.logger.error(f"Service crashed with exit code {exit_code}")
                    self.retry_count += 1
                
                if self.retry_count < self.max_retries:
                    self.logger.info(f"Waiting {self.retry_delay} seconds before restart...")
                    time.sleep(self.retry_delay)
                
            except KeyboardInterrupt:
                self.logger.info("Received keyboard interrupt, stopping...")
                if process and process.poll() is None:
                    process.terminate()
                    process.wait()
                break
                
            except Exception as e:
                self.logger.error(f"Unexpected error: {e}")
                self.retry_count += 1
                if self.retry_count < self.max_retries:
                    time.sleep(self.retry_delay)
        
        if self.retry_count >= self.max_retries:
            self.logger.error(f"Max retries ({self.max_retries}) reached. Giving up.")
        
        self.logger.info("Monitor stopped")

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Auto-restart wrapper for DocsRay services")
    parser.add_argument(
        "service",
        choices=["web", "mcp"],
        help="Service to monitor and restart"
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=5,
        help="Maximum number of restart attempts (default: 5)"
    )
    parser.add_argument(
        "--retry-delay",
        type=int,
        default=5,
        help="Delay between restart attempts in seconds (default: 5)"
    )
    
    # Web-specific arguments
    parser.add_argument("--port", type=int, default=44665, help="Web server port")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Web server host")
    parser.add_argument("--share", action="store_true", help="Create public link")
    parser.add_argument("--timeout", type=int, default=300, help="PDF processing timeout")
    parser.add_argument("--pages", type=int, default=5, help="Max pages to process")
    
    args = parser.parse_args()
    
    # Build command
    if args.service == "web":
        # Build command for web service
        cmd = [sys.executable, "-m", "docsray.web_demo"]
        
        if args.port != 44665:
            cmd.extend(["--port", str(args.port)])
        if args.host != "0.0.0.0":
            cmd.extend(["--host", args.host])
        if args.share:
            cmd.append("--share")
        if args.timeout != 300:
            cmd.extend(["--timeout", str(args.timeout)])
        if args.pages != 5:
            cmd.extend(["--pages", str(args.pages)])
            
        service_name = "DocsRay Web"
        
    else:  # mcp
        cmd = [sys.executable, "-m", "docsray.mcp_server"]
        service_name = "DocsRay MCP"
    
    # Create and run monitor
    monitor = SimpleServiceMonitor(
        service_name=service_name,
        command_args=cmd,
        max_retries=args.max_retries,
        retry_delay=args.retry_delay
    )
    
    try:
        monitor.run()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()