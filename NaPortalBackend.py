#!/usr/bin/env python
# -*- coding: utf-8 -*-

import requests
import json
import subprocess
import time
import os
import argparse
import socket

def write_to_file(path, fname, data, timestamp=time.strftime("%Y%m%d-%H%M%S")):
    ''' Writes data to a file.
        The file name will be timestamp concatenated with _ concatenated with fname
        It will be stored in path
        Arguments: path = path to store file, fname = name of the file, data = data to write in file, timestamp = time '''
    if timestamp != '':
        timestamp = timestamp + '_'
    catalogs_file = open(path + timestamp + fname + '.json', "w")
    catalogs_file.write(data)
    catalogs_file.close()


def create_empty_dir(dir):
    ''' Checks if directory exists.
        Is directory doesn't exists, it will be created.
        If exists, all files inside the directory will be deleted. '''
    if os.path.isdir(dir):
        print dir + ' exists'
        for f in os.listdir(dir):
            print 'Removing ' + f + '...'
            file_path = os.path.join(dir, f)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print e
    else:
        os.makedirs(dir)
        print dir + ' created'


def check_create_dir(dir):
    ''' Checks if directory exists.
        Is directory doesn't exists, it will be created. '''
    if os.path.isdir(dir):
        print dir + ' exists'
    else:
        os.makedirs(dir)
        print dir + ' created'

def timestamp(self):
    return time.strftime("%Y%m%d-%H%M%S")


