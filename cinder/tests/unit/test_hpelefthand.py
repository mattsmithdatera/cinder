#    (c) Copyright 2014-2016 Hewlett Packard Enterprise Development LP
#    All Rights Reserved.
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
#
"""Unit tests for OpenStack Cinder volume drivers."""

import json
import mock
from oslo_utils import units

from cinder import context
from cinder import exception
from cinder.objects import fields
from cinder import test
from cinder.tests.unit import fake_hpe_lefthand_client as hpelefthandclient
from cinder.volume.drivers.hpe import hpe_lefthand_iscsi
from cinder.volume import volume_types

hpeexceptions = hpelefthandclient.hpeexceptions

GOODNESS_FUNCTION = \
    "capabilities.capacity_utilization < 0.6? 100 : 25"
FILTER_FUNCTION = \
    "capabilities.total_volumes < 400 && capabilities.capacity_utilization"
HPELEFTHAND_SAN_SSH_CON_TIMEOUT = 44
HPELEFTHAND_SAN_SSH_PRIVATE = 'foobar'
HPELEFTHAND_API_URL = 'http://fake.foo:8080/lhos'
HPELEFTHAND_API_URL2 = 'http://fake2.foo2:8080/lhos'
HPELEFTHAND_SSH_IP = 'fake.foo'
HPELEFTHAND_SSH_IP2 = 'fake2.foo2'
HPELEFTHAND_USERNAME = 'foo1'
HPELEFTHAND_PASSWORD = 'bar2'
HPELEFTHAND_SSH_PORT = 16022
HPELEFTHAND_CLUSTER_NAME = 'CloudCluster1'
VOLUME_TYPE_ID_REPLICATED = 'be9181f1-4040-46f2-8298-e7532f2bf9db'
FAKE_FAILOVER_HOST = 'fakefailover@foo#destfakepool'


class HPELeftHandBaseDriver(object):

    cluster_id = 1

    volume_name = "fakevolume"
    volume_name_repl = "fakevolume_replicated"
    volume_id = 1
    volume = {
        'name': volume_name,
        'display_name': 'Foo Volume',
        'provider_location': ('10.0.1.6 iqn.2003-10.com.lefthandnetworks:'
                              'group01:25366:fakev 0'),
        'id': volume_id,
        'provider_auth': None,
        'size': 1}

    volume_replicated = {
        'name': volume_name_repl,
        'display_name': 'Foo Volume',
        'provider_location': ('10.0.1.6 iqn.2003-10.com.lefthandnetworks:'
                              'group01:25366:fakev 0'),
        'id': volume_id,
        'provider_auth': None,
        'size': 1,
        'volume_type': 'replicated',
        'volume_type_id': VOLUME_TYPE_ID_REPLICATED,
        'replication_driver_data': ('{"location": "' + HPELEFTHAND_API_URL +
                                    '"}')}

    repl_targets = [{'target_device_id': 'target',
                     'managed_backend_name': FAKE_FAILOVER_HOST,
                     'hpelefthand_api_url': HPELEFTHAND_API_URL2,
                     'hpelefthand_username': HPELEFTHAND_USERNAME,
                     'hpelefthand_password': HPELEFTHAND_PASSWORD,
                     'hpelefthand_clustername': HPELEFTHAND_CLUSTER_NAME,
                     'hpelefthand_ssh_port': HPELEFTHAND_SSH_PORT,
                     'ssh_conn_timeout': HPELEFTHAND_SAN_SSH_CON_TIMEOUT,
                     'san_private_key': HPELEFTHAND_SAN_SSH_PRIVATE,
                     'cluster_id': 6,
                     'cluster_vip': '10.0.1.6'}]

    repl_targets_unmgd = [{'target_device_id': 'target',
                           'hpelefthand_api_url': HPELEFTHAND_API_URL2,
                           'hpelefthand_username': HPELEFTHAND_USERNAME,
                           'hpelefthand_password': HPELEFTHAND_PASSWORD,
                           'hpelefthand_clustername': HPELEFTHAND_CLUSTER_NAME,
                           'hpelefthand_ssh_port': HPELEFTHAND_SSH_PORT,
                           'ssh_conn_timeout': HPELEFTHAND_SAN_SSH_CON_TIMEOUT,
                           'san_private_key': HPELEFTHAND_SAN_SSH_PRIVATE,
                           'cluster_id': 6,
                           'cluster_vip': '10.0.1.6'}]

    list_rep_targets = [{'target_device_id': 'target'}]

    serverName = 'fakehost'
    server_id = 0
    server_uri = '/lhos/servers/0'

    snapshot_name = "fakeshapshot"
    snapshot_id = 3
    snapshot = {
        'id': snapshot_id,
        'name': snapshot_name,
        'display_name': 'fakesnap',
        'volume_name': volume_name,
        'volume': volume}

    cloned_volume_name = "clone_volume"
    cloned_volume = {'name': cloned_volume_name}

    cloned_snapshot_name = "clonedshapshot"
    cloned_snapshot_id = 5
    cloned_snapshot = {
        'name': cloned_snapshot_name,
        'volume_name': volume_name}

    volume_type_id = 4
    init_iqn = 'iqn.1993-08.org.debian:01:222'

    volume_type = {'name': 'gold',
                   'deleted': False,
                   'updated_at': None,
                   'extra_specs': {'hpelh:provisioning': 'thin',
                                   'hpelh:ao': 'true',
                                   'hpelh:data_pl': 'r-0'},
                   'deleted_at': None,
                   'id': 'gold'}
    old_volume_type = {'name': 'gold',
                       'deleted': False,
                       'updated_at': None,
                       'extra_specs': {'hplh:provisioning': 'thin',
                                       'hplh:ao': 'true',
                                       'hplh:data_pl': 'r-0'},
                       'deleted_at': None,
                       'id': 'gold'}

    connector = {
        'ip': '10.0.0.2',
        'initiator': 'iqn.1993-08.org.debian:01:222',
        'host': serverName}

    driver_startup_call_stack = [
        mock.call.login('foo1', 'bar2'),
        mock.call.getClusterByName('CloudCluster1'),
        mock.call.setSSHOptions(
            HPELEFTHAND_SSH_IP,
            HPELEFTHAND_USERNAME,
            HPELEFTHAND_PASSWORD,
            missing_key_policy='AutoAddPolicy',
            privatekey=HPELEFTHAND_SAN_SSH_PRIVATE,
            known_hosts_file=mock.ANY,
            port=HPELEFTHAND_SSH_PORT,
            conn_timeout=HPELEFTHAND_SAN_SSH_CON_TIMEOUT),
    ]


