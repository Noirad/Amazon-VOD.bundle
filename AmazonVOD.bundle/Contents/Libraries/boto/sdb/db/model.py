# Copyright (c) 2006,2007,2008 Mitch Garnaat http://garnaat.org/
#
# Permission is hereby granted, free of charge, to any person obtaining a
# copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish, dis-
# tribute, sublicense, and/or sell copies of the Software, and to permit
# persons to whom the Software is furnished to do so, subject to the fol-
# lowing conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
# OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABIL-
# ITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT
# SHALL THE AUTHOR BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, 
# WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

from boto.sdb.db.manager import get_manager
from boto.sdb.db.property import *
from boto.sdb.db.key import Key
from boto.sdb.db.query import Query
import boto

class ModelMeta(type):
    "Metaclass for all Models"

    def __init__(cls, name, bases, dict):
        super(ModelMeta, cls).__init__(name, bases, dict)
        # Make sure this is a subclass of Model - mainly copied from django ModelBase (thanks!)
        cls.__sub_classes__ = []
        try:
            if filter(lambda b: issubclass(b, Model), bases):
                for base in bases:
                    base.__sub_classes__.append(cls)
                cls._manager = get_manager(cls)
                # look for all of the Properties and set their names
                for key in dict.keys():
                    if isinstance(dict[key], Property):
                        property = dict[key]
                        property.__property_config__(cls, key)
                prop_names = []
                props = cls.properties()
                for prop in props:
                    if not prop.__class__.__name__.startswith('_'):
                        prop_names.append(prop.name)
                setattr(cls, '_prop_names', prop_names)
        except NameError:
            # 'Model' isn't defined yet, meaning we're looking at our own
            # Model class, defined below.
            pass
        
class Model(object):
    __metaclass__ = ModelMeta

    @classmethod
    def get_lineage(cls):
        l = [c.__name__ for c in cls.mro()]
        l.reverse()
        return '.'.join(l)

    @classmethod
    def kind(cls):
        return cls.__name__
    
    @classmethod
    def _get_by_id(cls, id, manager=None):
        if not manager:
            manager = cls._manager
        return manager.get_object(cls, id)
            
    @classmethod
    def get_by_id(cls, ids=None, parent=None):
        if isinstance(ids, list):
            objs = [cls._get_by_id(id) for id in ids]
            return objs
        else:
            return cls._get_by_id(ids)

    get_by_ids = get_by_id

    @classmethod
    def get_by_key_name(cls, key_names, parent=None):
        raise NotImplementedError, "Key Names are not currently supported"

    @classmethod
    def find(cls, **params):
        q = Query(cls)
        for key, value in params.items():
            q.filter('%s =' % key, value)
        return q

    @classmethod
    def lookup(cls, name, value):
        return cls._manager.lookup(cls, name, value)

    @classmethod
    def all(cls, max_items=None):
        return cls.find()

    @classmethod
    def get_or_insert(key_name, **kw):
        raise NotImplementedError, "get_or_insert not currently supported"
            
    @classmethod
    def properties(cls, hidden=True):
        properties = []
        while cls:
            for key in cls.__dict__.keys():
                prop = cls.__dict__[key]
                if isinstance(prop, Property):
                    if hidden or not prop.__class__.__name__.startswith('_'):
                        properties.append(prop)
            if len(cls.__bases__) > 0:
                cls = cls.__bases__[0]
            else:
                cls = None
        return properties

    @classmethod
    def find_property(cls, prop_name):
        property = None
        while cls:
            for key in cls.__dict__.keys():
                prop = cls.__dict__[key]
                if isinstance(prop, Property):
                    if not prop.__class__.__name__.startswith('_') and prop_name == prop.name:
                        property = prop
            if len(cls.__bases__) > 0:
                cls = cls.__bases__[0]
            else:
                cls = None
        return property

    @classmethod
    def get_xmlmanager(cls):
        if not hasattr(cls, '_xmlmanager'):
            from boto.sdb.db.manager.xmlmanager import XMLManager
            cls._xmlmanager = XMLManager(cls, None, None, None,
                                         None, None, None, None, False)
        return cls._xmlmanager

    @classmethod
    def from_xml(cls, fp):
        xmlmanager = cls.get_xmlmanager()
        return xmlmanager.unmarshal_object(fp)

    def __init__(self, id=None, **kw):
        self._loaded = False
        # first initialize all properties to their default values
        for prop in self.properties(hidden=False):
            setattr(self, prop.name, prop.default_value())
        if kw.has_key('manager'):
            self._manager = kw['manager']
        self.id = id
        for key in kw:
            if key != 'manager':
                setattr(self, key, kw[key])

    def __repr__(self):
        return '%s<%s>' % (self.__class__.__name__, self.id)

    def __str__(self):
        return str(self.id)
    
    def __eq__(self, other):
        return other and isinstance(other, Model) and self.id == other.id

    def _get_raw_item(self):
        return self._manager.get_raw_item(self)

    def load(self):
        if self.id and not self._loaded:
            self._manager.load_object(self)

    def put(self):
        self._manager.save_object(self)

    save = put
        
    def delete(self):
        self._manager.delete_object(self)

    def key(self):
        return Key(obj=self)

    def set_manager(self, manager):
        self._manager = manager

    def to_dict(self):
        props = {}
        for prop in self.properties(hidden=False):
            props[prop.name] = getattr(self, prop.name)
        obj = {'properties' : props,
               'id' : self.id}
        return {self.__class__.__name__ : obj}

    def to_xml(self, doc=None):
        xmlmanager = self.get_xmlmanager()
        doc = xmlmanager.marshal_object(self, doc)
        return doc

class Expando(Model):

    def __setattr__(self, name, value):
        if name in self._prop_names:
            object.__setattr__(self, name, value)
        elif name.startswith('_'):
            object.__setattr__(self, name, value)
        elif name == 'id':
            object.__setattr__(self, name, value)
        else:
            self._manager.set_key_value(self, name, value)
            object.__setattr__(self, name, value)

    def __getattr__(self, name):
        if not name.startswith('_'):
            value = self._manager.get_key_value(self, name)
            if value:
                object.__setattr__(self, name, value)
                return value
        raise AttributeError

    
