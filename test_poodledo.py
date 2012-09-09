#!/usr/bin/env python
# -*- coding: UTF-8 -*-
from pprint import pprint

import sys

import unittest
from datetime import datetime,timedelta

from poodledo.apiclient import ApiClient, ToodledoError
from poodledo.cli import get_config, store_config

cached_client = None


def tasks_to_dict(taskList):
    return dict((task.id,task) for task in taskList)

class MockOpener(object):
    def __init__(self):
        self.url_map = {}

    def add_file(self, url, fname):
        self.url_map[url] = fname

    def open(self,url):
        if url in self.url_map:
            return open(self.url_map[url],'r')
        else:
            raise AssertionError("Unexpected url requested:  "+url)

class PoodleDoTest(unittest.TestCase):
    def __init__(self, methodName='runTest'):
        self.mocked = True
        if not self.mocked:
            global cached_client
            config = get_config()
            self.user_email = config.get('config', 'username')
            self.password = config.get('config', 'password')
            self.app_id = config.get('application', 'id')
            self.app_token = config.get('application', 'token')
            if not cached_client:
                cached_client = ApiClient(app_id=self.app_id,app_token=self.app_token,cache_xml=True)
                config.set('cache','user_token',str(cached_client._key))
                store_config(config)
        super(PoodleDoTest, self).__init__(methodName)


    def setUp(self):
        self.opener = MockOpener()
        if self.mocked:
            self.opener.add_file('default', 'testdata/error.xml')
            self.opener.add_file(
                #   'https://api.toodledo.com/2/account/lookup.php?appid=PoodledoAppTest&email=test%40test.de&f=xml&pass=mypassword&sig=40f30694b091f2c98e8c192885604beb'
                    'https://api.toodledo.com/2/account/lookup.php?appid=PoodledoAppTest&email=test%40test.de&f=xml&pass=mypassword&sig=40f30694b091f2c98e8c192885604beb',
                    'testdata/getUserid_good.xml')
            self.opener.add_file(
                'https://api.toodledo.com/2/account/lookup.php?appid=PoodledoAppTest&email=test%40test.de&f=xml&pass=mypasswordwrong_password&sig=40f30694b091f2c98e8c192885604beb',
                'testdata/getUserid_bad.xml')
            self.opener.add_file(
                    'https://api.toodledo.com/2/account/token.php?appid=PoodledoAppTest&f=xml&sig=0bf850945b57d0a50c3eeabb2ec5fac3&userid=sampleuserid156',
                    'testdata/getToken_good.xml')
            self.opener.add_file(
                    'http://api.toodledo.com/2/account/get.php?f=xml&key=6f931665ef2604b76b82ae814aa9a686',
                    'testdata/getServerInfo.xml')

            self.user_email = 'test@test.de'
            self.password = 'mypassword'
            self.app_id = 'PoodledoAppTest'
            self.app_token = 'nonsensetoken'


    def _createApiClient(self,authenticate=False):
        if self.mocked:
            api = ApiClient(app_id=self.app_id,app_token=self.app_token)
            api._urlopener = self.opener
        else:
            api = cached_client
        if authenticate:
            api.authenticate(self.user_email, self.password)
        return api

    def test_getUserid(self):
        api = self._createApiClient()

        api.getUserid(self.user_email,self.password)
        self.assertRaises(ToodledoError, api.getUserid, self.user_email,self.password + 'wrong_password')

    def test_getToken(self):
        assert self.mocked, "This test only runs in mocked configuration"
        api = self._createApiClient()

        token = api.getToken('sampleuserid156')
        self.assertEquals(token, 'td493900752ca4d')

    def test__authenticate(self):
        """
        This task is a named with an extra underscore so that it can
        run in unmocked mode as long as the test runner sorts it to
        the top.  If your testrunner does not do that then this test
        should be expected to fail with the error
        "Already authenticated"
        """
        api = self._createApiClient()

        self.assertFalse( api.isAuthenticated,"Already authenticated")
        api.authenticate(self.user_email, self.password)
        self.assertTrue( api.isAuthenticated )

    def test_getAccountInfo(self):
        api = self._createApiClient(True)
        info = api.getAccountInfo()
        #test parse
        datetime.fromtimestamp(int(info.lastedit_task))-timedelta(hours = .5*int(info.timezone))
        if self.mocked:
            self.assertEquals(info.lastedit_task, '1228476730')
            assert not api.isPro()
        else:
            assert info.lastedit_task.isdigit()

    def test_getTasks(self):
        self.opener.add_file(
            'http://api.toodledo.com/2/tasks/get.php?f=xml&key=6f931665ef2604b76b82ae814aa9a686',
            'testdata/getTasks.xml'
        )
        api = self._createApiClient(True)
        tasks = api.getTasks()

        expected_tasks={43635427: {'completed': 0, 'id': 43635427, 'modified': 1345993845, 'title': u'Add some items to your todo list'},
                        43635429: {'completed': 0, 'id': 43635429, 'modified': 1345993845, 'title': u'Visit your Account Settings section and configure your account.'},
                        43649333: {'completed': 0, 'id': 43649333, 'modified': 1346000146, 'title': u'Test Task'}}
        self.assertEquals(len(tasks), len(expected_tasks))
        for task in tasks:
            assert all(expected_tasks[task.id][field] == getattr(task,field) for field in expected_tasks[task.id])

    def test_addDeleteTask(self):
        self.opener.add_file('http://api.toodledo.com/2/tasks/add.php?f=xml&key=6f931665ef2604b76b82ae814aa9a686&tasks=[{"title"%3A"Added+task"}]',
            'testdata/addTask.xml')
        self.opener.add_file(
            'http://api.toodledo.com/2/tasks/get.php?f=xml&key=6f931665ef2604b76b82ae814aa9a686',
            'testdata/getTasks.xml'
        )

        api = self._createApiClient(True)
        tasksBefore = tasks_to_dict(api.getTasks())
        testTaskTitle = "Added task"
        api.addTask(title=testTaskTitle)


        self.opener.add_file(
            'http://api.toodledo.com/2/tasks/get.php?f=xml&key=6f931665ef2604b76b82ae814aa9a686',
            'testdata/getTasksPostAdd.xml'
        )
        tasksAfter = tasks_to_dict(api.getTasks())
        assert len(tasksAfter) - len(tasksBefore) == 1

        addedTask = tasksAfter[(set(tasksAfter)-set(tasksBefore)).pop()]
        assert addedTask.title == testTaskTitle,"Found added task:\n"+str(addedTask)

        self.opener.add_file('http://api.toodledo.com/2/tasks/delete.php?f=xml&key=6f931665ef2604b76b82ae814aa9a686&tasks=[46420424]',
            'testdata/deleteTask.xml')
        api.deleteTask(testTaskTitle)

        pprint(api._xml_cache)

        self.opener.add_file(
            'http://api.toodledo.com/2/tasks/get.php?f=xml&key=6f931665ef2604b76b82ae814aa9a686',
            'testdata/getTasks.xml'
        )
        assert len(api.getTasks()) == len(tasksBefore)

    def test_getEditTask(self):
        self.opener.add_file('http://api.toodledo.com/2/tasks/add.php?f=xml&key=6f931665ef2604b76b82ae814aa9a686&tasks=[{"title"%3A"Added+task"}]',
            'testdata/addTask.xml')
        self.opener.add_file(
            'http://api.toodledo.com/2/tasks/get.php?f=xml&fields=note&key=6f931665ef2604b76b82ae814aa9a686',
            'testdata/getTasksNote.xml'
        )
        self.opener.add_file('http://api.toodledo.com/2/tasks/edit.php?f=xml&key=6f931665ef2604b76b82ae814aa9a686&tasks=[{"note"%3A"More+Text"%2C"id"%3A46420424}]',
            'testdata/editTask.xml')
        self.opener.add_file(
            'http://api.toodledo.com/2/tasks/get.php?f=xml&key=6f931665ef2604b76b82ae814aa9a686',
            'testdata/getTasksPostAdd.xml'
        )

        api = self._createApiClient(True)
        tasksBefore = tasks_to_dict(api.getTasks(fields='note'))
        testTaskTitle = "Added task"
        api.addTask(title=testTaskTitle)

        self.opener.add_file(
            'http://api.toodledo.com/2/tasks/get.php?f=xml&fields=note&key=6f931665ef2604b76b82ae814aa9a686',
            'testdata/getTasksPostAddNote.xml'
        )
        tasksAfter = tasks_to_dict(api.getTasks(fields='note'))
        self.assertEqual(len(tasksAfter) - len(tasksBefore),1)

        addedTask = tasksAfter[(set(tasksAfter)-set(tasksBefore)).pop()]
        assert addedTask.title == testTaskTitle,"Found added task:\n"+str(addedTask)
        self.assertEqual(addedTask.note,'None')

        api.editTask(testTaskTitle,note="More Text")

        pprint(api._xml_cache)
        self.opener.add_file(
            'http://api.toodledo.com/2/tasks/get.php?f=xml&fields=note&key=6f931665ef2604b76b82ae814aa9a686',
            'testdata/getTasksPostEditNote.xml'
        )
        postEdit = api.getTask(testTaskTitle,fields='note')
        pprint(api._xml_cache)

        pprint(postEdit)
        self.assertEquals(postEdit.note,"More Text")

        self.opener.add_file('http://api.toodledo.com/2/tasks/delete.php?f=xml&key=6f931665ef2604b76b82ae814aa9a686&tasks=[46420424]',
            'testdata/deleteTask.xml')
        api.deleteTask(testTaskTitle)


        self.opener.add_file(
            'http://api.toodledo.com/2/tasks/get.php?f=xml&key=6f931665ef2604b76b82ae814aa9a686',
            'testdata/getTasks.xml'
        )
        assert len(api.getTasks()) == len(tasksBefore)

def suite():
    loader = unittest.TestLoader()
    testsuite = loader.loadTestsFromTestCase(PoodleDoTest)
    return testsuite


if __name__ == '__main__':
    testsuite = suite()
    runner = unittest.TextTestRunner(sys.stdout, verbosity=2)
    result = runner.run(testsuite)
