from na_portal_backend import NaPortalBackend
import sys

def main():
    portal = NaPortalBackend(sys.argv[1], debug=False)
    portal.insert_entity(sys.argv[2], sys.argv[3])

if __name__ == "__main__":
    main()
