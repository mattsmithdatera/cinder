# Copyright 2014 Datera
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

import mock

from cinder import context
from cinder import exception
from cinder.openstack.common import log as logging
from cinder import test
from cinder.volume import configuration as conf
from cinder.volume.drivers import datera


LOG = logging.getLogger(__name__)


class DateraVolumeTestCase(test.TestCase):

    def setUp(self):
        super(DateraVolumeTestCase, self).setUp()

        self.cfg = mock.Mock(spec=conf.Configuration)
        self.cfg.san_ip = '127.0.0.1'
        self.cfg.san_is_local = True
        self.cfg.datera_api_token = 'secret'
        self.cfg.datera_api_port = '7717'
        self.cfg.datera_api_version = '1'
        self.cfg.datera_num_replicas = '2'

        mock_exec = mock.Mock()
        mock_exec.return_value = ('', '')

        self.driver = datera.DateraDriver(execute=mock_exec,
                                          configuration=self.cfg)
        self.driver.set_initialized()
        self.volume = _stub_volume()
        self.api_patcher = mock.patch('cinder.volume.drivers.datera.'
                                      'DateraDriver._issue_api_request')
        self.mock_api = self.api_patcher.start()

        self.addCleanup(self.api_patcher.stop)

    def test_volume_create_success(self):
        self.mock_api.return_value = {
            'uuid': 'c20aba21-6ef6-446b-b374-45733b4883ba',
            'size': '1073741824',
            'name': 'volume-00000001',
            'parent': '00000000-0000-0000-0000-000000000000',
            'numReplicas': '2',
            'subType': 'IS_ORIGINAL'
        }
        self.assertIsNone(self.driver.create_volume(self.volume))

    def test_volume_create_fails(self):
        self.mock_api.side_effect = exception.DateraAPIException
        self.assertRaises(exception.DateraAPIException,
                          self.driver.create_volume, self.volume)

    def test_create_cloned_volume_success(self):
        self.mock_api.return_value = {
            'uuid': 'c20aba21-6ef6-446b-b374-45733b4883ba',
            'size': '1073741824',
            'name': 'volume-00000001',
            'parent': '7f91abfa-7964-41ed-88fc-207c3a290b4f',
            'numReplicas': '2',
            'subType': 'IS_CLONE'
        }
        source_volume = _stub_volume(
            id='7f91abfa-7964-41ed-88fc-207c3a290b4f',
            display_name='foo'
        )
        self.assertIsNone(self.driver.create_cloned_volume(self.volume,
                                                           source_volume))

    def test_create_cloned_volume_fails(self):
        self.mock_api.side_effect = exception.DateraAPIException
        source_volume = _stub_volume(
            id='7f91abfa-7964-41ed-88fc-207c3a290b4f',
            display_name='foo'
        )
        self.assertRaises(exception.DateraAPIException,
                          self.driver.create_cloned_volume, self.volume,
                          source_volume)

    def test_delete_volume_success(self):
        self.mock_api.return_value = {
            'uuid': 'c20aba21-6ef6-446b-b374-45733b4883ba',
            'size': '1073741824',
            'name': 'volume-00000001',
            'parent': '00000000-0000-0000-0000-000000000000',
            'numReplicas': '2',
            'subType': 'IS_ORIGINAL',
            'target': None
        }
        self.assertIsNone(self.driver.delete_volume(self.volume))

    def test_delete_volume_not_found(self):
        self.mock_api.side_effect = exception.NotFound
        self.assertIsNone(self.driver.delete_volume(self.volume))

    def test_delete_volume_fails(self):
        self.mock_api.side_effect = exception.DateraAPIException
        self.assertRaises(exception.DateraAPIException,
                          self.driver.delete_volume, self.volume)

    def test_ensure_export_success(self):
        self.mock_api.side_effect = self._generate_fake_api_request()
        ctxt = context.get_admin_context()
        expected = {
            'provider_location': '172.28.94.11:3260 iqn.2013-05.com.daterainc'
                                 ':c20aba21-6ef6-446b-b374-45733b4883ba--ST--'
                                 'storage-1:01:sn:34e5b20fbadd3abb 0'}
        self.assertEqual(expected, self.driver.ensure_export(ctxt,
                                                             self.volume))

    def test_ensure_export_fails(self):
        self.mock_api.side_effect = exception.DateraAPIException
        ctxt = context.get_admin_context()
        self.assertRaises(exception.DateraAPIException,
                          self.driver.ensure_export, ctxt, self.volume)

    def test_create_export_target_does_not_exist_success(self):
        self.mock_api.side_effect = self._generate_fake_api_request(
            targets_exist=False)
        ctxt = context.get_admin_context()
        expected = {
            'provider_location': '172.28.94.11:3260 iqn.2013-05.com.daterainc'
                                 ':c20aba21-6ef6-446b-b374-45733b4883ba--ST--'
                                 'storage-1:01:sn:34e5b20fbadd3abb 0'}

        self.assertEqual(expected, self.driver.create_export(ctxt,
                                                             self.volume))

    def test_create_export_fails(self):
        self.mock_api.side_effect = exception.DateraAPIException
        ctxt = context.get_admin_context()
        self.assertRaises(exception.DateraAPIException,
                          self.driver.create_export, ctxt, self.volume)

    def test_detach_volume_success(self):
        self.mock_api.return_value = {}
        ctxt = context.get_admin_context()
        volume = _stub_volume(status='in-use')
        self.assertIsNone(self.driver.detach_volume(ctxt, volume))

    def test_detach_volume_fails(self):
        self.mock_api.side_effect = exception.DateraAPIException
        ctxt = context.get_admin_context()
        volume = _stub_volume(status='in-use')
        self.assertRaises(exception.DateraAPIException,
                          self.driver.detach_volume, ctxt, volume)

    def test_detach_volume_not_found(self):
        self.mock_api.side_effect = exception.NotFound
        ctxt = context.get_admin_context()
        volume = _stub_volume(status='in-use')
        self.assertIsNone(self.driver.detach_volume(ctxt, volume))

    def test_create_snapshot_success(self):
        self.mock_api.return_value = {
            'uuid': '0bb34f0c-fea4-48e0-bf96-591120ac7e3c',
            'parent': 'c20aba21-6ef6-446b-b374-45733b4883ba',
            'subType': 'IS_SNAPSHOT',
            'numReplicas': 2,
            'size': '1073741824',
            'name': 'snapshot-00000001'
        }
        snapshot = _stub_snapshot(volume_id=self.volume['id'])
        self.assertIsNone(self.driver.create_snapshot(snapshot))

    def test_create_snapshot_fails(self):
        self.mock_api.side_effect = exception.DateraAPIException
        snapshot = _stub_snapshot(volume_id=self.volume['id'])
        self.assertRaises(exception.DateraAPIException,
                          self.driver.create_snapshot, snapshot)

    def test_delete_snapshot_success(self):
        snapshot = _stub_snapshot(volume_id=self.volume['id'])
        self.assertIsNone(self.driver.delete_snapshot(snapshot))

    def test_delete_snapshot_not_found(self):
        self.mock_api.side_effect = [_stub_snapshots, exception.NotFound]
        snapshot = _stub_snapshot(self.volume['id'])
        self.assertIsNone(self.driver.delete_snapshot(snapshot))

    def test_delete_snapshot_fails(self):
        self.mock_api.side_effect = exception.DateraAPIException
        snapshot = _stub_snapshot(volume_id=self.volume['id'])
        self.assertRaises(exception.DateraAPIException,
                          self.driver.delete_snapshot, snapshot)

    def test_create_volume_from_snapshot_success(self):
        self.mock_api.side_effect = [_stub_snapshots, None]
        snapshot = _stub_snapshot(volume_id=self.volume['id'])
        self.assertIsNone(
            self.driver.create_volume_from_snapshot(self.volume, snapshot))

    def test_create_volume_from_snapshot_fails(self):
        self.mock_api.side_effect = exception.DateraAPIException
        snapshot = _stub_snapshot(volume_id=self.volume['id'])
        self.assertRaises(exception.DateraAPIException,
                          self.driver.create_volume_from_snapshot, self.volume,
                          snapshot)

    def test_extend_volume_success(self):
        volume = _stub_volume(size=1)
        self.assertIsNone(self.driver.extend_volume(volume, 2))

    def test_extend_volume_fails(self):
        self.mock_api.side_effect = exception.DateraAPIException
        volume = _stub_volume(size=1)
        self.assertRaises(exception.DateraAPIException,
                          self.driver.extend_volume, volume, 2)

    def _generate_fake_api_request(self, targets_exist=True):
        def _fake_api_request(resource_type, method='get', resource=None,
                              body=None, action=None, sensitive=False):
            if resource_type.split('/')[-1] == 'storage-1':
                return stub_get_export
            elif resource_type == 'app_instances':
                return stub_app_instance
            elif resource_type.split('/')[-1] == 'c20aba21-6ef6-446b-b374-45733b4883ba':
                return stub_app_instance[
                    'c20aba21-6ef6-446b-b374-45733b4883ba']
        return _fake_api_request


