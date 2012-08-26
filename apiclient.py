## Import library functions
from urllib import quote_plus
from urllib2 import build_opener, quote
from sys import exit
from datetime import datetime, timedelta
from toodledodata import ToodledoData

try:
    import xml.etree.cElementTree as ET
except ImportError:
    try:
        import elementtree.ElementTree as ET
    except ImportError:
        exit("poodledo requires either Python 2.5+, or the ElementTree module installed.")

try:
    from hashlib import md5
except ImportError:
    from md5 import md5

try:
    from json import dumps
except ImportError:
    try:
        from simplejson import dumps
    except ImportError:
        exit("poodledo requires either Python 2.6+, or the simplejson module installed.")

## Expose the ApiClient and error classes for importing
__all__ = ['ApiClient', 'ToodledoError', 'PoodledoError']

class ToodledoError(Exception):
    ''' Error return from Toodledo API server'''
    def __init__(self, error_msg):
        self.msg = error_msg

    def __str__(self):
        return "Toodledo server returned error: %s" % self.msg

class PoodledoError(Exception):
    '''Error internal to the Poodledo library'''
    def __init__(self, msg):
        self.msg = msg

    def __repr__(self):
        return 'PoodledoError("%s")' % self.msg

    def __str__(self):
        return self.msg

def returns_list(f):
    '''A decorator that converts the API output to a list of L{ToodledoData} objects'''
    def fn(self, **kwargs):
        return [ ToodledoData(elem) for elem in f(self, **kwargs) ]
    return fn

def returns_item(f):
    '''A decorator that converts the API output to a L{ToodledoData} object'''
    def fn(self, **kwargs):
        return ToodledoData(f(self, **kwargs))
    return fn

def check_api_key(f):
    ''' A decorator that makes the decorated function check for a API key'''
    def fn(*args, **kwargs):
        self = args[0]
        # check if key is set to a value in kwargs
        if 'key' in kwargs and kwargs['key'] is not None:
            return f(*args, **kwargs)
        else:
            # try to get the key from the class
            if self._key is not None:
                kwargs['key'] = self._key
                return f(*args, **kwargs)
            # no key in kwargs or in class; die
            else:
                raise PoodledoError('need API key to call function %s; call authenticate()' % f.__name__)
    return fn

