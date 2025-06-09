from rich import print
from t3api.api.packages_api import PackagesApi

from t3api_utils.main.utils import (get_authenticated_client_or_error,
                                    pick_license)


def main():
    api_client = get_authenticated_client_or_error()

    license = pick_license(api_client=api_client)
    
    response = PackagesApi(api_client=api_client).v2_packages_active_get(license_number=license.license_number)
    
    print(response)

if __name__ == "__main__":
    main()
