import re
import boto3
import pandas as pd
import os
from dotenv import load_dotenv
import json
import ratemyprof_info
import gcal
import csv

# === Load AWS credentials ===
load_dotenv()
access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")

# === Check if credentials are set ===
if not access_key_id or access_key_id == "your_access_key_here":
    print("ERROR: AWS_ACCESS_KEY_ID not set properly in .env file!")
    print("Please edit backend/.env and add your real AWS credentials.")
    exit(1)

if not secret_access_key or secret_access_key == "your_secret_key_here":
    print("ERROR: AWS_SECRET_ACCESS_KEY not set properly in .env file!")
    print("Please edit backend/.env and add your real AWS credentials.")
    exit(1)

# === S3 setup ===
bucket_name = 'schedulebuildertool'
s3_key = 'classes/SCU_Find_Course_Sections.xlsx'
local_file = 'SCU_Find_Course_Sections.xlsx'

s3_client = boto3.client(
    's3',
    aws_access_key_id=access_key_id,
    aws_secret_access_key=secret_access_key,
    region_name="us-east-1"
)

# === Download and read Excel ===
print("Downloading Excel file from S3...")
try:
    s3_client.download_file(bucket_name, s3_key, local_file)
except Exception as e:
    print(f"ERROR accessing S3 bucket: {e}")
    print("\nTroubleshooting:")
    print("1. Check that your AWS credentials in .env are correct")
    print("2. Verify your credentials have S3 read permissions")
    print("3. Make sure the bucket 'schedulebuildertool' exists")
    print("4. Check that the file 'classes/SCU_Find_Course_Sections.xlsx' exists in the bucket")
    exit(1)
print("File downloaded successfully.\n")

# === Read relevant data ===
df = pd.read_excel(local_file)
columns_of_interest = [
    "Course Section",
    "All Instructors",
    "Section Status",
    "Enrolled/Capacity",
    "Meeting Patterns",
    "Locations",
    "Start Date",
    "End Date"
]

# Only keep valid columns
df = df[[c for c in columns_of_interest if c in df.columns]]

# === Collect user preferences ===
print("="*60)
print("SCHEDULE GENERATION")
print("="*60)

specific_courses = input("Courses you must take (e.g., 'MATH 51, PHYS 32'): ").strip()
teacher_preference = input("What do you want in a teacher: ").strip()
num_schedules = input("How many schedule options do you want? ").strip()

# === Filter for user-specified courses ===
if specific_courses:
    course_keywords = [c.strip() for c in specific_courses.split(',')]
    mask = pd.Series(False, index=df.index)
    
    for keyword in course_keywords:
        pattern = f"{keyword}-"
        mask |= df["Course Section"].str.contains(pattern, case=False, na=False, regex=False)
    
    filtered_df = df[mask]
    
    if filtered_df.empty:
        print(f"⚠️ No matching courses found for: {course_keywords}")
        filtered_df = df
else:
    filtered_df = df

print("Generating schedules...")

# === Summarize course data for Claude ===
summary = f"""
COURSE DATA SUMMARY:
- Total matching sections: {len(filtered_df)}
- Columns: {', '.join(filtered_df.columns.tolist())}

Sample of matching data:
{filtered_df.head(20).to_string(index=False)}
"""

# Clean up downloaded file
os.remove(local_file)

# === Prepare Bedrock client ===
client = boto3.client(
    service_name="bedrock-runtime",
    aws_access_key_id=access_key_id,
    aws_secret_access_key=secret_access_key,
    region_name="us-east-1",
)

model_id = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

# === Helper function for Claude ===
def split_name(full_name: str) -> tuple[str, str] | None:
    parts = [p for p in re.split(r"\s+", full_name.strip()) if p]
    if len(parts) < 2:
        return None
    first = parts[0]
    last  = " ".join(parts[1:])
    return first, last

def extract_json_from_response(text):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    
    json_pattern = r'\[[\s\S]*?\]'
    matches = re.findall(json_pattern, text)
    for match in matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue
    return None

