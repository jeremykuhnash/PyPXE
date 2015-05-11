#!/usr/bin/env python
import threading
import os
import sys
import json
import logging
import logging.handlers

try:
    import argparse
except ImportError:
    sys.exit("ImportError: You do not have the Python 'argparse' module installed. Please install the 'argparse' module and try again.")

from time import sleep
from pypxe import tftp # PyPXE TFTP service
from pypxe import dhcp # PyPXE DHCP service
from pypxe import http # PyPXE HTTP service

# default settings
SETTINGS = {'NETBOOT_DIR':'netboot',
            'NETBOOT_FILE':'',
            'DHCP_SERVER_IP':'192.168.2.2',
            'DHCP_SERVER_PORT':67,
            'DHCP_OFFER_BEGIN':'192.168.2.100',
            'DHCP_OFFER_END':'192.168.2.150',
            'DHCP_SUBNET':'255.255.255.0',
            'DHCP_DNS':'8.8.8.8',
            'DHCP_ROUTER':'192.168.2.1',
            'DHCP_BROADCAST':'<broadcast>',
            'DHCP_FILESERVER':'192.168.2.2',
            'SYSLOG_SERVER':None,
            'SYSLOG_PORT':514,
            'USE_IPXE':False,
            'USE_HTTP':False,
            'USE_TFTP':True,
            'USE_DHCP':True,
            'DHCP_MODE_PROXY':False,
            'MODE_DEBUG':''}