class NaPortalBackend:

    def __init__(self, ip, port=9015, debug=False):
        self.ip=ip
        self.port=port
        self.endpoint='http://'+self.ip+':'+str(self.port)
        self.headers={'Content-type': 'application/json'}
        self.debug=debug


    def list_catalog_entities(self):
        ''' Prints out all entities with format "entity_id : entity_name" '''
        entities_json = self.get_entities()
        entities = entities_json.json()['catEntities']['children']

        for entity in entities:
            print str(entity['id'])+' : '+entity['name']


    def get_entities(self):
        ''' Gets portal entity json '''
        entities_json = requests.get(self.endpoint+'/netwin/nacatalogs/entities-tree/6')

        if self.debug:
            print "\nDEBUG: get_entities\n"
            print entities_json.text.encode('utf-8')
        return entities_json


    def get_entity_id(self, catalog_name):
        ''' Get catalog id given the @catalog_name '''
        entities_json = self.get_entities()
        entities = entities_json.json()['catEntities']['children']

        id = ''
        for entity in entities:
            if entity['name'] == catalog_name:
                id = entity['id']

        if self.debug:
            print "\nDEBUG: get_entity_id("+catalog_name+")\n"
            print "ID of " + catalog_name + ": " + str(id)

        return id


    def get_entity_entries(self, catalog_name):
        ''' Gets portal catalog entries json given @catalog_name '''
        id = self.get_entity_id(catalog_name)
        entries_json = requests.get(self.endpoint+'/netwin/nacatalogs?$filter=idCatEntity eq '+str(id))

        if self.debug:
            print "\nDEBUG: get_entity_entries("+catalog_name+")\n"
            print entries_json.text.encode('utf-8')

        return entries_json.text.encode('utf-8')
        #return json.loads(entries_json)


    def get_catalog_entities(self, catalog_name):
        ''' Gets a list of all the entities associated with @catalog_name '''
        catalog_entities = requests.get(self.endpoint+'/netwin/catalog/entities-full?$filter=name eq \''+catalog_name+'\'')

        if self.debug:
            print "\nDEBUG: get_catalog_entities("+catalog_name+")\n"
            print catalog_entities.text.encode('utf-8')

        return catalog_entities


    def get_catalog_attributes_list(self, catalog_name, attribute_type):
        ''' Gets... '''
        catalog_entities = self.get_catalog_entities(catalog_name).json()['entities'][0]['attributes']

        enumeratedAttributeValues = {}
        for attribute in catalog_entities:
            if attribute['attributetype']['name'] == attribute_type:
                enumeratedAttributeValues = attribute['attributetype']['enumeratedattributevalues']
        return json.dumps(enumeratedAttributeValues)


    def create_catalog_entries(self, catalog_name, catalog_entries, attributeType, new_attribute):
        ''' Docs! '''
        newCatalogEntries = []
        elementsList=['name', 'state', 'externalCode', 'host', 'endpoint', 'info', 'nodeName', 'siteName', 'clusterName', 'siteType', 'username', 'password', 'keystore', 'keystorePassword']
        enumeratedAttributeValues=json.loads(self.get_catalog_attributes_list(catalog_name, attributeType))

        if self.debug:
            print "Catalog entries"
            print catalog_entries
            print "-----------\n\n"

            print "Enumerated"
            print enumeratedAttributeValues
            print "-----------\n\n"

        catalog_entries=json.loads(catalog_entries)
        for entry in catalog_entries['nacatalogs']:
            new_entry = dict()
            new_entry['idCatEntity'] = '-1'

            # copy all elements from entry to new_entry
            for element in elementsList:
                new_entry[element] = entry[element]

            real_element_id = entry[new_attribute]
            elementName = ''

            for attributeValue in enumeratedAttributeValues:
                if str(attributeValue['id']) == str(real_element_id):
                    elementName = attributeValue['value']
            elementEntry = '${attributetype§enumeratedattributevalues§' + attributeType + '§{0}'.format(elementName) + '}'

            # only save element if it is not "null"
            if not elementEntry.endswith('§}'):
                new_entry[new_attribute] = elementEntry

            newCatalogEntries.append(new_entry)

        if self.debug:
            print "\n\n-----------"
            print 'New catalog entries: ' + json.dumps(newCatalogEntries).decode('unicode-escape').encode('utf-8')
            print "-----------\n\n"

        create_empty_dir('beforeTranslate')
        create_empty_dir('afterTranslate')

        write_to_file('beforeTranslate', 'catalogsTranslate', json.dumps(newCatalogEntries).decode('unicode-escape').encode('utf-8'), '')

        translateCommand = '/opt/ptin/na-portal/bin/na-portal-catalog-template-translator/translate.sh -i ' + self.ip + ' -p ' + str(self.port) + ' -c ' + catalog_name + ' -s beforeTranslate' + ' -t afterTranslate'
        if self.debug:
            print "\n\n-----------"
            print 'Translate command: ' + translateCommand
            print "-----------\n\n"

        try:
            return_code = subprocess.call(translateCommand, shell=True)
        except Exception as e:
            return_code = str(e)

        if str(return_code) != '0':
            print return_code
            print 'Error while translating catalog'
            exit(1)

        # Read translated file
        catalogTranslatedTemp = open('afterTranslate' + 'catalogsTranslate.json', 'r')
        catalogTranslated = catalogTranslatedTemp.read()
        catalogTranslatedTemp.close()
        print 'Translated file: ' + catalogTranslated


    def update_entry(self, catalog_name, entry_name):
        pass


    def delete_entry(self, catalog_name, entry_name):
        pass


    def insert_entity(self, file_path, file_name, sca_connection, sca_path, sca_file):
        ''' Docs! '''
        endpoint = self.endpoint+'/netwin/catalog-entities'
        entity_file = open(file_path + '/' + file_name + '.json','r')
        insert_entity = requests.post(endpoint, headers=self.headers, data=entity_file)
        entity_file.close()
        # update SQL to make entity visible
        #sca_sql = file_name.split('.')[1].upper()
        #print sca_sql
        os.system('/opt/oracle-client/bin/sqlplus ' + sca_connection +' ' + sca_path + '/catEntity_'+sca_file+'.sql')

        if self.debug:
            print '\ninsert_entity result\n'
            print insert_entity.text.encode('utf-8')


    def delete_entity(self, entity_name):
        endpoint = self.endpoint+'/netwin/catalog-entities/'+entity_name
        delete_entity = requests.delete(endpoint, headers=self.headers)
        print '\nSystem Response (empty = success)\n'
        print delete_entity.text.encode('utf-8')


    def update_attribute_type(self, attribute_type, attribute_file):
        endpoint = self.endpoint+'/netwin/catalog-attributetypes/'+attribute_type
        attribute_file = open(attribute_file,'r')
        put_attribute = requests.put(endpoint, headers=self.headers, data=attribute_file)
        attribute_file.close()
        # update SQL to make entity visible
        #sca_sql = file_name.split('.')[1].upper()
        #print sca_sql
        #os.system('/opt/oracle-client/bin/sqlplus SCAG_USA/SCAG_USA@10.112.100.144:1521/omusatstdb1 /opt/ptin/solution/conf/solution-na-portal-conf/sca/catalogs/catEntity_'+sca_sql+'.sql')

        if self.debug:
            print '\nPUT RESULT\n'
            print put_attribute.text.encode('utf-8')

        # print 'Status code: ' + str(r.status_code) + '\nMessage: ' + r.reason
        #if str(r.status_code) != '204' and str(r.status_code) != '200':
        #    print 'Error with status code: ' + str(r.status_code) + '\nMessage: ' + r.reason


    def delete_entries(self, catalog_entries):
        catalog_entries=json.loads(catalog_entries)
        for instance in catalog_entries['nacatalogs']:
            endpoint = self.endpoint + '/netwin/nacatalogs/' + str(instance['id'])
            requests.delete(endpoint, headers=self.headers)


    def post_updated_entries(self):
        catalogTranslatedTemp = open('afterTranslate' + 'catalogsTranslate.json', 'r')
        catalogTranslated = catalogTranslatedTemp.read()
        catalogTranslatedTemp.close()
        catalogTranslatedJson = json.loads(catalogTranslated)
        for x in catalogTranslatedJson:
            endpoint = self.endpoint + '/netwin/nacatalogs/'
            requests.post(endpoint, headers=self.headers, data=json.dumps(x).decode('unicode-escape').encode('utf-8'))


    def insert_attribute_type(self, file_path, file_name):
        endpoint = self.endpoint+'/netwin/catalog-attributetypes'
        attribute_file = open(file_path + '/' + file_name + '.json','r')
        insert_attribute = requests.post(endpoint, headers=self.headers, data=attribute_file)

        if self.debug:
            print '\ninsert_attribute_type result\n'
            print insert_attribute.text.encode('utf-8')


    def delete_attribute_type(self):
        pass


    def connectivity_check(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((self.ip, self.port))
        sock.close()

        if result == 0:
           print "Connectivity check: port " + str(self.port) + " is open!"
        else:
           print "Connectivity check: port " + str(self.port) + " is not open!"


    def help(self):
        print '\nUseful portal links'
        print self.endpoint+'/netwin/nacatalogs/entities-tree/6'
        print self.endpoint+'/netwin/catalog-entities/'
        print self.endpoint+'/netwin/catalog-attributetypes/'
        print '\nEntities usual path:'
        print '/opt/ptin/solution/conf/solution-na-portal-conf/catalogs/entities'
        print '\nSCA usual path:'
        print '/opt/ptin/solution/conf/solution-na-portal-conf/sca/catalogs'


    def restart(self):
        print('Executing: sudo /etc/init.d/play-portal restart')
        os.system('./etc/init.d/play-portal restart')

'''
class CatalogEntity:
    def __init__(self, name):
        self.name=name

    def getEntities():


class CatalogAttribute:
    def __init__(self):
        self.
'''


#class Utils:
#    def __init__(self):
#        pass
