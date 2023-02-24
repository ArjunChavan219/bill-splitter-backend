import os
from dotenv import load_dotenv

load_dotenv()

LOCAL_IP = os.getenv('LOCAL_IP')
KEY_FILE = os.getenv('KEY_FILE')
CERT_FILE = os.getenv('CERT_FILE')
CHAIN_FILE = os.getenv('CHAIN_FILE')

bind = LOCAL_IP
workers = 1

keyfile = KEY_FILE
certfile = CERT_FILE
ca_certs = CHAIN_FILE
