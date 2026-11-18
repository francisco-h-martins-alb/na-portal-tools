from na_portal_backend import NaPortalBackend

def menu():
    print('\n------- Menu -------')
    print('0 - Restart portal')
    print('1 - List entities')
    print('2 - List entries')
    print('3 - Insert entity')
    print('4 - Delete entity')
    print('5 - Translate existing entries (preview only)')
    print('6 - Delete all entries')
    print('8 - Connectivity check')
    print('9 - Help')
    print('---------------------')

def main():
    portal = NaPortalBackend('localhost', debug=False)

    while True:
        menu()
        choice = input('Select an option (q to quit): ')
        if choice == '0':
            portal.restart()
        elif choice == '1':
            portal.list_catalog_entities()
        elif choice == '2':
            catalog_name = input('Enter catalog name: ')
            entries = portal.get_entity_entries(catalog_name)
            print(entries)
        elif choice == '3':
            file_path = input('Enter entity file path: ')
            file_name = input('Enter entity file name (without .json): ')
            portal.insert_entity(file_path, file_name)
        elif choice == '4':
            entity_name = input('Enter entity name to delete: ')
            portal.delete_entity(entity_name)
        elif choice == '5':
            catalog_name = input('Enter catalog name: ')
            attribute_type = input('Enter attribute type: ')
            new_attribute = input('Enter new attribute name: ')
            entity_entries = portal.get_entity_entries(catalog_name)
            portal.create_catalog_entries(catalog_name, entity_entries, attribute_type, new_attribute)
        elif choice == '6':
            catalog_name = input('Enter catalog name: ')
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
