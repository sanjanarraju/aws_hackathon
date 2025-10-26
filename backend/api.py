from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import sys
import json

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import schedule generator and Google Calendar integration
try:
    from schedule_generator import generate_schedule
    import gcal_integration
    import converse_api
except Exception as e:
    print(f"Warning: Could not import all modules: {e}")

app = Flask(__name__)
CORS(app)

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'healthy'}), 200

@app.route('/api/generate-schedule', methods=['POST'])
def generate_schedule_endpoint():
    try:
        data = request.json
        quarter = data.get('quarter', 'Fall')
        days_of_week = data.get('days_of_week', [])
        time_preference = data.get('time_preference', 'any')
        courses = data.get('courses', [])
        teacher_preference = data.get('teacher_preference', '')
        num_schedules = data.get('num_schedules', 3)
        
        print(f"📝 Received schedule generation request:")
        print(f"  Quarter: {quarter}")
        print(f"  Days: {days_of_week}")
        print(f"  Time: {time_preference}")
        print(f"  Courses: {courses}")
        print(f"  Teacher preference: {teacher_preference}")
        
        # Convert courses list to comma-separated string
        courses_str = ','.join(courses) if isinstance(courses, list) else courses
        
        # Generate schedule using converse_api (real Claude AI integration)
        schedules = converse_api.generate_schedules(
            specific_courses=courses_str,
            teacher_preference=teacher_preference or 'Good teacher',
            num_schedules=int(num_schedules)
        )
        
        # Format results for frontend
        result = {
            'all_sections': [],
            'professor_info': [],
            'recommendations': schedules,  # List of schedule options
            'summary': {
                'total_sections': sum(len(s['schedule']) for s in schedules),
                'professors_researched': 0,
                'recommendations_count': len(schedules)
            }
        }
        
        return jsonify({'success': True, 'data': result}), 200
        
    except Exception as e:
        print(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/quarters', methods=['GET'])
def get_quarters():
    return jsonify([
        {'value': 'Fall', 'label': 'Fall 2024'},
        {'value': 'Winter', 'label': 'Winter 2025'},
        {'value': 'Spring', 'label': 'Spring 2025'},
    ]), 200

@app.route('/api/add-to-calendar', methods=['POST'])
def add_to_calendar():
    try:
        data = request.json
        schedule_data = data.get('schedule', [])
        calendar_name = data.get('calendar_name', 'Class Schedule')
        
        print(f"📅 Adding schedule to Google Calendar...")
        print(f"  Calendar name: {calendar_name}")
        print(f"  Number of events: {len(schedule_data)}")
        
        # Save schedule to CSV temporarily
        import csv
        # Get the absolute path to backend directory
        backend_dir = os.path.dirname(os.path.abspath(__file__))
        csv_filename = os.path.join(backend_dir, 'schedule.csv')
        
        print(f"  Writing CSV to: {csv_filename}")
        
        with open(csv_filename, 'w', newline='') as csvfile:
            fieldnames = ['summary', 'location', 'description', 'start', 'end', 'days_of_week', 'end_sem']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for entry in schedule_data:
                # Ensure days_of_week is a string
                entry_copy = entry.copy()
                if isinstance(entry.get('days_of_week'), list):
                    entry_copy['days_of_week'] = ','.join(entry['days_of_week'])
                writer.writerow(entry_copy)
        
        print(f"  ✅ CSV file created successfully")
        
        # Add to Google Calendar using gcal.py
        from gcal import get_or_create_calendar, add_events_from_csv
        print(f"  📝 Getting or creating calendar...")
        calendar_id = get_or_create_calendar(calendar_name)
        print(f"  📅 Calendar ID: {calendar_id}")
        print(f"  ➕ Adding events from CSV...")
        add_events_from_csv(calendar_id, csv_filename)
        
        print(f"  🧹 Cleaning up CSV file...")
        # Clean up CSV file
        if os.path.exists(csv_filename):
            os.remove(csv_filename)
            print(f"  ✅ CSV file deleted")
        
        return jsonify({
            'success': True, 
            'calendar_id': calendar_id,
            'message': 'Schedule added to Google Calendar successfully!'
        }), 200
        
    except Exception as e:
        print(f"❌ Error adding to calendar: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    print("🚀 Flask Server Starting...")
    app.run(debug=True, port=5001, host='0.0.0.0')