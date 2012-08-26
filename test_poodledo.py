#!/usr/bin/env python
# -*- coding: UTF-8 -*-

import sys
import os

import unittest
import urllib2
import time
from datetime import datetime,timedelta

from poodledo.apiclient import ApiClient, ToodledoError
from poodledo.cli import get_config


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
            # print url
            return open(self.url_map['default'],'r')

class MyTest(unittest.TestCase):


    def __init__(self, methodName='runTest'):
        self.mocked = True
        if not self.mocked:
            config = get_config()
            self.user_email = config.get('config', 'username')
            self.password = config.get('config', 'password')
            self.app_id = config.get('application', 'id')
            self.app_token = config.get('application', 'token')
        return super(MyTest, self).__init__(methodName)


    def setUp(self):
        if self.mocked:
            self.opener = MockOpener()
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
        api = ApiClient(app_id=self.app_id,app_token=self.app_token)
        if self.mocked:
            api._urlopener = self.opener
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

    def test_authenticate(self):
        api = self._createApiClient()

        api.authenticate(self.user_email, self.password)
        self.assertTrue( api.isAuthenticated )

    def test_getAccountInfo(self):
        api = self._createApiClient(True)
        info = api.getAccountInfo()
        self.assertEquals(info.unixtime, 1228476730)
        # self.assertEquals(info.date, 'Fri, 05 Dec 2008 05:32:10 -0600')
        if time.daylight:
            self.assertEquals(info.date, datetime(2008, 12, 5, 11, 32, 10) - timedelta(seconds=time.altzone))
        else:
            self.assertEquals(info.date, datetime(2008, 12, 5, 11, 32, 10) - timedelta(seconds=time.timezone))

        self.assertEquals(info.tokenexpires, 238.53)


def suite():
    loader = unittest.TestLoader()
    testsuite = loader.loadTestsFromTestCase(MyTest)
    return testsuite


if __name__ == '__main__':
    testsuite = suite()
    runner = unittest.TextTestRunner(sys.stdout, verbosity=2)
    result = runner.run(testsuite)
