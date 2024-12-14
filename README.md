# PlayMoreTCG

A web application for generating and managing trading card game cards using AI. This project combines FastAPI, OpenAI, Firebase Authentication, and Backblaze B2 for storage to create a powerful card generation and management system.

## Features

- AI-powered card generation
- User authentication via Firebase
- Card storage and management
- Pack opening simulation
- Card exploration and listing
- Responsive web interface

## Tech Stack

- **Backend**: FastAPI (Python)
- **Template Engine**: Jinja2
- **Database**: SQLAlchemy
- **Authentication**: Firebase Admin
- **Storage**: Backblaze B2
- **AI Integration**: OpenAI
- **Other Tools**: Python-Multipart, Python-Dotenv, Tenacity

## Prerequisites

Before you begin, ensure you have:
- Python 3.7+
- A Firebase project with authentication enabled
- A Backblaze B2 account
- An OpenAI API key

## Installation

1. Clone the repository:
```bash
git clone git@github.com:CardSorting/playmoretcg.git
cd playmoretcg
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows use: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up environment variables in `.env`:
```env
# OpenAI Configuration
OPENAI_API_KEY=your_openai_api_key

# Firebase Configuration
FIREBASE_PROJECT_ID=your_project_id

# Backblaze Configuration
B2_KEY_ID=your_b2_key_id
B2_APPLICATION_KEY=your_b2_app_key
B2_BUCKET_NAME=your_bucket_name
```

5. Place your Firebase service account key in:
```
cred/playmoretcg-[your-project]-firebase-adminsdk-[hash].json
```

## Project Structure

```
├── main.py                 # FastAPI application entry point
├── models.py              # Database models
├── database.py           # Database configuration
├── card_generator.py     # AI card generation logic
├── requirements.txt      # Project dependencies
├── static/              # Static files
│   └── card_images/     # Generated card images
├── templates/           # Jinja2 templates
│   ├── auth/           # Authentication templates
│   ├── cards/          # Card-related templates
│   ├── legal/          # Legal documents
│   └── base.html       # Base template
└── cred/               # Credentials directory
```

## Running the Application

Start the development server:
```bash
uvicorn main:app --reload
```

The application will be available at `http://localhost:8000`

## Configuration Files

### Firebase Configuration
Create `firebase_config.py` with your Firebase project configuration:
```python
FIREBASE_CONFIG = {
    "apiKey": "your-api-key",
    "authDomain": "your-project.firebaseapp.com",
    "projectId": "your-project-id",
    "storageBucket": "your-project.appspot.com",
    "messagingSenderId": "your-messaging-sender-id",
    "appId": "your-app-id"
}
```

### Backblaze Configuration
Update `backblaze_config.py` with your Backblaze B2 credentials:
```python
B2_KEY_ID = "your-key-id"
B2_APPLICATION_KEY = "your-application-key"
B2_BUCKET_NAME = "your-bucket-name"
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is proprietary and confidential. All rights reserved.