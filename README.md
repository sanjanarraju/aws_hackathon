# Schedule Builder - AWS INRIX Hackathon

A course scheduling system that helps students find the best classes and professors based on RateMyProfessor data, then syncs schedules to Google Calendar.

## Project Structure

```
ratemyprof_fetcher/
├── frontend/          # React + TypeScript frontend (AWS HACKATTACK)
├── backend/           # Python backend (Flask API, scheduling, RateMyProfessor, Google Calendar)
└── README.md          # This file
```

## Features

- Course scheduling with AI-powered recommendations
- RateMyProfessor integration for professor ratings
- Google Calendar synchronization

## Quick Start - Running the Full Stack

### 1. Backend API Server

```bash
cd backend

# Install dependencies (if not already done)
pip install -r requirements.txt

# Set up your AWS credentials in .env file
# AWS_ACCESS_KEY_ID=your_key
# AWS_SECRET_ACCESS_KEY=your_secret

# Start the Flask API server
python api.py
```

The backend API will run on `http://localhost:5001`

### 2. Frontend App

In a new terminal:

```bash
cd frontend

# Install dependencies (if not already done)
npm install

# Start the development server
npm run dev
```

The frontend will run on `http://localhost:5173` (or port shown)

## Requirements

- Python 3
- Node.js and npm
- AWS account with Bedrock access
- Google OAuth credentials for Calendar API


