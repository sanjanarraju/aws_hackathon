import csv
from datetime import datetime
import pytz
import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import time

SCOPES = ['https://www.googleapis.com/auth/calendar']
TIMEZONE = 'America/Los_Angeles'

def get_service():
    creds = None
    # Get the directory where gcal.py is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    token_file = os.path.join(script_dir, 'token.json')
    
    # Try different possible credential file names
    possible_creds_files = [
        'client_secret_974602177125-dtuesgj2qfbjp7sgfk4b1vt4hc38ng7f.apps.googleusercontent.com.json',
        'credentials.json',
        'client_secret.json'
    ]
    
    creds_file = None
    for filename in possible_creds_files:
        full_path = os.path.join(script_dir, filename)
        if os.path.exists(full_path):
            creds_file = full_path
            break
    
    if not creds_file:
        raise FileNotFoundError(
            f"❌ Google OAuth credentials file not found!\n"
            f"Please place one of these files in the backend directory:\n"
            f"  • credentials.json\n"
            f"  • client_secret.json\n"
            f"  • client_secret_974602177125-dtuesgj2qfbjp7sgfk4b1vt4hc38ng7f.apps.googleusercontent.com.json\n\n"
            f"You can download your Google OAuth credentials from:\n"
            f"https://console.cloud.google.com/apis/credentials"
        )
    
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(creds_file, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_file, 'w') as token:
            token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)

def get_or_create_calendar(name="Class Schedule", timezone=TIMEZONE):
    service = get_service()
    calendar_list = service.calendarList().list().execute()
    for cal in calendar_list.get('items', []):
        if cal['summary'] == name:
            print(f"✅ Found existing calendar: {name}")
            return cal['id']
    calendar = {'summary': name, 'timeZone': timezone}
    created_calendar = service.calendars().insert(body=calendar).execute()
    print(f"✅ Created new calendar: {name}")
    return created_calendar['id']

def add_events_from_csv(calendar_id, filename):
    service = get_service()
    tz = pytz.timezone(TIMEZONE)
    schedule = []

    with open(filename, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            start_time = tz.localize(datetime.fromisoformat(row['start']))
            end_time = tz.localize(datetime.fromisoformat(row['end']))

            event = {
                'summary': row['summary'],
                'location': row['location'],
                'description': row['description'],
                'start': {'dateTime': start_time.isoformat(), 'timeZone': TIMEZONE},
                'end': {'dateTime': end_time.isoformat(), 'timeZone': TIMEZONE}
            }

            # Add recurrence if days_of_week and end_sem are provided
            if row.get('days_of_week') and row.get('end_sem'):
                days = row['days_of_week'].split(',')
                until_date = datetime.fromisoformat(row['end_sem']).strftime('%Y%m%dT235959Z')
                rrule = f"RRULE:FREQ=WEEKLY;BYDAY={','.join(days)};UNTIL={until_date}"
                event['recurrence'] = [rrule]

            created = service.events().insert(calendarId=calendar_id, body=event).execute()
            time.sleep(1)
            event_id = created['id']
            retrieved = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

            schedule.append({
                'summary': retrieved['summary'],
                'location': retrieved.get('location', ''),
                'description': retrieved.get('description', ''),
                'start': retrieved['start']['dateTime'],
                'end': retrieved['end']['dateTime'],
                'recurrence': retrieved.get('recurrence', [])
            })

    # Print human-readable schedule
    print("\n📅 Your Class Schedule:\n")
    for evt in schedule:
        rec_str = f" (Recurring: {evt['recurrence'][0]})" if evt['recurrence'] else ""
        print(f"{evt['summary']} | {evt['start']} - {evt['end']} | {evt['location']}{rec_str}")
        if evt['description']:
            print(f"  Description: {evt['description']}")
        print("---------------------------------------------------")

def run():
    calendar_id = get_or_create_calendar("Class Schedule")
    add_events_from_csv(calendar_id, 'schedule.csv')

if __name__ == '__main__':
    run()
