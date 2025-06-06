from t3api_utils.cli import app
from t3api_utils.decorators import cli_options
from t3api_utils.auth import create_credentials_authenticated_client

@app.command()
@cli_options
def main(host, hostname, username, password, otp):
    client = create_credentials_authenticated_client(
        host=host,
        hostname=hostname,
        username=username,
        password=password,
        otp=otp,
    )
    print("Authenticated:", client)

if __name__ == "__main__":
    app()
