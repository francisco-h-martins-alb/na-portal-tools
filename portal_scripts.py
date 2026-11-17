from NaPortalBackend import *

#id = portal.get_entity_id('NA_CATALOG.NASPUSA.NETWORKEQUIPMENTCATALOG')
#id = portal.get_entity_id('string100')

#portal.update_attribute_type('naspusaNetEquipClass', 'catAttributeType_naspusa_netEquipClass.json')

#entity_entries = portal.get_entity_entries('NA_CATALOG.NASPUSA.NETWORKEQUIPMENTCATALOG')
#portal.create_catalog_entries('NA_CATALOG.NASPUSA.NETWORKEQUIPMENTCATALOG', entity_entries, 'naspusaNetEquipClass', 'class')

#portal.delete_entries(entity_entries)
#portal.post_updated_entries()

#portal.insert_entity('/opt/ptin/nasp-usa/conf/nasp-usa-na-portal-conf/catalogs/entities', 'naspusa.ipProf2')

def menu():
    print('\n------- Menu -------')
    print '0 - Restart portal'
    print '1 - List entities'
    print '2 - List entries'
    print '3 - Insert entity'
    print '4 - Delete entity'
    print '5 - Insert entry'
    print '6 - Delete all entries'
    print '8 - Connectivity check'
    print '9 - Help'
    print('---------------------')

def main():
    # intlab
    #portal = NaPortalBackend('10.112.101.183', debug=True)
    # quickfix
    #portal = NaPortalBackend('10.113.137.243', debug=False)
    # localhost
    #portal = NaPortalBackend('localhost', debug=False)

    # NA-ABC DEV
    portal = NaPortalBackend('localhost', debug=False)

    while True:
        menu()
        # Use input for Python 3, raw_input for Python 2
        import sys
        if sys.version_info[0] < 3:
            input_func = raw_input
        else:
            input_func = input
        choice = input_func('Select an option (q to quit): ')
        if choice == '0':
            portal.restart()
        elif choice == '1':
            portal.list_catalog_entities()
        elif choice == '2':
            catalog_name = input_func('Enter catalog name: ')
            entries = portal.get_entity_entries(catalog_name)
            print(entries)
        elif choice == '3':
            file_path = input_func('Enter entity file path: ')
            file_name = input_func('Enter entity file name (without .json): ')
            portal.insert_entity(file_path, file_name)
        elif choice == '4':
            entity_name = input_func('Enter entity name to delete: ')
            portal.delete_entity(entity_name)
        elif choice == '5':
            catalog_name = input_func('Enter catalog name: ')
            attribute_type = input_func('Enter attribute type: ')
            new_attribute = input_func('Enter new attribute name: ')
            entity_entries = portal.get_entity_entries(catalog_name)
            portal.create_catalog_entries(catalog_name, entity_entries, attribute_type, new_attribute)
        elif choice == '6':
            catalog_name = input_func('Enter catalog name: ')
            entity_entries = portal.get_entity_entries(catalog_name)
            portal.delete_entries(entity_entries)
        elif choice == '8':
            portal.connectivity_check()
        elif choice == '9':
            portal.help()
        elif choice.lower() == 'q':
            print('Exiting.')
            break
        else:
            print('Invalid option. Please try again.')


if __name__ == "__main__":
    main()
