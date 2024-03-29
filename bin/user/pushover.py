#
#    Copyright (c) 2023 Rich Bell <bellrichm@gmail.com>
#
#    See the file LICENSE.txt for your full rights.
#
'''
Monitor that observation values are within a defined range.
If a value is out of range, send a notification via pushover.net
See, https://pushover.net

Configuration:
[Pushover]
    
    # Whether the service is enabled or not.
    # Valid values: True or False
    # Default is True.
    # enable = True

    # The server to send the pushover request to.
    # Default is api.pushover.net:443.
    # server = api.pushover.net:443

    # The endpoint/API to use.
    # Default is /1/messages.json.
    # api = /1/messages.json

    app_token = REPLACE_ME
    user_key = REPLACE_ME

    client_error_log_frequency = 3600
    server_error_wait_period = 3600

    # The set of WeeWX observations to monitor.
    # Each subsection is the name of WeeWX observation.
    # For example, outTemp, inTemp, txBatteryStatus, etc
    [[observations]]
        [[[REPLACE_ME]]]
            # A Descriptive name of this observation
            # Default is the WeeWX name.
            #name = 


            # The time in seconds to wait before sending another notification.
            # This is used to throttle the number of notifications.
            # The default is 3600 seconds.
            #wait_time = 3600

            # The number of times the minimum needs to be reached before sending a notification.
            # The default is 10.
            #min_count = 10

            # The minimum value to monitor.
            #min = REPLACE_ME

            # The number of times the minimum needs to be reached before sending a notification.
            # The default is 10.
            #max_count = 10

            The maximum value to monitor.
            #max =  REPLACE_ME
'''

import argparse
import http.client
import json
import logging
import os
import time
import urllib
from concurrent.futures import ThreadPoolExecutor

import configobj

import weewx
from weewx.engine import StdService
from weeutil.weeutil import to_bool, to_int

log = logging.getLogger(__name__)

