from rich import print
from t3api.api.packages_api import PackagesApi

from t3api_utils.collection.utils import extract_data, parallel_load_collection
from t3api_utils.main.utils import get_authenticated_client_or_error, pick_license


def main():
    api_client = get_authenticated_client_or_error()

    license = pick_license(api_client=api_client)

    all_package_responses = parallel_load_collection(
        method=PackagesApi(api_client=api_client).v2_packages_active_get,
        license_number=license.license_number,
    )

    # Extracts packages and preserves typing
    # all_packages = [item for response in all_package_responses for item in response.data]

    # Simpler extraction, but does not preserve typing
    all_packages = extract_data(all_package_responses)

    print(len(all_packages))


if __name__ == "__main__":
    main()
