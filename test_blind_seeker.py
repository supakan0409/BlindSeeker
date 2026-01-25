import pytest
import asyncio
from blind_seeker2 import BlindSQLExploiter, InjectionStrategy, BooleanBasedStrategy

# ==========================================
# 🎭 MOCK OBJECTS (ตัวแสดงแทน)
# ==========================================
class MockStrategy(InjectionStrategy):
    """
    Strategy ของปลอม สำหรับทดสอบ Logic (ไม่ต้องต่อเน็ตจริง)
    มันจะจำลองว่าตัวเองเป็น Database ที่ชื่อว่า 'secret_db'
    """
    def __init__(self, target_db_name="secret_db"):
        self.target_db_name = target_db_name

    async def is_truthy(self, session, payload: str) -> bool:
        # จำลองการประมวลผล SQL แบบง่ายๆ ใน Python
        # Payload ที่ส่งมาหน้าตาประมาณ: 1' AND ASCII(SUBSTRING(database(),1,1)) > 100 #
        
        # 1. จำลองการหาความยาว (LENGTH)
        if "LENGTH(database())" in payload:
            # ดึงเลขที่ Code ถามมา (เช่น ... = 4)
            # ตัวอย่าง payload: "1' AND LENGTH(database()) = 5 #"
            check_val = int(payload.split('=')[1].strip().replace('#', ''))
            return len(self.target_db_name) == check_val

        # 2. จำลองการหาตัวอักษร (ASCII/SUBSTRING)
        if "ASCII(SUBSTRING" in payload:
            # Payload: ...database(),{pos},1)) > {mid} #
            parts = payload.split(',')
            position = int(parts[1]) # ดึงตำแหน่ง (pos)
            
            # ดึงค่า mid ที่ถาม (... > 100)
            check_condition = payload.split('>')[1].strip().replace('#', '')
            mid_value = int(check_condition)

            # ดึงตัวอักษรจริงจาก Database ปลอมของเรา
            # position เริ่มที่ 1 แต่ string index เริ่มที่ 0
            if position > len(self.target_db_name):
                return False
                
            actual_char = self.target_db_name[position - 1]
            actual_ascii = ord(actual_char)

            # ตอบกลับเหมือน SQL (True ถ้า ASCII จริง มากกว่าค่าที่ถาม)
            return actual_ascii > mid_value

        return False

# ==========================================
# ✅ TEST CASES
# ==========================================

# 1. Test Cookie Parsing (เทสฟังก์ชันย่อย)
def test_cookie_parsing():
    # สร้าง instance เปล่าๆ ขึ้นมาเพื่อเทส method
    exploiter = BlindSQLExploiter(None, "PHPSESSID=12345; security=low")
    
    expected = {'PHPSESSID': '12345', 'security': 'low'}
    assert exploiter.cookies == expected
    print("\n✅ Cookie Parsing Test Passed")

# 2. Test Binary Search Algorithm (เทส Logic หลัก)
@pytest.mark.asyncio
async def test_binary_search_logic():
    target_name = "super_secret"
    mock_strategy = MockStrategy(target_name)
    
    # Init Engine โดยใช้ Mock Strategy (ไม่ต้องใส่ URL จริง)
    engine = BlindSQLExploiter(mock_strategy, "")
    
    # สร้าง Session ปลอม (Mock object) เพราะ MockStrategy ไม่ได้ใช้ session จริง
    fake_session = None 

    # ลองให้ Engine หาตัวอักษรตำแหน่งที่ 1 ('s')
    # 's' คือ ASCII 115
    await engine._binary_search_char(fake_session, 1)
    
    # ตรวจสอบผลลัพธ์
    assert engine.results[1] == 's'
    print(f"\n✅ Logic Test Passed: Found 's' correctly")

# 3. Test Full Flow (จำลองการเจาะทั้งคำ)
@pytest.mark.asyncio
async def test_full_extraction_flow():
    target_name = "testdb" # ยาว 6 ตัว
    mock_strategy = MockStrategy(target_name)
    engine = BlindSQLExploiter(mock_strategy, "")
    
    # จำลองการหาความยาว (เราเรียกฟังก์ชัน _find_length ผ่าน Mock)
    length_found = await engine._find_length(None)
    assert length_found == 6
    
    # จำลองการหาตัวอักษรทุกตัว
    tasks = [engine._binary_search_char(None, pos) for pos in range(1, length_found + 1)]
    await asyncio.gather(*tasks)
    
    # รวมร่างผลลัพธ์
    extracted = "".join([engine.results[i] for i in sorted(engine.results.keys())])
    
    assert extracted == target_name
    print(f"\n✅ Full Flow Test Passed: Expected '{target_name}', Got '{extracted}'")