class ApiClient(object):
    ''' Toodledo API client'''
    _SERVICE_URL = 'api.toodledo.com/2'

    def __init__(self, key=None, app_id=None, app_token=None):
        ''' Initializes a new ApiClient w/o auth credentials'''
        self._key = key
        self.application_id = app_id
        self.application_token = app_token
        self._urlopener = build_opener()
        self._userid = None
        self._token = None
        self._pro = None

        # caches
        self._contexts_cache = None
        self._folders_cache = None
        self._goals_cache = None
        self._locations_cache = None
        self._notebooks_cache = None
        self._tasks_cache = None

    @property
    def userid(self):
        '''Property for accessing the cached userid'''
        if self._userid is None:
            raise KeyError('userid not set! call authenticate()')
        return self._userid
    @property
    def token(self):
        '''Property for accessing the cached token'''
        if self._token is None:
            raise KeyError('token not set! call authenticate()')
        return self._token
    @property
    def key(self):
        '''Property for accessing the cached session key'''
        if self._key is None:
            raise KeyError('key not set! call authenticate()')
        return self._key

    def _call(self, **kwargs):
        '''Performs the actual API call and parses the output'''
        url = self._create_url(f='xml', **kwargs)
        stream = self._urlopener.open(url)
        root_node = ET.parse(stream).getroot()
        if root_node.tag == 'error':
            raise ToodledoError(root_node.text)
        return root_node

    def _create_url(self, kind=None, action=None, **kwargs):
        ''' Creates a request url by appending key-value pairs to the SERVICE_URL'''
        url = ApiClient._SERVICE_URL

        # these three API calls always allow https
        if (kind == 'account' and action in ['create', 'lookup', 'token']):
            url = 'https://' + url
        # this API call is used for isPro, thus we can't know whether https is allowed
        elif (kind == 'account' and action == 'get'):
            url = 'http://' + url
        else:
            url = (self.isPro() and 'https://' or 'http://') + url

        url = "%s/%s/%s.php?" % (url, kind, action)

        # add args to url (key1=value1&key2=value2);
        newlist = []
        for item in sorted(kwargs):
            if isinstance(kwargs[item], bool):
                # translate boolean values to 0/1
                newlist.append(item + '=' + str(int(kwargs[item])))
            elif isinstance(kwargs[item], list):
                newlist.append(item + '=' + quote_plus(dumps(kwargs[item], separators=('%2C','%3A')), safe='"[]{}%'))
            elif isinstance(kwargs[item], dict):
                # translate dict to key=value pairs
                for k, v in kwargs[item].iteritems():
                    newlist.append(k + '=' + quote_plus(dumps(v, separators=('%2C','%3A')), safe='"[]{}%'))
            else:
                # trailing underscores are stripped from items to allow
                # items like pass_ (which is a python keyword)
                newlist.append(item.rstrip('_') + '=' + quote(str(kwargs[item]), safe=","))
        url += '&'.join(newlist)
        return url

    ###
    # Authentication
    ###
    def authenticate(self, email, passwd):
        '''Uses credentials to get userid, token and auth key.'''
        self._userid = bool(self._userid) and self._userid or self.getUserid(email, passwd)
        self._token = bool(self._token) and self._token or self.getToken(self._userid)
        self._key = bool(self._key) and self._key or self.generateKey(self._token, self.application_token, passwd)

    @property
    def isAuthenticated(self):
        '''Returns whether the session has been authenticated.'''
        return bool(self._key)

    def getUserid(self, email, passwd):
        '''Translates an email address and password into a hashed userid'''
        userid = self._call(
            kind='account', action='lookup',
            appid=self.application_id,
            sig=md5(email + self.application_token).hexdigest(),
            email=email, pass_=passwd).text
        if userid == '1':
            raise ToodledoError('invalid username/password')
        return userid

    def getToken(self, userid=None):
        '''Gets a hashed user identification token from the API.'''
        return self._call(kind='account', action='token', userid=userid, appid=self.application_id, sig=md5(userid + self.application_token).hexdigest()).text

    def generateKey(self, userid, token, passwd):
        '''Generates a session key as specified in the API docs'''
        return md5(md5(passwd).hexdigest() + token + userid).hexdigest()

    ###
    # Misc
    ###
    def createAccount(self, email, pass_):
        '''Creates a new account.
        @return: userid - 15 or 16 character hexidecimal string
        '''
        return self._call(method='createAccount', email=_email, pass_=pass_).text

    @check_api_key
    @returns_item
    def getAccountInfo(self, key=None):
        '''Retrieves account information (like pro, timezone, and lastedit_task).'''
        return self._call(key=self._key, kind='account', action='get')

    def isPro(self):
        '''Shows whether the account is a Pro account (enabling HTTPS API and subtasks).'''
        if self._pro is None:
            self._pro = self.getAccountInfo().pro
        return self._pro

    ###
    # Dispatch
    ###
    def dispatchCall(self, kind, action):
        dt = {
            'folder': {
                'add': self.addFolder,
                'delete': self.deleteFolder,
                'edit': self.editFolder,
                'get': self.getFolder,
                'getall': self.getFolders
            },
            'context': {
                'add': self.addContext,
                'delete': self.deleteContext,
                'edit': self.editContext,
                'get': self.getContext,
                'getall': self.getContexts
            },
            'goal': {
                'add': self.addGoal,
                'delete': self.deleteGoal,
                'edit': self.editGoal,
                'get': self.getGoal,
                'getall': self.getGoals
            },
            'location': {
                'add': self.addLocation,
                'delete': self.deleteLocation,
                'edit': self.editLocation,
                'get': self.getLocation,
                'getall': self.getLocations
            },
            'notebook': {
                'add': self.addNotebook,
                'delete': self.deleteNotebook,
                'edit': self.editNotebook,
                'get': self.getNotebook,
                'getall': self.getNotebooks
            },
            'task': {
                'add': self.addTask,
                'delete': self.deleteTask,
                'edit': self.editTask,
                'get': self.getTask,
                'getall': self.getTasks
            }
        }
        return dt[kind][action]

    ###
    # Translate
    ###
    def translate(self, field, value):
        if field == 'status':
            statuses = [
                'none',
                'next action',
                'active',
                'planning',
                'delegated',
                'waiting',
                'hold',
                'postponed',
                'someday',
                'canceled',
                'reference'
                ]

            lval = value.lower()
            if lval in statuses:
                return statuses.index(lval)
            return 0

        if field in ['folder', 'context', 'goal', 'location']:
            try:
                fid = getattr(self.dispatchCall(field, 'get')(value), 'id')
            except PoodledoError:
                fid = 0
            return fid

        return value

    ###
    # Folders
    ###
    @check_api_key
    def addFolder(self, name, key=None, **kwargs):
        '''Adds a new folder.
        @param name: The new folder's name
        @type name: C{str}
        @keyword private: The new folder's private flag; off (i.e. public) by default
        @type private: C{bool}
        '''
        self._folders_cache = None
        return self._call(key=key, kind='folders', action='add', name=name, **kwargs).text

    @check_api_key
    def deleteFolder(self, label, key=None):
        '''Deletes an existing folder.
        @param label: The folder's name, id, or C{ToodledoData} object; anything L{getFolder} would accept.
        @type label: C{str}/C{int}/C{ToodledoData}
        @raise PoodledoError: Throws an error if the folder does not exist
        '''
        id_ = self.getFolder(label).id
        self._folders_cache = None
        return self._call(key=key, kind='folders', action='delete', id_=id_).text

    @check_api_key
    def editFolder(self, label, key=None, **kwargs):
        '''Edits the parameters of an existing folder.
        @param label: The folder's name, id, or C{ToodledoData} object; anything L{getFolder} would accept.
        @type label: C{str}/C{int}/C{ToodledoData}
        @keyword name: The folder's new name
        @type name: C{str}
        @keyword private: The folder's private flag
        @type private: C{bool}
        @raise PoodledoError: Throws an error if the folder does not exist
        '''
        id_ = self.getFolder(label).id
        self._folders_cache = None
        return self._call(key=key, kind='folders', action='edit', id_=id_, **kwargs).text

    @check_api_key
    @returns_list
    def getFolders(self, key=None):
        '''Retrieves the folder listing from Toodledo and caches it
        locally for quick reference.
        '''
        if not self._folders_cache:
            self._folders_cache = self._call(key=key, kind='folders', action='get')
        return self._folders_cache

    def getFolder(self, label):
        '''Return a C{ToodledoData} object representing a folder.

        @param label: The folder's name, id, or a C{ToodledoData} object representing the folder.
        @type label: C{str}/C{int}/C{ToodledoData}
        @raise PoodledoError: Throws an error if the folder does not exist
        '''
        for f in self.getFolders():
            if str(label) == str(f.id) or \
                    label.lower() == f.name.lower() or \
                    (hasattr(label, 'id') and label.id == f.id):
                return f
        raise PoodledoError('A folder with that name/id does not exist!')

    ###
    # Contexts
    ###
    @check_api_key
    def addContext(self, name, key=None, **kwargs):
        '''Adds a new context.
        @param name: The new context's name
        @type name: C{str}
        '''
        self._contexts_cache = None
        return self._call(key=key, kind='contexts', action='add', name=name, **kwargs).text

    @check_api_key
    def deleteContext(self, label, key=None):
        '''Deletes an existing context.
        @param label: The context's name, id, or C{ToodledoData} object; anything L{getContext} would accept.
        @type label: C{str}/C{int}/C{ToodledoData}
        @raise PoodledoError: Throws an error if the context does not exist
        '''
        id_ = self.getContext(label).id
        self._contexts_cache = None
        return self._call(key=key, kind='contexts', action='delete', id_=id_).text

    @check_api_key
    def editContext(self, label, key=None, **kwargs):
        '''Edits the parameters of an existing context.
        @param label: The context's name, id, or C{ToodledoData} object; anything L{getContext} would accept.
        @type label: C{str}/C{int}/C{ToodledoData}
        @keyword name: The context's new name
        @type name: C{str}
        @raise PoodledoError: Throws an error if the context does not exist
        '''
        id_ = self.getContext(label).id
        self._contexts_cache = None
        return self._call(key=key, kind='contexts', action='edit', id_=id_, **kwargs).text

    @check_api_key
    @returns_list
    def getContexts(self, key=None):
        '''Retrieves the context listing from Toodledo and caches it
        locally for quick reference.
        '''
        if not self._contexts_cache:
            self._contexts_cache = self._call(key=key, kind='contexts', action='get')
        return self._contexts_cache

    def getContext(self, label):
        '''Return a C{ToodledoData} object representing a context.

        @param label: The context's name, id, or a C{ToodledoData} object representing the context.
        @type label: C{str}/C{int}/C{ToodledoData}
        @raise PoodledoError: Throws an error if the context does not exist
        '''
        for f in self.getContexts():
            if str(label) == str(f.id) or \
                    label.lower() == f.name.lower() or \
                    (hasattr(label, 'id') and label.id == f.id):
                return f
        raise PoodledoError('A context with that name/id does not exist!')

    ###
    # Goals
    ###
    @check_api_key
    def addGoal(self, name, key=None, **kwargs):
        '''Adds a new goal.
        @param name: The new goal's name
        @type name: C{str}
        @keyword archived: Whether the goal is archived
        @type archived: C{bool}
        @keyword level: The scope of the goal (0: Lifelong, 1: Long-term, 2: Short-term)
        @type level: C{int}
        @keyword note: Text describing the goal
        @type note: C{str}
        @keyword contributes: The id number of this goal's parent
        @type contributes: C{int}
        '''
        self._goals_cache = None
        return self._call(key=key, kind='goals', action='add', name=name, **kwargs).text

    @check_api_key
    def deleteGoal(self, label, key=None):
        '''Deletes an existing goal.
        @param label: The goal's name, id, or C{ToodledoData} object; anything L{getGoal} would accept.
        @type label: C{str}/C{int}/C{ToodledoData}
        @raise PoodledoError: Throws an error if the goal does not exist
        '''
        id_ = self.getGoal(label).id
        self._goals_cache = None
        return self._call(key=key, kind='goals', action='delete', id_=id_).text

    @check_api_key
    def editGoal(self, label, key=None, **kwargs):
        '''Edits the parameters of an existing goal.
        @param label: The goal's name, id, or C{ToodledoData} object; anything L{getGoal} would accept.
        @type label: C{str}/C{int}/C{ToodledoData}
        @keyword name: The goal's new name
        @type name: C{str}
        @keyword archived: Whether the goal is archived
        @type archived: C{bool}
        @keyword level: The scope of the goal (0: Lifelong, 1: Long-term, 2: Short-term)
        @type level: C{int}
        @keyword contributes: The id number of this goal's parent
        @type contributes: C{int}
        @raise PoodledoError: Throws an error if the goal does not exist
        '''
        id_ = self.getGoal(label).id
        self._goals_cache = None
        return self._call(key=key, kind='goals', action='edit', id_=id_, **kwargs).text

    @check_api_key
    @returns_list
    def getGoals(self, key=None):
        '''Retrieves the goal listing from Toodledo and caches it
        locally for quick reference.
        '''
        if not self._goals_cache:
            self._goals_cache = self._call(key=key, kind='goals', action='get')
        return self._goals_cache

    def getGoal(self, label):
        '''Return a C{ToodledoData} object representing a goal.

        @param label: The goal's name, id, or a C{ToodledoData} object representing the goal.
        @type label: C{str}/C{int}/C{ToodledoData}
        @raise PoodledoError: Throws an error if the goal does not exist
        '''
        for f in self.getGoals():
            if str(label) == str(f.id) or \
                    label.lower() == f.name.lower() or \
                    (hasattr(label, 'id') and label.id == f.id):
                return f
        raise PoodledoError('A goal with that name/id does not exist!')

    ###
    # Locations
    ###
    @check_api_key
    def addLocation(self, name, key=None, **kwargs):
        '''Adds a new location.
        @param name: The new location's name
        @type name: C{str}
        @keyword description: Description of the new location
        @type description: C{str}
        @keyword lat: The new location's latitude
        @type lat: C{float}
        @keyword lon: The new location's longitude
        @type lon: C{float}
        '''
        self._locations_cache = None
        return self._call(key=key, kind='locations', action='add', name=name, **kwargs).text

    @check_api_key
    def deleteLocation(self, label, key=None):
        '''Deletes an existing location.
        @param label: The location's name, id, or C{ToodledoData} object; anything L{getLocation} would accept.
        @type label: C{str}/C{int}/C{ToodledoData}
        @raise PoodledoError: Throws an error if the location does not exist
        '''
        id_ = self.getLocation(label).id
        self._locations_cache = None
        return self._call(key=key, kind='locations', action='delete', id_=id_).text

    @check_api_key
    def editLocation(self, label, key=None, **kwargs):
        '''Edits the parameters of an existing location.
        @param label: The location's name, id, or C{ToodledoData} object; anything L{getLocation} would accept.
        @type label: C{str}/C{int}/C{ToodledoData}
        @keyword name: The location's new name
        @type name: C{str}
        @keyword description: Description of the location
        @type description: C{str}
        @keyword lat: The location's latitude
        @type lat: C{float}
        @keyword lon: The location's longitude
        @type lon: C{float}
        @raise PoodledoError: Throws an error if the location does not exist
        '''
        id_ = self.getLocation(label).id
        self._locations_cache = None
        return self._call(key=key, kind='locations', action='edit', id_=id_, **kwargs).text

    @check_api_key
    @returns_list
    def getLocations(self, key=None):
        '''Retrieves the location listing from Toodledo and caches it
        locally for quick reference.
        '''
        if not self._locations_cache:
            self._locations_cache = self._call(key=key, kind='locations', action='get')
        return self._locations_cache

    def getLocation(self, label):
        '''Return a C{ToodledoData} object representing a location.

        @param label: The location's name, id, or a C{ToodledoData} object representing the location.
        @type label: C{str}/C{int}/C{ToodledoData}
        @raise PoodledoError: Throws an error if the location does not exist
        '''
        for f in self.getLocations():
            if str(label) == str(f.id) or \
                    label.lower() == f.name.lower() or \
                    (hasattr(label, 'id') and label.id == f.id):
                return f
        raise PoodledoError('A location with that name/id does not exist!')

    ###
    # Notebooks
    ###
    @check_api_key
    def addNotebook(self, title, key=None, **kwargs):
        '''Adds a new notebook.
        @param title: The new notebook's title
        @type title: C{str}
        @keyword text: The new notebook's text
        @type text: C{string}
        @keyword private: Whether the notebook is private
        @type private: C{bool}
        @keyword folder: The folder to which the notebook is attached
        @type folder: C{int}
        '''
        kwargs['title'] = title
        self._notebooks_cache = None
        return self._call(key=key, kind='notebooks', action='add', notebooks=[kwargs]).text

    @check_api_key
    def deleteNotebook(self, label, key=None):
        '''Deletes an existing notebook.
        @param label: The notebook's title, id, or C{ToodledoData} object; anything L{getNotebook} would accept.
        @type label: C{str}/C{int}/C{ToodledoData}
        @raise PoodledoError: Throws an error if the notebook does not exist
        '''
        id_ = self.getNotebook(label).id
        self._notebooks_cache = None
        return self._call(key=key, kind='notebooks', action='delete', notebooks=[id_]).text

    @check_api_key
    def editNotebook(self, label, key=None, **kwargs):
        '''Edits the parameters of an existing notebook.
        @param label: The notebook's title, id, or C{ToodledoData} object; anything L{getNotebook} would accept.
        @type label: C{str}/C{int}/C{ToodledoData}
        @param title: The notebook's new title
        @type title: C{str}
        @keyword text: The new notebook's text
        @type text: C{string}
        @keyword private: Whether the notebook is private
        @type private: C{bool}
        @keyword folder: The folder to which the notebook is attached
        @type folder: C{int}
        @raise PoodledoError: Throws an error if the notebook does not exist
        '''
        kwargs['id'] = self.getNotebook(label).id
        self._notebooks_cache = None
        return self._call(key=key, kind='notebooks', action='edit', notebooks=[kwargs]).text

    @check_api_key
    @returns_list
    def getDeletedNotes(self, after=0, key=None ):
        return self._call(key=key, kind='notebooks', action='deleted', after=after)

    @check_api_key
    @returns_list
    def getNotebooks(self, key=None):
        '''Retrieves the notebook listing from Toodledo and caches it
        locally for quick reference.
        '''
        if not self._notebooks_cache:
            self._notebooks_cache = self._call(key=key, kind='notebooks', action='get')
        return self._notebooks_cache

    def getNotebook(self, label):
        '''Return a C{ToodledoData} object representing a notebook.

        @param label: The notebook's name, id, or a C{ToodledoData} object representing the notebook.
        @type label: C{str}/C{int}/C{ToodledoData}
        @raise PoodledoError: Throws an error if the notebook does not exist
        '''
        for f in self.getNotebooks():
            if str(label) == str(f.id) or \
                    label.lower() == f.title.lower() or \
                    (hasattr(label, 'id') and label.id == f.id):
                return f
        raise PoodledoError('A notebook with that name/id does not exist!')

    ###
    # Tasks
    ###
    @check_api_key
    def addTask(self, title, key=None, **kwargs):
        '''Adds a new task.
        @param title: The new task's title
        @type title: C{str}
        @keyword text: The new task's text
        @type text: C{string}
        @keyword private: Whether the task is private
        @type private: C{bool}
        @keyword folder: The folder to which the task is attached
        @type folder: C{int}
        '''
        kwargs['title'] = title
        for field in kwargs: kwargs[field] = self.translate(field, kwargs[field])
        self._tasks_cache = None
        return self._call(key=key, kind='tasks', action='add', tasks=[kwargs]).text

    @check_api_key
    def deleteTask(self, label, key=None):
        '''Deletes an existing task.
        @param label: The task's title, id, or C{ToodledoData} object; anything L{getTask} would accept.
        @type label: C{str}/C{int}/C{ToodledoData}
        @raise PoodledoError: Throws an error if the task does not exist
        '''
        id_ = self.getTask(label).id
        self._tasks_cache = None
        return self._call(key=key, kind='tasks', action='delete', tasks=[id_]).text

    @check_api_key
    def editTask(self, label, key=None, **kwargs):
        '''Edits the parameters of an existing task.
        @param label: The task's title, id, or C{ToodledoData} object; anything L{getTask} would accept.
        @type label: C{str}/C{int}/C{ToodledoData}
        @param title: The task's new title
        @type title: C{str}
        @keyword text: The new task's text
        @type text: C{string}
        @keyword private: Whether the task is private
        @type private: C{bool}
        @keyword folder: The folder to which the task is attached
        @type folder: C{int}
        @raise PoodledoError: Throws an error if the task does not exist
        '''
        kwargs['id'] = self.getTask(label).id
        for field in kwargs: kwargs[field] = self.translate(field, kwargs[field])
        self._tasks_cache = None
        return self._call(key=key, kind='tasks', action='edit', tasks=[kwargs]).text

    @check_api_key
    @returns_list
    def getDeletedTasks(self, after=0, key=None):
        return self._call(key=key, kind='tasks', action='deleted', after=after)

    @check_api_key
    @returns_list
    def getTasks(self, cache=False, key=None, **kwargs):
        '''Retrieves the task listing.

        @keyword fields: Comma-separated list of fields to retrieve
        @type fields: C{str}
        @keyword cache: Whether to populate the local cache
        @type cache: C{bool}

        @keyword folder: id of the folder to place task in
        @type folder: C{int}
        @keyword context: context ID
        @type context: C{int}
        @keyword goal: goal ID
        @type goal: C{int}
        @keyword location: location ID
        @type location: C{int}
        @keyword tag: comma-separated string
        @keyword startdate: time_t
        @type startdate: C{time_t}
        @keyword duedate: time_t
        @type duedate: C{time_t}
        @keyword starttime: time_t
        @type starttime: C{time_t}
        @keyword duetime: time_t
        @type duetime: C{time_t}
        @keyword remind: int, minutes before duetime
        @keyword repeat: parseable string (every 6 months)
        @keyword status: Reference (10), Canceled (9), Active (2), Next Action (1),
        @keyword star: C{bool}
        @keyword priority: -1, 0, 1, 2, 3
        @keyword length: parseable string (4 hours) or minutes
        @keyword timer:
        @keyword note: unicode
        @keyword parent:
        @keyword children:
        @keyword order:
        '''
        if cache:
            kwargs['fields'] = "folder,context,goal,location,tag,startdate,duedate,duedatemod,starttime,duetime,remind,repeat,status,star,priority,length,timer,added,note,parent,children,order,meta"
            self._tasks_cache = self._call(key=key, kind='tasks', action='get', **kwargs)
            return self._tasks_cache
        elif self._tasks_cache:
            return self._tasks_cache
        else:
            return self._call(key=key, kind='tasks', action='get', **kwargs)

    def getTask(self, label, cache=False):
        '''Return a C{ToodledoData} object representing a task.
        @param label: The task's name, id, or a C{ToodledoData} object representing the task.
        @type label: C{str}/C{int}/C{ToodledoData}
        @raise PoodledoError: Throws an error if the task does not exist
        '''
        for f in self.getTasks(cache=cache):
            try:
                if int(label) == f.id: return f
            except ValueError:
                if label.lower() == f.title.lower(): return f
            except TypeError:
                if hasattr(label, 'id') and label.id == f.id: return f
        raise PoodledoError('A task with that name/id does not exist!')
