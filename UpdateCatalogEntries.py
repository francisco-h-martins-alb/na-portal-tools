#!/usr/bin/env python
# -*- coding: utf-8 -*-

import requests
import json
import subprocess
import time
import os
import argparse


def write_to_file(path, fname, data, timestr):
    """Writes data to a file.
    The file name will be timestr concatenated with _ concatenated with fname
    It will be stored in path
    Arguments: path = path to store file, fname = name of the file, data = data to write in file, timestr = time"""
    if timestr != '':
        timestr = timestr + '_'
    catalogs_file = open(path + timestr + fname + '.json', "w")
    catalogs_file.write(data)
    catalogs_file.close()


def check_create_empty_dir(dir):
    """Checks if directory exists.
    Is directory doesn't exists, it will be created.
    If exists, all files inside the directory will be deleted."""
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
    """Checks if directory exists.
    Is directory doesn't exists, it will be created."""
    if os.path.isdir(dir):
        print dir + ' exists'
    else:
        os.makedirs(dir)
        print dir + ' created'


# Date that the files will be created
timestr = time.strftime("%Y%m%d-%H%M%S")


# Arguments management
parser = argparse.ArgumentParser(description='Program to add new values to enumerated types without losing information in catalogs')

parser.add_argument('-i', dest='ip', help='Portal backend ip')
parser.add_argument('-p', dest='port', help='Portal backend nossis inv port')
parser.add_argument('-c', dest='catalogName', help='Catalog Name')
parser.add_argument('-a', dest='attributeType', help='Attribute to be updated')
parser.add_argument('-u', dest='attributesToUpdate', help='File path with attributes to be updated')
parser.add_argument('-f', dest='filesPath', help='Path where the temporary files will be stored')
parser.add_argument('-l', dest='elementsList', help='List of elements to save from catalogs', nargs='*')
parser.add_argument('-e', dest='elementToUpdate', help='Element with enumerated values that will be updated')


result = parser.parse_args()

print 'Arguments:'
print 'IP: ' + result.ip
print 'Port: ' + result.port
print 'Catalog name: ' + result.catalogName
print 'Attribute type: ' + result.attributeType
print 'Attributes to Update: ' + result.attributesToUpdate
print 'Temporary files path: ' + result.filesPath

tempElements = ''
for x in result.elementsList:
    tempElements += x + ' '

print 'Elements to save: ' + tempElements
print 'Element to be updated: ' + result.elementToUpdate

ip = result.ip
port = result.port
catalogName = result.catalogName
attributeType = result.attributeType
attributesToUpdate = result.attributesToUpdate
filesPath = result.filesPath
elementsList = result.elementsList
elementToUpdate = result.elementToUpdate


# Verifies if directory to store temporary files exists
check_create_dir(filesPath)





# 1 - Get catalogs list

getCatalogs = 'http://'+ip+':'+port+'/netwin/nacatalogs/entities-tree/6'

r = requests.get(getCatalogs)

write_to_file(filesPath, 'catalogsTypes', r.text.encode('utf-8'), timestr)





# 2 - Get id from the correct catalog with the name defined in catalogName

temp = r.json()['catEntities']['children']
idCatalog = ''

for x in temp:
    if x['name'] == catalogName:
        idCatalog = x['id']

print('Catalog found, id is ' + str(idCatalog) + '.')






# 3 - Get entries from the catalog

getEntries = 'http://'+ip+':'+port+'/netwin/nacatalogs?$filter=idCatEntity eq '+str(idCatalog)

r = requests.get(getEntries)

write_to_file(filesPath, 'catalogsEntries', r.text.encode('utf-8'), timestr)
catalogEntries = r.json()





# 4 - Get entities from the catalog

getEntities = 'http://'+ip+':'+port+'/netwin/catalog/entities-full?$filter=name eq \''+catalogName+'\''

r = requests.get(getEntities)

