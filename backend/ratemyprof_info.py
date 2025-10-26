import requests
import json
from typing import List, Dict, Any

SCHOOL_ID = "U2Nob29sLTg4Mg=="

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/115.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "Referer": "https://www.ratemyprofessors.com/",
}

def get_professor_info(first_name, last_name):
    url = "https://www.ratemyprofessors.com/graphql"
    query = """
    query TeacherSearchPaginationQuery($count: Int!, $cursor: String, $query: TeacherSearchQuery!) {
      search: newSearch {
        teachers(query: $query, first: $count, after: $cursor) {
          edges {
            node {
              firstName
              lastName
              id
              department
              avgRating
              avgDifficulty
              numRatings
              wouldTakeAgainPercent
              school { name }
            }
          }
        }
      }
    }
    """
    variables = {
        "count": 10,
        "cursor": None,
        "query": {"text": f"{first_name} {last_name}", "schoolID": SCHOOL_ID, "fallback": True}
    }

    response = requests.post(url, headers=HEADERS, json={"query": query, "variables": variables}, timeout=10)
    if response.status_code != 200:
        print("Error: Status code", response.status_code)
        return None

    try:
        data = response.json()
    except json.JSONDecodeError:
        print("Error: Response is not JSON")
        return None

    teachers = data.get("data", {}).get("search", {}).get("teachers", {}).get("edges", [])
    for t in teachers:
        node = t.get("node", {})
        if node.get("firstName", "").strip().lower() == first_name.strip().lower() and \
           node.get("lastName", "").strip().lower() == last_name.strip().lower():
            return node
    return None

def get_professor_comments(professor_id, count=50):
    url = "https://www.ratemyprofessors.com/graphql"
    query = """
    query RatingsListQuery($count: Int!, $id: ID!, $courseFilter: String, $cursor: String) {
      node(id: $id) {
        __typename
        ... on Teacher {
          ratings(first: $count, after: $cursor, courseFilter: $courseFilter) {
            edges {
              node {
                comment
                ratingTags
                class
                date
              }
            }
          }
        }
      }
    }
    """
    variables = {"count": count, "id": professor_id, "courseFilter": None, "cursor": None}

    response = requests.post(url, headers=HEADERS, json={"query": query, "variables": variables}, timeout=10)
    if response.status_code != 200:
        print("Error fetching comments:", response.status_code)
        return []

    try:
        data = response.json()
    except json.JSONDecodeError:
        print("Comments response not JSON")
        return []

    edges = data.get("data", {}).get("node", {}).get("ratings", {}).get("edges", [])
    comments = []
    for e in edges:
        n = e.get("node", {})
        comments.append({
            "comment": n.get("comment", ""),
            "tags": n.get("ratingTags", ""),
            "class": n.get("class", ""),
            "date": n.get("date", "")
        })
    return comments

def save_combined_json(professor, comments, filename):
    combined = {
        "professor_info": {
            "firstName": professor.get("firstName"),
            "lastName": professor.get("lastName"),
            "department": professor.get("department"),
            "school": professor.get("school", {}).get("name"),
            "avgRating": professor.get("avgRating"),
            "avgDifficulty": professor.get("avgDifficulty"),
            "numRatings": professor.get("numRatings"),
            "wouldTakeAgainPercent": professor.get("wouldTakeAgainPercent")
        },
        "comments": comments
    }
    return combined

def rateMyProfessor(name):
    print("Rate My Professors SCU - Live Data")
    
    #first_name = input("Enter professor's first name: ").strip()
    #last_name = input("Enter professor's last name: ").strip()
    parts = name.strip().split()
    if len(parts) < 2:
        print(f"Skipping '{name}': need at least first and last name.")
        return
    
    first_name = parts[0]
    last_name  = " ".join(parts[1:])   # supports multi-word last names

    professor = get_professor_info(first_name, last_name)
    if not professor:
        print("Professor not found or unable to fetch info.")
        return

    comments = get_professor_comments(professor.get("id"))

    filename = f"{name}.json"
    save_combined_json(professor, comments, filename)

def parse_courses_list(text: str) -> List[str]:
    # "PSYC 51, MATH 30" -> ["PSYC 51","MATH 30"]
    return [c.strip() for c in text.split(",") if c.strip()]

def handle_ai_output(ai_json_text: str):
    """
    ai_json_text should look like:
    {
      "assignments": [
        {"course":"PSYC 51","professor":{"first":"Shan","last":"Wu"}},
        {"course":"MATH 30","professor":{"first":"Jane","last":"Doe"}}
      ]
    }
    """
    data = json.loads(ai_json_text)
    seen = set()
    for item in data.get("assignments", []):
        prof = item.get("professor", {})
        first = (prof.get("first") or "").strip()
        last  = (prof.get("last")  or "").strip()
        if not first or not last:
            print(f"Missing name in item: {item}")
            continue
        key = (first.lower(), last.lower())
        if key in seen:
            continue
        seen.add(key)
        rateMyProfessor(f"{first} {last}")
        

def professorRater(first_name, last_name):
    professor = get_professor_info(first_name, last_name)
    if not professor:
        print(f"Professor not found or unable to fetch info for {first_name} {last_name}.")
        return None

    comments = get_professor_comments(professor.get("id"))

    filename_base = f"{first_name}_{last_name}"
    combined_data = save_combined_json(professor, comments, f"{filename_base}.json")
    
    # Return the combined data structure that includes both professor info and comments
    return combined_data
