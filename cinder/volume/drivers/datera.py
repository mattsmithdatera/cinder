# Copyright 2015 Datera
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import json
from functools import wraps

from oslo.config import cfg
from oslo.utils import excutils
import requests

from cinder import exception
from cinder.i18n import _, _LI, _LE
from cinder.openstack.common import log as logging
from cinder.openstack.common import units
from cinder.volume.drivers.san import san

LOG = logging.getLogger(__name__)

d_opts = [
    cfg.StrOpt('datera_api_token',
               default=None,
               help='Datera API token.'),
    cfg.StrOpt('datera_api_port',
               default='7717',
               help='Datera API port.'),
    cfg.StrOpt('datera_api_version',
               default='2',
               help='Datera API version.'),
    cfg.StrOpt('datera_num_replicas',
               default='3',
               help='Number of replicas to create of an inode.')
]


CONF = cfg.CONF
CONF.import_opt('driver_client_cert_key', 'cinder.volume.driver')
CONF.import_opt('driver_client_cert', 'cinder.volume.driver')
CONF.register_opts(d_opts)

DEFAULT_STORAGE_NAME = 'storage-1'
DEFAULT_VOLUME_NAME = 'volume-1'


def _authenticated(func):
    """Ensure the driver is authenticated to make a request.

    In do_setup() we fetch an auth token and store it. If that expires when
    we do API request, we'll fetch a new one.
    """
    @wraps(func)
    def func_wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except exception.NotAuthorized:
            # Prevent recursion loop. After the self arg is the
            # resource_type arg from _issue_api_request(). If attempt to
            # login failed, we should just give up.
            if args[0] == 'login':
                raise

            # Token might've expired, get a new one, try again.
            self._login()
            return func(self, *args, **kwargs)
    return func_wrapper


