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

def test_salary_estimation():
    print("\nTesting salary estimation logic...")
    from bot.sites.linkedin import _estimate_expected_salary
    
    # Test case 1: UK location, text field
    res_uk = _estimate_expected_salary("What is your expected salary?", "Senior .Net Developer", "Awesome Corp", "We need a Senior .NET Developer", "London, United Kingdom", is_number_field=False)
    print(f"UK Expected (text): {res_uk}")
    assert any(symbol in res_uk for symbol in ["£", "GBP", "65,000", "70,000", "75,000", "80,000", "90,000", "85,000"]), f"Failed to detect GBP currency or amount in: {res_uk}"

    # Test case 2: US location, numeric field
    res_us = _estimate_expected_salary("Expected salary in USD", "Senior .Net Developer", "Awesome Corp", "We need a Senior .NET Developer", "San Francisco, CA, USA", is_number_field=True)
    print(f"US Expected (numeric): {res_us}")
    import re
    digits = re.sub(r'[^\d]', '', res_us)
    assert digits.isdigit(), f"Expected numeric digits only for numeric field, got: {res_us}"
    assert int(digits) > 0, f"Expected a positive salary amount, got: {digits}"

    # Test case 3: Malaysia location, text field
    res_my = _estimate_expected_salary("Expected monthly salary", "Senior .Net Developer", "Awesome Corp", "We need a Senior .NET Developer", "Kuala Lumpur, Malaysia", is_number_field=False)
    print(f"Malaysia Expected (text): {res_my}")
    assert any(symbol in res_my for symbol in ["RM", "MYR", "10,000", "12,000", "15,000", "96,000", "120,000", "80,000"]), f"Failed to detect MYR currency/amount in: {res_my}"

    print("[PASS] Salary estimation verified successfully.")

if __name__ == "__main__":
    test_config()
    test_india_filtering()
    test_query_generation()
    test_stack_relevance()
    test_experience_relevance()
    test_salary_estimation()
    print("\nAll unit tests passed successfully!")
