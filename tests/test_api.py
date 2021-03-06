import json
import unittest
from collections import Counter
from mock import patch
from bogus.server import Bogus

from swiftsuru import app, conf


class APITest(unittest.TestCase):

    def setUp(self):
        self.maxDiff = None
        self.client = app.test_client()
        self.content_type = "application/x-www-form-urlencoded"

    @patch("swiftsuru.api.SwiftsuruDBClient")
    @patch("swiftsuru.api.SwiftClient")
    @patch("swiftsuru.api.KeystoneClient")
    def test_add_instance(self, mock_keystoneclient, mock_swiftclient, mock_dbclient):
        mock_dbclient.return_value.get_plan.return_value = {'tenant': 'tenant_name'}
        mock_dbclient.retun_value.get_plan.retun_value = {'name': 'plan', 'tenant': 'tenant'}

        data = "name=myinstance&plan=small&team=myteam"
        response = self.client.post("/resources",
                                    data=data,
                                    content_type=self.content_type)

        self.assertEqual(response.status_code, 201)

        expected_username = 'myteam_myinstance'
        expected_role = conf.KEYSTONE_DEFAULT_ROLE

        self.assertTrue(mock_keystoneclient.return_value.create_user.called)
        _, _, kargs = mock_keystoneclient.return_value.create_user.mock_calls[0]

        self.assertEqual(kargs['name'], expected_username)
        self.assertEqual(kargs['role_name'], expected_role)
        self.assertEqual(len(kargs['password']), 8)
        self.assertEqual(kargs['enabled'], True)
        self.assertEqual(kargs['project_name'], 'tenant_name')

    def test_add_instance_should_have_a_plan(self):
        data = "name=mysql_instance&team=myteam"
        response = self.client.post("/resources",
                                    data=data,
                                    content_type=self.content_type)

        self.assertEqual(response.status_code, 500)

    @patch("swiftsuru.api.SwiftsuruDBClient")
    def test_remove_instance_returns_200(self, dbclient_mock):
        response = self.client.delete("/resources/my_instance")
        self.assertEqual(response.status_code, 200)

        _, _, kargs = dbclient_mock.return_value.remove_instance.mock_calls[0]
        expected = 'my_instance'
        computed = kargs.get('name')

        self.assertEqual(computed, expected)

    def _mock_confs(self, aclapi_url, conf_mock):
        conf_mock.ACLAPI_URL = aclapi_url
        conf_mock.KEYSTONE_HOST = "127.0.0.1"
        conf_mock.KEYSTONE_PORT = "5000"
        conf_mock.SWIFT_API_HOST = "10.1.2.3"
        conf_mock.SWIFT_API_PORT = "35357"

    def _keystoneclient_mock(self, k_mock):
        k_mock.return_value.get_storage_endpoints.return_value = {
            "adminURL": "http://localhost:35357",
            "publicURL": "http://localhost",
            "internalURL": "http://localhost"
        }

    @patch("swiftsuru.api.SwiftClient")
    @patch("swiftsuru.api.KeystoneClient")
    @patch("swiftsuru.api.SwiftsuruDBClient")
    @patch("swiftsuru.api.utils.conf")
    def test_bind_app_export_swift_enviroments_and_returns_201(self, conf_mock, dbclient_mock, keystoneclient_mock, swiftclient_mock):
        bog = Bogus()
        bog.register(("/api/ipv4/acl/10.4.3.2/24", lambda: ("{}", 200)),
                     method="PUT",
                     headers={"Location": "/api/jobs/1"})
        url = bog.serve()
        self._mock_confs(url, conf_mock)
        dbclient_mock.return_value.get_instance.return_value = {"name": 'instance_name',
                                                                "team": 'intance_team',
                                                                "container": 'intance_container',
                                                                "plan": 'intance_plan',
                                                                "user": 'intance_user',
                                                                "password": 'instance_password'}

        dbclient_mock.return_value.get_instance.return_value = {"name": 'plan_name',
                                                                "tenant": 'plan_tenant',
                                                                "description": 'plan_desc'}

        self._keystoneclient_mock(keystoneclient_mock)

        data = "app-host=myapp.cloud.tsuru.io&unit-host=10.4.3.2"
        response = self.client.post("/resources/instance_name/bind-app",
                                    data=data,
                                    content_type=self.content_type)

        self.assertEqual(response.status_code, 201)

        expected_keys = ["SWIFT_ADMIN_URL",
                         "SWIFT_PUBLIC_URL",
                         "SWIFT_INTERNAL_URL",
                         "SWIFT_AUTH_URL",
                         "SWIFT_CONTAINER",
                         "SWIFT_TENANT",
                         "SWIFT_USER",
                         "SWIFT_PASSWORD"]

        computed = json.loads(response.get_data())

        self.assertEquals(len(computed), len(expected_keys))

        for key in expected_keys:
            self.assertIn(key, computed.keys())

    @patch("swiftsuru.api.SwiftClient.set_cors")
    @patch("swiftsuru.api.KeystoneClient")
    @patch("swiftsuru.api.SwiftsuruDBClient")
    @patch("swiftsuru.api.utils.conf")
    def test_bind_app_should_set_cors(self, conf_mock, dbclient_mock, keystoneclient_mock, set_cors_mock):

        dbclient_mock.return_value.get_instance.return_value = {"name": 'instance_name',
                                                                "team": 'intance_team',
                                                                "container": 'intance_container',
                                                                "plan": 'intance_plan',
                                                                "user": 'intance_user',
                                                                "password": 'instance_password'}

        self._keystoneclient_mock(keystoneclient_mock)

        data = "app-host=myapp.cloud.tsuru.io&unit-host=10.4.3.2"
        _ = self.client.post("/resources/instance_name/bind-app",
                             data=data,
                             content_type=self.content_type)

        self.assertTrue(set_cors_mock.called)
        set_cors_mock.assert_called_once_with('intance_container', u'myapp.cloud.tsuru.io')

    @patch("swiftsuru.api.SwiftClient.set_cors")
    @patch("swiftsuru.api.KeystoneClient")
    @patch("swiftsuru.api.SwiftsuruDBClient")
    @patch("swiftsuru.api.conf")
    def test_bind_unit_should_not_set_cors(self, conf_mock, dbclient_mock, keystoneclient_mock, set_cors_mock):
        conf_mock.ENABLE_ACLAPI = False

        self._keystoneclient_mock(keystoneclient_mock)

        data = "app-host=myapp.cloud.tsuru.io&unit-host=10.4.3.2"
        _ = self.client.post("/resources/instance_name/bind",
                             data=data,
                             content_type=self.content_type)

        self.assertFalse(set_cors_mock.called)

    @patch("swiftsuru.api.KeystoneClient")
    @patch("swiftsuru.api.SwiftsuruDBClient")
    @patch("swiftsuru.api.utils.conf")
    def test_bind_unit_calls_aclapi_to_liberate_keystone_through_aclapiclient(self, conf_mock, dbclient_mock, keystoneclient_mock):
        self._keystoneclient_mock(keystoneclient_mock)
        bog = Bogus()
        bog.register(("/api/ipv4/acl/10.4.3.0/24", lambda: ("{}", 200)),
                     method="PUT",
                     headers={"Location": "/api/jobs/1"})
        url = bog.serve()
        self._mock_confs(url, conf_mock)
        data = "app-host=myapp.cloud.tsuru.io&unit-host=10.4.3.2"
        response = self.client.post("/resources/instance_name/bind",
                                    data=data,
                                    content_type=self.content_type)

        self.assertEqual(response.status_code, 201)
        self.assertIn("/api/ipv4/acl/10.4.3.0/24", bog.called_paths)

    @patch("swiftsuru.api.KeystoneClient")
    @patch("swiftsuru.api.SwiftsuruDBClient")
    @patch("swiftsuru.api.utils.conf")
    def test_bind_calls_aclapi_to_liberate_swift_through_aclapiclient(self, conf_mock, dbclient_mock, keystoneclient_mock):
        self._keystoneclient_mock(keystoneclient_mock)
        Bogus.called_paths = []
        bog = Bogus()
        bog.register(("/api/ipv4/acl/10.4.3.0/24", lambda: ("{}", 200)),
                     method="PUT",
                     headers={"Location": "/api/jobs/1"})
        url = bog.serve()
        self._mock_confs(url, conf_mock)
        data = "app-host=myapp.cloud.tsuru.io&unit-host=10.4.3.2"
        response = self.client.post("/resources/instance_name/bind",
                                    data=data,
                                    content_type=self.content_type)

        self.assertEqual(response.status_code, 201)
        self.assertIn("/api/ipv4/acl/10.4.3.0/24", bog.called_paths)
        count = Counter(bog.called_paths)
        self.assertEqual(count["/api/ipv4/acl/10.4.3.0/24"], 2)

    @patch("swiftsuru.api.KeystoneClient")
    @patch("swiftsuru.api.SwiftsuruDBClient")
    @patch("swiftsuru.api.conf")
    def test_bind_doesnt_call_aclapi_when_conf_is_false(self, conf_mock, dbclient_mock, keystoneclient_mock):
        self._keystoneclient_mock(keystoneclient_mock)
        Bogus.called_paths = []
        bog = Bogus()
        url = bog.serve()
        self._mock_confs(url, conf_mock)
        conf_mock.ENABLE_ACLAPI = False

        data = "app-host=myapp.cloud.tsuru.io&unit-host=10.4.3.2"
        response = self.client.post("/resources/instance_name/bind",
                                    data=data,
                                    content_type=self.content_type)
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("/api/ipv4/acl/10.4.3.2/24", bog.called_paths)

    @patch("swiftclient.client.Connection.get_auth")
    def test_unbind_returns_200(self, get_auth_mock):
        data = "app-host=awesomeapp.tsuru.io&unit-host=10.10.10.10"
        response = self.client.delete("/resources/my-swift/bind", data=data, content_type=self.content_type)
        self.assertEqual(response.status_code, 200)

    def test_healthcheck(self):
        response = self.client.get("/healthcheck")
        content = response.get_data()

        self.assertEqual(response.status_code, 200)
        self.assertIn(content, 'WORKING')

    @patch("swiftsuru.api.SwiftsuruDBClient")
    def test_list_plan(self, dbclient_mock):
        dbclient_mock.return_value.list_plans.return_value = [{'name': 'Infra',
                                         'description': 'Tenant para Infra'}]

        response = self.client.get("/resources/plans")
        self.assertEqual(response.status_code, 200)

        expected = [{u'name': u'Infra', u'description': u'Tenant para Infra'}]
        computed = json.loads(response.get_data())
        self.assertEqual(computed, expected)