# === Step 1: Get course sections and professor info ===
prompt1 = f"""
You are an expert academic advisor. Extract course sections and professor information from the data.

COURSE DATA:
{summary}

MY PREFERENCES:
- Required courses: {specific_courses or 'None specified'}

TASK:
Find all course sections for the required courses and extract professor information.

OUTPUT FORMAT (JSON array only):
[
    {{"class number": "1", "course section": "MATH 51-1", "teacher": "Professor Name", "time": "MWF 1:00-2:05 pm"}},
    {{"class number": "1", "course section": "MATH 51-2", "teacher": "Another Professor", "time": "TTH 8:00-12:10pm"}}
]

The "class number" indicates what class it is. All course sections of the same course share the same class number.
Respond with JSON ONLY - NO OTHER TEXT.
"""

response1 = client.converse_stream(
    modelId=model_id,
    messages=[{"role": "user", "content": [{"text": prompt1}]}],
    inferenceConfig={"maxTokens": 1467, "temperature": 0.9},
)

claude_output1 = ""
for chunk in response1["stream"]:
    if "contentBlockDelta" in chunk:
        delta = chunk["contentBlockDelta"]["delta"]
        if delta.get("text"):
            claude_output1 += delta["text"]

all_sections = extract_json_from_response(claude_output1)

# === Get professor info from RateMyProfessor ===
teacher_jsons = []
for section in all_sections:
    teacher_name = section['teacher']
    name_parts = split_name(teacher_name)
    
    if name_parts:
        first_name, last_name = name_parts
        teacher_info = ratemyprof_info.professorRater(first_name, last_name)
        teacher_jsons.append(teacher_info)
    else:
        teacher_jsons.append(None)

# === Step 2: Generate schedules with dates/times ===
schedule_prompt = f"""
You are an academic advisor creating course schedules.

STUDENT'S TEACHER PREFERENCES: "{teacher_preference}"

AVAILABLE COURSE SECTIONS AND PROFESSORS:
{json.dumps([
    {
        'course_section': section.get('course section', ''),
        'teacher': section.get('teacher', ''),
        'time': section.get('time', ''),
        'class_number': section.get('class number', ''),
        'prof_info': teacher_jsons[i] if teacher_jsons[i] else None
    }
    for i, section in enumerate(all_sections)
], indent=2)}

ORIGINAL DATA WITH DATES AND TIMES:
{filtered_df[['Course Section', 'Meeting Patterns', 'Locations', 'Start Date', 'End Date']].to_string(index=False)}

TASK:
Create {num_schedules} different course schedules. For each schedule, also provide pros and cons.

For each schedule:
1. For each course (by class_number), pick ONE section with the best professor matching the preferences
2. Use Start Date for the first class meeting
3. Parse Meeting Patterns to get days and times
4. Use End Date for the semester end
5. Provide brief pros and cons based on professor quality, schedule convenience, time preferences

OUTPUT FORMAT (JSON array with schedule and analysis):
[
  {{
    "schedule": [
      {{"summary": "MATH 51-3", "location": "Daly Science 300", "description": "Schaeffer", "start": "2025-09-22T13:00:00", "end": "2025-09-22T14:05:00", "days_of_week": ["MO","WE","FR"], "end_sem": "2025-12-12"}},
      {{"summary": "PHYS 32-2", "location": "SCDI 1308", "description": "Williams", "start": "2025-09-23T08:00:00", "end": "2025-09-23T09:05:00", "days_of_week": ["MO","WE","FR"], "end_sem": "2025-12-12"}}
    ],
    "pros": ["High-rated professors", "Morning classes", "No Friday classes"],
    "cons": ["Early start time", "Classes on MWF only"]
  }},
  {{
    "schedule": [
      {{"summary": "MATH 51-1", "location": "Heafey 124", "description": "Walden", "start": "2025-09-22T13:00:00", "end": "2025-09-22T14:05:00", "days_of_week": ["MO","WE","FR"], "end_sem": "2025-12-12"}},
      {{"summary": "PHYS 32-2", "location": "SCDI 1308", "description": "Williams", "start": "2025-09-23T08:00:00", "end": "2025-09-23T09:05:00", "days_of_week": ["MO","WE","FR"], "end_sem": "2025-12-12"}}
    ],
    "pros": ["Best-rated professor for Math", "Afternoon classes"],
    "cons": ["Lower rated for one course", "Friday classes"]
  }}
]

OUTPUT ONLY THE JSON ARRAY - NO OTHER TEXT.
"""

