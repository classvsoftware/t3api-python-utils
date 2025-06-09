from rich import print

from t3api_utils.main.utils import get_authenticated_client


def main():
    try:
        client = get_authenticated_client()
        print("[bold green]✅ Authenticated successfully.[/bold green]")
    except Exception as e:
        print(f"[bold red]❌ Authentication failed: {e}[/bold red]")


if __name__ == "__main__":
    main()
