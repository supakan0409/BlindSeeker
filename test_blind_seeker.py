import pytest
import asyncio
from blind_seeker2 import BlindSQLExploiter, InjectionStrategy, BooleanBasedStrategy

# ==========================================
# MOCK OBJECTS
# ==========================================
class MockStrategy(InjectionStrategy):
    """
    Mock Strategy for offline testing.
    Simulates a database interaction without network calls.
    Target Database Name: Configurable via constructor.
    """
    def __init__(self, target_db_name="secret_db"):
        self.target_db_name = target_db_name

    async def is_truthy(self, session, payload: str) -> bool:
        # Simulate SQL logic in Python
        # Example payload: 1' AND ASCII(SUBSTRING(database(),1,1)) > 100 #
        
        # 1. Simulate LENGTH() check
        if "LENGTH(database())" in payload:
            # Extract the length value being checked
            # Payload format: ... = 5 #
            check_val = int(payload.split('=')[1].strip().replace('#', ''))
            return len(self.target_db_name) == check_val

        # 2. Simulate ASCII/SUBSTRING check
        if "ASCII(SUBSTRING" in payload:
            # Payload format: ...database(),{pos},1)) > {mid} #
            parts = payload.split(',')
            position = int(parts[1]) # Extract position
            
            # Extract the comparison value (mid)
            check_condition = payload.split('>')[1].strip().replace('#', '')
            mid_value = int(check_condition)

            # Check bounds (1-based index in SQL vs 0-based in Python)
            if position > len(self.target_db_name):
                return False
                
            actual_char = self.target_db_name[position - 1]
            actual_ascii = ord(actual_char)

            # Return True if actual ASCII value is greater than the check value
            return actual_ascii > mid_value

        return False

# ==========================================
# TEST CASES
# ==========================================

# 1. Test Cookie Parsing Utility
def test_cookie_parsing():
    """Verify that raw cookie strings are parsed correctly into dictionaries."""
    exploiter = BlindSQLExploiter(None, "PHPSESSID=12345; security=low")
    
    expected = {'PHPSESSID': '12345', 'security': 'low'}
    assert exploiter.cookies == expected
    print("\nCookie Parsing Test Passed")

# 2. Test Binary Search Algorithm Logic
@pytest.mark.asyncio
async def test_binary_search_logic():
    """Verify the binary search logic against the Mock Strategy."""
    target_name = "super_secret"
    mock_strategy = MockStrategy(target_name)
    
    # Initialize engine with Mock Strategy
    engine = BlindSQLExploiter(mock_strategy, "")
    
    # Use None for session as MockStrategy doesn't use it
    fake_session = None 

    # Attempt to find the first character ('s' -> ASCII 115)
    await engine._binary_search_char(fake_session, 1)
    
    # Verify result
    assert engine.results[1] == 's'
    print(f"\nLogic Test Passed: Found 's' correctly")

# 3. Test Full Extraction Flow
@pytest.mark.asyncio
async def test_full_extraction_flow():
    """Verify the entire flow: Length check -> Parallel Extraction -> Result Assembly."""
    target_name = "testdb" # Length: 6
    mock_strategy = MockStrategy(target_name)
    engine = BlindSQLExploiter(mock_strategy, "")
    
    # 1. Verify Length Detection
    length_found = await engine._find_length(None)
    assert length_found == 6
    
    # 2. Verify Character Extraction (Parallel)
    tasks = [engine._binary_search_char(None, pos) for pos in range(1, length_found + 1)]
    await asyncio.gather(*tasks)
    
    # 3. Verify Final Assembly
    extracted = "".join([engine.results[i] for i in sorted(engine.results.keys())])
    
    assert extracted == target_name
    print(f"\nFull Flow Test Passed: Expected '{target_name}', Got '{extracted}'")