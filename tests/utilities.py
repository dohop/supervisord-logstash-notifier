#
# Copyright 2016 Dohop hf.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Test utilities
"""

import json
import os
import subprocess
import threading

from time import sleep
from unittest import TestCase
from testfixtures import TempDirectory
from six.moves import socketserver


class LogstashHandler(socketserver.BaseRequestHandler):
    """
    Save received messages.
    """
    messages = []

    def handle(self):
        self.messages.append(self.request[0].strip().decode())


class BaseSupervisorTestCase(TestCase):
    """
    Base class for running supervisor tests
    """
    maxDiff = None

    def __init__(self, *args, **kwargs):
        super(BaseSupervisorTestCase, self).__init__(*args, **kwargs)
        self.supervisor = None
        self.logstash = None

    def setUp(self):
        self.scratch = TempDirectory()

    def tearDown(self):
        self.scratch.cleanup()

    def run_supervisor(self, overrides, configuration_string):
        """
        Runs Supervisor
        """
        environment = os.environ.copy()
        environment.update(overrides)

        working_directory = os.path.dirname(__file__)

        template_path = os.path.join(working_directory, 'supervisord.template')
        with open(template_path) as template:
            configuration = template.read()
            configuration += configuration_string
            self.scratch.write('supervisor.conf', configuration, 'utf-8')

        self.supervisor = subprocess.Popen(
            ['supervisord', '-c', self.scratch.getpath('supervisor.conf')],
            env=environment,
            cwd=os.path.dirname(working_directory),
        )

    def shutdown_supervisor(self):
        """
        Shuts Supervisor down
        """
        self.supervisor.terminate()
        while self.supervisor.poll() is None:
            # need to wait while the process kills off it's children and exits
            # so that it doesn't block the port
            sleep(1)

    def run_logstash(self):
        """
        Runs a socketserver instance emulating Logstash
        """
        self.logstash = socketserver.UDPServer(('0.0.0.0', 0), LogstashHandler)
        threading.Thread(target=self.logstash.serve_forever).start()
        return self.logstash

    def shutdown_logstash(self):
        """
        Shuts the socketserver instance down
        """
        self.logstash.shutdown()
        self.logstash.server_close()

    def messages(self, clear_buffer=False, wait_for=None):
        """
        Returns the contents of the logstash message buffer
        """
        messages = []
        if wait_for is not None:
            while len(messages) < wait_for:
                sleep(0.1)
                messages = self.logstash.RequestHandlerClass.messages[:]
        else:
            messages = self.logstash.RequestHandlerClass.messages[:]

        parsed_messages = list(map(strip_volatile, messages))
        if clear_buffer:
            self.clear_message_buffer()

        return parsed_messages

    def clear_message_buffer(self):
        """
        Clears the logstash message buffer
        """
        self.logstash.RequestHandlerClass.messages = []


def strip_volatile(message):
    """
    Strip volatile parts (PID, datetime, host) from a logging message.
    """
    volatile = [
        '@timestamp',
        'host',
        'pid',
        'tries',
        'stack_info'
    ]
    message_dict = json.loads(message)
    for key in volatile:
        if key in message_dict:
            message_dict.pop(key)

    return message_dict


def record(eventname, from_state):
    """
    Returns a pre-formatted log line to save on the boilerplate
    """
    return {
        '@version': '1',
        'eventname': eventname,
        'from_state': from_state,
        'groupname': 'messages',
        'level': 'INFO',
        'logger_name': 'supervisor',
        'message': '%s messages' % eventname,
        'path': './logstash_notifier/__init__.py',
        'processname': 'messages',
        'tags': [],
        'type': 'logstash'
    }