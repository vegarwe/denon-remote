#!/bin/sh

### BEGIN INIT INFO
# Provides:             ssh_tunnel
# Required-Start:       $sshd
# Required-Stop:
# Default-Start:        2 3 4 5
# Default-Stop:
# Short-Description:    Simple SSH tunnel daemon
### END INIT INFO

# To install: sudo update-rc.d denon_avr.sh defaults

set -e

. /lib/lsb/init-functions

case "$1" in
  start)
    python /home/vegarwe/devel/denon_avr/server.py &
    ;;
  status)
    pid=`pgrep -f 'python /home/vegarwe/devel/denon_avr/server.py'` || true
    if [ -z "$pid" ]; then
        echo "Not running"
    elif kill -0 "$pid"; then
        echo "true"
    else
        echo "false"
    fi
    ;;
  stop)
    echo "killing `pgrep -f 'python /home/vegarwe/devel/denon_avr/server.py'`"
    pkill -f 'python /home/vegarwe/devel/denon_avr/server.py'
    ;;
  *)
    log_action_msg "Usage: /etc/init.d/ssh_tunnel {start|stop|status}" || true
    exit 1
esac

exit 0

