#!/usr/bin/env python3
"""Generate TypedDict definitions from OpenAPI specification.

This script fetches the OpenAPI spec from the T3 API and generates
TypedDict definitions for all schemas, placing them in the interfaces/
directory for easy import and use.
"""
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from urllib.request import urlopen
from urllib.error import URLError


class TypedDictGenerator:
    """Generates TypedDict definitions from OpenAPI schemas."""

    def __init__(self, spec_url: str, output_dir: Path):
        self.spec_url = spec_url
        self.output_dir = output_dir
        self.spec: Dict[str, Any] = {}
        self.generated_types: Set[str] = set()

    def fetch_spec(self) -> None:
        """Fetch the OpenAPI specification from the API."""
        try:
            print(f"Fetching OpenAPI spec from {self.spec_url}")
            with urlopen(self.spec_url) as response:
                self.spec = json.loads(response.read().decode('utf-8'))
            print("✓ Successfully fetched OpenAPI spec")
        except URLError as e:
            raise RuntimeError(f"Failed to fetch OpenAPI spec: {e}")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse OpenAPI spec JSON: {e}")

    def sanitize_name(self, name: str) -> str:
        """Sanitize schema name to be a valid Python identifier."""
        # Remove special characters and convert to PascalCase
        name = re.sub(r'[^a-zA-Z0-9_]', '', name)
        # Ensure it starts with a letter
        if name and name[0].isdigit():
            name = f"Schema{name}"
        return name or "UnnamedSchema"

    def get_python_type(self, schema: Dict[str, Any], context: str = "") -> str:
        """Convert OpenAPI schema type to Python type annotation."""
        schema_type = schema.get('type')

        if 'anyOf' in schema:
            # Handle anyOf as Union
            types = []
            for sub_schema in schema['anyOf']:
                types.append(self.get_python_type(sub_schema, context))
            return f"Union[{', '.join(types)}]"

        if 'oneOf' in schema:
            # Handle oneOf as Union
            types = []
            for sub_schema in schema['oneOf']:
                types.append(self.get_python_type(sub_schema, context))
            return f"Union[{', '.join(types)}]"

        if '$ref' in schema:
            # Handle references to other schemas
            ref_path = schema['$ref']
            if ref_path.startswith('#/components/schemas/'):
                schema_name = ref_path.split('/')[-1]
                return self.sanitize_name(schema_name)
            return "Any"

        if schema_type == 'object':
            if 'properties' in schema:
                # This should be a separate TypedDict, but for inline we'll use Dict
                return "Dict[str, Any]"
            return "Dict[str, Any]"

        elif schema_type == 'array':
            items = schema.get('items', {})
            item_type = self.get_python_type(items, context)
            return f"List[{item_type}]"

        elif schema_type == 'string':
            if 'enum' in schema:
                # Handle enums as Literal types
                enum_values = ", ".join(f'"{val}"' for val in schema['enum'])
                return f"Literal[{enum_values}]"
            elif schema.get('format') == 'date-time':
                return "datetime"
            elif schema.get('format') == 'date':
                return "date"
            return "str"

        elif schema_type == 'integer':
            return "int"

        elif schema_type == 'number':
            return "float"

        elif schema_type == 'boolean':
            return "bool"

        elif schema_type is None and 'nullable' in schema:
            return "Optional[Any]"

        return "Any"

    def generate_typeddict_class(self, name: str, schema: Dict[str, Any]) -> str:
        """Generate a TypedDict class definition from a schema."""
        class_name = self.sanitize_name(name)

        if schema.get('type') != 'object' or 'properties' not in schema:
            # Not an object schema, generate an alias instead
            python_type = self.get_python_type(schema, class_name)
            return f"{class_name} = {python_type}\n"

        properties = schema.get('properties', {})
        required = set(schema.get('required', []))

        # Generate class definition
        lines = []
        lines.append(f"class {class_name}(TypedDict):")

        # Add docstring if description exists
        description = schema.get('description', '').strip()
        if description:
            # Clean up description for docstring
            description = description.replace('\\', '\\\\').replace('"', '\\"')
            lines.append(f'    """{description}"""')

        if not properties:
            lines.append("    pass")
        else:
            # Add properties
            for prop_name, prop_schema in properties.items():
                prop_type = self.get_python_type(prop_schema, f"{class_name}.{prop_name}")

                # Determine if field is required
                if prop_name in required:
                    lines.append(f"    {prop_name}: {prop_type}")
                else:
                    lines.append(f"    {prop_name}: NotRequired[{prop_type}]")

        return '\n'.join(lines) + '\n\n'

    def collect_imports(self, schemas: Dict[str, Dict[str, Any]]) -> Set[str]:
        """Collect all necessary imports for the generated types."""
        imports = {"TypedDict", "NotRequired"}

        for schema in schemas.values():
            self._collect_imports_from_schema(schema, imports)

        return imports

    def _collect_imports_from_schema(self, schema: Dict[str, Any], imports: Set[str]) -> None:
        """Recursively collect imports from a schema."""
        if isinstance(schema, dict):
            if 'anyOf' in schema or 'oneOf' in schema:
                imports.add("Union")
            if 'enum' in schema:
                imports.add("Literal")
            if schema.get('format') == 'date-time':
                imports.add("datetime")
            if schema.get('format') == 'date':
                imports.add("date")
            if schema.get('type') == 'array':
                imports.add("List")
            if schema.get('type') == 'object':
                imports.add("Dict")

            # Recurse into nested schemas
            for value in schema.values():
                if isinstance(value, (dict, list)):
                    self._collect_imports_from_schema(value, imports)
        elif isinstance(schema, list):
            for item in schema:
                self._collect_imports_from_schema(item, imports)

    def generate_interfaces_file(self, schemas: Dict[str, Dict[str, Any]], filename: str) -> str:
        """Generate a complete interfaces file with all TypedDict definitions."""
        imports = self.collect_imports(schemas)

        lines = []
        lines.append('"""Auto-generated TypedDict definitions from OpenAPI spec."""')
        lines.append("from __future__ import annotations")
        lines.append("")

        # Group imports
        typing_imports = sorted(imports & {
            "Any", "Dict", "List", "Optional", "Union", "Literal", "TypedDict", "NotRequired"
        })
        if typing_imports:
            lines.append(f"from typing import {', '.join(typing_imports)}")

        if "datetime" in imports or "date" in imports:
            datetime_imports = []
            if "datetime" in imports:
                datetime_imports.append("datetime")
            if "date" in imports:
                datetime_imports.append("date")
            lines.append(f"from datetime import {', '.join(datetime_imports)}")

        lines.append("")
        lines.append("")

        # Generate TypedDict classes
        for name, schema in schemas.items():
            class_def = self.generate_typeddict_class(name, schema)
            lines.append(class_def)

        return '\n'.join(lines)

    def generate_interfaces(self) -> None:
        """Generate TypedDict interfaces from the OpenAPI spec."""
        if not self.spec:
            raise RuntimeError("No OpenAPI spec loaded. Call fetch_spec() first.")

        # Extract schemas from components
        components = self.spec.get('components', {})
        schemas = components.get('schemas', {})

        if not schemas:
            print("⚠ No schemas found in OpenAPI spec")
            return

        # Create output directory
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Generate __init__.py
        init_file = self.output_dir / "__init__.py"
        with open(init_file, 'w') as f:
            f.write('"""Auto-generated TypedDict definitions from OpenAPI spec."""\n')

        # Group schemas by logical categories if possible
        # For now, we'll put everything in a single file
        all_schemas_content = self.generate_interfaces_file(schemas, "schemas.py")

        schemas_file = self.output_dir / "schemas.py"
        with open(schemas_file, 'w') as f:
            f.write(all_schemas_content)

        print(f"✓ Generated {len(schemas)} TypedDict definitions in {schemas_file}")

        # Generate an index file that exports everything
        index_content = self._generate_index_file(schemas)
        index_file = self.output_dir / "__init__.py"
        with open(index_file, 'w') as f:
            f.write(index_content)

        print(f"✓ Generated index file {index_file}")

    def _generate_index_file(self, schemas: Dict[str, Dict[str, Any]]) -> str:
        """Generate an __init__.py file that exports all TypedDict definitions."""
        lines = []
        lines.append('"""Auto-generated TypedDict definitions from OpenAPI spec."""')
        lines.append("")

        # Import all the schemas
        schema_names = [self.sanitize_name(name) for name in schemas.keys()]
        schema_names.sort()

        lines.append("from .schemas import (")
        for name in schema_names:
            lines.append(f"    {name},")
        lines.append(")")
        lines.append("")

        # __all__ export
        lines.append("__all__ = [")
        for name in schema_names:
            lines.append(f'    "{name}",')
        lines.append("]")

        return '\n'.join(lines)

    def run(self) -> None:
        """Run the complete type generation process."""
        self.fetch_spec()
        self.generate_interfaces()


def main() -> None:
    """Main entry point for the script."""
    import argparse

    parser = argparse.ArgumentParser(description="Generate TypedDict definitions from OpenAPI spec")
    parser.add_argument(
        "--spec-url",
        default="https://api.trackandtrace.tools/v2/spec/openapi.json",
        help="URL to the OpenAPI specification"
    )
    parser.add_argument(
        "--output-dir",
        default="interfaces",
        help="Output directory for generated interfaces"
    )

    args = parser.parse_args()

    # Convert to Path relative to project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    output_dir = project_root / args.output_dir

    try:
        generator = TypedDictGenerator(args.spec_url, output_dir)
        generator.run()
        print(f"\n🎉 Successfully generated TypedDict definitions in {output_dir}")
        print(f"Import them with: from interfaces import <TypeName>")
    except Exception as e:
        print(f"❌ Error: {e}")
        exit(1)


if __name__ == "__main__":
    main()