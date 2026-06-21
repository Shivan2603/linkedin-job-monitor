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

def test_query_generation():
    print("\nTesting profile-based query generation...")
    from bot.sites.linkedin import _generate_profile_query
    query = _generate_profile_query()
    print(f"Generated search query: {query}")
    assert "C#" in query, "Expected C# in query"
    assert ".NET" in query, "Expected .NET in query"
    assert "NOT" in query, "Expected exclusions in query"
    print("[PASS] Profile-based query generation verified successfully.")

def test_stack_relevance():
    print("\nTesting technology stack relevance checks...")
    from bot.ai_resume import check_tech_stack_relevance
    
    cases = [
        ("Senior .NET Developer", "We are looking for a C# programmer with SQL Server experience.", True),
        ("Python Engineer", "Strong Python and django experience required.", False),
        ("C# Software Engineer", "Full stack role building modern web applications.", True),
        ("Full Stack Developer (Angular / Node)", "We need a Node.js developer.", False),
        ("Backend Engineer", "This is a C# .NET core development position.", True),
    ]
    
    for title, jd, expected in cases:
        is_ok, reason = check_tech_stack_relevance(title, jd)
        assert is_ok == expected, f"Failed for '{title}': expected {expected}, got {is_ok} ({reason})"
        print(f"Title: '{title}' -> Tech Stack Match: {is_ok} [OK]")
        
    print("[PASS] Technology stack relevance verified successfully.")

def test_experience_relevance():
    print("\nTesting experience relevance checks...")
    from bot.ai_resume import check_experience_relevance
    
    cases = [
        ("Requires 3-5 years of experience.", True),
        ("Minimum 5 years of .NET development.", False),
        ("4+ years in C#.", True),
        ("2-4 years of experience.", True),
        ("6+ years required.", False),
    ]
    
    for jd, expected in cases:
        is_ok, reason = check_experience_relevance(jd)
        assert is_ok == expected, f"Failed for '{jd[:30]}...': expected {expected}, got {is_ok} ({reason})"
        print(f"JD: '{jd}' -> Experience Match: {is_ok} [OK]")
        
    print("[PASS] Experience relevance verified successfully.")

if __name__ == "__main__":
    test_config()
    test_india_filtering()
    test_query_generation()
    test_stack_relevance()
    test_experience_relevance()
    print("\nAll unit tests passed successfully!")