write_to_file(filesPath, 'catalogsEntities', r.text.encode('utf-8'), timestr)






# 5 - Get attributes list from the response of the point number 4

temp = r.json()['entities'][0]['attributes']
enumeratedAttributeValues = {}

for x in temp:
    if x['attributetype']['name'] == attributeType:
        enumeratedAttributeValues = x['attributetype']['enumeratedattributevalues']

print 'Enumerated attribute values: ' + json.dumps(enumeratedAttributeValues)







# 6 - Generate catalogs entries

newCatalogEntries = []
for x in catalogEntries['nacatalogs']:
    entry = dict()
    for y in elementsList:
        entry[y] = x[y]
    entry['idCatEntity'] = '-1'
    elementId = x[elementToUpdate]
    elementName = ''
    for y in enumeratedAttributeValues:
        if str(y['id']) == str(elementId):
            elementName = y['value']
    elementEntry = '${attributetype§enumeratedattributevalues§' + attributeType + '§{0}'.format(elementName) + '}'

    # only save element if it is not "null"
    if not elementEntry.endswith('§}'):
        entry[elementToUpdate] = elementEntry

    newCatalogEntries.append(entry)

print 'New catalog entries: ' + json.dumps(newCatalogEntries).decode('unicode-escape').encode('utf-8')

write_to_file(filesPath, 'catalogsTempFile', json.dumps(newCatalogEntries).decode('unicode-escape').encode('utf-8'), timestr)





# 7 - Class attributes update

headers = {'Content-type': 'application/json'}
putAttributes = 'http://'+ip+':'+port+'/netwin/catalog-attributetypes/'+attributeType

classFile = open(attributesToUpdate, 'r')
r = requests.put(putAttributes, headers=headers, data=classFile.read())
classFile.close()

# print 'Status code: ' + str(r.status_code) + '\nMessage: ' + r.reason

if str(r.status_code) != '204' and str(r.status_code) != '200':
    print 'Error with status code: ' + str(r.status_code) + '\nMessage: ' + r.reason
    exit(1)




# 8 - Translate of catalog generated in point 6

beforeTranslate = filesPath + 'beforeTranslate/'
afterTranslate = filesPath + 'afterTranslate/'

check_create_empty_dir(beforeTranslate)
check_create_empty_dir(afterTranslate)


write_to_file(beforeTranslate, 'catalogsTranslate', json.dumps(newCatalogEntries).decode('unicode-escape').encode('utf-8'), '')

translateCommand = '/opt/ptin/na-portal/bin/na-portal-catalog-template-translator/translate.sh -i ' + ip + ' -p ' + port + ' -c ' + catalogName + ' -s ' + beforeTranslate + ' -t ' + afterTranslate

print 'Translate command: ' + translateCommand

try:
    return_code = subprocess.call(translateCommand, shell=True)
except Exception as e:
    return_code = str(e)

if str(return_code) != '0':
    print return_code
    print 'Error while translating catalog'
    exit(1)

# Read translated file
catalogTranslatedTemp = open(afterTranslate + 'catalogsTranslate.json', 'r')
catalogTranslated = catalogTranslatedTemp.read()
catalogTranslatedTemp.close()
print 'Translated file: ' + catalogTranslated





# 9 - Clear catalog entries

for x in catalogEntries['nacatalogs']:
    deleteEntries = 'http://'+ip+':'+port+'/netwin/nacatalogs/'+str(x['id'])
    r = requests.delete(deleteEntries)






# 10 - Post updated entries in catalog

headers = {'Content-type': 'application/json'}
postEntries = 'http://'+ip+':'+port+'/netwin/nacatalogs/'

catalogTranslatedJson = json.loads(catalogTranslated)
for x in catalogTranslatedJson:
    r = requests.post(postEntries, headers=headers, data=json.dumps(x).decode('unicode-escape').encode('utf-8'))


print 'End of script'
print 'Play-portal needs to be restarted'
