from typing import List

from rich import print
from t3api.api.packages_api import PackagesApi
from t3api.models.metrc_package import MetrcPackage

from t3api_utils.collection.utils import extract_data, parallel_load_collection
from t3api_utils.main.utils import (
    get_authenticated_client_or_error,
    load_collection,
    pick_license,
)


def main():
    api_client = get_authenticated_client_or_error()

    license = pick_license(api_client=api_client)

    all_active_packages: List[MetrcPackage] = load_collection(
        method=PackagesApi(api_client=api_client).v2_packages_active_get,
        license_number=license.license_number,
    )

    print(len(all_active_packages))


if __name__ == "__main__":
    main()