stub_create_export = {
    "_ipColl": ["172.28.121.10", "172.28.120.10"],
    "acls": {},
    "activeServers": {"4594953e-f97f-e111-ad85-001e6738c0f0": "1"},
    "ctype": "TC_BLOCK_ISCSI",
    "endpointsExt1": {
        "4594953e-f97f-e111-ad85-001e6738c0f0": {
            "ipHigh": 0,
            "ipLow": "192421036",
            "ipStr": "172.28.120.11",
            "ipV": 4,
            "name": "",
            "network": 24
        }
    },
    "endpointsExt2": {
        "4594953e-f97f-e111-ad85-001e6738c0f0": {
            "ipHigh": 0,
            "ipLow": "192486572",
            "ipStr": "172.28.121.11",
            "ipV": 4,
            "name": "",
            "network": 24
        }
    },
    "inodes": {"c20aba21-6ef6-446b-b374-45733b4883ba": "1"},
    "name": "",
    "networkPort": 0,
    "serverAllocation": "TS_ALLOC_COMPLETED",
    "servers": {"4594953e-f97f-e111-ad85-001e6738c0f0": "1"},
    "targetAllocation": "TS_ALLOC_COMPLETED",
    "targetIds": {
        "4594953e-f97f-e111-ad85-001e6738c0f0": {
            "ids": [{
                "dev": None,
                "id": "iqn.2013-05.com.daterainc::01:sn:fc372bc0490b2dbe"
            }]
        }
    },
    "typeName": "TargetIscsiConfig",
    "uuid": "7071efd7-9f22-4996-8f68-47e9ab19d0fd"
}

