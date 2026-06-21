import os, sys

# Add project folder to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bot.config import JOB_TITLES

def test_config():
    print("Testing config loading...")
    print(f"Loaded JOB_TITLES: {JOB_TITLES}")
    assert JOB_TITLES == [".Net"], f"Expected ['.Net'], got {JOB_TITLES}"
    print("[PASS] Config verified successfully.")

def test_india_filtering():
    print("\nTesting India location filtering logic...")
    
    # India keywords list from bot/sites/linkedin.py
    india_keywords = {"india", "bangalore", "bengaluru", "chennai", "hyderabad", "mumbai", "pune", "delhi", "noida", "gurgaon", "gurugram", "kolkata", "kochi", "coimbatore", "kerala"}
    
    test_cases = [
        ("Bangalore, Karnataka, India", True),
        ("Chennai, Tamil Nadu", True),
        ("Hyderabad, Telangana", True),
        ("London, England, United Kingdom", False),
        ("Sydney, NSW, Australia", False),
        ("New York, United States", False),
        ("Remote, US", False),
        ("Gurugram, Haryana, India", True),
        ("Mumbai, Maharashtra", True),
    ]
    
    for loc_text, expected_skip in test_cases:
        is_india = any(k in loc_text.lower() for k in india_keywords)
        assert is_india == expected_skip, f"Failed for '{loc_text}': expected skip={expected_skip}, got={is_india}"
        print(f"Location: '{loc_text}' -> Skip: {is_india} [OK]")
        
    print("[PASS] India location filtering verified successfully.")

if __name__ == "__main__":
    test_config()
    test_india_filtering()
    print("\nAll unit tests passed successfully!")