class TestHPELeftHandISCSIDriver(HPELeftHandBaseDriver, test.TestCase):

    CONSIS_GROUP_ID = '3470cc4c-63b3-4c7a-8120-8a0693b45838'
    CGSNAPSHOT_ID = '5351d914-6c90-43e7-9a8e-7e84610927da'

    class fake_consistencygroup_object(object):
        volume_type_id = '371c64d5-b92a-488c-bc14-1e63cef40e08'
        name = 'cg_name'
        cgsnapshot_id = None
        id = '3470cc4c-63b3-4c7a-8120-8a0693b45838'
        description = 'consistency group'

    class fake_cgsnapshot_object(object):
        consistencygroup_id = '3470cc4c-63b3-4c7a-8120-8a0693b45838'
        description = 'cgsnapshot'
        id = '5351d914-6c90-43e7-9a8e-7e84610927da'
        readOnly = False

    def default_mock_conf(self):

        mock_conf = mock.MagicMock()
        mock_conf.hpelefthand_api_url = HPELEFTHAND_API_URL
        mock_conf.hpelefthand_username = HPELEFTHAND_USERNAME
        mock_conf.hpelefthand_password = HPELEFTHAND_PASSWORD
        mock_conf.hpelefthand_ssh_port = HPELEFTHAND_SSH_PORT
        mock_conf.ssh_conn_timeout = HPELEFTHAND_SAN_SSH_CON_TIMEOUT
        mock_conf.san_private_key = HPELEFTHAND_SAN_SSH_PRIVATE
        mock_conf.hpelefthand_iscsi_chap_enabled = False
        mock_conf.hpelefthand_debug = False
        mock_conf.hpelefthand_clustername = "CloudCluster1"
        mock_conf.goodness_function = GOODNESS_FUNCTION
        mock_conf.filter_function = FILTER_FUNCTION
        mock_conf.reserved_percentage = 25

        def safe_get(attr):
            try:
                return mock_conf.__getattribute__(attr)
            except AttributeError:
                return None
        mock_conf.safe_get = safe_get

        return mock_conf

    @mock.patch('hpelefthandclient.client.HPELeftHandClient', spec=True)
    def setup_driver(self, _mock_client, config=None):
        if config is None:
            config = self.default_mock_conf()

        _mock_client.return_value.getClusterByName.return_value = {
            'id': 1, 'virtualIPAddresses': [{'ipV4Address': '10.0.1.6'}]}
        _mock_client.return_value.getCluster.return_value = {
            'spaceTotal': units.Gi * 500,
            'spaceAvailable': units.Gi * 250}
        _mock_client.return_value.getApiVersion.return_value = '1.2'
        _mock_client.return_value.getIPFromCluster.return_value = '1.1.1.1'
        self.driver = hpe_lefthand_iscsi.HPELeftHandISCSIDriver(
            configuration=config)
        self.driver.do_setup(None)
        self.cluster_name = config.hpelefthand_clustername
        return _mock_client.return_value

    @mock.patch('hpelefthandclient.version', "1.0.0")
    def test_unsupported_client_version(self):

        self.assertRaises(exception.InvalidInput,
                          self.setup_driver)

    @mock.patch('hpelefthandclient.version', "3.0.0")
    def test_supported_client_version(self):

        self.setup_driver()

    def test_create_volume(self):

        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()

        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        # mock return value of createVolume
        mock_client.createVolume.return_value = {
            'iscsiIqn': self.connector['initiator']}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # execute driver
            volume_info = self.driver.create_volume(self.volume)

            self.assertEqual('10.0.1.6:3260,1 iqn.1993-08.org.debian:01:222 0',
                             volume_info['provider_location'])

            expected = self.driver_startup_call_stack + [
                mock.call.createVolume(
                    'fakevolume',
                    1,
                    units.Gi,
                    {'isThinProvisioned': True,
                     'clusterName': 'CloudCluster1'}),
                mock.call.logout()]

            mock_client.assert_has_calls(expected)

            # mock HTTPServerError
            mock_client.createVolume.side_effect =\
                hpeexceptions.HTTPServerError()
            # ensure the raised exception is a cinder exception
            self.assertRaises(exception.VolumeBackendAPIException,
                              self.driver.create_volume, self.volume)

    @mock.patch.object(
        volume_types,
        'get_volume_type',
        return_value={'extra_specs': {'hpelh:provisioning': 'full'}})
    def test_create_volume_with_es(self, _mock_volume_type):

        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()

        volume_with_vt = self.volume
        volume_with_vt['volume_type_id'] = 1

        # mock return value of createVolume
        mock_client.createVolume.return_value = {
            'iscsiIqn': self.connector['initiator']}
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # execute create_volume
            volume_info = self.driver.create_volume(volume_with_vt)

            self.assertEqual('10.0.1.6:3260,1 iqn.1993-08.org.debian:01:222 0',
                             volume_info['provider_location'])

            expected = self.driver_startup_call_stack + [
                mock.call.createVolume(
                    'fakevolume',
                    1,
                    units.Gi,
                    {'isThinProvisioned': False,
                     'clusterName': 'CloudCluster1'}),
                mock.call.logout()]

            mock_client.assert_has_calls(expected)

    @mock.patch.object(
        volume_types,
        'get_volume_type',
        return_value={'extra_specs': (HPELeftHandBaseDriver.
                                      old_volume_type['extra_specs'])})
    def test_create_volume_old_volume_type(self, _mock_volume_type):

        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()

        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        # mock return value of createVolume
        mock_client.createVolume.return_value = {
            'iscsiIqn': self.connector['initiator']}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # execute driver
            volume_info = self.driver.create_volume(self.volume)

            self.assertEqual('10.0.1.6:3260,1 iqn.1993-08.org.debian:01:222 0',
                             volume_info['provider_location'])

            expected = self.driver_startup_call_stack + [
                mock.call.createVolume(
                    'fakevolume',
                    1,
                    units.Gi,
                    {'isThinProvisioned': True,
                     'clusterName': 'CloudCluster1'}),
                mock.call.logout()]

            mock_client.assert_has_calls(expected)

            # mock HTTPServerError
            mock_client.createVolume.side_effect =\
                hpeexceptions.HTTPServerError()
            # ensure the raised exception is a cinder exception
            self.assertRaises(exception.VolumeBackendAPIException,
                              self.driver.create_volume, self.volume)

    def test_delete_volume(self):

        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()

        # mock return value of getVolumeByName
        mock_client.getVolumeByName.return_value = {'id': self.volume_id}
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # execute delete_volume
            del_volume = self.volume
            del_volume['volume_type_id'] = None
            self.driver.delete_volume(del_volume)

            expected = self.driver_startup_call_stack + [
                mock.call.getVolumeByName('fakevolume'),
                mock.call.deleteVolume(self.volume_id),
                mock.call.logout()]

            mock_client.assert_has_calls(expected)

            # mock HTTPNotFound (volume not found)
            mock_client.getVolumeByName.side_effect =\
                hpeexceptions.HTTPNotFound()
            # no exception should escape method
            self.driver.delete_volume(del_volume)

            # mock HTTPConflict
            mock_client.deleteVolume.side_effect = hpeexceptions.HTTPConflict()
            # ensure the raised exception is a cinder exception
            self.assertRaises(exception.VolumeBackendAPIException,
                              self.driver.delete_volume, {})

    def test_extend_volume(self):

        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()

        # mock return value of getVolumeByName
        mock_client.getVolumeByName.return_value = {'id': self.volume_id}
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # execute extend_volume
            self.driver.extend_volume(self.volume, 2)

            expected = self.driver_startup_call_stack + [
                mock.call.getVolumeByName('fakevolume'),
                mock.call.modifyVolume(1, {'size': 2 * units.Gi}),
                mock.call.logout()]

            # validate call chain
            mock_client.assert_has_calls(expected)

            # mock HTTPServerError (array failure)
            mock_client.modifyVolume.side_effect =\
                hpeexceptions.HTTPServerError()
            # ensure the raised exception is a cinder exception
            self.assertRaises(exception.VolumeBackendAPIException,
                              self.driver.extend_volume, self.volume, 2)

    def test_initialize_connection(self):

        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()

        # mock return value of getVolumeByName
        mock_client.getServerByName.side_effect = hpeexceptions.HTTPNotFound()
        mock_client.createServer.return_value = {'id': self.server_id}
        mock_client.getVolumeByName.return_value = {
            'id': self.volume_id,
            'iscsiSessions': None
        }
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # execute initialize_connection
            result = self.driver.initialize_connection(
                self.volume,
                self.connector)

            # validate
            self.assertEqual('iscsi', result['driver_volume_type'])
            self.assertFalse(result['data']['target_discovered'])
            self.assertEqual(self.volume_id, result['data']['volume_id'])
            self.assertTrue('auth_method' not in result['data'])

            expected = self.driver_startup_call_stack + [
                mock.call.getServerByName('fakehost'),
                mock.call.createServer
                (
                    'fakehost',
                    'iqn.1993-08.org.debian:01:222',
                    None
                ),
                mock.call.getVolumeByName('fakevolume'),
                mock.call.addServerAccess(1, 0),
                mock.call.logout()]

            # validate call chain
            mock_client.assert_has_calls(expected)

            # mock HTTPServerError (array failure)
            mock_client.createServer.side_effect =\
                hpeexceptions.HTTPServerError()
            # ensure the raised exception is a cinder exception
            self.assertRaises(
                exception.VolumeBackendAPIException,
                self.driver.initialize_connection, self.volume, self.connector)

    def test_initialize_connection_session_exists(self):

        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()

        # mock return value of getVolumeByName
        mock_client.getServerByName.side_effect = hpeexceptions.HTTPNotFound()
        mock_client.createServer.return_value = {'id': self.server_id}
        mock_client.getVolumeByName.return_value = {
            'id': self.volume_id,
            'iscsiSessions': [{'server': {'uri': self.server_uri}}]
        }
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # execute initialize_connection
            result = self.driver.initialize_connection(
                self.volume,
                self.connector)

            # validate
            self.assertEqual('iscsi', result['driver_volume_type'])
            self.assertFalse(result['data']['target_discovered'])
            self.assertEqual(self.volume_id, result['data']['volume_id'])
            self.assertTrue('auth_method' not in result['data'])

            expected = self.driver_startup_call_stack + [
                mock.call.getServerByName('fakehost'),
                mock.call.createServer
                (
                    'fakehost',
                    'iqn.1993-08.org.debian:01:222',
                    None
                ),
                mock.call.getVolumeByName('fakevolume'),
                mock.call.logout()]

            # validate call chain
            mock_client.assert_has_calls(expected)

    def test_initialize_connection_with_chaps(self):

        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()

        # mock return value of getVolumeByName
        mock_client.getServerByName.side_effect = hpeexceptions.HTTPNotFound()
        mock_client.createServer.return_value = {
            'id': self.server_id,
            'chapAuthenticationRequired': True,
            'chapTargetSecret': 'dont_tell'}
        mock_client.getVolumeByName.return_value = {
            'id': self.volume_id,
            'iscsiSessions': None
        }
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # execute initialize_connection
            result = self.driver.initialize_connection(
                self.volume,
                self.connector)

            # validate
            self.assertEqual('iscsi', result['driver_volume_type'])
            self.assertFalse(result['data']['target_discovered'])
            self.assertEqual(self.volume_id, result['data']['volume_id'])
            self.assertEqual('CHAP', result['data']['auth_method'])

            expected = self.driver_startup_call_stack + [
                mock.call.getServerByName('fakehost'),
                mock.call.createServer
                (
                    'fakehost',
                    'iqn.1993-08.org.debian:01:222',
                    None
                ),
                mock.call.getVolumeByName('fakevolume'),
                mock.call.addServerAccess(1, 0),
                mock.call.logout()]

            # validate call chain
            mock_client.assert_has_calls(expected)

    def test_terminate_connection(self):

        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()

        mock_client.getVolumeByName.return_value = {'id': self.volume_id}
        mock_client.getServerByName.return_value = {
            'id': self.server_id,
            'name': self.serverName}
        mock_client.findServerVolumes.return_value = [{'id': self.volume_id}]
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # execute terminate_connection
            self.driver.terminate_connection(self.volume, self.connector)

            expected = self.driver_startup_call_stack + [
                mock.call.getVolumeByName('fakevolume'),
                mock.call.getServerByName('fakehost'),
                mock.call.findServerVolumes('fakehost'),
                mock.call.removeServerAccess(1, 0),
                mock.call.deleteServer(0)]

            # validate call chain
            mock_client.assert_has_calls(expected)

            mock_client.getVolumeByName.side_effect = (
                hpeexceptions.HTTPNotFound())
            # ensure the raised exception is a cinder exception
            self.assertRaises(
                exception.VolumeBackendAPIException,
                self.driver.terminate_connection,
                self.volume,
                self.connector)

    def test_terminate_connection_multiple_volumes_on_server(self):

        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()

        mock_client.getVolumeByName.return_value = {'id': self.volume_id}
        mock_client.getServerByName.return_value = {
            'id': self.server_id,
            'name': self.serverName}
        mock_client.findServerVolumes.return_value = [
            {'id': self.volume_id},
            {'id': 99999}]
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # execute terminate_connection
            self.driver.terminate_connection(self.volume, self.connector)

            expected = self.driver_startup_call_stack + [
                mock.call.getVolumeByName('fakevolume'),
                mock.call.getServerByName('fakehost'),
                mock.call.findServerVolumes('fakehost'),
                mock.call.removeServerAccess(1, 0)]

            # validate call chain
            mock_client.assert_has_calls(expected)
            self.assertFalse(mock_client.deleteServer.called)

            mock_client.getVolumeByName.side_effect = (
                hpeexceptions.HTTPNotFound())
            # ensure the raised exception is a cinder exception
            self.assertRaises(
                exception.VolumeBackendAPIException,
                self.driver.terminate_connection,
                self.volume,
                self.connector)

    def test_create_snapshot(self):

        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()

        mock_client.getVolumeByName.return_value = {'id': self.volume_id}
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # execute create_snapshot
            self.driver.create_snapshot(self.snapshot)
            mock_client.getVolumes.return_value = {'total': 1, 'members': []}

            expected = self.driver_startup_call_stack + [
                mock.call.getVolumeByName('fakevolume'),
                mock.call.createSnapshot(
                    'fakeshapshot',
                    1,
                    {'inheritAccess': True}),
                mock.call.logout()]

            # validate call chain
            mock_client.assert_has_calls(expected)

            # mock HTTPServerError (array failure)
            mock_client.getVolumeByName.side_effect =\
                hpeexceptions.HTTPNotFound()
            # ensure the raised exception is a cinder exception
            self.assertRaises(
                exception.VolumeBackendAPIException,
                self.driver.create_snapshot, self.snapshot)

    def test_delete_snapshot(self):

        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()

        mock_client.getSnapshotByName.return_value = {'id': self.snapshot_id}
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # execute delete_snapshot
            self.driver.delete_snapshot(self.snapshot)

            expected = self.driver_startup_call_stack + [
                mock.call.getSnapshotByName('fakeshapshot'),
                mock.call.deleteSnapshot(3),
                mock.call.logout()]

            # validate call chain
            mock_client.assert_has_calls(expected)

            mock_client.getSnapshotByName.side_effect =\
                hpeexceptions.HTTPNotFound()
            # no exception is thrown, just error msg is logged
            self.driver.delete_snapshot(self.snapshot)

            # mock HTTPServerError (array failure)
            ex = hpeexceptions.HTTPServerError({'message': 'Some message.'})
            mock_client.getSnapshotByName.side_effect = ex
            # ensure the raised exception is a cinder exception
            self.assertRaises(
                exception.VolumeBackendAPIException,
                self.driver.delete_snapshot,
                self.snapshot)

            # mock HTTPServerError because the snap is in use
            ex = hpeexceptions.HTTPServerError({
                'message':
                'Hey, dude cannot be deleted because it is a clone point'
                ' duh.'})
            mock_client.getSnapshotByName.side_effect = ex
            # ensure the raised exception is a cinder exception
            self.assertRaises(
                exception.SnapshotIsBusy,
                self.driver.delete_snapshot,
                self.snapshot)

    def test_create_volume_from_snapshot(self):

        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()

        mock_client.getSnapshotByName.return_value = {'id': self.snapshot_id}
        mock_client.cloneSnapshot.return_value = {
            'iscsiIqn': self.connector['initiator']}
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # execute create_volume_from_snapshot
            model_update = self.driver.create_volume_from_snapshot(
                self.volume, self.snapshot)

            expected_iqn = 'iqn.1993-08.org.debian:01:222 0'
            expected_location = "10.0.1.6:3260,1 %s" % expected_iqn
            self.assertEqual(expected_location,
                             model_update['provider_location'])

            expected = self.driver_startup_call_stack + [
                mock.call.getSnapshotByName('fakeshapshot'),
                mock.call.cloneSnapshot('fakevolume', 3),
                mock.call.logout()]

            # validate call chain
            mock_client.assert_has_calls(expected)

    def test_create_cloned_volume(self):

        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()

        mock_client.getVolumeByName.return_value = {'id': self.volume_id}
        mock_client.cloneVolume.return_value = {
            'iscsiIqn': self.connector['initiator']}
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # execute create_cloned_volume
            model_update = self.driver.create_cloned_volume(
                self.cloned_volume, self.volume)

            expected_iqn = 'iqn.1993-08.org.debian:01:222 0'
            expected_location = "10.0.1.6:3260,1 %s" % expected_iqn
            self.assertEqual(expected_location,
                             model_update['provider_location'])

            expected = self.driver_startup_call_stack + [
                mock.call.getVolumeByName('fakevolume'),
                mock.call.cloneVolume('clone_volume', 1),
                mock.call.logout()]

            # validate call chain
            mock_client.assert_has_calls(expected)

    @mock.patch.object(volume_types, 'get_volume_type')
    def test_extra_spec_mapping(self, _mock_get_volume_type):

        # setup drive with default configuration
        self.setup_driver()

        # 2 extra specs we don't care about, and
        # 1 that will get mapped
        _mock_get_volume_type.return_value = {
            'extra_specs': {
                'foo:bar': 'fake',
                'bar:foo': 1234,
                'hpelh:provisioning': 'full'}}

        volume_with_vt = self.volume
        volume_with_vt['volume_type_id'] = self.volume_type_id

        # get the extra specs of interest from this volume's volume type
        volume_extra_specs = self.driver._get_volume_extra_specs(
            volume_with_vt)
        extra_specs = self.driver._get_lh_extra_specs(
            volume_extra_specs,
            hpe_lefthand_iscsi.extra_specs_key_map.keys())

        # map the extra specs key/value pairs to key/value pairs
        # used as optional configuration values by the LeftHand backend
        optional = self.driver._map_extra_specs(extra_specs)

        self.assertDictMatch({'isThinProvisioned': False}, optional)

    @mock.patch.object(volume_types, 'get_volume_type')
    def test_extra_spec_mapping_invalid_value(self, _mock_get_volume_type):

        # setup drive with default configuration
        self.setup_driver()

        volume_with_vt = self.volume
        volume_with_vt['volume_type_id'] = self.volume_type_id

        _mock_get_volume_type.return_value = {
            'extra_specs': {
                # r-07 is an invalid value for hpelh:ao
                'hpelh:data_pl': 'r-07',
                'hpelh:ao': 'true'}}

        # get the extra specs of interest from this volume's volume type
        volume_extra_specs = self.driver._get_volume_extra_specs(
            volume_with_vt)
        extra_specs = self.driver._get_lh_extra_specs(
            volume_extra_specs,
            hpe_lefthand_iscsi.extra_specs_key_map.keys())

        # map the extra specs key/value pairs to key/value pairs
        # used as optional configuration values by the LeftHand backend
        optional = self.driver._map_extra_specs(extra_specs)

        # {'hpelh:ao': 'true'} should map to
        # {'isAdaptiveOptimizationEnabled': True}
        # without hpelh:data_pl since r-07 is an invalid value
        self.assertDictMatch({'isAdaptiveOptimizationEnabled': True}, optional)

    def test_retype_with_no_LH_extra_specs(self):
        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        ctxt = context.get_admin_context()

        host = {'host': self.serverName}
        key_specs_old = {'foo': False, 'bar': 2, 'error': True}
        key_specs_new = {'foo': True, 'bar': 5, 'error': False}
        old_type_ref = volume_types.create(ctxt, 'old', key_specs_old)
        new_type_ref = volume_types.create(ctxt, 'new', key_specs_new)

        diff, equal = volume_types.volume_types_diff(ctxt, old_type_ref['id'],
                                                     new_type_ref['id'])

        volume = dict.copy(self.volume)
        old_type = volume_types.get_volume_type(ctxt, old_type_ref['id'])
        volume['volume_type'] = old_type
        volume['host'] = host
        new_type = volume_types.get_volume_type(ctxt, new_type_ref['id'])

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            self.driver.retype(ctxt, volume, new_type, diff, host)

            expected = self.driver_startup_call_stack + [
                mock.call.getVolumeByName('fakevolume'),
                mock.call.logout()]

            # validate call chain
            mock_client.assert_has_calls(expected)

    def test_retype_with_only_LH_extra_specs(self):
        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()
        mock_client.getVolumeByName.return_value = {'id': self.volume_id}
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        ctxt = context.get_admin_context()

        host = {'host': self.serverName}
        key_specs_old = {'hpelh:provisioning': 'thin'}
        key_specs_new = {'hpelh:provisioning': 'full', 'hpelh:ao': 'true'}
        old_type_ref = volume_types.create(ctxt, 'old', key_specs_old)
        new_type_ref = volume_types.create(ctxt, 'new', key_specs_new)

        diff, equal = volume_types.volume_types_diff(ctxt, old_type_ref['id'],
                                                     new_type_ref['id'])

        volume = dict.copy(self.volume)
        old_type = volume_types.get_volume_type(ctxt, old_type_ref['id'])
        volume['volume_type'] = old_type
        volume['host'] = host
        new_type = volume_types.get_volume_type(ctxt, new_type_ref['id'])

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            self.driver.retype(ctxt, volume, new_type, diff, host)

            expected = self.driver_startup_call_stack + [
                mock.call.getVolumeByName('fakevolume'),
                mock.call.modifyVolume(
                    1, {
                        'isThinProvisioned': False,
                        'isAdaptiveOptimizationEnabled': True}),
                mock.call.logout()]

            # validate call chain
            mock_client.assert_has_calls(expected)

    def test_retype_with_both_extra_specs(self):
        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()
        mock_client.getVolumeByName.return_value = {'id': self.volume_id}
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        ctxt = context.get_admin_context()

        host = {'host': self.serverName}
        key_specs_old = {'hpelh:provisioning': 'full', 'foo': 'bar'}
        key_specs_new = {'hpelh:provisioning': 'thin', 'foo': 'foobar'}
        old_type_ref = volume_types.create(ctxt, 'old', key_specs_old)
        new_type_ref = volume_types.create(ctxt, 'new', key_specs_new)

        diff, equal = volume_types.volume_types_diff(ctxt, old_type_ref['id'],
                                                     new_type_ref['id'])

        volume = dict.copy(self.volume)
        old_type = volume_types.get_volume_type(ctxt, old_type_ref['id'])
        volume['volume_type'] = old_type
        volume['host'] = host
        new_type = volume_types.get_volume_type(ctxt, new_type_ref['id'])

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            self.driver.retype(ctxt, volume, new_type, diff, host)

            expected = self.driver_startup_call_stack + [
                mock.call.getVolumeByName('fakevolume'),
                mock.call.modifyVolume(1, {'isThinProvisioned': True}),
                mock.call.logout()]

            # validate call chain
            mock_client.assert_has_calls(expected)

    def test_retype_same_extra_specs(self):
        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()
        mock_client.getVolumeByName.return_value = {'id': self.volume_id}
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        ctxt = context.get_admin_context()

        host = {'host': self.serverName}
        key_specs_old = {'hpelh:provisioning': 'full', 'hpelh:ao': 'true'}
        key_specs_new = {'hpelh:provisioning': 'full', 'hpelh:ao': 'false'}
        old_type_ref = volume_types.create(ctxt, 'old', key_specs_old)
        new_type_ref = volume_types.create(ctxt, 'new', key_specs_new)

        diff, equal = volume_types.volume_types_diff(ctxt, old_type_ref['id'],
                                                     new_type_ref['id'])

        volume = dict.copy(self.volume)
        old_type = volume_types.get_volume_type(ctxt, old_type_ref['id'])
        volume['volume_type'] = old_type
        volume['host'] = host
        new_type = volume_types.get_volume_type(ctxt, new_type_ref['id'])

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            self.driver.retype(ctxt, volume, new_type, diff, host)

            expected = self.driver_startup_call_stack + [
                mock.call.getVolumeByName('fakevolume'),
                mock.call.modifyVolume(
                    1,
                    {'isAdaptiveOptimizationEnabled': False}),
                mock.call.logout()]

            # validate call chain
            mock_client.assert_has_calls(expected)

    def test_migrate_no_location(self):
        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()

        host = {'host': self.serverName, 'capabilities': {}}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            (migrated, update) = self.driver.migrate_volume(
                None,
                self.volume,
                host)
            self.assertFalse(migrated)

            mock_client.assert_has_calls([])
            self.assertEqual(0, len(mock_client.method_calls))

    def test_migrate_incorrect_vip(self):
        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()
        mock_client.getClusterByName.return_value = {
            "virtualIPAddresses": [{
                "ipV4Address": "10.10.10.10",
                "ipV4NetMask": "255.255.240.0"}],
            "id": self.cluster_id}

        mock_client.getVolumeByName.return_value = {'id': self.volume_id}
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        location = (self.driver.DRIVER_LOCATION % {
            'cluster': 'New_CloudCluster',
            'vip': '10.10.10.111'})

        host = {
            'host': self.serverName,
            'capabilities': {'location_info': location}}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            (migrated, update) = self.driver.migrate_volume(
                None,
                self.volume,
                host)
            self.assertFalse(migrated)

            expected = self.driver_startup_call_stack + [
                mock.call.getClusterByName('New_CloudCluster'),
                mock.call.logout()]

            mock_client.assert_has_calls(expected)
            # and nothing else
            self.assertEqual(
                len(expected),
                len(mock_client.method_calls))

    def test_migrate_with_location(self):
        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()
        mock_client.getClusterByName.return_value = {
            "virtualIPAddresses": [{
                "ipV4Address": "10.10.10.111",
                "ipV4NetMask": "255.255.240.0"}],
            "id": self.cluster_id}

        mock_client.getVolumeByName.return_value = {'id': self.volume_id,
                                                    'iscsiSessions': None}
        mock_client.getVolume.return_value = {'snapshots': {
            'resource': None}}
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        location = (self.driver.DRIVER_LOCATION % {
            'cluster': 'New_CloudCluster',
            'vip': '10.10.10.111'})

        host = {
            'host': self.serverName,
            'capabilities': {'location_info': location}}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            (migrated, update) = self.driver.migrate_volume(
                None,
                self.volume,
                host)
            self.assertTrue(migrated)

            expected = self.driver_startup_call_stack + [
                mock.call.getClusterByName('New_CloudCluster'),
                mock.call.logout()] + self.driver_startup_call_stack + [
                mock.call.getVolumeByName('fakevolume'),
                mock.call.getVolume(
                    1,
                    'fields=snapshots,snapshots[resource[members[name]]]'),
                mock.call.modifyVolume(1, {'clusterName': 'New_CloudCluster'}),
                mock.call.logout()]

            mock_client.assert_has_calls(expected)
            # and nothing else
            self.assertEqual(
                len(expected),
                len(mock_client.method_calls))

    def test_migrate_with_Snapshots(self):
        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()
        mock_client.getClusterByName.return_value = {
            "virtualIPAddresses": [{
                "ipV4Address": "10.10.10.111",
                "ipV4NetMask": "255.255.240.0"}],
            "id": self.cluster_id}

        mock_client.getVolumeByName.return_value = {
            'id': self.volume_id,
            'iscsiSessions': None}
        mock_client.getVolume.return_value = {'snapshots': {
            'resource': 'snapfoo'}}
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        location = (self.driver.DRIVER_LOCATION % {
            'cluster': 'New_CloudCluster',
            'vip': '10.10.10.111'})

        host = {
            'host': self.serverName,
            'capabilities': {'location_info': location}}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            (migrated, update) = self.driver.migrate_volume(
                None,
                self.volume,
                host)
            self.assertFalse(migrated)

            expected = self.driver_startup_call_stack + [
                mock.call.getClusterByName('New_CloudCluster'),
                mock.call.logout()] + self.driver_startup_call_stack + [
                mock.call.getVolumeByName('fakevolume'),
                mock.call.getVolume(
                    1,
                    'fields=snapshots,snapshots[resource[members[name]]]'),
                mock.call.logout()]

            mock_client.assert_has_calls(expected)
            # and nothing else
            self.assertEqual(
                len(expected),
                len(mock_client.method_calls))

    def test_update_migrated_volume(self):
        mock_client = self.setup_driver()
        volume_id = 'fake_vol_id'
        clone_id = 'fake_clone_id'
        fake_old_volume = {'id': volume_id}
        provider_location = 'foo'
        fake_new_volume = {'id': clone_id,
                           '_name_id': clone_id,
                           'provider_location': provider_location}
        original_volume_status = 'available'
        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client
            actual_update = self.driver.update_migrated_volume(
                context.get_admin_context(), fake_old_volume,
                fake_new_volume, original_volume_status)

            expected_update = {'_name_id': None,
                               'provider_location': None}
            self.assertEqual(expected_update, actual_update)

    def test_update_migrated_volume_attached(self):
        mock_client = self.setup_driver()
        volume_id = 'fake_vol_id'
        clone_id = 'fake_clone_id'
        fake_old_volume = {'id': volume_id}
        provider_location = 'foo'
        fake_new_volume = {'id': clone_id,
                           '_name_id': clone_id,
                           'provider_location': provider_location}
        original_volume_status = 'in-use'

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client
            actual_update = self.driver.update_migrated_volume(
                context.get_admin_context(), fake_old_volume,
                fake_new_volume, original_volume_status)

            expected_update = {'_name_id': fake_new_volume['_name_id'],
                               'provider_location': provider_location}
            self.assertEqual(expected_update, actual_update)

    @mock.patch.object(volume_types, 'get_volume_type',
                       return_value={'extra_specs': {'hpelh:ao': 'true'}})
    def test_create_volume_with_ao_true(self, _mock_volume_type):

        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()

        volume_with_vt = self.volume
        volume_with_vt['volume_type_id'] = 1

        # mock return value of createVolume
        mock_client.createVolume.return_value = {
            'iscsiIqn': self.connector['initiator']}
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            volume_info = self.driver.create_volume(volume_with_vt)

            self.assertEqual('10.0.1.6:3260,1 iqn.1993-08.org.debian:01:222 0',
                             volume_info['provider_location'])

            # make sure createVolume is called without
            # isAdaptiveOptimizationEnabled == true
            expected = self.driver_startup_call_stack + [
                mock.call.createVolume(
                    'fakevolume',
                    1,
                    units.Gi,
                    {'isThinProvisioned': True,
                     'clusterName': 'CloudCluster1'}),
                mock.call.logout()]

            mock_client.assert_has_calls(expected)

    @mock.patch.object(volume_types, 'get_volume_type',
                       return_value={'extra_specs': {'hpelh:ao': 'false'}})
    def test_create_volume_with_ao_false(self, _mock_volume_type):

        # setup drive with default configuration
        # and return the mock HTTP LeftHand client
        mock_client = self.setup_driver()

        volume_with_vt = self.volume
        volume_with_vt['volume_type_id'] = 1

        # mock return value of createVolume
        mock_client.createVolume.return_value = {
            'iscsiIqn': self.connector['initiator']}
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            volume_info = self.driver.create_volume(volume_with_vt)

            self.assertEqual('10.0.1.6:3260,1 iqn.1993-08.org.debian:01:222 0',
                             volume_info['provider_location'])

            # make sure createVolume is called with
            # isAdaptiveOptimizationEnabled == false
            expected = self.driver_startup_call_stack + [
                mock.call.createVolume(
                    'fakevolume',
                    1,
                    units.Gi,
                    {'isThinProvisioned': True,
                     'clusterName': 'CloudCluster1',
                     'isAdaptiveOptimizationEnabled': False}),
                mock.call.logout()]

            mock_client.assert_has_calls(expected)

    def test_get_existing_volume_ref_name(self):
        self.setup_driver()

        existing_ref = {'source-name': self.volume_name}
        result = self.driver._get_existing_volume_ref_name(
            existing_ref)
        self.assertEqual(self.volume_name, result)

        existing_ref = {'bad-key': 'foo'}
        self.assertRaises(
            exception.ManageExistingInvalidReference,
            self.driver._get_existing_volume_ref_name,
            existing_ref)

    def test_manage_existing(self):
        mock_client = self.setup_driver()

        self.driver.api_version = "1.1"

        volume = {'display_name': 'Foo Volume',
                  'volume_type': None,
                  'volume_type_id': None,
                  'id': '12345'}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client
            mock_client.getVolumeByName.return_value = {'id': self.volume_id}
            mock_client.getVolumes.return_value = {
                "type": "volume",
                "total": 1,
                "members": [{
                    "id": self.volume_id,
                    "clusterName": self.cluster_name,
                    "size": 1
                }]
            }

            existing_ref = {'source-name': self.volume_name}

            expected_obj = {'display_name': 'Foo Volume'}

            obj = self.driver.manage_existing(volume, existing_ref)

            mock_client.assert_has_calls(
                self.driver_startup_call_stack + [
                    mock.call.getVolumeByName(self.volume_name),
                    mock.call.logout()] +
                self.driver_startup_call_stack + [
                    mock.call.modifyVolume(self.volume_id,
                                           {'name': 'volume-12345'}),
                    mock.call.logout()])
            self.assertEqual(expected_obj, obj)

    @mock.patch.object(volume_types, 'get_volume_type')
    def test_manage_existing_retype(self, _mock_volume_types):
        mock_client = self.setup_driver()

        _mock_volume_types.return_value = {
            'name': 'gold',
            'id': 'gold-id',
            'extra_specs': {
                'hpelh:provisioning': 'thin',
                'hpelh:ao': 'true',
                'hpelh:data_pl': 'r-0',
                'volume_type': self.volume_type}}

        self.driver.api_version = "1.1"

        volume = {'display_name': 'Foo Volume',
                  'host': 'stack@lefthand#lefthand',
                  'volume_type': 'gold',
                  'volume_type_id': 'bcfa9fa4-54a0-4340-a3d8-bfcf19aea65e',
                  'id': '12345'}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client
            mock_client.getVolumeByName.return_value = {'id': self.volume_id}
            mock_client.getVolumes.return_value = {
                "type": "volume",
                "total": 1,
                "members": [{
                    "id": self.volume_id,
                    "clusterName": self.cluster_name,
                    "size": 1
                }]
            }

            existing_ref = {'source-name': self.volume_name}

            expected_obj = {'display_name': 'Foo Volume'}

            obj = self.driver.manage_existing(volume, existing_ref)

            mock_client.assert_has_calls(
                self.driver_startup_call_stack + [
                    mock.call.getVolumeByName(self.volume_name),
                    mock.call.logout()] +
                self.driver_startup_call_stack + [
                    mock.call.modifyVolume(self.volume_id,
                                           {'name': 'volume-12345'}),
                    mock.call.logout()])
            self.assertEqual(expected_obj, obj)

    @mock.patch.object(volume_types, 'get_volume_type')
    def test_manage_existing_retype_exception(self, _mock_volume_types):
        mock_client = self.setup_driver()

        _mock_volume_types.return_value = {
            'name': 'gold',
            'id': 'gold-id',
            'extra_specs': {
                'hpelh:provisioning': 'thin',
                'hpelh:ao': 'true',
                'hpelh:data_pl': 'r-0',
                'volume_type': self.volume_type}}

        self.driver.retype = mock.Mock(
            side_effect=exception.VolumeNotFound(volume_id="fake"))

        self.driver.api_version = "1.1"

        volume = {'display_name': 'Foo Volume',
                  'host': 'stack@lefthand#lefthand',
                  'volume_type': 'gold',
                  'volume_type_id': 'bcfa9fa4-54a0-4340-a3d8-bfcf19aea65e',
                  'id': '12345'}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client
            mock_client.getVolumeByName.return_value = {'id': self.volume_id}
            mock_client.getVolumes.return_value = {
                "type": "volume",
                "total": 1,
                "members": [{
                    "id": self.volume_id,
                    "clusterName": self.cluster_name,
                    "size": 1
                }]
            }

            existing_ref = {'source-name': self.volume_name}

            self.assertRaises(exception.VolumeNotFound,
                              self.driver.manage_existing,
                              volume,
                              existing_ref)

            mock_client.assert_has_calls(
                self.driver_startup_call_stack + [
                    mock.call.getVolumeByName(self.volume_name),
                    mock.call.logout()] +
                self.driver_startup_call_stack + [
                    mock.call.modifyVolume(self.volume_id,
                                           {'name': 'volume-12345'}),
                    mock.call.logout()] +
                self.driver_startup_call_stack + [
                    mock.call.modifyVolume(self.volume_id,
                                           {'name': 'fakevolume'}),
                    mock.call.logout()])

    def test_manage_existing_volume_type_exception(self):
        mock_client = self.setup_driver()

        self.driver.api_version = "1.1"

        volume = {'display_name': 'Foo Volume',
                  'volume_type': 'gold',
                  'volume_type_id': 'bcfa9fa4-54a0-4340-a3d8-bfcf19aea65e',
                  'id': '12345'}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client
            mock_client.getVolumeByName.return_value = {'id': self.volume_id}
            mock_client.getVolumes.return_value = {
                "type": "volume",
                "total": 1,
                "members": [{
                    "id": self.volume_id,
                    "clusterName": self.cluster_name,
                    "size": 1
                }]
            }

            existing_ref = {'source-name': self.volume_name}

            self.assertRaises(exception.ManageExistingVolumeTypeMismatch,
                              self.driver.manage_existing,
                              volume=volume,
                              existing_ref=existing_ref)

            mock_client.assert_has_calls(
                self.driver_startup_call_stack + [
                    mock.call.getVolumeByName(self.volume_name),
                    mock.call.logout()])

    def test_manage_existing_snapshot(self):
        mock_client = self.setup_driver()

        self.driver.api_version = "1.1"

        volume = {
            'id': '111',
        }
        snapshot = {
            'display_name': 'Foo Snap',
            'id': '12345',
            'volume': volume,
            'volume_id': '111',
        }

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client
            mock_client.getSnapshotByName.return_value = {
                'id': self.snapshot_id
            }
            mock_client.getSnapshotParentVolume.return_value = {
                'name': 'volume-111'
            }

            existing_ref = {'source-name': self.snapshot_name}
            expected_obj = {'display_name': 'Foo Snap'}

            obj = self.driver.manage_existing_snapshot(snapshot, existing_ref)

            mock_client.assert_has_calls(
                self.driver_startup_call_stack + [
                    mock.call.getSnapshotByName(self.snapshot_name),
                    mock.call.getSnapshotParentVolume(self.snapshot_name),
                    mock.call.modifySnapshot(self.snapshot_id,
                                             {'name': 'snapshot-12345'}),
                    mock.call.logout()])
            self.assertEqual(expected_obj, obj)

    def test_manage_existing_snapshot_failed_over_volume(self):
        mock_client = self.setup_driver()

        self.driver.api_version = "1.1"

        volume = {
            'id': self.volume_id,
            'replication_status': 'failed-over',
        }
        snapshot = {
            'display_name': 'Foo Snap',
            'id': '12345',
            'volume': volume,
        }
        existing_ref = {'source-name': self.snapshot_name}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            self.assertRaises(exception.InvalidInput,
                              self.driver.manage_existing_snapshot,
                              snapshot=snapshot,
                              existing_ref=existing_ref)

    def test_manage_existing_get_size(self):
        mock_client = self.setup_driver()
        mock_client.getVolumeByName.return_value = {'size': 2147483648}

        self.driver.api_version = "1.1"

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client
            mock_client.getVolumes.return_value = {
                "type": "volume",
                "total": 1,
                "members": [{
                    "id": self.volume_id,
                    "clusterName": self.cluster_name,
                    "size": 1
                }]
            }

            volume = {}
            existing_ref = {'source-name': self.volume_name}

            size = self.driver.manage_existing_get_size(volume, existing_ref)

            expected_size = 2
            expected = [mock.call.getVolumeByName(existing_ref['source-name']),
                        mock.call.logout()]

            mock_client.assert_has_calls(
                self.driver_startup_call_stack +
                expected)
            self.assertEqual(expected_size, size)

    def test_manage_existing_get_size_invalid_reference(self):
        mock_client = self.setup_driver()
        mock_client.getVolumeByName.return_value = {'size': 2147483648}

        self.driver.api_version = "1.1"

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            volume = {}
            existing_ref = {'source-name': "volume-12345"}

            self.assertRaises(exception.ManageExistingInvalidReference,
                              self.driver.manage_existing_get_size,
                              volume=volume,
                              existing_ref=existing_ref)

            mock_client.assert_has_calls([])

            existing_ref = {}

            self.assertRaises(exception.ManageExistingInvalidReference,
                              self.driver.manage_existing_get_size,
                              volume=volume,
                              existing_ref=existing_ref)

            mock_client.assert_has_calls([])

    def test_manage_existing_get_size_invalid_input(self):
        mock_client = self.setup_driver()
        mock_client.getVolumeByName.side_effect = (
            hpeexceptions.HTTPNotFound('fake'))

        self.driver.api_version = "1.1"

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client
            mock_client.getVolumes.return_value = {
                "type": "volume",
                "total": 1,
                "members": [{
                    "id": self.volume_id,
                    "clusterName": self.cluster_name,
                    "size": 1
                }]
            }

            volume = {}
            existing_ref = {'source-name': self.volume_name}

            self.assertRaises(exception.InvalidInput,
                              self.driver.manage_existing_get_size,
                              volume=volume,
                              existing_ref=existing_ref)

            expected = [mock.call.getVolumeByName(existing_ref['source-name'])]

            mock_client.assert_has_calls(
                self.driver_startup_call_stack +
                expected)

    def test_manage_existing_snapshot_get_size(self):
        mock_client = self.setup_driver()
        mock_client.getSnapshotByName.return_value = {'size': 2147483648}

        self.driver.api_version = "1.1"

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            snapshot = {}
            existing_ref = {'source-name': self.snapshot_name}

            size = self.driver.manage_existing_snapshot_get_size(snapshot,
                                                                 existing_ref)

            expected_size = 2
            expected = [mock.call.getSnapshotByName(
                        existing_ref['source-name']),
                        mock.call.logout()]

            mock_client.assert_has_calls(
                self.driver_startup_call_stack +
                expected)
            self.assertEqual(expected_size, size)

    def test_manage_existing_snapshot_get_size_invalid_reference(self):
        mock_client = self.setup_driver()
        mock_client.getSnapshotByName.return_value = {'size': 2147483648}

        self.driver.api_version = "1.1"

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            snapshot = {}
            existing_ref = {'source-name': "snapshot-12345"}

            self.assertRaises(exception.ManageExistingInvalidReference,
                              self.driver.manage_existing_snapshot_get_size,
                              snapshot=snapshot,
                              existing_ref=existing_ref)

            mock_client.assert_has_calls([])

            existing_ref = {}

            self.assertRaises(exception.ManageExistingInvalidReference,
                              self.driver.manage_existing_snapshot_get_size,
                              snapshot=snapshot,
                              existing_ref=existing_ref)

            mock_client.assert_has_calls([])

    def test_manage_existing_snapshot_get_size_invalid_input(self):
        mock_client = self.setup_driver()
        mock_client.getSnapshotByName.side_effect = (
            hpeexceptions.HTTPNotFound('fake'))

        self.driver.api_version = "1.1"

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            snapshot = {}
            existing_ref = {'source-name': self.snapshot_name}

            self.assertRaises(exception.InvalidInput,
                              self.driver.manage_existing_snapshot_get_size,
                              snapshot=snapshot,
                              existing_ref=existing_ref)

            expected = [mock.call.getSnapshotByName(
                        existing_ref['source-name'])]

            mock_client.assert_has_calls(
                self.driver_startup_call_stack +
                expected)

    def test_unmanage(self):
        mock_client = self.setup_driver()
        mock_client.getVolumeByName.return_value = {'id': self.volume_id}

        # mock return value of getVolumes
        mock_client.getVolumes.return_value = {
            "type": "volume",
            "total": 1,
            "members": [{
                "id": self.volume_id,
                "clusterName": self.cluster_name,
                "size": 1
            }]
        }

        self.driver.api_version = "1.1"

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client
            self.driver.unmanage(self.volume)

            new_name = 'unm-' + str(self.volume['id'])

            expected = [
                mock.call.getVolumeByName(self.volume['name']),
                mock.call.modifyVolume(self.volume['id'], {'name': new_name}),
                mock.call.logout()
            ]

            mock_client.assert_has_calls(
                self.driver_startup_call_stack +
                expected)

    def test_unmanage_snapshot(self):
        mock_client = self.setup_driver()
        volume = {
            'id': self.volume_id,
        }
        snapshot = {
            'name': self.snapshot_name,
            'display_name': 'Foo Snap',
            'volume': volume,
            'id': self.snapshot_id,
        }
        mock_client.getSnapshotByName.return_value = {'id': self.snapshot_id, }

        self.driver.api_version = "1.1"

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client
            self.driver.unmanage_snapshot(snapshot)

            new_name = 'ums-' + str(self.snapshot_id)

            expected = [
                mock.call.getSnapshotByName(snapshot['name']),
                mock.call.modifySnapshot(self.snapshot_id, {'name': new_name}),
                mock.call.logout()
            ]

            mock_client.assert_has_calls(
                self.driver_startup_call_stack +
                expected)

    def test_unmanage_snapshot_failed_over_volume(self):
        mock_client = self.setup_driver()
        volume = {
            'id': self.volume_id,
            'replication_status': 'failed-over',
        }
        snapshot = {
            'name': self.snapshot_name,
            'display_name': 'Foo Snap',
            'volume': volume,
            'id': self.snapshot_id,
        }
        mock_client.getSnapshotByName.return_value = {'id': self.snapshot_id, }

        self.driver.api_version = "1.1"

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            self.assertRaises(exception.SnapshotIsBusy,
                              self.driver.unmanage_snapshot,
                              snapshot=snapshot)

    def test_api_version(self):
        self.setup_driver()
        self.driver.api_version = "1.1"
        self.driver._check_api_version()

        self.driver.api_version = "1.0"
        self.assertRaises(exception.InvalidInput,
                          self.driver._check_api_version)

    def test_get_volume_stats(self):

        # set up driver with default config
        mock_client = self.setup_driver()

        # mock return value of getVolumes
        mock_client.getVolumes.return_value = {
            "type": "volume",
            "total": 1,
            "members": [{
                "id": 12345,
                "clusterName": self.cluster_name,
                "size": 1 * units.Gi
            }]
        }

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # execute driver
            stats = self.driver.get_volume_stats(True)

            self.assertEqual('iSCSI', stats['storage_protocol'])
            self.assertEqual(GOODNESS_FUNCTION, stats['goodness_function'])
            self.assertEqual(FILTER_FUNCTION, stats['filter_function'])
            self.assertEqual(1, int(stats['total_volumes']))
            self.assertTrue(stats['thin_provisioning_support'])
            self.assertTrue(stats['thick_provisioning_support'])
            self.assertEqual(1, int(stats['provisioned_capacity_gb']))
            self.assertEqual(25, int(stats['reserved_percentage']))

            cap_util = (
                float(units.Gi * 500 - units.Gi * 250) / float(units.Gi * 500)
            ) * 100

            self.assertEqual(cap_util, float(stats['capacity_utilization']))

            expected = self.driver_startup_call_stack + [
                mock.call.getCluster(1),
                mock.call.getVolumes(fields=['members[id]',
                                             'members[clusterName]',
                                             'members[size]'],
                                     cluster=self.cluster_name),
                mock.call.logout()]

            mock_client.assert_has_calls(expected)

    def test_create_consistencygroup(self):
        ctxt = context.get_admin_context()
        # set up driver with default config
        mock_client = self.setup_driver()

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # create a consistency group
            group = self.fake_consistencygroup_object()
            cg = self.driver.create_consistencygroup(ctxt, group)

            self.assertEqual(fields.ConsistencyGroupStatus.AVAILABLE,
                             cg['status'])

    def test_delete_consistencygroup(self):
        ctxt = context.get_admin_context()
        # set up driver with default config
        mock_client = self.setup_driver()

        mock_volume = mock.MagicMock()
        volumes = [mock_volume]

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # create a consistency group
            group = self.fake_consistencygroup_object()
            cg = self.driver.create_consistencygroup(ctxt, group)
            self.assertEqual(fields.ConsistencyGroupStatus.AVAILABLE,
                             cg['status'])

            # delete the consistency group
            group.status = fields.ConsistencyGroupStatus.DELETING
            cg, vols = self.driver.delete_consistencygroup(ctxt, group,
                                                           volumes)
            self.assertEqual(fields.ConsistencyGroupStatus.DELETING,
                             cg['status'])

    def test_update_consistencygroup_add_vol_delete_cg(self):
        ctxt = context.get_admin_context()

        # set up driver with default config
        mock_client = self.setup_driver()

        mock_volume = mock.MagicMock()
        volumes = [mock_volume]

        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        # mock return value of createVolume
        mock_client.createVolume.return_value = {
            'iscsiIqn': self.connector['initiator']}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # create a consistency group
            group = self.fake_consistencygroup_object()
            cg = self.driver.create_consistencygroup(ctxt, group)
            self.assertEqual(fields.ConsistencyGroupStatus.AVAILABLE,
                             cg['status'])

            # add volume to consistency group
            cg = self.driver.update_consistencygroup(
                ctxt, group, add_volumes=[self.volume], remove_volumes=None)

            # delete the consistency group
            group.status = fields.ConsistencyGroupStatus.DELETING
            cg, vols = self.driver.delete_consistencygroup(ctxt, group,
                                                           volumes)
            self.assertEqual(fields.ConsistencyGroupStatus.DELETING,
                             cg['status'])

    def test_update_consistencygroup_remove_vol_delete_cg(self):
        ctxt = context.get_admin_context()

        # set up driver with default config
        mock_client = self.setup_driver()

        mock_volume = mock.MagicMock()
        volumes = [mock_volume]

        mock_client.getVolumes.return_value = {'total': 1, 'members': []}

        # mock return value of createVolume
        mock_client.createVolume.return_value = {
            'iscsiIqn': self.connector['initiator']}

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # create a consistency group
            group = self.fake_consistencygroup_object()
            cg = self.driver.create_consistencygroup(ctxt, group)
            self.assertEqual(fields.ConsistencyGroupStatus.AVAILABLE,
                             cg['status'])

            # add volume to consistency group
            cg = self.driver.update_consistencygroup(
                ctxt, group, add_volumes=[self.volume], remove_volumes=None)

            # remove volume from consistency group
            cg = self.driver.update_consistencygroup(
                ctxt, group, add_volumes=None, remove_volumes=[self.volume])

            # delete the consistency group
            group.status = fields.ConsistencyGroupStatus.DELETING
            cg, vols = self.driver.delete_consistencygroup(ctxt, group,
                                                           volumes)
            self.assertEqual(fields.ConsistencyGroupStatus.DELETING,
                             cg['status'])

    def test_create_cgsnapshot(self):
        ctxt = context.get_admin_context()

        # set up driver with default config
        mock_client = self.setup_driver()

        mock_client.getVolumes.return_value = {'total': 1, 'members': []}
        mock_client.getVolumeByName.return_value = {'id': self.volume_id}

        mock_snap = mock.MagicMock()
        mock_snap.volumeName = self.volume_name
        expected_snaps = [mock_snap]

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # create a consistency group
            group = self.fake_consistencygroup_object()
            cg = self.driver.create_consistencygroup(ctxt, group)
            self.assertEqual(fields.ConsistencyGroupStatus.AVAILABLE,
                             cg['status'])

            # create volume and add it to the consistency group
            self.driver.update_consistencygroup(
                ctxt, group, add_volumes=[self.volume], remove_volumes=None)

            # create the conistency group snapshot
            cgsnapshot = self.fake_cgsnapshot_object()
            cgsnap, snaps = self.driver.create_cgsnapshot(
                ctxt, cgsnapshot, expected_snaps)
            self.assertEqual('available', cgsnap['status'])

    def test_delete_cgsnapshot(self):
        ctxt = context.get_admin_context()

        # set up driver with default config
        mock_client = self.setup_driver()

        mock_client.getVolumes.return_value = {'total': 1, 'members': []}
        mock_client.getVolumeByName.return_value = {'id': self.volume_id}

        mock_snap = mock.MagicMock()
        mock_snap.volumeName = self.volume_name
        expected_snaps = [mock_snap]

        with mock.patch.object(hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                               '_create_client') as mock_do_setup:
            mock_do_setup.return_value = mock_client

            # create a consistency group
            group = self.fake_consistencygroup_object()
            cg = self.driver.create_consistencygroup(ctxt, group)
            self.assertEqual(fields.ConsistencyGroupStatus.AVAILABLE,
                             cg['status'])

            # create volume and add it to the consistency group
            self.driver.update_consistencygroup(
                ctxt, group, add_volumes=[self.volume], remove_volumes=None)

            # delete the consistency group snapshot
            cgsnapshot = self.fake_cgsnapshot_object()
            cgsnapshot.status = 'deleting'
            cgsnap, snaps = self.driver.delete_cgsnapshot(
                ctxt, cgsnapshot, expected_snaps)
            self.assertEqual('deleting', cgsnap['status'])

    @mock.patch.object(volume_types, 'get_volume_type')
    def test_create_volume_replicated_managed(self, _mock_get_volume_type):
        # set up driver with default config
        conf = self.default_mock_conf()
        conf.replication_device = self.repl_targets
        mock_client = self.setup_driver(config=conf)
        mock_client.createVolume.return_value = {
            'iscsiIqn': self.connector['initiator']}
        mock_client.doesRemoteSnapshotScheduleExist.return_value = False
        mock_replicated_client = self.setup_driver(config=conf)

        _mock_get_volume_type.return_value = {
            'name': 'replicated',
            'extra_specs': {
                'replication_enabled': '<is> True'}}

        with mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_client') as mock_do_setup, \
            mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_replication_client') as mock_replication_client:
            mock_do_setup.return_value = mock_client
            mock_replication_client.return_value = mock_replicated_client
            return_model = self.driver.create_volume(self.volume_replicated)

            expected = [
                mock.call.createVolume(
                    'fakevolume_replicated',
                    1,
                    units.Gi,
                    {'isThinProvisioned': True,
                     'clusterName': 'CloudCluster1'}),
                mock.call.doesRemoteSnapshotScheduleExist(
                    'fakevolume_replicated_SCHED_Pri'),
                mock.call.createRemoteSnapshotSchedule(
                    'fakevolume_replicated',
                    'fakevolume_replicated_SCHED',
                    1800,
                    '1970-01-01T00:00:00Z',
                    5,
                    'CloudCluster1',
                    5,
                    'fakevolume_replicated',
                    '1.1.1.1',
                    'foo1',
                    'bar2'),
                mock.call.logout()]

            mock_client.assert_has_calls(
                self.driver_startup_call_stack +
                expected)
            prov_location = '10.0.1.6:3260,1 iqn.1993-08.org.debian:01:222 0'
            rep_data = json.dumps({"location": HPELEFTHAND_API_URL})
            self.assertEqual({'replication_status': 'enabled',
                              'replication_driver_data': rep_data,
                              'provider_location': prov_location},
                             return_model)

    @mock.patch.object(volume_types, 'get_volume_type')
    def test_create_volume_replicated_unmanaged(self, _mock_get_volume_type):
        # set up driver with default config
        conf = self.default_mock_conf()
        conf.replication_device = self.repl_targets_unmgd
        mock_client = self.setup_driver(config=conf)
        mock_client.createVolume.return_value = {
            'iscsiIqn': self.connector['initiator']}
        mock_client.doesRemoteSnapshotScheduleExist.return_value = False
        mock_replicated_client = self.setup_driver(config=conf)

        _mock_get_volume_type.return_value = {
            'name': 'replicated',
            'extra_specs': {
                'replication_enabled': '<is> True'}}

        with mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_client') as mock_do_setup, \
            mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_replication_client') as mock_replication_client:
            mock_do_setup.return_value = mock_client
            mock_replication_client.return_value = mock_replicated_client
            return_model = self.driver.create_volume(self.volume_replicated)

            expected = [
                mock.call.createVolume(
                    'fakevolume_replicated',
                    1,
                    units.Gi,
                    {'isThinProvisioned': True,
                     'clusterName': 'CloudCluster1'}),
                mock.call.doesRemoteSnapshotScheduleExist(
                    'fakevolume_replicated_SCHED_Pri'),
                mock.call.createRemoteSnapshotSchedule(
                    'fakevolume_replicated',
                    'fakevolume_replicated_SCHED',
                    1800,
                    '1970-01-01T00:00:00Z',
                    5,
                    'CloudCluster1',
                    5,
                    'fakevolume_replicated',
                    '1.1.1.1',
                    'foo1',
                    'bar2'),
                mock.call.logout()]

            mock_client.assert_has_calls(
                self.driver_startup_call_stack +
                expected)
            prov_location = '10.0.1.6:3260,1 iqn.1993-08.org.debian:01:222 0'
            rep_data = json.dumps({"location": HPELEFTHAND_API_URL})
            self.assertEqual({'replication_status': 'enabled',
                              'replication_driver_data': rep_data,
                              'provider_location': prov_location},
                             return_model)

    @mock.patch.object(volume_types, 'get_volume_type')
    def test_delete_volume_replicated(self, _mock_get_volume_type):
        # set up driver with default config
        conf = self.default_mock_conf()
        conf.replication_device = self.repl_targets
        mock_client = self.setup_driver(config=conf)
        mock_client.getVolumeByName.return_value = {'id': self.volume_id}
        mock_client.getVolumes.return_value = {'total': 1, 'members': []}
        mock_replicated_client = self.setup_driver(config=conf)

        _mock_get_volume_type.return_value = {
            'name': 'replicated',
            'extra_specs': {
                'replication_enabled': '<is> True'}}

        with mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_client') as mock_do_setup, \
            mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_replication_client') as mock_replication_client:
            mock_do_setup.return_value = mock_client
            mock_replication_client.return_value = mock_replicated_client
            self.driver.delete_volume(self.volume_replicated)

            expected = [
                mock.call.deleteRemoteSnapshotSchedule(
                    'fakevolume_replicated_SCHED'),
                mock.call.getVolumeByName('fakevolume_replicated'),
                mock.call.deleteVolume(1)]
            mock_client.assert_has_calls(
                self.driver_startup_call_stack +
                expected)

    @mock.patch.object(volume_types, 'get_volume_type')
    def test_replication_enable_no_snapshot_schedule(self,
                                                     _mock_get_volume_type):
        # set up driver with default config
        conf = self.default_mock_conf()
        conf.replication_device = self.repl_targets
        mock_client = self.setup_driver(config=conf)
        mock_client.doesRemoteSnapshotScheduleExist.return_value = False
        mock_replicated_client = self.setup_driver(config=conf)

        _mock_get_volume_type.return_value = {
            'name': 'replicated',
            'extra_specs': {
                'replication_enabled': '<is> True'}}

        with mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_client') as mock_do_setup, \
            mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_replication_client') as mock_replication_client:
            mock_do_setup.return_value = mock_client
            mock_replication_client.return_value = mock_replicated_client
            return_model = self.driver.replication_enable(
                context.get_admin_context(),
                self.volume_replicated)

            expected = [
                mock.call.doesRemoteSnapshotScheduleExist(
                    'fakevolume_replicated_SCHED_Pri'),
                mock.call.createRemoteSnapshotSchedule(
                    'fakevolume_replicated',
                    'fakevolume_replicated_SCHED',
                    1800,
                    '1970-01-01T00:00:00Z',
                    5,
                    'CloudCluster1',
                    5,
                    'fakevolume_replicated',
                    '1.1.1.1',
                    'foo1',
                    'bar2')]
            mock_client.assert_has_calls(
                self.driver_startup_call_stack +
                expected)

            self.assertEqual({'replication_status': 'enabled'},
                             return_model)

    @mock.patch.object(volume_types, 'get_volume_type')
    def test_replication_enable_with_snapshot_schedule(self,
                                                       _mock_get_volume_type):
        # set up driver with default config
        conf = self.default_mock_conf()
        conf.replication_device = self.repl_targets
        mock_client = self.setup_driver(config=conf)
        mock_client.doesRemoteSnapshotScheduleExist.return_value = True
        mock_replicated_client = self.setup_driver(config=conf)

        _mock_get_volume_type.return_value = {
            'name': 'replicated',
            'extra_specs': {
                'replication_enabled': '<is> True'}}

        with mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_client') as mock_do_setup, \
            mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_replication_client') as mock_replication_client:
            mock_do_setup.return_value = mock_client
            mock_replication_client.return_value = mock_replicated_client
            return_model = self.driver.replication_enable(
                context.get_admin_context(),
                self.volume_replicated)

            expected = [
                mock.call.doesRemoteSnapshotScheduleExist(
                    'fakevolume_replicated_SCHED_Pri'),
                mock.call.startRemoteSnapshotSchedule(
                    'fakevolume_replicated_SCHED_Pri')]
            mock_client.assert_has_calls(
                self.driver_startup_call_stack +
                expected)

            self.assertEqual({'replication_status': 'enabled'},
                             return_model)

    @mock.patch.object(volume_types, 'get_volume_type')
    def test_replication_disable(self, _mock_get_volume_type):
        # set up driver with default config
        conf = self.default_mock_conf()
        conf.replication_device = self.repl_targets
        mock_client = self.setup_driver(config=conf)
        mock_replicated_client = self.setup_driver(config=conf)

        _mock_get_volume_type.return_value = {
            'name': 'replicated',
            'extra_specs': {
                'replication_enabled': '<is> True'}}

        with mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_client') as mock_do_setup, \
            mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_replication_client') as mock_replication_client:
            mock_do_setup.return_value = mock_client
            mock_replication_client.return_value = mock_replicated_client
            return_model = self.driver.replication_disable(
                context.get_admin_context(),
                self.volume_replicated)

            expected = [
                mock.call.stopRemoteSnapshotSchedule(
                    'fakevolume_replicated_SCHED_Pri')]
            mock_client.assert_has_calls(
                self.driver_startup_call_stack +
                expected)

            self.assertEqual({'replication_status': 'disabled'},
                             return_model)

    @mock.patch.object(volume_types, 'get_volume_type')
    def test_replication_disable_fail(self, _mock_get_volume_type):
        # set up driver with default config
        conf = self.default_mock_conf()
        conf.replication_device = self.repl_targets
        mock_client = self.setup_driver(config=conf)
        mock_client.stopRemoteSnapshotSchedule.side_effect = (
            Exception("Error: Could not stop remote snapshot schedule."))
        mock_replicated_client = self.setup_driver(config=conf)

        _mock_get_volume_type.return_value = {
            'name': 'replicated',
            'extra_specs': {
                'replication_enabled': '<is> True'}}

        with mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_client') as mock_do_setup, \
            mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_replication_client') as mock_replication_client:
            mock_do_setup.return_value = mock_client
            mock_replication_client.return_value = mock_replicated_client
            return_model = self.driver.replication_disable(
                context.get_admin_context(),
                self.volume_replicated)

            expected = [
                mock.call.stopRemoteSnapshotSchedule(
                    'fakevolume_replicated_SCHED_Pri')]
            mock_client.assert_has_calls(
                self.driver_startup_call_stack +
                expected)

            self.assertEqual({'replication_status': 'disable_failed'},
                             return_model)

    @mock.patch.object(volume_types, 'get_volume_type')
    def test_list_replication_targets(self, _mock_get_volume_type):
        # set up driver with default config
        conf = self.default_mock_conf()
        conf.replication_device = self.repl_targets
        mock_client = self.setup_driver(config=conf)
        mock_replicated_client = self.setup_driver(config=conf)

        _mock_get_volume_type.return_value = {
            'name': 'replicated',
            'extra_specs': {
                'replication_enabled': '<is> True'}}

        with mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_client') as mock_do_setup, \
            mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_replication_client') as mock_replication_client:
            mock_do_setup.return_value = mock_client
            mock_replication_client.return_value = mock_replicated_client
            return_model = self.driver.list_replication_targets(
                context.get_admin_context(),
                self.volume_replicated)

            targets = self.list_rep_targets
            self.assertEqual({'volume_id': 1,
                              'targets': targets},
                             return_model)

    @mock.patch.object(volume_types, 'get_volume_type')
    def test_replication_failover_managed(self, _mock_get_volume_type):
        ctxt = context.get_admin_context()
        # set up driver with default config
        conf = self.default_mock_conf()
        conf.replication_device = self.repl_targets
        mock_client = self.setup_driver(config=conf)
        mock_replicated_client = self.setup_driver(config=conf)
        mock_replicated_client.getVolumeByName.return_value = {
            'iscsiIqn': self.connector['initiator']}

        _mock_get_volume_type.return_value = {
            'name': 'replicated',
            'extra_specs': {
                'replication_enabled': '<is> True'}}

        with mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_client') as mock_do_setup, \
            mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_replication_client') as mock_replication_client:
            mock_do_setup.return_value = mock_client
            mock_replication_client.return_value = mock_replicated_client
            valid_target_device_id = (self.repl_targets[0]['target_device_id'])
            invalid_target_device_id = 'INVALID'

            # test invalid secondary target
            self.assertRaises(
                exception.VolumeBackendAPIException,
                self.driver.replication_failover,
                ctxt,
                self.volume_replicated,
                invalid_target_device_id)

            # test a successful failover
            return_model = self.driver.replication_failover(
                context.get_admin_context(),
                self.volume_replicated,
                valid_target_device_id)
            rep_data = json.dumps({"location": HPELEFTHAND_API_URL2})
            prov_location = '10.0.1.6:3260,1 iqn.1993-08.org.debian:01:222 0'
            self.assertEqual({'provider_location': prov_location,
                              'replication_driver_data': rep_data,
                              'host': FAKE_FAILOVER_HOST},
                             return_model)

    @mock.patch.object(volume_types, 'get_volume_type')
    def test_replication_failover_unmanaged(self, _mock_get_volume_type):
        ctxt = context.get_admin_context()
        # set up driver with default config
        conf = self.default_mock_conf()
        conf.replication_device = self.repl_targets_unmgd
        mock_client = self.setup_driver(config=conf)
        mock_replicated_client = self.setup_driver(config=conf)
        mock_replicated_client.getVolumeByName.return_value = {
            'iscsiIqn': self.connector['initiator']}

        _mock_get_volume_type.return_value = {
            'name': 'replicated',
            'extra_specs': {
                'replication_enabled': '<is> True'}}

        with mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_client') as mock_do_setup, \
            mock.patch.object(
                hpe_lefthand_iscsi.HPELeftHandISCSIDriver,
                '_create_replication_client') as mock_replication_client:
            mock_do_setup.return_value = mock_client
            mock_replication_client.return_value = mock_replicated_client
            valid_target_device_id = (self.repl_targets[0]['target_device_id'])
            invalid_target_device_id = 'INVALID'

            # test invalid secondary target
            self.assertRaises(
                exception.VolumeBackendAPIException,
                self.driver.replication_failover,
                ctxt,
                self.volume_replicated,
                invalid_target_device_id)

            # test a successful failover
            return_model = self.driver.replication_failover(
                context.get_admin_context(),
                self.volume_replicated,
                valid_target_device_id)
            rep_data = json.dumps({"location": HPELEFTHAND_API_URL2})
            prov_location = '10.0.1.6:3260,1 iqn.1993-08.org.debian:01:222 0'
            self.assertEqual({'provider_location': prov_location,
                              'replication_driver_data': rep_data},
                             return_model)
