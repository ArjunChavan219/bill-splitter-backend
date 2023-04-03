import os
from dotenv import load_dotenv

load_dotenv()

LOCAL_IP = os.getenv('LOCAL_IP')

bind = LOCAL_IP
workers = 10
