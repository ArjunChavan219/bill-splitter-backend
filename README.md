# bill-splitter
This is the backend code in Python (Flask) for the Bill Splitter Website
<br><br>

## Setup
```bash
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
```

<br>

## Deployment
```bash
source venv/bin/activate
gunicorn server:app
```