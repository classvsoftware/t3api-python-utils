# t3api-python-utils

Utility functions and helpers for the T3 API ecosystem.

This library is designed to support development of tools and clients that integrate with the Track & Trace Tools (T3) platform and Metrc data. It includes shared logic, validation helpers, transformation utilities, and other reusable Python components.

---

## 🚀 Getting Started

### 1. Clone the repo

```bash
git clone https://github.com/classvsoftware/t3api-python-utils.git
cd t3api-python-utils
````

### 2. Create virtual environment with `uv`

```bash
uv venv
source .venv/bin/activate
```

### 3. Install the package (editable mode)

```bash
uv pip install -e .
```

---

## 🧪 Running Tests

```bash
pytest
```

Add test modules under the `tests/` directory.

---

## 🛠️ Development Tips

* All core source files live in the `t3api_python_utils/` directory.
* Add type annotations and follow [PEP 8](https://peps.python.org/pep-0008/) and [mypy strict rules](https://mypy.readthedocs.io/en/stable/config_file.html).

---

## 📦 Building the Package

Make sure your virtualenv is activated:

```bash
uv pip install build
python -m build
```

This generates `.tar.gz` and `.whl` files inside the `dist/` folder.

---

## 🚀 Publishing to PyPI

### 1. Install Twine

```bash
uv pip install twine
```

### 2. Upload to TestPyPI (recommended for first-time testing)

```bash
twine upload --repository testpypi dist/*
```

Test it via:

```bash
uv pip install --index-url https://test.pypi.org/simple/ t3api-python-utils
```

### 3. Upload to PyPI (when ready)

```bash
twine upload dist/*
```

You’ll need a valid `.pypirc` file or Twine will prompt for your PyPI credentials.

---

## 📎 License

Licensed under the GNU General Public License v3.0.

---

## 🔗 Links

* [T3 Website](https://trackandtrace.tools)
* [T3 API Docs](https://api.trackandtrace.tools/v2/docs)
* [GitHub Repo](https://github.com/classvsoftware/t3api-python-utils)

---

```

---

Let me know if you want:

- A badge row (e.g. PyPI version, license).
- GitHub Actions CI instructions.
- `requirements-dev.txt` for lint/test tools (`mypy`, `pytest`, etc).
```
