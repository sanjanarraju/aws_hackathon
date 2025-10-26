import re
import boto3
import pandas as pd
import os
from dotenv import load_dotenv
import json
import ratemyprof_info
import csv

# Load AWS credentials once at module level
load_dotenv()
access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")

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

def times_overlap(schedule1, schedule2):
    """
    Check if two schedule entries overlap in time.
    
    Args:
        schedule1, schedule2: Schedule entries with start, end, and days_of_week
        
    Returns:
        True if they overlap, False otherwise
    """
    # Check if they share any days
    days1 = set(schedule1.get('days_of_week', []))
    days2 = set(schedule2.get('days_of_week', []))
    
    if not days1 or not days2 or not days1.intersection(days2):
        return False
    
    # Check if times overlap
    try:
        start1 = schedule1.get('start')
        end1 = schedule1.get('end')
        start2 = schedule2.get('start')
        end2 = schedule2.get('end')
        
        if not all([start1, end1, start2, end2]):
            return False
        
        # Parse ISO datetime strings
        from datetime import datetime
        dt_start1 = datetime.fromisoformat(start1)
        dt_end1 = datetime.fromisoformat(end1)
        dt_start2 = datetime.fromisoformat(start2)
        dt_end2 = datetime.fromisoformat(end2)
        
        # Check if time ranges overlap
        # Two ranges overlap if: start1 < end2 AND start2 < end1
        return dt_start1 < dt_end2 and dt_start2 < dt_end1
        
    except (ValueError, AttributeError):
        return False

def check_schedule_validity(schedule):
    """
    Check if a schedule has any overlapping class times.
    
    Args:
        schedule: List of schedule entries
        
    Returns:
        True if valid (no overlaps), False otherwise
    """
    if not schedule or len(schedule) < 2:
        return True
    
    # Check all pairs for overlaps
    for i in range(len(schedule)):
        for j in range(i + 1, len(schedule)):
            if times_overlap(schedule[i], schedule[j]):
                return False
    
    return True

def filter_valid_schedules(schedules):
    """
    Filter out schedules that have overlapping class times.
    
    Args:
        schedules: List of schedule options
        
    Returns:
        List of schedule options without overlapping times
    """
    valid_schedules = []
    for schedule_option in schedules:
        if check_schedule_validity(schedule_option.get('schedule', [])):
            valid_schedules.append(schedule_option)
    return valid_schedules

def generate_schedules(specific_courses: str, teacher_preference: str, num_schedules: int = 3):
    """
    Generate course schedules using Claude AI and RateMyProfessor data.
    
    Args:
        specific_courses: Comma-separated course names (e.g., "MATH 51, PHYS 32")
        teacher_preference: Description of what user wants in a teacher
        num_schedules: Number of schedule options to generate
        
    Returns:
        List of schedule options with pros/cons
    """
    # Setup S3 client
    bucket_name = 'schedulebuildertool'
    s3_key = 'classes/SCU_Find_Course_Sections.xlsx'
    local_file = 'SCU_Find_Course_Sections.xlsx'
    
    s3_client = boto3.client(
        's3',
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="us-east-1"
    )
    
    # Download Excel file
    try:
        s3_client.download_file(bucket_name, s3_key, local_file)
    except Exception as e:
        raise Exception(f"Failed to download course data from S3: {e}")
    
    # Read and filter data
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
    df = df[[c for c in columns_of_interest if c in df.columns]]
    
    # Filter for specified courses
    if specific_courses:
        course_keywords = [c.strip() for c in specific_courses.split(',')]
        mask = pd.Series(False, index=df.index)
        for keyword in course_keywords:
            pattern = f"{keyword}-"
            mask |= df["Course Section"].str.contains(pattern, case=False, na=False, regex=False)
        filtered_df = df[mask]
        if filtered_df.empty:
            filtered_df = df  # Fallback to all courses if none found
    else:
        filtered_df = df
    
    # Summarize data for Claude
    summary = f"""
COURSE DATA SUMMARY:
- Total matching sections: {len(filtered_df)}
- Columns: {', '.join(filtered_df.columns.tolist())}

Sample of matching data:
{filtered_df.head(20).to_string(index=False)}
"""
    
    # Clean up downloaded file
    os.remove(local_file)
    
    # Setup Bedrock client
    client = boto3.client(
        service_name="bedrock-runtime",
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="us-east-1",
    )
    model_id = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    
    # Step 1: Get course sections
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
    
    # Get professor info from RateMyProfessor
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
    
    # Step 2: Generate schedules with dates/times
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

CRITICAL REQUIREMENTS:
- NO OVERLAPPING TIMES: Within each schedule, classes MUST be scheduled at different times
- Each course can only have ONE section per schedule (no duplicates)
- Classes cannot overlap if they share any common days (e.g., both Monday+Wednesday)

For each schedule:
1. For each course (by class_number), pick ONE section with the best professor matching the preferences
2. Ensure NO two classes overlap in time (check days_of_week and start/end times)
3. Use Start Date for the first class meeting
4. Parse Meeting Patterns to get days and times
5. Use End Date for the semester end
6. Provide brief pros and cons based on professor quality, schedule convenience, time preferences

OUTPUT FORMAT (JSON array with schedule and analysis):
[
  {{
    "schedule": [
      {{"summary": "MATH 51-3", "location": "Daly Science 300", "description": "Schaeffer", "start": "2025-09-22T13:00:00", "end": "2025-09-22T14:05:00", "days_of_week": ["MO","WE","FR"], "end_sem": "2025-12-12"}},
      {{"summary": "PHYS 32-2", "location": "SCDI 1308", "description": "Williams", "start": "2025-09-23T08:00:00", "end": "2025-09-23T09:05:00", "days_of_week": ["MO","WE","FR"], "end_sem": "2025-12-12"}}
    ],
    "pros": ["High-rated professors", "Morning classes", "No Friday classes"],
    "cons": ["Early start time", "Classes on MWF only"]
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
    
    # Parse schedules with pros/cons
    total_schedules = []
    for item in schedules_with_analysis:
        if isinstance(item, dict) and 'schedule' in item:
            total_schedules.append({
                'schedule': item['schedule'],
                'pros': item.get('pros', []),
                'cons': item.get('cons', [])
            })
        else:
            total_schedules.append({
                'schedule': item,
                'pros': [],
                'cons': []
            })
    
    # Filter out schedules with overlapping times
    valid_schedules = filter_valid_schedules(total_schedules)
    
    # If we lost some schedules due to overlaps, log it
    if len(valid_schedules) < len(total_schedules):
        print(f"⚠️ Filtered out {len(total_schedules) - len(valid_schedules)} schedules with overlapping times")
    
    # If no valid schedules remain, return the original (better than nothing)
    if not valid_schedules:
        print("⚠️ No schedules passed overlap check, returning all schedules")
        return total_schedules
    
    return valid_schedules

