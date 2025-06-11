from typing import List

from t3api.api.packages_api import PackagesApi
from t3api.models.metrc_package import MetrcPackage

from t3api_utils.main.utils import (
    get_authenticated_client_or_error,
    load_collection,
    pick_license,
    save_collection_to_csv,
    save_collection_to_json,
)


def main():
    api_client = get_authenticated_client_or_error()

    license = pick_license(api_client=api_client)

    all_active_packages: List[MetrcPackage] = load_collection(
        method=PackagesApi(api_client=api_client).v2_packages_active_get,
        license_number=license.license_number,
    )

    save_collection_to_csv(
        all_active_packages, open_after=True, strip_empty_columns=True
    )


if __name__ == "__main__":
    main()
