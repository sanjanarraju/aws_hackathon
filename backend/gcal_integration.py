import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gcal import get_or_create_calendar, add_events_from_csv

def add_to_google_calendar(csv_filename, calendar_name="Class Schedule"):
    try:
        calendar_id = get_or_create_calendar(calendar_name)
        add_events_from_csv(calendar_id, csv_filename)
        return calendar_id
    except Exception as e:
        raise Exception(f"Failed to add to Google Calendar: {str(e)}")

