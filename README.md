# weewx-pushover

This repository has a new home at, https://github.com/weewx-extensions/pushover/


A WeeWX extension that sends alerts via [Pushover](https://pushover.net).

## Installation and configuring `weewx-pushover`

After installing `weewx-pushover`, edit the `Pushover` in `weewx.conf` as needed.

```text
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
    
    # Pushover returns a status code in the range of 400 to 499 when the http request is bad.
    # In this case, WeeWX-Pushover will stop sending requests.
    # (On the assumption that all future requests will have the same error.)
    # An error will be logged every 'client_error_log_frequency' seconds.
    # The default is 3600 seconds.
    # client_error_log_frequency = 3600

    # Pushover returns a status code in the range of 500 to 599 when something went wrong on the server.
    # In this case WeeWX-Pushover will wait 'server_error_wait_period' before resuming sending requests.
    # (On the assumption that the server needs some time to be fixed.)
    # The default is 3600 seconds.
    # server_error_wait_period = 3600
    
    # The time to wait before sending another notification.
    # The default is 3600 seconds.
    # wait_time = 3600

    # Whether to monitor the loop or archive data.
    # With two sections [[loop]] and [[archive]], both loop and archive data can be monitored.
    [[loop or archive]]
        # The set of WeeWX observations to monitor.
        # Each subsection is the name of WeeWX observation.
        # For example, outTemp, inTemp, txBatteryStatus, etc
        # The section name can be anything. If possible, it is recommended to use the WeeWX name.
        [[[REPLACE_ME]]]
            # The WeeWX name (outTemp, inTemp, etc.)
            # If this section 'REPLACE_ME is the WeeWX name, this is not needed.
            #name = 

            # A Descriptive name of this observation (Outside Temperature, Inside Temperature, etc.)
            label = 
            
            # All three sections can be specified for a given WeeWX observation.
            # This allows one to monitor when values go below, above, or are no longer equal to a value.
            [[[[ min or max or equal]]]]
                # The time in seconds to wait before sending another notification.
                # This is used to throttle the number of notifications.
                # The default is 3600 seconds.
                #wait_time = 3600

                # The number of times the threshold needs to be reached before sending a notification.
                # The default is 10.
                #count = 10

                # The value to monitor.
                #value = REPLACE_ME
```
