"""Python decorator @retry_on_lock from Qwen (qwen-coder).
Retries sqlite3 OperationalError containing 'locked' or 'busy' with 100ms/200ms/400ms exponential backoff."""
import sqlite3
import time
import functools

def retry_on_lock(max_retries=3):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            delays = [0.1, 0.2, 0.4]  # 100ms, 200ms, 400ms
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except sqlite3.OperationalError as e:
                    error_msg = str(e).lower()
                    if 'locked' in error_msg or 'busy' in error_msg:
                        if attempt < max_retries:
                            time.sleep(delays[attempt])
                            continue
                    raise
            return func(*args, **kwargs)  # Final attempt after loop
        return wrapper
    return decorator
