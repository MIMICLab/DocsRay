import multiprocessing
import queue
import time
import traceback
from functools import wraps
from typing import Any, Callable, Tuple, Optional, Dict

def safehouse(timeout: int = 30, memory_limit_gb: float = 2):
   """
   Decorator that executes a function in an isolated process with timeout and memory limits.
   
   Usage:
       @safehouse(timeout=10)
       def dangerous_function(arg):
           # Code that might hang or crash
           return result
       
       success, result, error = dangerous_function("input")
   """
   def decorator(func: Callable) -> Callable:
       @wraps(func)
       def wrapper(*args, **kwargs) -> Tuple[bool, Any, Optional[Dict]]:
           return _execute_in_safehouse(func, args, kwargs, timeout, memory_limit_gb)
       return wrapper
   return decorator

def _execute_in_safehouse(
   func: Callable, 
   args: tuple, 
   kwargs: dict, 
   timeout: int,
   memory_limit_gb: float
) -> Tuple[bool, Any, Optional[Dict]]:
   """Core isolation execution logic"""
   
   def worker(result_queue, error_queue):
       try:
           # Set memory limit for Unix-like systems
           import platform
           if platform.system() != 'Windows':
               import resource
               memory_bytes = int(memory_limit_gb * 1024 * 1024 * 1024)
               resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
           
           # Execute the target function
           result = func(*args, **kwargs)
           result_queue.put(result)
           
       except Exception as e:
           error_queue.put({
               'type': type(e).__name__,
               'message': str(e),
               'traceback': traceback.format_exc()
           })
   
   # Create communication queues
   result_queue = multiprocessing.Queue()
   error_queue = multiprocessing.Queue()
   
   # Start isolated process
   process = multiprocessing.Process(
       target=worker,
       args=(result_queue, error_queue)
   )
   process.start()
   
   # Wait with timeout
   process.join(timeout=timeout)
   
   # Handle timeout
   if process.is_alive():
       process.terminate()
       process.join()
       return False, None, {
           'type': 'TimeoutError',
           'message': f'Execution exceeded {timeout} seconds',
           'traceback': None
       }
   
   # Collect results
   try:
       if not error_queue.empty():
           error = error_queue.get_nowait()
           return False, None, error
           
       if not result_queue.empty():
           result = result_queue.get_nowait()
           return True, result, None
           
   except queue.Empty:
       pass
   
   # Unknown termination
   return False, None, {
       'type': 'UnknownError',
       'message': 'Process terminated without result',
       'traceback': None
   }

def run_safe(func: Callable, *args, timeout: int = 10, **kwargs) -> Tuple[bool, Any, Optional[Dict]]:
   """
   Execute a function once in a safe isolated environment.
   
   Usage:
       success, result, error = run_safe(dangerous_function, arg1, arg2, timeout=10)
   """
   return _execute_in_safehouse(func, args, kwargs, timeout, 2)


# ============= BASIC USAGE EXAMPLES =============
'''
# Method 1: As a decorator
@safehouse(timeout=30)
def parse_pdf(pdf_path):
   import pdfplumber
   with pdfplumber.open(pdf_path) as pdf:
       return pdf.pages[0].extract_text()

# Use it
success, text, error = parse_pdf("document.pdf")
if success:
   print(text)
else:
   print(f"Failed: {error['type']} - {error['message']}")


# Method 2: One-time execution
def risky_operation(data):
   # Some dangerous code
   return process_data(data)

success, result, error = run_safe(risky_operation, my_data, timeout=10)


# Method 3: Wrap existing functions
import pdfplumber
safe_pdf_open = safehouse(timeout=20)(pdfplumber.open)
success, pdf, error = safe_pdf_open("problematic.pdf")
'''