class DateraDriver(san.SanISCSIDriver):

    """The OpenStack Datera Driver

    Version history:
        1.0 - Initial driver
        1.2 - Updated API v1 Driver
        2.0 - API v2 Driver
    """
    VERSION = '2.0'

    def __init__(self, *args, **kwargs):
        super(DateraDriver, self).__init__(*args, **kwargs)
        self.configuration.append_config_values(d_opts)
        self.num_replicas = self.configuration.datera_num_replicas
        self.cluster_stats = {}

    def _get_lunid(self):
        return 0

    def _login(self):
        """Use the san_login and san_password to set self.auth_token."""
        body = {
            'name': self.configuration.san_login,
            'password': self.configuration.san_password
        }

        # Unset token now, otherwise potential expired token will be sent
        # along to be used for authorization when trying to login.
        self.auth_token = None

        try:
            LOG.debug('Getting Datera auth token.')
            results = self._issue_api_request('login', 'put', body=body)

            self.configuration.datera_api_token = results['key']
        except exception.NotAuthorized:
            with excutils.save_and_reraise_exception():
                LOG.error(_LE('Logging into the Datera cluster failed. Please '
                              'check your username and password set in the '
                              'cinder.conf and start the cinder-volume'
                              'service again.'))

    def create_volume(self, volume):
        """Create a logical volume."""
        # Generate App Instance, Storage Instance and Volume

        app_params = \
            {
                'create_mode': "openstack",
                'uuid': str(volume['id']),
                'name': str(volume['id']),
                'storage_instances': [
                    {
                        'name': DEFAULT_STORAGE_NAME,
                        'volumes': {
                            DEFAULT_VOLUME_NAME: {
                                'name': DEFAULT_VOLUME_NAME,
                                'size': volume['size'],
                                'replica_count': int(self.num_replicas),
                                'snapshot_policies': {
                                }
                            }
                        }
                    }
                ]
            }
        self._issue_api_request('app_instances', method='post',
                                body=app_params)

    def extend_volume(self, volume, new_size):
        # Offline App Instance, if necessary
        reonline = False
        app_inst = self._issue_api_request(
            "app_instances/{}".format(volume['id']))
        if app_inst['admin_state'] == 'online':
            reonline = True
            self.detach_volume(None, volume)
        # Change Volume Size
        app_inst = volume['id']
        storage_inst = DEFAULT_STORAGE_NAME
        data = {
            'size': new_size
        }
        self._issue_api_request(
            'app_instances/{}/storage_instances/{}/volumes/{}'.format(
                app_inst, storage_inst, DEFAULT_VOLUME_NAME),
            method='put', body=data)
        # Online Volume, if it was online before
        if reonline:
            self.create_export(None, volume)

    def create_cloned_volume(self, volume, src_vref):
        clone_src_template = "/app_instances/{}/storage_instances/{" + \
                             "}/volumes/{}"
        src = clone_src_template.format(src_vref['id'], DEFAULT_STORAGE_NAME,
                                        DEFAULT_VOLUME_NAME)
        data = {
            'create_mode': 'openstack',
            'name': str(volume['id']),
            'uuid': str(volume['id']),
            'clone_src': src,
            'access_control_mode': 'allow_all'
        }
        self._issue_api_request('app_instances', 'post', body=data)

    def delete_volume(self, volume):
        self.detach_volume(None, volume)
        app_inst = volume['id']
        try:
            self._issue_api_request('app_instances/{}'.format(app_inst),
                                    method='delete')
        except exception.NotFound:
            msg = _("Tried to delete volume %s, but it was not found in the "
                    "Datera cluster. Continuing with delete.")
            LOG.info(msg, volume['id'])

    def ensure_export(self, context, volume):
        """Gets the associated account, retrieves CHAP info and updates."""
        storage_instance = self._issue_api_request(
            'app_instances/{}/storage_instances/{}'.format(
                volume['id'], DEFAULT_STORAGE_NAME))

        portal = storage_instance['access']['ips'][0] + ':3260'
        iqn = storage_instance['access']['iqn']

        # Portal, IQN, LUNID
        provider_location = '%s %s %s' % (portal, iqn, self._get_lunid())
        return {'provider_location': provider_location}

    def create_export(self, context, volume):
        url = "app_instances/{}".format(volume['id'])
        data = {
            'admin_state': 'online'
        }
        app_inst = self._issue_api_request(url, method='put', body=data)
        storage_instance = app_inst['storage_instances'][
            DEFAULT_STORAGE_NAME]

        portal = storage_instance['access']['ips'][0] + ':3260'
        iqn = storage_instance['access']['iqn']

        # Portal, IQN, LUNID
        provider_location = '%s %s %s' % (portal, iqn, self._get_lunid())
        return {'provider_location': provider_location}

    def detach_volume(self, context, volume):
        url = "app_instances/{}".format(volume['id'])
        data = {
            'admin_state': 'offline',
            'force': True
        }
        try:
            self._issue_api_request(url, method='put', body=data)
        except exception.NotFound:
            msg = _("Tried to detach volume %s, but it was not found in the "
                    "Datera cluster. Continuing with detach.")
            LOG.info(msg, volume['id'])

    def create_snapshot(self, snapshot):
        url_template = 'app_instances/{}/storage_instances/{}/volumes/{' \
                       '}/snapshots'
        url = url_template.format(snapshot['volume_id'],
                                  DEFAULT_STORAGE_NAME,
                                  DEFAULT_VOLUME_NAME)

        snap_params = {
            'uuid': snapshot['id'],
        }
        self._issue_api_request(url, method='post', body=snap_params)

    def delete_snapshot(self, snapshot):
        snap_temp = 'app_instances/{}/storage_instances/{}/volumes/{' \
                    '}/snapshots'
        snapu = snap_temp.format(snapshot['volume_id'],
                                 DEFAULT_STORAGE_NAME,
                                 DEFAULT_VOLUME_NAME)

        snapshots = self._issue_api_request(snapu, method='get')

        try:
            for ts, snap in snapshots.viewitems():
                if snap['uuid'] == snapshot['id']:
                    url_template = snapu + '/{}'
                    url = url_template.format(ts)
                    self._issue_api_request(url, method='delete')
                    break
            else:
                raise exception.NotFound
        except exception.NotFound:
            msg = _LI("Tried to delete snapshot %s, but was not found in "
                      "Datera cluster. Continuing with delete.")
            LOG.info(msg, snapshot['id'])

    def create_volume_from_snapshot(self, volume, snapshot):
        snap_temp = 'app_instances/{}/storage_instances/{}/volumes/{' \
                    '}/snapshots'
        snapu = snap_temp.format(snapshot['volume_id'],
                                 DEFAULT_STORAGE_NAME,
                                 DEFAULT_VOLUME_NAME)

        snapshots = self._issue_api_request(snapu, method='get')
        for ts, snap in snapshots.viewitems():
            if snap['uuid'] == snapshot['id']:
                found_ts = ts
                print(found_ts)
                break
        else:
            raise exception.NotFound

        src = '/app_instances/{}/storage_instances/{}/volumes/{' \
            '}/snapshots/{}'.format(
                snapshot['volume_id'],
                DEFAULT_STORAGE_NAME,
                DEFAULT_VOLUME_NAME,
                found_ts)
        app_params = \
            {
                'create_mode': 'openstack',
                'uuid': str(volume['id']),
                'name': str(volume['id']),
                'clone_src': src,
                'access_control_mode': 'allow_all'
            }
        self._issue_api_request('app_instances', method='post', body=app_params)

    def get_volume_stats(self, refresh=False):
        """Get volume stats.

        If 'refresh' is True, run update first.
        The name is a bit misleading as
        the majority of the data here is cluster
        data.
        """
        if refresh or not self.cluster_stats:
            try:
                self._update_cluster_stats()
            except exception.DateraAPIException:
                LOG.error('Failed to get updated stats from Datera cluster.')
                pass

        return self.cluster_stats

    def _update_cluster_stats(self):
        LOG.debug("Updating cluster stats info.")

        results = self._issue_api_request('system')

        if 'uuid' not in results:
            LOG.error(_('Failed to get updated stats from Datera Cluster.'))

        backend_name = self.configuration.safe_get('volume_backend_name')
        stats = {
            'volume_backend_name': backend_name or 'Datera',
            'vendor_name': 'Datera',
            'driver_version': self.VERSION,
            'storage_protocol': 'iSCSI',
            'total_capacity_gb': int(results['total_capacity']) / units.Gi,
            'free_capacity_gb': int(results['available_capacity']) / units.Gi,
            'reserved_percentage': 0,
        }

        self.cluster_stats = stats

    @_authenticated
    def _issue_api_request(self, resource_type, method='get', resource=None,
                           body=None, action=None):
        """All API requests to Datera cluster go through this method.

        :param resource_type: the type of the resource
        :param method: the request verb
        :param resource: the identifier of the resource
        :param body: a dict with options for the action_type
        :param action: the action to perform
        :returns: a dict of the response from the Datera cluster
        """
        host = self.configuration.san_ip
        port = self.configuration.datera_api_port
        api_token = self.configuration.datera_api_token
        api_version = self.configuration.datera_api_version

        payload = json.dumps(body, ensure_ascii=False)
        payload.encode('utf-8')
        header = {'Content-Type': 'application/json; charset=utf-8'}

        if api_token:
            header['Auth-Token'] = api_token

        LOG.debug("Payload for Datera API call: %s", payload)

        client_cert = self.configuration.driver_client_cert
        client_cert_key = self.configuration.driver_client_cert_key
        protocol = 'http'
        cert_data = None

        if client_cert:
            protocol = 'https'
            cert_data = (client_cert, client_cert_key)

        connection_string = '%s://%s:%s/v%s/%s' % (protocol, host, port,
                                                   api_version, resource_type)

        if resource is not None:
            connection_string += '/%s' % resource
        if action is not None:
            connection_string += '/%s' % action

        LOG.debug("Endpoint for Datera API call: %s", connection_string)
        LOG.debug("Payload for Datera API call: header: {}, payload: {}"
                  "cert {}".format(header, payload, cert_data))
        try:
            response = getattr(requests, method)(connection_string,
                                                 data=payload, headers=header,
                                                 verify=False, cert=cert_data)
        except requests.exceptions.RequestException as ex:
            msg = _('Failed to make a request to Datera cluster endpoint due '
                    'to the following reason: %s') % ex.message
            LOG.error(msg)
            raise exception.DateraAPIException(msg)

        data = response.json()
        LOG.debug("Results of Datera API call: %s", data)
        if not response.ok:
            print(response.url)
            print(payload)
            print(vars(response))
            if response.status_code == 404:
                raise exception.NotFound(data['message'])
            elif response.status_code in [403, 401]:
                raise exception.NotAuthorized()
            else:
                msg = _('Request to Datera cluster returned bad status:'
                        ' %(status)s | %(reason)s') % {
                            'status': response.status_code,
                            'reason': response.reason}
                LOG.error(msg)
                raise exception.DateraAPIException(msg)

        return data
