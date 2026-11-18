#!/usr/bin/env python3
"""Backend helpers for the legacy command-line tools."""

import requests
import json
import subprocess
import os
import socket

def create_empty_dir(dir):
    ''' Checks if directory exists.
        Is directory doesn't exists, it will be created.
        If exists, all files inside the directory will be deleted. '''
    if os.path.isdir(dir):
        print(dir + ' exists')
        for f in os.listdir(dir):
            print('Removing ' + f + '...')
            file_path = os.path.join(dir, f)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(e)
    else:
        os.makedirs(dir)
        print(dir + ' created')


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
            print(str(entity['id'])+' : '+entity['name'])


    def get_entities(self):
        ''' Gets portal entity json '''
        entities_json = requests.get(self.endpoint+'/netwin/nacatalogs/entities-tree/6')

        if self.debug:
            print("\nDEBUG: get_entities\n")
            print(entities_json.text)
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
            print("\nDEBUG: get_entity_id("+catalog_name+")\n")
            print("ID of " + catalog_name + ": " + str(id))

        return id


    def get_entity_entries(self, catalog_name):
        ''' Gets portal catalog entries json given @catalog_name '''
        id = self.get_entity_id(catalog_name)
        entries_json = requests.get(self.endpoint+'/netwin/nacatalogs?$filter=idCatEntity eq '+str(id))

        if self.debug:
            print("\nDEBUG: get_entity_entries("+catalog_name+")\n")
            print(entries_json.text)

        return entries_json.text


    def get_catalog_entities(self, catalog_name):
        ''' Gets a list of all the entities associated with @catalog_name '''
        catalog_entities = requests.get(self.endpoint+'/netwin/catalog/entities-full?$filter=name eq \''+catalog_name+'\'')

        if self.debug:
            print("\nDEBUG: get_catalog_entities("+catalog_name+")\n")
            print(catalog_entities.text)

        return catalog_entities


    def get_catalog_attributes_list(self, catalog_name, attribute_type):
        """Return the enumerated values for the named catalog attribute type."""
        catalog_entities = self.get_catalog_entities(catalog_name).json()['entities'][0]['attributes']

        enumeratedAttributeValues = {}
        for attribute in catalog_entities:
            if attribute['attributetype']['name'] == attribute_type:
                enumeratedAttributeValues = attribute['attributetype']['enumeratedattributevalues']
        return json.dumps(enumeratedAttributeValues)


    def create_catalog_entries(self, catalog_name, catalog_entries, attributeType, new_attribute):
        """Translate existing entries and print the resulting JSON without posting it."""
        newCatalogEntries = []
        elementsList=['name', 'state', 'externalCode', 'host', 'endpoint', 'info', 'nodeName', 'siteName', 'clusterName', 'siteType', 'username', 'password', 'keystore', 'keystorePassword']
        enumeratedAttributeValues=json.loads(self.get_catalog_attributes_list(catalog_name, attributeType))

        if self.debug:
            print("Catalog entries")
            print(catalog_entries)
            print("-----------\n\n")

            print("Enumerated")
            print(enumeratedAttributeValues)
            print("-----------\n\n")

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
            print("\n\n-----------")
            print('New catalog entries: ' + json.dumps(newCatalogEntries, ensure_ascii=False))
            print("-----------\n\n")

        create_empty_dir('beforeTranslate')
        create_empty_dir('afterTranslate')

        with open(os.path.join('beforeTranslate', 'catalogsTranslate.json'), 'w', encoding='utf-8') as catalogs_file:
            json.dump(newCatalogEntries, catalogs_file, ensure_ascii=False)

        translateCommand = [
            '/opt/ptin/na-portal/bin/na-portal-catalog-template-translator/translate.sh',
            '-i', self.ip,
            '-p', str(self.port),
            '-c', catalog_name,
            '-s', 'beforeTranslate',
            '-t', 'afterTranslate',
        ]
        if self.debug:
            print("\n\n-----------")
            print('Translate command: ' + ' '.join(translateCommand))
            print("-----------\n\n")

        try:
            return_code = subprocess.call(translateCommand)
        except Exception as e:
            return_code = str(e)

        if str(return_code) != '0':
            print(return_code)
            print('Error while translating catalog')
            exit(1)

        # Read translated file
        with open(os.path.join('afterTranslate', 'catalogsTranslate.json'), 'r', encoding='utf-8') as catalogTranslatedTemp:
            catalogTranslated = catalogTranslatedTemp.read()
        print('Translated file: ' + catalogTranslated)


    def insert_entity(self, file_path, file_name):
        """Post the named JSON entity definition."""
        endpoint = self.endpoint+'/netwin/catalog-entities'
        with open(os.path.join(file_path, file_name + '.json'), 'r', encoding='utf-8') as entity_file:
            insert_entity = requests.post(endpoint, headers=self.headers, data=entity_file.read().encode('utf-8'))

        if self.debug:
            print('\ninsert_entity result\n')
            print(insert_entity.text)


    def delete_entity(self, entity_name):
        endpoint = self.endpoint+'/netwin/catalog-entities/'+entity_name
        delete_entity = requests.delete(endpoint, headers=self.headers)
        print('\nSystem Response (empty = success)\n')
        print(delete_entity.text)


    def delete_entries(self, catalog_entries):
        catalog_entries=json.loads(catalog_entries)
        for instance in catalog_entries['nacatalogs']:
            endpoint = self.endpoint + '/netwin/nacatalogs/' + str(instance['id'])
            requests.delete(endpoint, headers=self.headers)


    def connectivity_check(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((self.ip, self.port))
        sock.close()

        if result == 0:
           print("Connectivity check: port " + str(self.port) + " is open!")
        else:
           print("Connectivity check: port " + str(self.port) + " is not open!")


    def help(self):
        print('\nUseful portal links')
        print(self.endpoint+'/netwin/nacatalogs/entities-tree/6')
        print(self.endpoint+'/netwin/catalog-entities/')
        print(self.endpoint+'/netwin/catalog-attributetypes/')
        print('\nEntities usual path:')
        print('/opt/ptin/solution/conf/solution-na-portal-conf/catalogs/entities')


    def restart(self):
        print('Executing: sudo /etc/init.d/play-portal restart')
        os.system('./etc/init.d/play-portal restart')
