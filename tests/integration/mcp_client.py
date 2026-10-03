import json
import queue
import subprocess
import threading


class Client:
    def __init__(self, command):
        self.process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )
        self.responses = queue.Queue()
        self.errors = []
        self.seq = 0
        self.transcript = []

        def reader():
            for line in self.process.stdout:
                self.responses.put(json.loads(line))
            self.responses.put({"eof": True})

        def stderr():
            for line in self.process.stderr:
                self.errors.append(line)

        threading.Thread(target=reader, daemon=True).start()
        threading.Thread(target=stderr, daemon=True).start()
        self.rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "direct-spike-tests", "version": "1"},
            },
        )
        self.process.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        self.process.stdin.flush()

    def rpc(self, method, params=None):
        self.seq += 1
        request = {"jsonrpc": "2.0", "id": self.seq, "method": method, "params": params or {}}
        self.process.stdin.write(json.dumps(request) + "\n")
        self.process.stdin.flush()
        while True:
            response = self.responses.get(timeout=90)
            if response.get("eof"):
                raise RuntimeError("Server exited: " + "".join(self.errors))
            if response.get("id") == self.seq:
                self.transcript.append({"request": request, "response": response})
                return response

    def tool(self, name, **args):
        response = self.rpc("tools/call", {"name": name, "arguments": args})
        return response["result"]["structuredContent"]

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=10)
