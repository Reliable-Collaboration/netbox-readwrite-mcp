"""Inject a real second HTTP writer at NetBox's post-commit response-query boundary."""

import json
import subprocess


def patch_with_intervening_writer(path, data, etag, agent_token, admin_token, newer):
    payload = {
        "path": "/api/" + path,
        "data": data,
        "etag": etag,
        "agent_token": agent_token,
        "admin_token": admin_token,
        "newer": newer,
    }
    program = (
        "payload="
        + repr(payload)
        + "\n"
        + """
import json
from urllib.request import Request,urlopen
from django.test import Client
from dcim.api.views import DeviceViewSet
original_update=DeviceViewSet.perform_update
def intervening_update(self,serializer):
    original_update(self,serializer)
    req=Request('http://127.0.0.1:8080'+payload['path'],
                data=json.dumps({'description':payload['newer']}).encode(),method='PATCH',
                headers={'Authorization':'Token '+payload['admin_token'],'Content-Type':'application/json'})
    with urlopen(req) as response:
        assert response.status==200
DeviceViewSet.perform_update=intervening_update
response=Client().patch(payload['path'],data=json.dumps(payload['data']),content_type='application/json',
    HTTP_AUTHORIZATION='Token '+payload['agent_token'],HTTP_IF_MATCH=payload['etag'])
result={'status':response.status_code,'body':json.loads(response.content),
        'headers':{k.lower():v for k,v in response.items() if k.lower() in ('etag','x-request-id','api-version')}}
print('RACE_RESULT:'+json.dumps(result))
"""
    )
    result = subprocess.run(
        [
            "podman",
            "exec",
            "-i",
            "nbrw-audit-netbox",
            "/opt/netbox/venv/bin/python",
            "/opt/netbox/netbox/manage.py",
            "shell",
        ],
        input=program,
        text=True,
        capture_output=True,
        check=True,
        timeout=60,
    )
    return json.loads(
        next(
            line.split("RACE_RESULT:", 1)[1]
            for line in result.stdout.splitlines()
            if line.startswith("RACE_RESULT:")
        )
    )
