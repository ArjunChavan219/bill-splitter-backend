# bill-splitter
This is the backend code in Python (Flask) for the Bill Splitter Website
<br><br>

## Setup
```bash
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
```

Install psycopg2 separately:
```bash
export PATH=/Library/PostgreSQL/15/bin:$PATH 
```

<br>

## Database setup
- Create a folder /Database
- Populate with JSON files for users, bills and user groups (from MongoDb)
- Run the following script to generate csv and create PostgreSQL database
```bash
python db_setup.py
```

<br>

## Deployment
```bash
source venv/bin/activate
gunicorn server:app
```