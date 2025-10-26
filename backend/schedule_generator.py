import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def generate_schedule(preferred_times, specific_courses, avoid_conflicts, teacher_preference, quarter='Fall', days_of_week=None):
    return {
        'all_sections': [],
        'professor_info': [],
        'recommendations': [
            {
                'course_section': 'TEST-1',
                'teacher': 'Dr. Test',
                'class_number': '1',
                'time': 'MWF 10:00-11:00am',
                'location': 'TBA',
                'reasoning': 'Mock data - backend working!'
            }
        ],
        'summary': {
            'total_sections': 1,
            'professors_researched': 1,
            'recommendations_count': 1
        }
    }