def parse_cli_arguments():
    # main service arguments
    parser = argparse.ArgumentParser(description = 'Set options at runtime. Defaults are in %(prog)s', formatter_class = argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--ipxe', action = 'store_true', dest = 'USE_IPXE', help = 'Enable iPXE ROM', default = SETTINGS['USE_IPXE'])
    parser.add_argument('--http', action = 'store_true', dest = 'USE_HTTP', help = 'Enable built-in HTTP server', default = SETTINGS['USE_HTTP'])
    parser.add_argument('--no-tftp', action = 'store_false', dest = 'USE_TFTP', help = 'Disable built-in TFTP server, by default it is enabled', default = SETTINGS['USE_TFTP'])
    parser.add_argument('--debug', action = 'store', dest = 'MODE_DEBUG', help = 'Comma Seperated (http,tftp,dhcp). Adds verbosity to the selected services while they run. Use \'all\' for enabling debug on all services', default = SETTINGS['MODE_DEBUG'])
    parser.add_argument('--config', action = 'store', dest = 'JSON_CONFIG', help = 'Configure from a JSON file rather than the command line', default = '')
    parser.add_argument('--syslog', action = 'store', dest = 'SYSLOG_SERVER', help = 'Syslog server', default = SETTINGS['SYSLOG_SERVER'])
    parser.add_argument('--syslog-port', action = 'store', dest = 'SYSLOG_PORT', help = 'Syslog server port', default = SETTINGS['SYSLOG_PORT'])

    # DHCP server arguments
    exclusive = parser.add_mutually_exclusive_group(required = False)
    exclusive.add_argument('--dhcp', action = 'store_true', dest = 'USE_DHCP', help = 'Enable built-in DHCP server', default = SETTINGS['USE_DHCP'])
    exclusive.add_argument('--dhcp-proxy', action = 'store_true', dest = 'DHCP_MODE_PROXY', help = 'Enable built-in DHCP server in proxy mode (implies --dhcp)', default = SETTINGS['DHCP_MODE_PROXY'])
    parser.add_argument('-s', '--dhcp-server-ip', action = 'store', dest = 'DHCP_SERVER_IP', help = 'DHCP Server IP', default = SETTINGS['DHCP_SERVER_IP'])
    parser.add_argument('-p', '--dhcp-server-port', action = 'store', dest = 'DHCP_SERVER_PORT', help = 'DHCP Server Port', default = SETTINGS['DHCP_SERVER_PORT'])
    parser.add_argument('-b', '--dhcp-begin', action = 'store', dest = 'DHCP_OFFER_BEGIN', help = 'DHCP lease range start', default = SETTINGS['DHCP_OFFER_BEGIN'])
    parser.add_argument('-e', '--dhcp-end', action = 'store', dest = 'DHCP_OFFER_END', help = 'DHCP lease range end', default = SETTINGS['DHCP_OFFER_END'])
    parser.add_argument('-n', '--dhcp-subnet', action = 'store', dest = 'DHCP_SUBNET', help = 'DHCP lease subnet', default = SETTINGS['DHCP_SUBNET'])
    parser.add_argument('-r', '--dhcp-router', action = 'store', dest = 'DHCP_ROUTER', help = 'DHCP lease router', default = SETTINGS['DHCP_ROUTER'])
    parser.add_argument('-d', '--dhcp-dns', action = 'store', dest = 'DHCP_DNS', help = 'DHCP lease DNS server', default = SETTINGS['DHCP_DNS'])
    parser.add_argument('-c', '--dhcp-broadcast', action = 'store', dest = 'DHCP_BROADCAST', help = 'DHCP broadcast address', default = SETTINGS['DHCP_BROADCAST'])
    parser.add_argument('-f', '--dhcp-fileserver', action = 'store', dest = 'DHCP_FILESERVER', help = 'DHCP fileserver IP', default = SETTINGS['DHCP_FILESERVER'])

    # network boot directory and file name arguments
    parser.add_argument('-a', '--netboot-dir', action = 'store', dest = 'NETBOOT_DIR', help = 'Local file serve directory', default = SETTINGS['NETBOOT_DIR'])
    parser.add_argument('-i', '--netboot-file', action = 'store', dest = 'NETBOOT_FILE', help = 'PXE boot file name (after iPXE if --ipxe)', default = SETTINGS['NETBOOT_FILE'])

    return parser.parse_args()

if __name__ == '__main__':
    try:
        # warn the user that they are starting PyPXE as non-root user
        if os.getuid() != 0:
            print '\nWARNING: Not root. Servers will probably fail to bind.\n'

        # configure
        args = parse_cli_arguments()
        if args.JSON_CONFIG: # load from configuration file if specified
            try:
                config_file = open(args.JSON_CONFIG, 'rb')
            except IOError:
                sys.exit('Failed to open {0}'.format(args.JSON_CONFIG))
            try:
                loaded_config = json.load(config_file)
                config_file.close()
            except ValueError:
                sys.exit('{0} does not contain valid JSON'.format(args.JSON_CONFIG))
            for setting in loaded_config:
                if type(loaded_config[setting]) is unicode:
                    loaded_config[setting] = loaded_config[setting].encode('ascii')
            SETTINGS.update(loaded_config) # update settings with JSON config
            args = parse_cli_arguments() # re-parse, CLI options take precedence

        # setup main logger
        sys_logger = logging.getLogger('PyPXE')
        if args.SYSLOG_SERVER:
            handler = logging.handlers.SysLogHandler(address = (args.SYSLOG_SERVER, int(args.SYSLOG_PORT)))
        else:
            handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s %(message)s')
        handler.setFormatter(formatter)
        sys_logger.addHandler(handler)
        sys_logger.setLevel(logging.INFO)

        # pass warning to user regarding starting HTTP server without iPXE
        if args.USE_HTTP and not args.USE_IPXE and not args.USE_DHCP:
            sys_logger.warning('HTTP selected but iPXE disabled. PXE ROM must support HTTP requests.')

        # if the argument was pased to enabled ProxyDHCP then enable the DHCP server
        if args.DHCP_MODE_PROXY:
            args.USE_DHCP = True

        # if the network boot file name was not specified in the argument,
        # set it based on what services were enabled/disabled
        if args.NETBOOT_FILE == '':
            if not args.USE_IPXE:
                args.NETBOOT_FILE = 'pxelinux.0'
            elif not args.USE_HTTP:
                args.NETBOOT_FILE = 'boot.ipxe'
            else:
                args.NETBOOT_FILE = 'boot.http.ipxe'

        # serve all files from one directory
        os.chdir (args.NETBOOT_DIR)

        # make a list of running threads for each service
        running_services = []

        # configure/start TFTP server
        if args.USE_TFTP:

            # setup TFTP logger
            tftp_logger = sys_logger.getChild('TFTP')
            sys_logger.info('Starting TFTP server...')

            # setup the thread
            tftp_server = tftp.TFTPD(mode_debug = ('tftp' in args.MODE_DEBUG.lower() or 'all' in args.MODE_DEBUG.lower()), logger = tftp_logger)
            tftpd = threading.Thread(target = tftp_server.listen)
            tftpd.daemon = True
            tftpd.start()
            running_services.append(tftpd)

        # configure/start DHCP server
        if args.USE_DHCP:

            # setup DHCP logger
            dhcp_logger = sys_logger.getChild('DHCP')
            if args.DHCP_MODE_PROXY:
                sys_logger.info('Starting DHCP server in ProxyDHCP mode...')
            else:
                sys_logger.info('Starting DHCP server...')

            # setup the thread
            dhcp_server = dhcp.DHCPD(
                    ip = args.DHCP_SERVER_IP,
                    port = args.DHCP_SERVER_PORT,
                    offer_from = args.DHCP_OFFER_BEGIN,
                    offer_to = args.DHCP_OFFER_END,
                    subnet_mask = args.DHCP_SUBNET,
                    router = args.DHCP_ROUTER,
                    dns_server = args.DHCP_DNS,
                    broadcast = args.DHCP_BROADCAST,
                    file_server = args.DHCP_FILESERVER,
                    file_name = args.NETBOOT_FILE,
                    use_ipxe = args.USE_IPXE,
                    use_http = args.USE_HTTP,
                    mode_proxy = args.DHCP_MODE_PROXY,
                    mode_debug = ('dhcp' in args.MODE_DEBUG.lower() or 'all' in args.MODE_DEBUG.lower()),
                    logger = dhcp_logger)
            dhcpd = threading.Thread(target = dhcp_server.listen)
            dhcpd.daemon = True
            dhcpd.start()
            running_services.append(dhcpd)

        # configure/start HTTP server
        if args.USE_HTTP:

            # setup HTTP logger
            http_logger = sys_logger.getChild('HTTP')
            sys_logger.info('Starting HTTP server...')

            # setup the thread
            http_server = http.HTTPD(mode_debug = ('http' in args.MODE_DEBUG.lower() or 'all' in args.MODE_DEBUG.lower()), logger = http_logger)
            httpd = threading.Thread(target = http_server.listen)
            httpd.daemon = True
            httpd.start()
            running_services.append(httpd)

        sys_logger.info('PyPXE successfully initialized and running!')

        while map(lambda x: x.isAlive(), running_services):
            sleep(1)

    except KeyboardInterrupt:
        sys.exit('\nShutting down PyPXE...\n')
