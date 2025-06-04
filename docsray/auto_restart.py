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
                
                self.logger.info(f"Starting {self.service_name} (attempt {self.retry_count + 1}/{self.max_retries})")
                
                # Run the service
                process = subprocess.Popen(
                    self.command_args,
                    env=env
                )
                
                # Wait for it to finish
                exit_code = process.wait()
                
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