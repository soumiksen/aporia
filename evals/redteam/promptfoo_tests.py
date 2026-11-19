from redteam.loaders import load_cases


def generate_tests(config=None):
    return [
        {
            "description": case["id"],
            "vars": {
                "case_id": case["id"],
                "student_message": case["student_message"],
                "category": case["category"],
            },
        }
        for case in load_cases()
    ]
