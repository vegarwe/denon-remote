#!/bin/sh

### BEGIN INIT INFO
# Provides:             denon_avr
# Required-Start:
# Required-Stop:
# Default-Start:        2 3 4 5
# Default-Stop:
# Short-Description:    Denon remote control HTTP daemon
### END INIT INFO

# To install: sudo update-rc.d denon_avr.sh defaults

set -e

. /lib/lsb/init-functions

case "$1" in
  start)
    python3 /home/vegarwe/devel/denon_avr/server.py &
    ;;
  status)
    pid=`pgrep -f 'python3 /home/vegarwe/devel/denon_avr/server.py'` || true
    if [ -z "$pid" ]; then
        echo "Not running"
    elif kill -0 "$pid"; then
        echo "true"
    else
        echo "false"
    fi
    ;;
  stop)
    echo "killing `pgrep -f 'python3 /home/vegarwe/devel/denon_avr/server.py'`"
    pkill -f 'python3 /home/vegarwe/devel/denon_avr/server.py'
    ;;
  *)
    log_action_msg "Usage: /etc/init.d/ssh_tunnel {start|stop|status}" || true
    exit 1
esac

exit 0