_stub_snapshots = {
    "1445384931.322468627": {
        "op_state": "available",
        "path": "/app_instances/c20aba21-6ef6-446b"
                "-b374-45733b4883ba/storage_instances"
                "/storage-1/volumes/volume-1/snapshots"
                "/1445384931.322468627",
        "uuid": "0bb34f0c-fea4-48e0-bf96-591120ac7e3c"
    }
}


stub_app_instance = {
    "c20aba21-6ef6-446b-b374-45733b4883ba": {
        "admin_state": "online",
        "clone_src": {},
        "create_mode": "openstack",
        "descr": "",
        "health": "ok",
        "name": "c20aba21-6ef6-446b-b374-45733b4883ba",
        "path": "/app_instances/c20aba21-6ef6-446b-b374-45733b4883ba",
        "storage_instances": {
            "storage-1": {
                "access": {
                    "ips": [
                        "172.28.94.11"
                    ],
                    "iqn": "iqn.2013-05.com.daterainc:c20aba21-6ef6-446b-"
                           "b374-45733b4883ba--ST--storage-1:01:sn:"
                           "34e5b20fbadd3abb",
                    "path": "/app_instances/c20aba21-6ef6-446b-b374"
                            "-45733b4883ba/storage_instances/storage-1/access"
                },
                "access_control": {
                    "initiator_groups": [],
                    "initiators": [],
                    "path": "/app_instances/c20aba21-6ef6-446b-b374-"
                            "45733b4883ba/storage_instances/storage-1"
                            "/access_control"
                },
                "access_control_mode": "allow_all",
                "active_initiators": [],
                "active_storage_nodes": [
                    "/storage_nodes/1c4feac4-17c7-478b-8928-c76e8ec80b72"
                ],
                "admin_state": "online",
                "auth": {
                    "initiator_pswd": "",
                    "initiator_user_name": "",
                    "path": "/app_instances/c20aba21-6ef6-446b-b374-"
                            "45733b4883ba/storage_instances/storage-1/auth",
                    "target_pswd": "",
                    "target_user_name": "",
                    "type": "none"
                },
                "creation_type": "user",
                "descr": "c20aba21-6ef6-446b-b374-45733b4883ba__ST__storage-1",
                "name": "storage-1",
                "path": "/app_instances/c20aba21-6ef6-446b-b374-45733b4883ba/storage_instances/storage-1",
                "uuid": "b9897b84-149f-43c7-b19c-27d6af8fa815",
                "volumes": {
                    "volume-1": {
                        "capacity_in_use": 0,
                        "name": "volume-1",
                        "op_state": "available",
                        "path": "/app_instances/c20aba21-6ef6-446b-b374-"
                                "45733b4883ba/storage_instances/storage-1"
                                "/volumes/volume-1",
                        "replica_count": 3,
                        "size": 500,
                        "snapshot_policies": {},
                        "snapshots": {
                            "1445384931.322468627": {
                                "op_state": "available",
                                "path": "/app_instances/c20aba21-6ef6-446b"
                                        "-b374-45733b4883ba/storage_instances"
                                        "/storage-1/volumes/volume-1/snapshots"
                                        "/1445384931.322468627",
                                "uuid": "0bb34f0c-fea4-48e0-bf96-591120ac7e3c"
                            }
                        },
                        "uuid": "c20aba21-6ef6-446b-b374-45733b4883ba"
                    }
                }
            }
        },
        "uuid": "c20aba21-6ef6-446b-b374-45733b4883ba"
    }
}


stub_get_export = stub_app_instance[
    'c20aba21-6ef6-446b-b374-45733b4883ba']['storage_instances']['storage-1']


def _stub_volume(*args, **kwargs):
    uuid = 'c20aba21-6ef6-446b-b374-45733b4883ba'
    name = 'volume-00000001'
    size = 1
    volume = {}
    volume['id'] = kwargs.get('id', uuid)
    volume['display_name'] = kwargs.get('display_name', name)
    volume['size'] = kwargs.get('size', size)
    volume['provider_location'] = kwargs.get('provider_location', None)
    return volume


def _stub_snapshot(*args, **kwargs):
    uuid = '0bb34f0c-fea4-48e0-bf96-591120ac7e3c'
    name = 'snapshot-00000001'
    volume = {}
    volume['id'] = kwargs.get('id', uuid)
    volume['display_name'] = kwargs.get('display_name', name)
    volume['volume_id'] = kwargs.get('volume_id', None)
    return volume
