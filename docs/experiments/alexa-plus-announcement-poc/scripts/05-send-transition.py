#!/usr/bin/env python3
"""Send the washer Running -> Done transition to the Alexa event gateway.

Prerequisites: the skill is enabled and linked on your Alexa account (the
AcceptGrant flow ran), so the Lambda logged an LWA_EXCHANGE line containing
a refresh_token.

Fetch the refresh token from CloudWatch:
  aws logs filter-log-events --region eu-west-1 \\
      --log-group-name /aws/lambda/washer-poc \\
      --filter-pattern 'LWA_EXCHANGE 200' --start-time 0 \\
      | grep -o '"refresh_token":"[^"]*"' | tail -1

Env: REFRESH_TOKEN, PERMISSIONS_CLIENT_ID, PERMISSIONS_CLIENT_SECRET,
     ENDPOINT_ID (default lavatrice-prova-001), INSTANCE (default Wash.Cycle),
     GATEWAY (default https://api.eu.amazonalexa.com)
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone


def token():
    body = '&'.join(f'{k}={v}' for k, v in {
        'grant_type': 'refresh_token',
        'refresh_token': os.environ['REFRESH_TOKEN'],
        'client_id': os.environ['PERMISSIONS_CLIENT_ID'],
        'client_secret': os.environ['PERMISSIONS_CLIENT_SECRET'],
    }.items())
    req = urllib.request.Request('https://api.amazon.com/auth/O2/token',
                                 data=body.encode(),
                                 headers={'Content-Type': 'application/x-www-form-urlencoded'})
    return json.loads(urllib.request.urlopen(req, timeout=20).read())['access_token']


def send_change(access, value):
    now = datetime.now(timezone.utc).isoformat()
    prop = {'namespace': 'Alexa.ModeController', 'instance': os.environ.get('INSTANCE', 'Wash.Cycle'),
            'name': 'mode', 'value': value, 'timeOfSample': now, 'uncertaintyInMilliseconds': 0}
    payload = {
        'context': {'properties': [
            {'namespace': 'Alexa.EndpointHealth', 'name': 'connectivity', 'value': {'state': 'OK'},
             'timeOfSample': now, 'uncertaintyInMilliseconds': 0}]},
        'event': {
            'header': {'namespace': 'Alexa', 'name': 'ChangeReport', 'payloadVersion': '3',
                       'messageId': str(uuid.uuid4())},
            'payload': {'change': {'cause': {'type': 'PHYSICAL_INTERACTION'}, 'properties': [prop]}},
            'endpoint': {'scope': {'type': 'BearerToken', 'token': access},
                         'endpointId': os.environ.get('ENDPOINT_ID', 'lavatrice-prova-001')},
        },
    }
    req = urllib.request.Request(os.environ.get('GATEWAY', 'https://api.eu.amazonalexa.com') + '/v3/events',
                                 data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json',
                                          'Authorization': 'Bearer ' + access})
    try:
        r = urllib.request.urlopen(req, timeout=20)
        print(f'{datetime.now().strftime("%H:%M:%S")} {value} -> HTTP {r.status}')
    except urllib.error.HTTPError as e:
        print(f'{value} -> HTTP {e.code}: {e.read().decode()[:200]}')
        sys.exit(1)


if __name__ == '__main__':
    access = token()
    running = os.environ.get('RUNNING_VALUE', 'Wash.Cycle.Running')
    done = os.environ.get('DONE_VALUE', 'Wash.Cycle.Done')
    send_change(access, running)
    time.sleep(10)
    send_change(access, done)
