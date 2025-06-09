from rich import print
from t3api.api.packages_api import PackagesApi

from t3api_utils.main.utils import get_authenticated_client, pick_license


def main():
    try:
        api_client = get_authenticated_client()
        print("[bold green]✅ Authenticated successfully.[/bold green]")
    except Exception as e:
        print(f"[bold red]❌ Authentication failed: {e}[/bold red]")

    license = pick_license(api_client=api_client)
    
    response = PackagesApi(api_client=api_client).v2_packages_active_get(license_number=license.license_number)
    
    print(response)

if __name__ == "__main__":
    main()
