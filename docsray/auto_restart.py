#!/usr/bin/env python3
"""
Auto-restart wrapper for DocsRay servers
Monitors and automatically restarts web_demo or mcp_server on crashes
"""

import subprocess
import sys
import time
import signal
import os
from pathlib import Path
import psutil
import logging
from datetime import datetime
import argparse

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

class ServiceMonitor:
    """Monitor and auto-restart a service"""
    
    def __init__(self, service_name, command, args=None, max_retries=5, 
                 retry_delay=5, health_check_interval=30):
        self.service_name = service_name
        self.command = command
        self.args = args or []
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.health_check_interval = health_check_interval
        self.process = None
        self.retry_count = 0
        self.running = True
        self.logger = setup_logging(service_name)
        
        # Setup signal handlers
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
    def signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.running = False
        self.stop_service()
        sys.exit(0)
        
    def start_service(self):
        """Start the service process"""
        try:
            cmd = [sys.executable, "-m", self.command] + self.args
            self.logger.info(f"Starting {self.service_name}: {' '.join(cmd)}")
            
            # Start process with proper output handling
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Reset retry count on successful start
            time.sleep(2)  # Give it time to start
            if self.is_running():
                self.retry_count = 0
                self.logger.info(f"{self.service_name} started successfully (PID: {self.process.pid})")
                return True
            else:
                self.logger.error(f"{self.service_name} failed to start properly")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to start {self.service_name}: {e}")
            return False
    
    def stop_service(self):
        """Stop the service process"""
        if self.process:
            try:
                # Try graceful shutdown first
                self.logger.info(f"Stopping {self.service_name} (PID: {self.process.pid})...")
                
                # For cross-platform compatibility
                if hasattr(self.process, 'terminate'):
                    self.process.terminate()
                    
                # Wait for process to end
                try:
                    self.process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    # Force kill if needed
                    self.logger.warning(f"Force killing {self.service_name}")
                    if hasattr(self.process, 'kill'):
                        self.process.kill()
                    self.process.wait()
                    
                self.logger.info(f"{self.service_name} stopped")
                
            except Exception as e:
                self.logger.error(f"Error stopping {self.service_name}: {e}")
            finally:
                self.process = None
    
    def is_running(self):
        """Check if the service is running"""
        if not self.process:
            return False
            
        # Check if process is still alive
        poll = self.process.poll()
        if poll is None:
            # Process is running, check if it's responsive
            try:
                # Check if process exists in system
                if psutil.pid_exists(self.process.pid):
                    proc = psutil.Process(self.process.pid)
                    return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
            except:
                pass
                
        return False
    
    def check_health(self):
        """Perform health check on the service"""
        if not self.is_running():
            return False
            
        # Service-specific health checks
        if self.service_name == "web_demo":
            return self.check_web_health()
        elif self.service_name == "mcp_server":
            return self.check_mcp_health()
            
        return True
    
    def check_web_health(self):
        """Health check for web demo"""
        try:
            import requests
            # Check if web server is responding
            response = requests.get("http://localhost:44665", timeout=5)
            return response.status_code == 200
        except:
            # If requests not available or server not responding
            return self.is_running()
    
    def check_mcp_health(self):
        """Health check for MCP server"""
        # For MCP, just check if process is running
        # More sophisticated checks could be added
        return self.is_running()
    
    def read_output(self):
        """Read and log process output"""
        if not self.process:
            return
            
        try:
            # Non-blocking read of stdout
            if self.process.stdout:
                while True:
                    line = self.process.stdout.readline()
                    if not line:
                        break
                    self.logger.info(f"[{self.service_name}] {line.strip()}")
                    
            # Non-blocking read of stderr
            if self.process.stderr:
                while True:
                    line = self.process.stderr.readline()
                    if not line:
                        break
                    self.logger.error(f"[{self.service_name} ERROR] {line.strip()}")
                    
        except:
            pass
    
    def monitor_loop(self):
        """Main monitoring loop"""
        self.logger.info(f"Starting monitor for {self.service_name}")
        
        # Initial start
        if not self.start_service():
            self.logger.error("Failed to start service initially")
            return
        
        last_health_check = time.time()
        
        while self.running:
            try:
                # Read any output
                self.read_output()
                
                # Check if process is still running
                if not self.is_running():
                    self.logger.error(f"{self.service_name} has stopped unexpectedly")
                    
                    # Check retry limit
                    if self.retry_count >= self.max_retries:
                        self.logger.error(f"Max retries ({self.max_retries}) reached. Stopping monitor.")
                        break
                    
                    # Wait before retry
                    self.retry_count += 1
                    self.logger.info(f"Waiting {self.retry_delay} seconds before retry {self.retry_count}/{self.max_retries}...")
                    time.sleep(self.retry_delay)
                    
                    # Try to restart
                    if self.start_service():
                        self.logger.info(f"Successfully restarted {self.service_name}")
                    else:
                        self.logger.error(f"Failed to restart {self.service_name}")
                        
                else:
                    # Perform periodic health check
                    current_time = time.time()
                    if current_time - last_health_check >= self.health_check_interval:
                        if not self.check_health():
                            self.logger.warning(f"{self.service_name} health check failed")
                            self.stop_service()
                        else:
                            self.logger.debug(f"{self.service_name} health check passed")
                        last_health_check = current_time
                
                # Small sleep to prevent CPU spinning
                time.sleep(1)
                
            except KeyboardInterrupt:
                self.logger.info("Keyboard interrupt received")
                break
            except Exception as e:
                self.logger.error(f"Monitor error: {e}")
                time.sleep(5)
        
        # Cleanup
        self.stop_service()
        self.logger.info(f"Monitor for {self.service_name} stopped")

def main():
    """Main entry point"""
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
    parser.add_argument(
        "--health-check-interval",
        type=int,
        default=30,
        help="Health check interval in seconds (default: 30)"
    )
    
    # Web-specific arguments
    parser.add_argument("--port", type=int, default=44665, help="Web server port")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Web server host")
    parser.add_argument("--share", action="store_true", help="Create public link")
    
    args = parser.parse_args()
    
    # Prepare service configuration
    if args.service == "web":
        service_name = "web_demo"
        command = "docsray.web_demo"
        service_args = []
        if args.port != 44665:
            service_args.extend(["--port", str(args.port)])
        if args.host != "0.0.0.0":
            service_args.extend(["--host", args.host])
        if args.share:
            service_args.append("--share")
    else:  # mcp
        service_name = "mcp_server"
        command = "docsray.mcp_server"
        service_args = []
    
    # Create and start monitor
    monitor = ServiceMonitor(
        service_name=service_name,
        command=command,
        args=service_args,
        max_retries=args.max_retries,
        retry_delay=args.retry_delay,
        health_check_interval=args.health_check_interval
    )
    
    try:
        monitor.monitor_loop()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()