response2 = client.converse_stream(
    modelId=model_id,
    messages=[{"role": "user", "content": [{"text": schedule_prompt}]}],
    inferenceConfig={"maxTokens": 2000, "temperature": 0.5},
)

schedule_output = ""
for chunk in response2["stream"]:
    if "contentBlockDelta" in chunk:
        delta = chunk["contentBlockDelta"]["delta"]
        if delta.get("text"):
            schedule_output += delta["text"]

json_str = schedule_output[schedule_output.find("["):schedule_output.rfind("]")+1] 
schedules_with_analysis = json.loads(json_str)

# === Parse schedules with pros/cons ===
total_schedules = []
for item in schedules_with_analysis:
    if isinstance(item, dict) and 'schedule' in item:
        total_schedules.append({
            'schedule': item['schedule'],
            'pros': item.get('pros', []),
            'cons': item.get('cons', [])
        })
    else:
        # Fallback for old format
        total_schedules.append({
            'schedule': item,
            'pros': [],
            'cons': []
        })

# === Display schedules ===
print(f"\n✅ Generated {len(total_schedules)} schedule options:\n")
print("="*70)

for i, schedule_data in enumerate(total_schedules, 1):
    schedule = schedule_data['schedule']
    pros = schedule_data.get('pros', [])
    cons = schedule_data.get('cons', [])
    
    print(f"\n📅 SCHEDULE {i}:")
    print("-" * 70)
    for entry in schedule:
        days = ','.join(entry['days_of_week']) if isinstance(entry['days_of_week'], list) else entry['days_of_week']
        print(f"  • {entry['summary']}")
        print(f"    Professor: {entry['description']}")
        print(f"    Time: {days} ({entry['start'][:10]} {entry['start'][11:16]})")
        print(f"    Location: {entry.get('location', 'TBD')}")
    
    # Display pros and cons
    if pros or cons:
        print(f"\n  💡 Analysis:")
        if pros:
            print(f"    ✅ Pros:")
            for pro in pros:
                print(f"       • {pro}")
        if cons:
            print(f"    ⚠️  Cons:")
            for con in cons:
                print(f"       • {con}")
    print()

# === User selects schedule ===
print("="*70)
print("SELECT SCHEDULE TO ADD TO CALENDAR")
print("="*70)
schedule_num = input("Which schedule number do you want? ").strip()

try:
    schedule_num = int(schedule_num)
    if 1 <= schedule_num <= len(total_schedules):
        selected_data = total_schedules[schedule_num - 1]
        selected_schedule = selected_data['schedule']
        
        # Write to CSV
        csv_columns = ["summary", "location", "description", "start", "end", "days_of_week", "end_sem"]
        with open('schedule.csv', 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=csv_columns)
            writer.writeheader()
            for entry in selected_schedule:
                entry_copy = entry.copy()
                entry_copy['days_of_week'] = ','.join(entry['days_of_week'])
                writer.writerow(entry_copy)
        
        print(f"✅ Saved schedule {schedule_num} to CSV")
        
        # Add to calendar
        print("\n" + "="*70)
        print("ADDING TO CALENDAR")
        print("="*70)
        gcal.run()
        
        # Clean up
        if os.path.exists('schedule.csv'):
            os.remove('schedule.csv')
    else:
        print(f"⚠️ Invalid schedule number. Must be between 1 and {len(total_schedules)}")
except ValueError:
    print("⚠️ Invalid input. Please enter a number.")