class Pushover(StdService):
    """ Manage sending Pushover notifications."""
    def __init__(self, engine, config_dict):
        """Initialize an instance of Pushover"""
        super().__init__(engine, config_dict)

        service_dict = config_dict.get('Pushover', {})

        enable = to_bool(service_dict.get('enable', True))
        if not enable:
            log.info("Pushover is not enabled, exiting")
            return

        self.user_key = service_dict.get('user_key', None)
        self.app_token = service_dict.get('app_token', None)
        self.server = service_dict.get('server', 'api.pushover.net:443')
        self.api = service_dict.get('api', '/1/messages.json')

        self.client_error_log_frequency = to_int(service_dict.get('client_error_log_frequency', 3600))
        self.server_error_wait_period = to_int(service_dict.get('server_error_wait_period', 3600))

        binding = service_dict.get('binding', 'loop')
        count = to_int(service_dict.get('count', 10))
        wait_time = to_int(service_dict.get('wait_time', 3600))

        self.loop_observations = {}
        self.archive_observation = {}

        for observation in service_dict['observations']:
            observation_binding = service_dict['observations'][observation].get('binding', binding)
            if observation_binding == 'loop':
                self.loop_observations[observation] = self.init_observation(service_dict['observations'][observation], observation, count, wait_time)
            if observation_binding == 'archive':
                self.archive_observations[observation] = self.init_observation(service_dict['observations'][observation], observation, count, wait_time)
            # ToDo: - error if unknown observation

        self.client_error_timestamp = 0
        self.client_error_last_logged = 0
        self.server_error_timestamp = 0

        self.executor = ThreadPoolExecutor(max_workers=5)

        self.bind(weewx.NEW_ARCHIVE_RECORD, self.new_archive_record)
        self.bind(weewx.NEW_LOOP_PACKET, self.new_loop_packet)

    def init_observation(self, config, observation_name, count, wait_time):
        observation = {}
        observation['name'] = config.get('name', observation_name)
        observation['weewx_name'] = config.get('weewx_name', observation_name)

        observation['min'] = {}
        min_value = config.get('min', None)
        if min_value:
            observation['min']['value'] = to_int(min_value)
            observation['min']['count'] = to_int(config.get('min_count', count))
            observation['min']['wait_time'] = to_int(config.get('min_wait_time', wait_time))
            observation['min']['last_sent_timestamp'] = 0
            observation['min']['counter'] = 0

        observation['max'] = {}
        max_value = config.get('max', None)
        if max_value:
            observation['max']['value'] = to_int(max_value)
            observation['max']['count'] = to_int(config.get('max_count', count))
            observation['max']['wait_time'] = to_int(config.get('max_wait_time', wait_time))
            observation['max']['last_sent_timestamp'] = 0
            observation['max']['counter'] = 0

        observation['equal'] = {}
        equal_value = config.get('equal', None)
        if equal_value:
            observation['equal']['value'] = to_int(equal_value)
            observation['equal']['count'] = to_int(config.get('equal_count', count))
            observation['equal']['wait_time'] = to_int(config.get('equal_wait_time', wait_time))
            observation['equal']['last_sent_timestamp'] = 0
            observation['equal']['counter'] = 0

        return observation         
  
    def _push_notification(self, observation_detail, title, msgs):
        msg = ''
        for _, value in msgs.items():
            if value:
                msg += value
        connection = http.client.HTTPSConnection(f"{self.server}")
        connection.request("POST",
                           f"{self.api}",
                           urllib.parse.urlencode({
                               "token": self.app_token,
                               "user": self.user_key,
                               "message": msg,
                               "title": title,                               
                               }),
                            { "Content-type": "application/x-www-form-urlencoded" })
        response = connection.getresponse()
        now = time.time()

        if response.code == 200:
            for key, value in msgs.items():
                if value:
                    observation_detail[key]['last_sent_timestamp'] = now

        else:
            log.error("Received code %s", response.code)
            if response.code >= 400 and response.code < 500:
                self.client_error_timestamp = now
                self.client_error_last_logged = now
            if response.code >= 500 and response.code < 600:
                self.server_error_timestamp = now
            response_body = response.read().decode()
            try:
                response_dict = json.loads(response_body)
                log.error('\n'.join(response_dict['errors']))
            except json.JSONDecodeError as exception:
                log.error("Unable to parse %s.", exception.doc)
                log.error("Error at %s, line: %s column: %s",
                          exception.pos, exception.lineno, exception.colno)

    def _check_min_value(self, name, observation_detail, value):
        msg = ''
        if value < observation_detail['value']:
            observation_detail['counter'] += 1
            if observation_detail['counter'] >= observation_detail['count']:
                if abs(time.time() - observation_detail['last_sent_timestamp']) >= observation_detail['wait_time']:
                    msg = f"{name} value {value} is less than {observation_detail['value']}.\n"
        else:
            observation_detail['counter'] = 0

        return msg

    def _check_max_value(self, name, observation_detail, value):
        msg = ''
        if value > observation_detail['value']:
            observation_detail['counter'] += 1
            if observation_detail['counter'] >= observation_detail['count']:
                if abs(time.time() - observation_detail['last_sent_timestamp']) >= observation_detail['wait_time']:
                    msg = f"{name} value {value} is greater than {observation_detail['value']}.\n"
        else:
            observation_detail['counter'] = 0

        return msg

    def _check_equal_value(self, name, observation_detail, value):
        msg = ''
        if value != observation_detail['value']:
            observation_detail['counter'] += 1
            if observation_detail['counter'] >= observation_detail['count']:
                if abs(time.time() - observation_detail['last_sent_timestamp']) >= observation_detail['wait_time']:
                    msg += f"{name} value {value} is not equal {observation_detail['value']}.\n"
        else:
            observation_detail['counter'] = 0

        return msg

    def _process_data(self, data, observations):   
        msgs = {}
        for obs, observation_detail in observations.items():
            observation = observation_detail['weewx_name']
            title = None

            if observation in data and data[observation]:
                if observation_detail['min']:
                    msgs['min'] = self._check_min_value(observation_detail['name'], observation_detail['min'], data[observation])
                    if msgs['min']:
                        title = f"Unexpected value for {observation}."
                if observation_detail['max']:
                    msgs['max'] = self._check_max_value(observation_detail['name'], observation_detail['max'], data[observation])
                    if msgs['max']:
                        title = f"Unexpected value for {observation}."
                if observation_detail['equal']:
                    msgs['equal'] = self._check_equal_value(observation_detail['name'], observation_detail['equal'], data[observation])
                    if msgs['equal']:
                        title = f"Unexpected value for {observation}."

                if title:
                    #self.executor.submit(self._push_notification, event.packet)
                    self._push_notification(observation_detail, title, msgs)

    def new_archive_record(self, event):
        """ Handle the new archive record event. """
        if self.client_error_timestamp:
            if abs(time.time() - self.client_error_last_logged) < self.client_error_log_frequency:
                log.error("Fatal error occurred at %s, Pushover skipped.", self.client_error_timestamp)
                self.client_error_last_logged = time.time()
                return

        if abs(time.time() - self.server_error_timestamp) < self.server_error_wait_period:
            log.debug("Server error received at %s, waiting %s seconds before retrying.",
                      self.server_error_timestamp,
                      self.server_error_wait_period)
            return
        self.server_error_timestamp = 0
        
        self._process_data(event.record, self.archive_observation)

    def new_loop_packet(self, event):
        """ Handle the new loop packet event. """
        if self.client_error_timestamp:
            if abs(time.time() - self.client_error_last_logged) < self.client_error_log_frequency:
                log.error("Fatal error occurred at %s, Pushover skipped.", self.client_error_timestamp)
                self.client_error_last_logged = time.time()
                return

        if abs(time.time() - self.server_error_timestamp) < self.server_error_wait_period:
            log.debug("Server error received at %s, waiting %s seconds before retrying.",
                      self.server_error_timestamp,
                      self.server_error_wait_period)
            return
        self.server_error_timestamp = 0
        
        self._process_data(event.packet, self.loop_observations)

    def shutDown(self): # need to override parent - pylint: disable=invalid-name
        """Run when an engine shutdown is requested."""
        self.executor.shutdown(wait=False)

def main():
    """ The main routine. """
    min_config_dict = {
        'Station': {
            'altitude': [0, 'foot'],
            'latitude': 0,
            'station_type': 'Simulator',
            'longitude': 0
        },
        'Simulator': {
            'driver': 'weewx.drivers.simulator',
        },
        'Engine': {
            'Services': {}
        }
    }

    parser = argparse.ArgumentParser()
    parser.add_argument("--conf",
                        required=True,
                        help="The WeeWX configuration file. Typically weewx.conf.")
    options = parser.parse_args()


    config_path = os.path.abspath(options.conf)
    config_dict = configobj.ConfigObj(config_path, file_error=True)

    engine = weewx.engine.DummyEngine(min_config_dict)

    packet = {'dateTime': int(time.time()),
              'extraTemp6': 6,
            }

    pushover = Pushover(engine, config_dict)

    event = weewx.Event(weewx.NEW_LOOP_PACKET, packet=packet)

    pushover.new_loop_packet(event)

    #pushover.new_loop_packet(event)

    pushover.shutDown()

if __name__ == '__main__':
    main()
